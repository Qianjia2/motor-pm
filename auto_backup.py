"""Auto-backup: DB + 本地配置 + NAS 活数据，双份落地（NAS + 本地镜像）。

2026-09-14 重写。旧版有四个结构性缺陷，实测导致 9/10–9/14 四天一次都没备成：

1. `run_loop` 先 `sleep(INTERVAL)` 才做第一次备份 —— 每次进程重启就把计时器
   清零，而重启远比一小时频繁，于是永远轮不到。现改为**启动后先备一次**再轮询。
2. DB 用 `shutil.copy2` 拷正在被写入的热文件 —— 可能拿到撕裂页，且从不校验。
   现改用 SQLite 在线备份 API 取一致性快照，并跑 `integrity_check` 验证。
3. **完全没备 NAS 上的活数据**：`MotorPM_Live/uploads`（3.7GB 附件，全公司唯一
   一份合同/需求文档）与 `MotorPM_Live/data`（知识库）。现纳入增量镜像。
4. 没跳过 `data/uploads_local_old` —— 3.5GB 死目录（2026-08-11 迁 NAS 前的残留，
   全仓无任何引用），旧版每次原样拷一份，是 NAS 被占到 810GB 的主要来源。现排除。

另外：失败不再只 `print`（注册表启动没有控制台，这些字全部丢失），改写
`data/backup.log` + 钉钉告警 + `data/backup_status.json`。
"""
import os
import shutil
import sqlite3
import time
import threading
from datetime import datetime
from pathlib import Path

# ── 路径 ──
NAS_ROOT = Path(r"\\10.136.101.13\easitech\个人文件夹\qianjia\麦克斯韦-AI项目管理平台工具后台资料存放")
NAS_BACKUP = NAS_ROOT                                # 时间戳快照落这里
NAS_LIVE = NAS_ROOT / "MotorPM_Live"
NAS_UPLOADS = NAS_LIVE / "uploads"                   # 活的上传附件（唯一一份）
NAS_KB_DATA = NAS_LIVE / "data"                      # 活的知识库数据

LOCAL_DATA = Path(__file__).parent / "data"
DB_PATH = LOCAL_DATA / "motor_pm_v2.db"
LOCAL_MIRROR = Path(r"D:\MotorPM_Backup")            # 本地镜像：防 NAS 整体故障
LOG_FILE = LOCAL_DATA / "backup.log"
STATUS_FILE = LOCAL_DATA / "backup_status.json"

INTERVAL = 1 * 3600          # 备份间隔
STARTUP_DELAY = 60           # 启动后等这么久再备第一次（等服务建表/播种完成）
ALERT_COOLDOWN = 1800        # 同类告警限流（秒）

# 本地 data/ 下不备份的东西
SKIP_DIRS = {"uploads_local_old", "backup_mirror", "__pycache__"}
# .db 也排除：活库走上面的在线快照，其余 .db 是历史一次性副本（本身就是备份），
# 塞进每一份快照等于把"备份的备份"再备一遍，白白撑大每小时快照。
SKIP_SUFFIX = (".log", ".db", ".db-wal", ".db-shm", ".tmp")
SKIP_NAMES = {"server.log", "watchdog.log", "backup.log"}

_lock = threading.Lock()
_alert_state = {"last": 0.0}


# ── 日志 / 告警 ────────────────────────────────────────────────

def _log(msg):
    """写 backup.log 并 stdout。旧版只 print，注册表启动时字全丢。"""
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(f"[Backup] {msg}")
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > 2 * 1024 * 1024:
            LOG_FILE.replace(LOG_FILE.with_suffix(".log.1"))
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _webhook_url():
    url = os.environ.get("DINGTALK_WEBHOOK_URL", "")
    if url:
        return url
    try:
        from backend_v2.config import settings
        return settings.DINGTALK_WEBHOOK_URL
    except Exception:
        return ""


def _alert(text):
    """备份失败必须有人知道 —— 否则就是下一个「坏了四天没人发现」。"""
    _log(f"ALERT {text}")
    url = _webhook_url()
    if not url:
        return False
    if time.time() - _alert_state["last"] < ALERT_COOLDOWN:
        return False
    try:
        import requests
        r = requests.post(url, json={"msgtype": "text", "text": {"content": text}}, timeout=5)
        if r.status_code == 200:
            _alert_state["last"] = time.time()
            return True
    except Exception as e:
        _log(f"告警发送失败: {e}")
    return False


def _write_status(**kw):
    """备份状态落盘 —— 给人和健康检查看，不用去翻日志。"""
    import json
    try:
        st = {}
        if STATUS_FILE.exists():
            try:
                st = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
            except Exception:
                st = {}
        st.update(kw)
        STATUS_FILE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# ── 三类备份 ──────────────────────────────────────────────────

