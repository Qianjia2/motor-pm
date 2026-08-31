"""DingTalk Open API integration — token, approvals, templates."""
import json, threading, time, requests
from urllib.parse import quote
from pathlib import Path
from backend_v2.storage import atomic_write
from concurrent.futures import ThreadPoolExecutor, as_completed

CONFIG_FILE = Path(__file__).parent.parent / "data" / "dingtalk_config.json"
INST_CACHE_FILE = Path(__file__).parent.parent / "data" / "dingtalk_instance_cache.json"
USER_CACHE_FILE = Path(__file__).parent.parent / "data" / "dingtalk_user_cache.json"
TOKEN_CACHE = {"token": "", "expires_at": 0}
OLD_TOKEN_CACHE = {"token": "", "expires_at": 0}  # oapi 旧接口专用 token(gettoken)
_TOKEN_LOCK = threading.Lock()
_CACHE_LOCK = threading.Lock()

# 缓存可显著降低钉钉 API 调用量(免费版每月 5000 次):
# 实例详情 5 分钟 TTL(状态可能变化,查看详情走实时接口),姓名永久缓存(几乎不变)
INST_CACHE_TTL = 300
_instance_cache = None
_user_cache = None


def _load_cache(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(path: Path, cache: dict):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
        tmp.replace(path)
    except Exception:
        pass


def _load_cfg():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cfg(cfg):
    atomic_write(str(CONFIG_FILE), cfg)


def get_config():
    cfg = _load_cfg()
    # Never return secret to frontend
    return {
        "app_key": cfg.get("app_key", ""),
        "corp_id": cfg.get("corp_id", ""),
        "has_secret": bool(cfg.get("app_secret")),
        "templates": cfg.get("templates", []),
    }


def save_credentials(app_key: str, app_secret: str, corp_id: str):
    cfg = _load_cfg()
    cfg["app_key"] = app_key
    cfg["app_secret"] = app_secret
    cfg["corp_id"] = corp_id
    cfg.setdefault("templates", _load_cfg().get("templates", []))
    _save_cfg(cfg)
    # Invalidate cached tokens
    TOKEN_CACHE["token"] = ""
    TOKEN_CACHE["expires_at"] = 0
    OLD_TOKEN_CACHE["token"] = ""
    OLD_TOKEN_CACHE["expires_at"] = 0
    # 换企业后实例/姓名/模板缓存全部失效
    global _instance_cache, _user_cache
    _instance_cache = None
    _user_cache = None
    _tpl_cache["ts"] = 0
    for f in (INST_CACHE_FILE, USER_CACHE_FILE):
        try:
            f.unlink()
        except Exception:
            pass


def save_templates(templates: list):
    cfg = _load_cfg()
    cfg["templates"] = templates
    _save_cfg(cfg)


def _get_token() -> str:
    """Get valid access token, refresh if expired (thread-safe for concurrent scans)."""
    with _TOKEN_LOCK:
        if TOKEN_CACHE["token"] and time.time() < TOKEN_CACHE["expires_at"] - 120:
            return TOKEN_CACHE["token"]

        cfg = _load_cfg()
        if not cfg.get("app_key") or not cfg.get("app_secret"):
            raise RuntimeError("钉钉凭证未配置")

        r = requests.post("https://api.dingtalk.com/v1.0/oauth2/accessToken", json={
            "appKey": cfg["app_key"],
            "appSecret": cfg["app_secret"],
        }, timeout=10)
        data = r.json()
        if r.status_code != 200 or "accessToken" not in data:
            raise RuntimeError(f"获取钉钉Token失败: {data}")

        TOKEN_CACHE["token"] = data["accessToken"]
        TOKEN_CACHE["expires_at"] = time.time() + data.get("expireIn", 7200)
        return TOKEN_CACHE["token"]


def _dt_post(path: str, body: dict) -> dict:
    token = _get_token()
    headers = {
        "x-acs-dingtalk-access-token": token,
        "Content-Type": "application/json",
    }
    r = requests.post(f"https://api.dingtalk.com{path}", json=body, headers=headers, timeout=15)
    return r.json()


def _dt_get(path: str, params: dict = None) -> dict:
    token = _get_token()
    headers = {"x-acs-dingtalk-access-token": token}
    r = requests.get(f"https://api.dingtalk.com{path}", params=params or {}, headers=headers, timeout=10)
    return r.json()


_tpl_cache = {"ts": 0, "data": []}


def list_process_templates() -> list:
    """从钉钉 API 拉取企业可见的全部 OA 审批模板(忽略本地配置),24h 缓存。

    注意:钉钉新版 v1.0 没有模板列表端点,须走旧接口
    topapi/process/listbyuserid(不传 userid = 查询企业下所有审批模板)。
    跨模板搜索等场景频繁调用,缓存避免重复消耗 API 调用量。
    """
    if _tpl_cache["data"] and time.time() - _tpl_cache["ts"] < 86400:
        return _tpl_cache["data"]
    token = _get_old_token()
    r = requests.post(
        "https://oapi.dingtalk.com/topapi/process/listbyuserid",
        params={"access_token": token},
        json={"offset": 0, "size": 100},
        timeout=10,
    )
    rsp = r.json()
    if rsp.get("errcode"):
        raise RuntimeError(f"拉取钉钉模板失败: {rsp.get('errmsg') or rsp}")
    items = rsp.get("result", {}).get("process_list", [])
    _tpl_cache["data"] = [{"name": it.get("name", ""), "process_code": it.get("process_code", "")}
                          for it in items]
    _tpl_cache["ts"] = time.time()
    return _tpl_cache["data"]


def get_process_templates():
    """List OA approval templates (processCode for each form)."""
    cfg = _load_cfg()
    # First try configured templates
    configured = cfg.get("templates", [])
    if configured:
        return configured

    # Fallback: try to query via API
    try:
        return list_process_templates()
    except Exception:
        return []


def create_approval(process_code: str, originator_user_id: str,
                    dept_id: int, title: str, form_values: list) -> dict:
    """Create a new OA approval instance.

    Args:
        process_code: approval template code (e.g. PROC-xxx)
        originator_user_id: DingTalk user ID of the initiator
        dept_id: department ID
        title: approval title
        form_values: list of {name, value} dicts for form fields
    """
    body = {
        "processCode": process_code,
        "originatorUserId": originator_user_id,
        "deptId": dept_id,
        "microappAgentId": 0,
        "approvers": [],  # Use template's default approvers
        "formComponentValues": [
            {"name": fv["name"], "value": str(fv["value"])}
            for fv in form_values
        ],
        "title": title,
    }
    token = _get_token()
    headers = {
        "x-acs-dingtalk-access-token": token,
        "Content-Type": "application/json",
    }
    r = requests.post("https://api.dingtalk.com/v1.0/workflow/processInstances",
                      json=body, headers=headers, timeout=15)
    rsp = r.json()
    # 钉钉失败时 HTTP 非 200 且返回 {code, message};成功时 result.instanceId
    if r.status_code != 200 or rsp.get("code") or rsp.get("success") is False:
        raise RuntimeError(f"钉钉发起审批失败: {rsp.get('message') or rsp.get('code') or rsp}")
    return rsp


def get_approval_status(instance_id: str) -> dict:
    """Query an approval instance status."""
    return _dt_get(f"/v1.0/workflow/processInstances/{instance_id}")


def get_user_info(user_ids: list) -> dict:
    """Batch query DingTalk user info."""
    rsp = _dt_post("/v1.0/contact/users/batchQuery", {
        "userIds": user_ids,
    })
    results = rsp.get("result", {}).get("list", [])
    return {u.get("userId", u.get("userid", "")): u for u in results}


def _get_old_token() -> str:
    """Get oapi 旧接口 access_token(gettoken),与 v1.0 token 不通用,需单独缓存。"""
    if OLD_TOKEN_CACHE["token"] and time.time() < OLD_TOKEN_CACHE["expires_at"] - 120:
        return OLD_TOKEN_CACHE["token"]

    cfg = _load_cfg()
    if not cfg.get("app_key") or not cfg.get("app_secret"):
        raise RuntimeError("钉钉凭证未配置")

    r = requests.get("https://oapi.dingtalk.com/gettoken", params={
        "appkey": cfg["app_key"], "appsecret": cfg["app_secret"],
    }, timeout=10)
    data = r.json()
    if data.get("errcode") != 0 or "access_token" not in data:
        raise RuntimeError(f"获取钉钉Token失败: {data}")

    OLD_TOKEN_CACHE["token"] = data["access_token"]
    OLD_TOKEN_CACHE["expires_at"] = time.time() + int(data.get("expires_in", 7200))
    return OLD_TOKEN_CACHE["token"]


def search_user_by_mobile(mobile: str) -> dict:
    """Search DingTalk user by mobile number.

    注意:钉钉新版 v1.0 API 没有 getByMobile 端点,须走旧接口
    topapi/v2/user/getbymobile(需 oapi gettoken 的 token)。
    """
    token = _get_old_token()
    r = requests.post(
        "https://oapi.dingtalk.com/topapi/v2/user/getbymobile",
        params={"access_token": token},
        json={"mobile": mobile},
        timeout=10,
    )
    return r.json()


def get_instance_detail(instance_id: str) -> dict:
    """查询单个审批实例详情(旧接口 topapi/processinstance/get)。"""
    token = _get_old_token()
    r = requests.post(
        "https://oapi.dingtalk.com/topapi/processinstance/get",
        params={"access_token": token},
        json={"process_instance_id": instance_id},
        timeout=10,
    )
    return r.json()


_KEY_FIELD_HINTS = ("客户", "项目", "金额", "合同", "产品", "供方", "供应商", "事由", "事项", "内容", "说明")


def _readable_value(v) -> str:
    """表格类字段的值是 JSON 结构,递归提取其中的文本 value,拼成可读内容。"""
    v = str(v).strip()
    if not v.startswith(("[", "{")):
        return v
    try:
        texts = []

        def walk(x):
            if isinstance(x, dict):
                ct = x.get("componentType", "")
                for kk, vv in x.items():
                    # TextNote 是表单提示文字,不属于填写内容
                    if kk == "value" and isinstance(vv, str) and vv.strip() and ct != "TextNote":
                        texts.append(vv.strip())
                    else:
                        walk(vv)
            elif isinstance(x, list):
                for i in x:
                    walk(i)

        walk(json.loads(v))
        return "；".join(texts)[:120] if texts else v
    except Exception:
        return v


def _extract_key_fields(form_values: list) -> list:
    """从表单字段中提取关键业务内容(优先客户/项目/金额等字段,不足再补其他非空字段)。"""
    nonempty = [(fv.get("name", ""), _readable_value(fv.get("value")))
                for fv in form_values if str(fv.get("value") or "").strip()
                and str(fv.get("value")).strip() not in ("暂无", "-", "无")]
    hits = [f"{n}: {v}" for n, v in nonempty if any(h in n for h in _KEY_FIELD_HINTS)]
    if len(hits) < 3:
        for n, v in nonempty:
            item = f"{n}: {v}"
            if item not in hits:
                hits.append(item)
            if len(hits) >= 3:
                break
    return hits[:3]


def _fmt_dt_time(v) -> str:
    """v1.0 接口返回 ISO8601(如 2026-07-30T12:44Z),统一成 YYYY-MM-DD HH:MM:SS。"""
    s = str(v or "")
    if not s or "T" not in s:
        return s
    return s.replace("T", " ").replace("Z", "").split(".")[0]


def _list_instance_ids_v10(process_code: str, start_ms: int, end_ms: int) -> list:
    """v1.0 workflow/processes/instanceIds/query 翻页拉取实例 ID。

    v1.0 限制: 时间窗口 ≤120 天、maxResults ≤20、首页 nextToken 传 "0"、
    查询起点距当前最多约 1 年(钉钉数据边界)。
    """
    token = _get_token()
    ids, ntok = [], "0"
    while True:
        r = requests.post(
            "https://api.dingtalk.com/v1.0/workflow/processes/instanceIds/query",
            json={"processCode": process_code, "startTime": start_ms, "endTime": end_ms,
                  "maxResults": 20, "nextToken": ntok},
            headers={"x-acs-dingtalk-access-token": token, "Content-Type": "application/json"},
            timeout=15,
        )
        d = r.json()
        if not d.get("success"):
            raise RuntimeError(f"拉取审批实例失败: {d.get('message') or d.get('code') or d}")
        result = d.get("result", {})
        ids += result.get("list", [])
        nnt = result.get("nextToken", "")
        if not nnt or nnt == ntok:
            break
        ntok = nnt
    return ids


def _get_instance_detail_v10(instance_id: str, use_cache: bool = True) -> dict:
    """v1.0 审批实例详情,统一成与旧接口相同的 snake_case 结构。

    use_cache=True 时 5 分钟 TTL 缓存,重复拉取/列表过滤不重复消耗 API 调用量
    (免费版每月 5000 次);查看详情/刷新状态走实时(use_cache=False)。
    """
    if use_cache:
        global _instance_cache
        with _CACHE_LOCK:
            if _instance_cache is None:
                _instance_cache = _load_cache(INST_CACHE_FILE)
            hit = _instance_cache.get(instance_id)
            if hit and time.time() - hit["ts"] < INST_CACHE_TTL:
                return json.loads(hit["data"])  # 反序列化深拷贝,防调用方改动
    token = _get_token()
    r = requests.get("https://api.dingtalk.com/v1.0/workflow/processInstances",
                     params={"processInstanceId": instance_id},
                     headers={"x-acs-dingtalk-access-token": token}, timeout=15)
    d = r.json()
    res = d.get("result") or {}
    if not d.get("success") or not res:
        raise RuntimeError(f"查询审批单失败: {d.get('message') or d.get('code') or d}")
    result = {
        "instance_id": instance_id,
        "title": res.get("title", ""),
        "status": res.get("status", ""),  # NEW/RUNNING/COMPLETED/TERMINATED/CANCELED
        "result": res.get("result", ""),
        "originator_userid": res.get("originatorUserId", ""),
        "create_time": _fmt_dt_time(res.get("createTime", "")),
        "finish_time": _fmt_dt_time(res.get("finishTime", "")),
        "form_component_values": [{"name": f.get("name", ""), "value": f.get("value", "")}
                                  for f in (res.get("formComponentValues") or [])],
        "operation_records": [{"date": o.get("date", ""), "type": o.get("type", ""),
                               "result": o.get("result", ""), "userid": o.get("userId", ""),
                               "remark": o.get("remark", "")}
                              for o in (res.get("operationRecords") or [])],
    }
    if use_cache:
        with _CACHE_LOCK:
            _instance_cache[instance_id] = {"ts": time.time(), "data": json.dumps(result, ensure_ascii=False)}
            _save_cache(INST_CACHE_FILE, _instance_cache)
    return result


MAX_START_AGE_DAYS = 360  # 钉钉数据边界约 1 年,更早的窗口直接跳过
MAX_WORKERS = 6  # 并发拉取数(实测 v1.0 6 并发不触发限流)


def _ids_for_code(code: str, days: int) -> list:
    """单模板分段拉取实例 ID(v1.0 单次窗口 ≤120 天)。"""
    ids = []
    end = int(time.time())
    remaining = min(days, MAX_START_AGE_DAYS)
    while remaining > 0:
        win = min(remaining, 120)
        ids += _list_instance_ids_v10(code, (end - win * 86400) * 1000, end * 1000)
        end -= win * 86400
        remaining -= win
    return ids


def list_process_instances(process_code: str = "", days: int = 30, mobile: str = "",
                           keyword: str = "") -> list:
    """拉取审批实例(含标题/状态/发起人/表单); process_code 为空时跨全部模板搜索。

    走 v1.0 接口(需 Workflow.Instance.Read 权限,已开通,限流独立于旧接口):
    - 时间窗口每段 ≤120 天,单页 20 条,按 nextToken 翻页
    - 查询起点最多 ~1 年前(钉钉数据边界),更早的窗口直接跳过不报错
    - 跨模板搜索时钉钉不支持一次查全部,须遍历全部模板再合并,
      用并发加速(6 线程实测不触发限流),耗时取决于模板内实例数量
    mobile 可选: 按手机号查到 userid 后本地过滤发起人;
    keyword 可选: 钉钉不支持关键词,拉取后按标题/表单内容本地过滤。
    """
    kw = (keyword or "").strip().lower()
    target_uid = ""
    if mobile:
        ursp = search_user_by_mobile(mobile)
        if ursp.get("errcode"):
            raise RuntimeError(f"未找到该手机号的钉钉用户: {ursp.get('errmsg') or ursp}")
        target_uid = ursp.get("result", {}).get("userid", "")
        if not target_uid:
            raise RuntimeError("未找到该手机号对应的钉钉用户")

    if process_code:
        codes, name_map = [process_code], {}
    else:
        tpls = get_process_templates()
        if not tpls:
            raise RuntimeError("未配置审批模板,无法跨模板搜索")
        codes = [t["process_code"] for t in tpls if t.get("process_code")]
        name_map = {t["process_code"]: t.get("name", "") for t in tpls}
    if not codes:
        raise RuntimeError("没有可查询的审批模板")

    # 阶段1: 并发拉各模板实例 ID,记录 iid → 模板名 映射
    iid2code = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_ids_for_code, c, days): c for c in codes}
        for f in as_completed(futs):
            try:
                for iid in f.result():
                    iid2code[iid] = futs[f]
            except Exception:
                continue
    all_ids = list(dict.fromkeys(iid2code))

    # 阶段2: 并发拉详情 + 按发起人/关键词本地过滤
    def build(iid):
        try:
            pi = _get_instance_detail_v10(iid)
        except Exception:
            return None
        if not pi:
            return None
        if target_uid and pi["originator_userid"] != target_uid:
            return None
        title = pi["title"]
        form_values = pi["form_component_values"]
        if kw:
            hay = (title + " " + " ".join(v["name"] + str(v["value"]) for v in form_values)).lower()
            if kw not in hay:
                return None
        return {
            "instance_id": iid,
            "title": title,
            "status": pi["status"],
            "created_at": pi["create_time"],  # YYYY-MM-DD HH:MM:SS
            "originator_userid": pi["originator_userid"],
            "originator": _originator_from_title(pi),
            "process_name": name_map.get(iid2code.get(iid, ""), ""),
            "form_values": form_values,
            "key_fields": _extract_key_fields(form_values),
        }

    out = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for res in ex.map(build, all_ids):
            if res:
                out.append(res)
    out.sort(key=lambda o: o["created_at"], reverse=True)

    # 有通讯录权限则把发起人 userid 替换为姓名,否则保留标题解析的名字
    uids = list({o["originator_userid"] for o in out if o["originator_userid"]})
    if uids:
        names = get_user_names(uids)
        for o in out:
            if o["originator_userid"] in names:
                o["originator"] = names[o["originator_userid"]]
    return out


