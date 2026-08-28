"""Send DingTalk reminders for pending weekly reports."""
import sys, os, json, urllib.request
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import create_app
from backend.models import Project, WeeklyReport, ProjectMember

DINGTALK_CONFIG = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'dingtalk_config.json')


def load_dingtalk_config():
    if os.path.exists(DINGTALK_CONFIG):
        with open(DINGTALK_CONFIG, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def send_dingtalk(webhook_url, title, content):
    """Send a markdown message via DingTalk webhook."""
    data = json.dumps({
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": content,
        }
    }).encode('utf-8')
    req = urllib.request.Request(webhook_url, data=data, headers={'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(req)
        return True
    except Exception as e:
        print(f"  DingTalk send failed: {e}")
        return False


def check_and_remind():
    app = create_app()
    with app.app_context():
        today = date.today()
        week_num = today.isocalendar()[1]
        year = today.year

        active_projects = Project.query.filter_by(is_active=True).all()
        pending = []

        for p in active_projects:
            report = WeeklyReport.query.filter_by(
                project_id=p.id, year=year, week_number=week_num
            ).first()

            if not report:
                pm = p.members[0].member.name if p.members else '未指定'
                pending.append({
                    'project_name': p.name,
                    'project_code': p.code,
                    'pm': pm,
                })

        if not pending:
            print(f'所有项目本周周报已填写完毕（W{week_num}）')
            return

        print(f'{len(pending)}/{len(active_projects)} 个项目未填本周周报（W{week_num}）：')
        for item in pending:
            print(f'  - {item["project_code"]} {item["project_name"][:30]} (PM: {item["pm"]})')

        # Send DingTalk reminder
        config = load_dingtalk_config()
        if not config or not config.get('webhook_url'):
            print('\n未配置钉钉 webhook，跳过发送。')
            print('请在 dingtalk_config.json 中配置 webhook_url')
            return

        lines = '\n'.join(
            f'- **{p["project_code"]}** {p["project_name"][:20]}（PM: {p["pm"]}）'
            for p in pending
        )

        msg = f"""## 📋 周报填写提醒
> W{week_num} 周报待填写

{len(pending)}/{len(active_projects)} 个项目尚未填写本周周报：

{lines}

---
请各位 PM 尽快登录 [项目管理工具](http://10.136.101.192:5000) 填写周报。
外网访问：https://reformat-handbag-oil.ngrok-free.dev"""

        send_dingtalk(config['webhook_url'], f'周报提醒 W{week_num}', msg)
        print('\n钉钉提醒已发送！')


if __name__ == '__main__':
    check_and_remind()
