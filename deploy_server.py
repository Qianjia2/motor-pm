"""
Server Deployment Script — package the MotorPM platform for company server deployment.
Usage: python deploy_server.py [target_dir]
Default target: D:/MotorPM_Deploy
"""
import shutil, os, sys

target = sys.argv[1] if len(sys.argv) > 1 else "D:/MotorPM_Deploy"
source = os.path.dirname(os.path.abspath(__file__))

print(f"Source: {source}")
print(f"Target: {target}")
print()

# What to copy
copy_items = [
    ("backend_v2", "backend_v2/"),
    ("frontend/dist", "frontend/dist/"),
    ("data", "data/"),
    ("run_v2.py", "run_v2.py"),
    ("requirements.txt", "requirements.txt"),
    ("start_all.bat", "start_all.bat"),
    ("ngrok_watchdog.py", "ngrok_watchdog.py"),
]

# Clean target
if os.path.exists(target):
    print("Cleaning target...")
    shutil.rmtree(target)

os.makedirs(target, exist_ok=True)

# Copy
for src_rel, dst_rel in copy_items:
    src = os.path.join(source, src_rel)
    dst = os.path.join(target, dst_rel)
    if not os.path.exists(src):
        print(f"  SKIP {src_rel} (not found)")
        continue
    print(f"  COPY {src_rel} -> {dst_rel}")
    if os.path.isdir(src):
        shutil.copytree(src, dst)
    else:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)

# Update start_all.bat to use absolute paths
bat_path = os.path.join(target, "start_all.bat")
if os.path.exists(bat_path):
    with open(bat_path, "r", encoding="utf-8") as f:
        content = f.read()
    content = content.replace("D:\\AI\\motor-pm", target)
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(content)

# Generate setup guide
guide = f"""
========================================
  MotorPM Platform — Server Setup Guide
========================================

1. PREREQUISITES (install on server):
   - Python 3.10+ : https://www.python.org/downloads/
   - Ollama : https://ollama.com/download/windows
     After install, run: ollama pull qwen2.5:3b
   - (Optional) ngrok : for external access

2. DEPLOY:
   - Copy this entire folder to server (e.g., D:\\MotorPM_Deploy)
   - Open CMD as Administrator, navigate to this folder
   - Run: pip install -r requirements.txt
   - Run: python run_v2.py   (test startup)
   - Open http://localhost:5002 in browser

3. AUTO-START (Windows Server):
   - Press Win+R, type: shell:startup
   - Create a shortcut to: {target}\\start_all.bat
   - Or create a Scheduled Task (runs even without login)

4. FIREWALL (allow LAN access):
   Run as Administrator:
   netsh advfirewall firewall add rule name="MotorPM-5002" dir=in action=allow protocol=TCP localport=5002

5. DATA PRESERVED:
   - Database: data/motor_pm_v2.db
   - Uploads: data/uploads/
   - AI Config: data/ai_config.json
   - Doc Types: data/doc_types.json
   - Tabs Config: data/tabs_config.json

6. BACKUP (daily scheduled):
   Create a .bat file with:
   xcopy /E /Y D:\\MotorPM_Deploy\\data D:\\Backups\\MotorPM_%date:~0,10%\\
   Schedule via Windows Task Scheduler.

========================================
  Deploy completed: {target}
  Data size: ~200MB (may take time to copy via network)
========================================
"""

guide_path = os.path.join(target, "SETUP_GUIDE.txt")
with open(guide_path, "w", encoding="utf-8") as f:
    f.write(guide)

print()
print(guide)
print(f"\nDeploy package created at: {target}")
print(f"Copy this folder to the server and follow SETUP_GUIDE.txt")