def get_user_names(userids: list) -> dict:
    """批量查询用户姓名(旧接口 topapi/v2/user/get),结果永久缓存到本地。

    需应用开通「通讯录用户详情」权限(qyapi_get_member);
    未开通时返回 {},由调用方回退到从标题解析姓名。
    姓名几乎不变,已查过的 userid 不再调用钉钉,省 API 调用量。
    注意:v1.0 的用户详情接口要的是 Contact.User.Read(新权限),与此不同。
    """
    global _user_cache
    with _CACHE_LOCK:
        if _user_cache is None:
            _user_cache = _load_cache(USER_CACHE_FILE)
        names = {u: _user_cache[u] for u in userids if u in _user_cache}
    todo = [u for u in dict.fromkeys(userids) if u not in names][:20]
    token = _get_old_token()
    changed = False
    for uid in todo:
        try:
            r = requests.post(
                "https://oapi.dingtalk.com/topapi/v2/user/get",
                params={"access_token": token},
                json={"userid": uid},
                timeout=8,
            )
            d = r.json()
            u = (d.get("result") or {})
            if not d.get("errcode") and u.get("name"):
                names[uid] = u["name"]
                with _CACHE_LOCK:
                    _user_cache[uid] = u["name"]
                    changed = True
        except Exception:
            pass
    if changed:
        _save_cache(USER_CACHE_FILE, _user_cache)
    return names