def backup_db(dst_dir):
    """SQLite 在线备份 API：服务正在写也能拿到一致快照，且拷完校验。"""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"数据库不存在: {DB_PATH}")
    dst_dir.mkdir(parents=True, exist_ok=True)
    out = dst_dir / DB_PATH.name
    tmp = out.with_suffix(".tmp")
    if tmp.exists():
        tmp.unlink()

    # 源库以只读方式打开；backup() 内部按页复制，天然避开写入中的撕裂页
    src = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True, timeout=20)
    try:
        dst = sqlite3.connect(str(tmp))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()

    # 校验：integrity_check + 表数量与源库一致（防止拷到一个能打开但缺表的副本）
    chk = sqlite3.connect(str(tmp))
    try:
        res = chk.execute("PRAGMA integrity_check").fetchone()
        if not res or res[0] != "ok":
            raise RuntimeError(f"integrity_check 未通过: {res}")
        n_dst = chk.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
    finally:
        chk.close()
    src2 = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True, timeout=20)
    try:
        n_src = src2.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
    finally:
        src2.close()
    if n_dst != n_src:
        raise RuntimeError(f"表数量不符: 源 {n_src} / 备 {n_dst}")

    if out.exists():
        out.unlink()
    tmp.replace(out)
    return {"bytes": out.stat().st_size, "tables": n_dst}


def copy_local_config(dst_dir):
    """本地 data/ 下的配置与小文件；排除死目录、日志、db（db 走在线备份）。"""
    dst_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for item in LOCAL_DATA.iterdir():
        if item.name in SKIP_DIRS or item.name in SKIP_NAMES:
            continue
        if item.suffix in SKIP_SUFFIX or item.name == DB_PATH.name:
            continue
        try:
            if item.is_dir():
                shutil.copytree(item, dst_dir / item.name, dirs_exist_ok=True,
                                ignore=shutil.ignore_patterns("*.log", "*-wal", "*-shm", "*.tmp"))
            else:
                shutil.copy2(item, dst_dir / item.name)
            n += 1
        except Exception as e:
            _log(f"  跳过 {item.name}: {e}")
    return n


def sync_tree(src, dst, label, stats):
    """增量镜像：只拷新增/变化的文件，**绝不删除目标已有文件**。

    不删是有意的 —— 源端误删的文件正是最需要从备份里捞回来的东西。
    以 (大小, mtime) 判断是否变化，SMB 上 mtime 可能被舍入到秒，故用 1 秒容差。
    """
    src, dst = Path(src), Path(dst)
    if not src.exists():
        stats["errors"] += 1
        stats.setdefault("missing", []).append(label)
        return
    dst.mkdir(parents=True, exist_ok=True)
    for dirpath, _dirnames, filenames in os.walk(src):
        target_dir = dst / Path(dirpath).relative_to(src)
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            stats["errors"] += 1
            _log(f"  {label} 建目录失败 {target_dir}: {e}")
            continue
        for fn in filenames:
            s, t = Path(dirpath) / fn, target_dir / fn
            try:
                sst = s.stat()
            except OSError:
                continue
            if t.exists():
                try:
                    tst = t.stat()
                    if tst.st_size == sst.st_size and abs(tst.st_mtime - sst.st_mtime) <= 1:
                        stats["skipped"] += 1
                        continue
                except OSError:
                    pass
            try:
                shutil.copy2(s, t)
                stats["copied"] += 1
                stats["bytes"] += sst.st_size
            except Exception as e:
                stats["errors"] += 1
                if stats["errors"] <= 5:
                    _log(f"  {label} 拷贝失败 {fn}: {e}")


# ── 保留策略 ──────────────────────────────────────────────────

def plan_prune(root=NAS_BACKUP):
    """分层保留，返回要删的目录列表（不执行删除）。

    24 小时内全留（小时级）；30 天内每天留最新一个；30 天以上每月留一个且永久保留。
    旧版只按「30 天」一刀切，注释里写的「1st-of-month forever」根本没实现。
    """
    now = time.time()
    snaps = []
    for d in Path(root).glob("auto_backup_*"):
        try:
            stamp = datetime.strptime(d.name[len("auto_backup_"):], "%Y%m%d_%H%M")
        except ValueError:
            continue
        snaps.append((stamp, d))
    snaps.sort(key=lambda x: x[0], reverse=True)   # 只按时间排；直接排元组会在时间戳
                                                  # 相同时去比较 Path 对象，抛 TypeError

    keep, hour_seen, day_seen, month_seen = set(), set(), set(), set()
    for stamp, d in snaps:
        age = now - stamp.timestamp()
        if age <= 24 * 3600:
            keep.add(d)
        elif age <= 30 * 86400:
            if stamp.strftime("%Y%m%d") not in day_seen:
                day_seen.add(stamp.strftime("%Y%m%d"))
                keep.add(d)
        else:
            if stamp.strftime("%Y%m") not in month_seen:
                month_seen.add(stamp.strftime("%Y%m"))
                keep.add(d)
    return [(d, s) for s, d in snaps if d not in keep]


def prune(root=NAS_BACKUP, dry_run=False):
    victims = plan_prune(root)
    if dry_run or not victims:
        return {"count": len(victims), "dirs": victims}
    freed = 0
    for d, _s in victims:
        try:
            shutil.rmtree(str(d), ignore_errors=True)
            freed += 1
        except Exception as e:
            _log(f"  清理失败 {d.name}: {e}")
    return {"count": freed, "dirs": victims}


