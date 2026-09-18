"""为「项目工作流」试点建一个软件测试项目,并造出几种状态。

为什么走接口而不是直接写库:建项目接口会自动生成阶段门(ProjectPhaseGate)、
里程碑、以及按交付物标准铺出来的交付物行。手写库容易漏掉这些,造出来的项目
在页面上就是残缺的。

造出来的状态(便于一次看全工作流的所有分支):
  S0 第 2 步 编制 SRS        → 交付物已提交(未批)  ⇒ 进行中
  S0 第 3 步 需求分析文档    → 交付物已批准          ⇒ 已完成
  S0 第 6 步 组织需求评审    → 交付物被驳回          ⇒ 有驳回
  S0 第 1 步 需求调研与澄清  → 交付物标准本库未配置  ⇒ 待确认(点一下就能确认)
  其余步骤                                        ⇒ 未开始
门禁:必交没齐 ⇒ 未发起,且列出缺件。

幂等:项目已存在就只把三条交付物重置回演示状态,不重复建。

用法: python scripts/seed_workflow_demo_project.py [--base URL]
"""
import argparse
import sys

import requests

DEFAULT_BASE = "http://127.0.0.1:5002"
CODE = "SW-WF-DEMO"
NAME = "软件工作流验证项目"

# (阶段码, 交付物名, 目标状态)
DEMO_STATUS = [
    ("S0", "软件需求规格说明书（SRS冻结版）", "submitted"),
    ("S0", "软件需求分析文档", "approved"),
    ("S0", "需求评审记录", "rejected"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    a = ap.parse_args()
    api = a.base.rstrip("/") + "/api"

    s = requests.Session()
    r = s.post(f"{api}/auth/login", json={"username": "admin", "password": "admin123"})
    if r.status_code != 200:
        print(f"[错误] 登录失败 {r.status_code}: {r.text[:200]}")
        return 1
    H = {"Authorization": f"Bearer {r.json()['access_token']}"}

    pid = _find_project(s, H, api)
    if pid:
        print(f"[跳过建项目] {NAME}({CODE}) 已存在, id={pid}")
    else:
        r = s.post(f"{api}/projects", headers=H, json={
            "name": NAME, "code": CODE, "project_type": "software",
            "description": "用于验证项目详情「工作流」页签的软件测试项目(试点)",
        })
        if r.status_code != 201:
            print(f"[错误] 建项目失败 {r.status_code}: {r.text[:300]}")
            return 1
        pid = r.json()["id"]
        print(f"[建项目] {NAME} id={pid}")

    # 阶段门/交付物是建项目时自动生成的,等一下再取
    pgs = s.get(f"{api}/projects/{pid}/phase-gates", headers=H).json()
    if not pgs:
        print("[错误] 项目没有阶段门,建项目流程可能没走完")
        return 1
    print(f"[阶段门] {len(pgs)} 个: {[p.get('phase', {}).get('code') for p in pgs]}")

    # 建项目接口只按交付物标准铺里程碑,不铺交付物行;演示用的这几条要自己建
    phase_ids = {p["phase"]["code"]: p["phase_id"] for p in pgs if p.get("phase")}
    dels = s.get(f"{api}/projects/{pid}/deliverables", headers=H).json()
    # 用 phase_id 做键,不能用 phase.code——交付物接口返回的 phase 里只有 id/name,
    # 拿 code 取会一直是 None,脚本就不幂等了,每跑一次多建一遍
    existing = {(d["phase_id"], d["name"]): d for d in dels}

    for phase_code, del_name, status in DEMO_STATUS:
        d = existing.get((phase_ids[phase_code], del_name))
        if d is None:
            r = s.post(f"{api}/projects/{pid}/deliverables", headers=H, json={
                "phase_id": phase_ids[phase_code], "name": del_name, "status": status,
                "description": "工作流演示数据",
            })
            if r.status_code != 201:
                print(f"[错误] 建交付物 {del_name} 失败 {r.status_code}: {r.text[:200]}")
                return 1
            print(f"[新建] {phase_code} {del_name} → {status}")
            continue
        if d["status"] == status:
            print(f"[已是] {phase_code} {del_name} = {status}")
            continue
        r = s.put(f"{api}/deliverables/{d['id']}", headers=H, json={"status": status})
        if r.status_code != 200:
            print(f"[错误] 更新 {del_name} → {status} 失败 {r.status_code}: {r.text[:200]}")
            return 1
        print(f"[设置] {phase_code} {del_name} → {status}")

    wf = s.get(f"{api}/projects/{pid}/workflow", headers=H).json()
    print()
    print(f"[工作流] 累计 {wf['summary']['steps_done']}/{wf['summary']['steps_total']} 步已完成")
    s0 = next((p for p in wf["phases"] if p["phase_code"] == "S0"), None)
    if s0:
        print(f"  S0 门禁={s0['gate_state_label']}  可发起={s0['progress']['can_initiate_signoff']}")
        print(f"  S0 缺件={s0['progress']['missing_required']}")
        for st in s0["steps"]:
            print(f"    {st['seq']} [{st['state_label']}] {st['node']['name']}"
                  + ("（本库未配置对应标准,可人工确认）" if st["definition_gap"] else ""))
    print()
    print(f"打开: {a.base.rstrip('/')}/projects/{pid}?tab=workflow")
    return 0


def _find_project(s, H, api):
    """按 code 找项目。列表接口 page_size 上限 100,项目可能超过,所以用搜索接口。"""
    r = s.get(f"{api}/projects/search", headers=H, params={"q": CODE})
    if r.status_code != 200:
        return None
    for p in (r.json() or {}).get("projects") or []:
        if p.get("code") == CODE:
            return p["id"]
    return None


if __name__ == "__main__":
    sys.exit(main())