def _originator_from_title(pi: dict) -> str:
    title = pi.get("title", "")
    idx = title.find("提交的")
    return title[:idx] if idx > 0 else pi.get("originator_userid", "")


def get_instance_full(instance_id: str) -> dict:
    """审批单完整信息: 表单 + 审批过程(操作记录) + 钉钉打开链接。

    查看详情走实时接口(不走缓存),保证看到最新审批状态。
    """
    pi = _get_instance_detail_v10(instance_id, use_cache=False)
    cfg = _load_cfg()
    corp_id = cfg.get("corp_id", "")
    title = pi["title"]
    originator = _originator_from_title(pi)

    ops = [{
        "time": op["date"],
        "type": op["type"],
        "result": op["result"],
        "userid": op["userid"],
        "remark": op["remark"],
    } for op in pi["operation_records"]]

    # 有通讯录权限则把操作人 userid 替换为姓名(如: 云媛媛)
    names = get_user_names([o["userid"] for o in ops if o["userid"]])
    if names:
        originator = names.get(pi["originator_userid"], originator)
        for op in ops:
            if op["userid"] in names:
                op["userid"] = names[op["userid"]]

    # 实测确认: 仅 pchomepage.htm 完整参数 + #/approval + pc_slide=true 的组合
    # 能在 PC 客户端侧边栏内直达审批实例;其它格式(聊天短链接、任务原始链接)
    # 客户端内均卡"加载中"。mobile 为钉钉聊天消息里审批单的链接格式,手机端可用。
    pc_web = (f"https://aflow.dingtalk.com/dingtalk/pc/query/pchomepage.htm"
              f"?procInstId={instance_id}&corpid={corp_id}&dd_share=false&swfrom=oa"
              f"&showmenu=false&dinghash=approval&dd_progress=false")
    short_url = (f"https://aflow.dingtalk.com/dingtalk/mobile/homepage.htm"
                 f"?corpid={corp_id}&procInstId={instance_id}#approval")

    links = {
        "pc_client": (f"dingtalk://dingtalkclient/page/link"
                      f"?url={quote(pc_web + '#/approval', safe='')}&pc_slide=true"),
        "mobile": short_url,
    }
    return {
        "instance_id": instance_id,
        "title": title,
        "status": pi["status"],
        "result": pi["result"],
        "originator": originator,
        "create_time": pi["create_time"],
        "finish_time": pi["finish_time"],
        "form_values": pi["form_component_values"],
        "operation_records": ops,
        "links": links,
    }


def get_department_lists(dept_id: int = 0) -> list:
    """Get sub-department list."""
    rsp = _dt_get(f"/v1.0/contact/departments/{dept_id}/subDeptIds")
    dept_ids = rsp.get("result", {}).get("deptIdList", [])
    # Get names
    result = []
    for did in dept_ids:
        try:
            info = _dt_get(f"/v1.0/contact/dept", {"deptId": did})
            dept = info.get("result", {})
            result.append({"id": did, "name": dept.get("deptName", str(did))})
        except:
            result.append({"id": did, "name": str(did)})
    return result