# ── 主流程 ────────────────────────────────────────────────────

def backup():
    """跑一轮完整备份。返回 (是否成功, 摘要 dict)。"""
    with _lock:
        t0 = time.time()
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        summary = {"ts": ts}

        # 1) NAS 可达性 —— 不可达就别装作备成了
        if not NAS_BACKUP.exists():
            msg = f"备 NAS 不可达，本轮跳过: {NAS_BACKUP}"
            _log(msg)
            _alert(f"【备份失败】{msg}\n时间: {datetime.now():%Y-%m-%d %H:%M}")
            _write_status(last_fail=datetime.now().isoformat(timespec="seconds"),
                          last_error=msg, ok=False)
            return False, summary

        dst = NAS_BACKUP / f"auto_backup_{ts}"
        try:
            # 2) 数据库（一致性快照 + 校验）
            info = backup_db(dst)
            summary["db"] = info
            _log(f"DB 快照 {info['bytes'] / 1024 / 1024:.1f}MB / {info['tables']} 表 / 校验通过")

            # 3) 本地配置
            summary["local_files"] = copy_local_config(dst / "local_data")

            # 4) NAS 活数据 —— 增量镜像到备份区 + 本地镜像
            for label, src in (("uploads", NAS_UPLOADS), ("kb_data", NAS_KB_DATA)):
                st = {"copied": 0, "skipped": 0, "bytes": 0, "errors": 0}
                sync_tree(src, dst / f"live_{label}", label, st)
                summary[label] = st
                _log(f"{label}: 新拷 {st['copied']} 个 / 跳过 {st['skipped']} 个 / "
                     f"{st['bytes'] / 1024 / 1024:.1f}MB / 失败 {st['errors']}")
                lst = {"copied": 0, "skipped": 0, "bytes": 0, "errors": 0}
                sync_tree(src, LOCAL_MIRROR / label, f"{label}(本地)", lst)
                summary[f"{label}_local"] = lst

            # 5) 轮转（只清新策略判定该清的）
            pr = prune()
            summary["pruned"] = pr["count"]

            dur = time.time() - t0
            summary["duration"] = round(dur, 1)
            errs = sum(summary[k]["errors"] for k in ("uploads", "kb_data") if k in summary)
            if errs:
                _alert(f"【备份部分失败】{errs} 个文件未拷成功\n快照: {ts}\n"
                       f"详见 data/backup.log")
                _write_status(last_fail=datetime.now().isoformat(timespec="seconds"),
                              last_error=f"{errs} 个文件拷贝失败", ok=False)
                return False, summary

            _log(f"完成，用时 {dur:.1f}s → {dst.name}")
            _write_status(ok=True, last_ok=datetime.now().isoformat(timespec="seconds"),
                          last_error="", last_snapshot=dst.name, duration=round(dur, 1),
                          db_bytes=summary["db"]["bytes"])
            return True, summary
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            _log(f"失败: {msg}")
            _alert(f"【备份失败】{msg}\n时间: {datetime.now():%Y-%m-%d %H:%M}")
            _write_status(ok=False, last_fail=datetime.now().isoformat(timespec="seconds"),
                          last_error=msg)
            return False, summary


def run_loop():
    time.sleep(STARTUP_DELAY)          # 等服务建表/播种完，别去抢
    while True:
        try:
            backup()
        except Exception as e:
            _log(f"轮询异常: {e}")
        time.sleep(INTERVAL)


_thread = None


def start():
    """显式启动后台备份线程；幂等，重复调用不会起第二个。

    刻意**不**在 import 时自动启动。旧版是模块级 `Thread(...).start()`，于是任何
    `import auto_backup` 都会产生「往 NAS 写备份」的副作用 —— 我自己就踩了：
    一个只读的路径检查脚本跑了 60 秒以上，后台线程醒来开始全量拷贝，脚本退出时
    把它腰斩，留下一个只拷了 217/1073 个文件的残缺快照（已清掉）。
    残缺的备份比没有备份更危险 —— 它会让人以为有得恢复。
    """
    global _thread
    if _thread is not None and _thread.is_alive():
        return _thread
    _thread = threading.Thread(target=run_loop, daemon=True)
    _thread.start()
    _log(f"后台备份已启动（{STARTUP_DELAY}s 后首次，之后每 {INTERVAL // 3600} 小时）")
    return _thread


if __name__ == "__main__":
    import sys
    if "--prune-report" in sys.argv:
        vs = plan_prune()
        total = len(list(NAS_BACKUP.glob("auto_backup_*")))
        print(f"现有快照 {total} 个，按新策略应清 {len(vs)} 个，保留 {total - len(vs)} 个")
        for d, s in vs[:20]:
            print(f"  删 {d.name}")
        if len(vs) > 20:
            print(f"  ...（其余 {len(vs) - 20} 个）")
    else:
        ok, s = backup()
        print(f"结果: {'成功' if ok else '失败'}")
        print(s)
