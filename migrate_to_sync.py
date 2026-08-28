"""Migrate all backend_v2 from async SQLAlchemy to sync."""
import os, re, glob, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PATHS = [
    os.path.join(ROOT, "backend_v2", "routes"),
    os.path.join(ROOT, "backend_v2"),
]

all_files = []
for p in PATHS:
    if os.path.isdir(p):
        all_files.extend(glob.glob(os.path.join(p, "*.py")))
    elif os.path.isfile(p):
        all_files.append(p)

for filepath in sorted(all_files):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except:
        continue

    original = content

    # Remove 'async ' before 'def '
    content = re.sub(r'\basync def\b', 'def', content)

    # Remove 'await ' before common patterns
    for pattern in [r'await db\.', r'await log_audit\(', r'await _fix_dates', r'await _fix_empty_strings',
                    r'await init_db\(\)', r'await _parse_dates']:
        content = re.sub(pattern, pattern.replace('await ', ''), content)

    # Replace AsyncSession in imports and type hints
    content = content.replace('from sqlalchemy.ext.asyncio import AsyncSession', 'from sqlalchemy.orm import Session')
    content = re.sub(r'\bAsyncSession\b', 'Session', content)

    # Fix result patterns - remove unnecessary .unique() for sync mode
    content = re.sub(r'\.unique\(\)\.scalars\(\)', '.scalars()', content)
    content = re.sub(r'\.unique\(\)\.scalar_one\(\)', '.scalars().one()', content)
    content = re.sub(r'\.unique\(\)\.scalar_one_or_none\(\)', '.scalars().one_or_none()', content)
    content = re.sub(r'\.unique\(\)\.all\(\)', '.scalars().all()', content)
    content = re.sub(r'result\.unique\(\)', 'result', content)

    if content != original:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        name = os.path.basename(filepath)
        # Count changes
        async_defs_removed = len(re.findall(r'\basync def\b', original)) - len(re.findall(r'\basync def\b', content))
        await_removed = len(re.findall(r'\bawait\b', original)) - len(re.findall(r'\bawait\b', content))
        async_session_removed = original.count('AsyncSession') - content.count('AsyncSession')
        if async_defs_removed or await_removed or async_session_removed:
            print(f"  {name}: -{async_defs_removed} async, -{await_removed} await, -{async_session_removed} AsyncSession")

print("Done!")
