"""工作流引擎 API 验证（一期地基）。

第 1-4 段是模板与视图（只读，跑完不留痕）；
第 5-8 段在**自建的一个临时项目**上跑真实流转/强制拖拽/回退，跑完把项目停用。

需要后端在跑（默认 http://localhost:5002）。
用法：python backend_v2/scripts/verify_wf_engine.py [--base http://localhost:5002]

为什么建临时项目而不是拿现网项目试：强制拖拽会写状态、写审计、跳过节点，
拿真项目跑会在真项目的流程上留下假的流转记录，事后没法干净地撤。
临时项目跑完 is_active=0 停用，既不删（约定：只新增）也不进任何列表。
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

ok = True
results = []


def check(name, cond, detail=""):
    global ok
    results.append((name, cond, detail))
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}")
    if not cond:
        ok = False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:5002")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin123")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    api = base + "/api"

    def call(method, path, token=None, body=None):
        url = api + path
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        # ngrok 免费版会给"看起来像浏览器"的请求插一个警告页，插页是 HTML 不是 JSON，
        # 打公网地址时脚本会解析失败。带上这个头就跳过插页。走 localhost 时后端
        # 不认识这个头，忽略掉，没有任何副作用。
        req.add_header("ngrok-skip-browser-warning", "true")
        if token:
            req.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read().decode("utf-8")
                return r.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "ignore")
            try:
                return e.code, json.loads(raw)
            except Exception:
                return e.code, {"detail": raw[:200]}
        except Exception as e:
            return 0, {"detail": str(e)}

    # ── 1. 登录 ──
    st, tok = call("POST", "/auth/login", body={"username": args.user, "password": args.password})
    token = tok.get("access_token")
    check("登录成功", st == 200 and bool(token), f"status={st}")
    if not token:
        print("\n=== 工作流引擎 API 验证 中断（登录失败）===")
        return 1

    # ── 2. 模板已播种（A/B 各一个已发布版本）──
    st, tpls = call("GET", "/wf-engine/templates", token)
    check("模板清单可取", st == 200 and isinstance(tpls, list), f"status={st}")
    by_code = {t["code"]: t for t in (tpls if isinstance(tpls, list) else [])}
    check("模板 A（合同交付·电机电控集成 / hardware）存在",
          "A" in by_code and by_code["A"]["project_type"] == "hardware",
          str(by_code.get("A", {}).get("name")))
    check("模板 B（合同交付·软件定制 / software）存在",
          "B" in by_code and by_code["B"]["project_type"] == "software",
          str(by_code.get("B", {}).get("name")))
    for code in ("A", "B"):
        if code in by_code:
            check(f"模板 {code} 有已发布版本", len(by_code[code]["versions"]) >= 1,
                  str(by_code[code]["versions"]))

    # ── 3. 建临时项目（软件 → 模板 B）──
    suffix = os.urandom(3).hex()
    code = ("WFE-" + suffix).upper()
    st, proj = call("POST", "/projects", token, {
        "name": "引擎验证临时项目" + suffix, "code": code, "project_type": "software",
    })
    check("临时项目创建成功", st in (200, 201) and bool(proj.get("id")), f"status={st} {proj}")
    if not proj.get("id"):
        print("\n=== 工作流引擎 API 验证 中断（建项目失败）===")
        return 1
    pid = proj["id"]
    member_id = None   # 第 5 段造的无权限账号，finally 里停用

    try:
        # ── 4. 视图：泳道 / 语义 / 权限原子 ──
        st, view = call("GET", f"/projects/{pid}/wf-engine", token)
        check("状态机视图可取", st == 200, f"status={st} {view.get('detail','')}")
        if st != 200:
            raise SystemExit(1)

        check("首次访问自动实例化（懒实例化）",
              view.get("template", {}).get("code") == "B",
              str(view.get("template")))
        check("基于版本与当前版本都是 v1（未迁移）",
              view["template"]["current_version_no"] == 1
              and view["template"]["is_migrated"] is False, "")
        lanes = [l["lane"] for l in view.get("lanes", [])]
        check("泳道覆盖 S0-S3", lanes == ["S0", "S1", "S2", "S3"], str(lanes))
        states = view.get("states", [])
        expect = sum(len(l["states"]) for l in view["lanes"])
        check("状态数自洽", len(states) == expect and len(states) > 0,
              f"{len(states)} vs {expect}")
        check("每个状态都带四类权限原子",
              all(set(s["can"]) == {"can_enter", "can_exit", "can_edit_fields", "can_force_drag"}
                  for s in states), "")
        check("语义只用七种标准值",
              all(s["runtime_status"] in {
                  "not_started", "in_progress", "pending_review", "pending_verify",
                  "completed", "blocked", "cancelled"} for s in states), "")
        cur = view.get("current_state_code")
        check("当前节点是第一个状态", cur == states[0]["state_code"], f"{cur}")
        check("开局第一个状态进行中、其余未开始",
              states[0]["runtime_status"] == "in_progress"
              and all(s["runtime_status"] == "not_started" for s in states[1:]), "")

        # ── 5. 服务端强制校验：无权限的人推不动 ──
        # admin 无条件全通，拿 admin 测不出拦截。要真正验证"服务端强制"，
        # 得造一个**真实存在、但不属于本项目**的账号：人员和账号一次调用建出来
        # （POST /api/team-members 同时吃 username/password/accRole）。
        # 这里验证的是"非项目成员被挡在项目外"这一层；ACL 原子级的判定
        # （是项目成员但角色不在 ACL 里 → 403）由 pytest 的 TestTransitions 覆盖。
        m_suffix = os.urandom(2).hex()
        uname = "wfe_nobody_" + m_suffix
        st, _u = call("POST", "/team-members", token, {
            "name": "引擎验证无权限者" + m_suffix,
            "username": uname, "password": "pw12345", "accRole": "member",
        })
        member_id = _u.get("id")
        account_ok = st == 201 and _u.get("account_created") is True
        check("受限账号建号成功（有账号、无项目身份）", account_ok,
              f"status={st} {_u.get('message', '')}")
        if account_ok:
            st, tk2 = call("POST", "/auth/login",
                           body={"username": uname, "password": "pw12345"})
            check("受限账号可登录", st == 200 and bool(tk2.get("access_token")), f"status={st}")
            if st == 200 and tk2.get("access_token"):
                # S0-1 此刻仍是当前节点，S0-1→S0-2 是合法边，
                # 所以被拒只能是权限原因，不是"路径不存在"。
                st, r = call("POST", f"/projects/{pid}/wf-engine/states/S0-1/transition",
                             tk2["access_token"], {"to_state_code": "S0-2"})
                check("非项目成员流转被服务端拒绝(403)", st == 403,
                      f"status={st} {r.get('detail', '')}")
                st, r = call("GET", f"/projects/{pid}/wf-engine", tk2["access_token"])
                check("非项目成员看不了本项目状态机", st in (403, 404), f"status={st}")

        # ── 6. 正式流转 ──
        st, r = call("POST", f"/projects/{pid}/wf-engine/states/S0-1/transition",
                     token, {"to_state_code": "S0-2"})
        check("管理员正式流转成功", st == 200, f"status={st} {r.get('detail','')}")
        st, view2 = call("GET", f"/projects/{pid}/wf-engine", token)
        sm = {s["state_code"]: s for s in view2["states"]}
        check("流转后 S0-1 完成、S0-2 进行中",
              sm["S0-1"]["runtime_status"] == "completed"
              and sm["S0-2"]["runtime_status"] == "in_progress", "")

        # ── 7. 跳边被拒绝（不是允许的路径）──
        st, r = call("POST", f"/projects/{pid}/wf-engine/states/S0-2/transition",
                     token, {"to_state_code": "S3-9"})
        check("非法流转路径被拒绝(400)", st == 400, f"status={st} {r.get('detail','')}")

        # ── 8. 强制拖拽：缺原因被拒 → 带原因成功 → 台账 → 回退 ──
        st, r = call("POST", f"/projects/{pid}/wf-engine/force-drag",
                     token, {"to_state_code": "S1-5"})
        check("跳过必经节点缺原因被拒绝(400)", st == 400, f"status={st} {r.get('detail','')}")

        st, r = call("POST", f"/projects/{pid}/wf-engine/force-drag",
                     token, {"to_state_code": "S1-5", "reason": "验证脚本：客户催进度"})
        check("带原因强制拖拽成功", st == 200, f"status={st} {r.get('detail','')}")
        skipped = r.get("skipped", []) if st == 200 else []
        check("跳过的节点被记录", len(skipped) > 0, f"{len(skipped)} 个")
        log_id = r.get("force_drag_log_id")

        st, view3 = call("GET", f"/projects/{pid}/wf-engine", token)
        sm3 = {s["state_code"]: s for s in view3["states"]}
        # 不变量：执行类被跳过 → 完成；验证/评审类被跳过 → 绝不能是完成
        fake = [c for c, s in sm3.items()
                if c in skipped and s["semantic_state"] in ("pending_verify", "pending_review")
                and s["runtime_status"] == "completed"]
        check("被跳过的验证/评审节点没有被假置为已完成", not fake, str(fake))
        check("目标节点进入自己的定义语义",
              sm3["S1-5"]["runtime_status"] == sm3["S1-5"]["semantic_state"],
              f'{sm3["S1-5"]["runtime_status"]} / {sm3["S1-5"]["semantic_state"]}')
        check("强制拖拽标记了来源",
              sm3["S1-5"]["status_source"] == "force", sm3["S1-5"]["status_source"])

        st, logs = call("GET", f"/projects/{pid}/wf-engine/force-drag-logs", token)
        check("强制拖拽台账可取", st == 200 and isinstance(logs, list), f"status={st}")
        mine = [x for x in logs if x["id"] == log_id] if isinstance(logs, list) else []
        check("台账含本次记录且字段完整", bool(mine) and mine[0]["reason"] == "验证脚本：客户催进度"
              and mine[0]["from_state_code"] == "S0-2" and mine[0]["is_reverted"] is False,
              str(mine[0]) if mine else "未找到")

        st, r = call("POST", f"/projects/{pid}/wf-engine/force-drag/{log_id}/revert",
                     token, {"reason": "验证脚本：拖错了"})
        check("回退成功", st == 200, f"status={st} {r.get('detail','')}")
        st, view4 = call("GET", f"/projects/{pid}/wf-engine", token)
        sm4 = {s["state_code"]: s for s in view4["states"]}
        check("回退后 S1-5 还原为未开始", sm4["S1-5"]["runtime_status"] == "not_started",
              sm4["S1-5"]["runtime_status"])
        check("回退后 S0-2 恢复为进行中", sm4["S0-2"]["runtime_status"] == "in_progress",
              sm4["S0-2"]["runtime_status"])

        st, r = call("POST", f"/projects/{pid}/wf-engine/force-drag/{log_id}/revert",
                     token, {"reason": "再退一次"})
        check("重复回退被拒绝(409)", st == 409, f"status={st}")

        st, clog = call("GET", f"/projects/{pid}/wf-engine/change-log", token)
        actions = {c["action"] for c in clog} if isinstance(clog, list) else set()
        check("流转台账记录了 enter/exit/force_drag/revert",
              {"enter", "exit", "force_drag", "revert"} <= actions, str(sorted(actions)))

        # ── 9. backfill 幂等 ──
        st, r1 = call("POST", "/wf-engine/backfill", token)
        check("backfill 可执行", st == 200, f"status={st}")
        st, r2 = call("POST", "/wf-engine/backfill", token)
        check("backfill 幂等（第二次不新建）",
              st == 200 and r2.get("created") == [], f'{r2.get("created")}')

    finally:
        # ── 清理：一律停用而不是删除（约定「只新增」，留痕可查）──
        st, _ = call("PUT", f"/projects/{pid}", token, {"is_active": False})
        print(f"临时项目 {code} (id={pid}) 已停用" if st == 200 else f"⚠ 临时项目 {pid} 停用失败 status={st}")
        if member_id:
            st, _ = call("PUT", f"/team-members/{member_id}", token, {"is_active": False})
            print(f"验证人员 id={member_id} 已停用" if st == 200
                  else f"⚠ 验证人员 {member_id} 停用失败 status={st}")

    print("\n=== 工作流引擎 API 验证", "全部通过" if ok else "存在失败项", "===")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
