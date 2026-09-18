"""给「软件工作流验证项目」配项目组,好让「我的工作台」有东西可看。

为什么需要:工作台是按「登录人的项目角色」算该谁做什么的。这个演示项目原来一个
成员都没有,admin 也没绑人员档案,所以谁进去都只会看到"你在本项目没有分配角色"
这一种状态——四种状态里三种压根触发不了,没法验。

挑的都是**绑定了登录账号**的人员档案,这样能用不同账号登录,看到不同的"我的下一步":
  zhangxiang   → 项目经理    (S0 第1步「需求调研与澄清」等)
  maxiaohao    → 软件工程师  (S1 大量步骤 + S2 第7步「问题整改闭环」)
  liangweien   → 测试工程师  (S2 测试类步骤)
  huanghui     → 商务经理    (S0/S3 商务类步骤)

幂等:已存在的(成员,角色)组合接口会返回 409,当成"已配好"跳过。

用法: python scripts/seed_workflow_demo_members.py [--base URL]
"""
import argparse
import sys

import requests

DEFAULT_BASE = "http://127.0.0.1:5002"
CODE = "SW-WF-DEMO"

# (人员档案 id, 姓名, 角色名) —— 姓名只用于打印
MEMBERS = [
    (4, "张翔", "项目经理"),
    (6, "马晓皓", "软件工程师"),
    (12, "梁伟恩", "测试工程师"),
    (11, "黄辉", "商务经理"),
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
    if not pid:
        print(f"[错误] 找不到项目 {CODE}，先跑 scripts/seed_workflow_demo_project.py")
        return 1
    print(f"项目: {CODE} (id={pid})\n")

    roles = {x["name"]: x["id"] for x in s.get(f"{api}/lookups/roles", headers=H).json()}
    missing = [r for _, _, r in MEMBERS if r not in roles]
    if missing:
        print(f"[错误] 角色表里没有: {missing}")
        return 1

    added = skipped = 0
    for mid, name, role in MEMBERS:
        resp = s.post(f"{api}/projects/{pid}/members", headers=H,
                      json={"member_id": mid, "role_id": roles[role],
                            "allocation_pct": 100, "is_key": True, "phase_ids": "[]"})
        if resp.status_code == 201:
            print(f"  + {name}  →  {role}")
            added += 1
        elif resp.status_code == 409:
            print(f"  = {name}  →  {role}  (已存在)")
            skipped += 1
        else:
            print(f"  ! {name}  →  {role}  失败 {resp.status_code}: {resp.text[:160]}")
            return 1

    print(f"\n新增 {added} 条，跳过 {skipped} 条（幂等）")

    # 回读确认,并核对角色名能对上工作流的节点 roles
    got = s.get(f"{api}/projects/{pid}/members", headers=H).json()
    print(f"\n项目组现有 {len(got)} 人:")
    for m in got:
        print(f"  {m.get('member', {}).get('name', '?'):8} {m.get('role', {}).get('name', '?')}")

    wf = s.get(f"{api}/projects/{pid}/workflow", headers=H).json()
    print(f"\n工作流接口 me 字段: has_role={wf['me']['has_role']} "
          f"roles={wf['me']['roles']} mine_total={wf['me']['mine_total']}")
    if not wf["me"]["has_role"]:
        print("[警告] admin 自己没角色是正常的（admin 未绑人员档案）；"
              "请用上面某个成员的账号登录验证工作台")
    return 0


def _find_project(s, H, api):
    r = s.get(f"{api}/projects", headers=H)
    if r.status_code != 200:
        return None
    data = r.json()
    rows = data.get("data") if isinstance(data, dict) else data
    for p in rows or []:
        if p.get("code") == CODE:
            return p["id"]
    return None


if __name__ == "__main__":
    sys.exit(main())
