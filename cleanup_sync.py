"""Cleanup: fix escaped backslashes, duplicate imports, remaining await."""
import os, re, glob

ROUTES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend_v2", "routes")

for filepath in sorted(glob.glob(os.path.join(ROUTES_DIR, "*.py"))):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    original = content

    # Fix escaped dot: db\.execute -> db.execute, log_audit\( -> log_audit(
    content = content.replace(r'db\.execute', 'db.execute')
    content = content.replace(r'db\.commit', 'db.commit')
    content = content.replace(r'db\.flush', 'db.flush')
    content = content.replace(r'db\.refresh', 'db.refresh')
    content = content.replace(r'db\.add', 'db.add')
    content = content.replace(r'db\.delete', 'db.delete')
    content = content.replace(r'db\.rollback', 'db.rollback')
    content = content.replace(r'log_audit\(db', 'log_audit(db')
    content = content.replace(r'update\(TeamMember', 'update(TeamMember')
    content = content.replace(r'update\(ProjectMember', 'update(ProjectMember')
    content = content.replace(r'update\(ChangeRequest', 'update(ChangeRequest')
    content = content.replace(r'update\(Project\)', 'update(Project)')
    content = content.replace(r'update\(WeeklyReport', 'update(WeeklyReport')
    content = content.replace(r'update\(Milestone', 'update(Milestone')
    content = content.replace(r'update\(RiskIssue', 'update(RiskIssue')
    content = content.replace(r'update\(Task\)', 'update(Task)')
    content = content.replace(r'update\(Requirement', 'update(Requirement')
    content = content.replace(r'update\(ApiKey', 'update(ApiKey')
    content = content.replace(r'update\(WebhookConfig', 'update(WebhookConfig')
    content = content.replace(r'update\(TestPlan', 'update(TestPlan')
    content = content.replace(r'update\(TestResult', 'update(TestResult')
    content = content.replace(r'update\(TestIssue', 'update(TestIssue')
    content = content.replace(r'update\(PrototypeBuild', 'update(PrototypeBuild')
    content = content.replace(r'update\(MaterialCheck', 'update(MaterialCheck')
    content = content.replace(r'update\(BomItem', 'update(BomItem')
    content = content.replace(r'update\(Ecn', 'update(Ecn')
    content = content.replace(r'update\(Phase\)', 'update(Phase)')
    content = content.replace(r'update\(Gate\)', 'update(Gate)')
    content = content.replace(r'update\(TechnicalLine', 'update(TechnicalLine')
    content = content.replace(r'update\(Role\)', 'update(Role)')
    content = content.replace(r'delete\(Task\)', 'delete(Task)')
    content = content.replace(r'delete\(WeeklyReportLine', 'delete(WeeklyReportLine')
    content = content.replace(r'delete\(ProjectMember', 'delete(ProjectMember')
    content = content.replace(r'delete\(ChangeRequest', 'delete(ChangeRequest')
    content = content.replace(r'delete\(Requirement', 'delete(Requirement')
    content = content.replace(r'delete\(RiskIssue', 'delete(RiskIssue')

    # Fix duplicate sqlalchemy.orm import
    if content.count('from sqlalchemy.orm import') > 1:
        lines = content.split('\n')
        seen_orm = False
        new_lines = []
        for line in lines:
            if line.strip().startswith('from sqlalchemy.orm import'):
                if not seen_orm:
                    seen_orm = True
                    # Merge all orm imports
                    imports = set()
                    for l in lines:
                        if l.strip().startswith('from sqlalchemy.orm import'):
                            imports.update(re.findall(r'\b(\w+)\b', l.split('import')[1]))
                    new_lines.append('from sqlalchemy.orm import ' + ', '.join(sorted(imports)))
                    continue
                else:
                    continue  # skip duplicate
            else:
                new_lines.append(line)
        content = '\n'.join(new_lines)

    # Fix remaining 'await ' calls (AI functions that are still async)
    content = content.replace('await financial_overview', 'financial_overview')

    if content != original:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Fixed: {os.path.basename(filepath)}")

# Also fix ai.py to keep async for AI functions
ai_path = os.path.join(ROUTES_DIR, "ai.py")
with open(ai_path, "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace('def ai_weekly_report', 'async def ai_weekly_report')
content = content.replace('def ai_analyze_risk', 'async def ai_analyze_risk')
content = content.replace('def ai_diagnose', 'async def ai_diagnose')
content = content.replace('def ai_chat', 'async def ai_chat')

with open(ai_path, "w", encoding="utf-8") as f:
    f.write(content)
print(f"Fixed: ai.py (kept async for AI)")

# Fix main.py to remove async lifespan
main_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend_v2", "main.py")
with open(main_path, "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace('async def lifespan', 'def lifespan')
content = content.replace('await init_db', 'init_db')

with open(main_path, "w", encoding="utf-8") as f:
    f.write(content)
print(f"Fixed: main.py")

print("\nCleanup complete!")
