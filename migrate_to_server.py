"""
迁移数据到公司服务器。

使用方法:
1. 在文件资源管理器映射服务器共享为网络驱动器（如 Z:）
   - 右键"此电脑" → 映射网络驱动器 → 输入服务器路径
2. 修改下方 SERVER_PATH 为实际路径
3. 运行: python migrate_to_server.py
"""
import os, shutil, sys

# ============================================
# 🔧 修改这里：你的服务器共享路径
# ============================================
SERVER_PATH = r"Z:\motor-pm-data"  # 改成你的实际服务器路径

LOCAL_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_FILE = os.path.join(LOCAL_DATA, "motor_pm_v2.db")
UPLOADS_DIR = os.path.join(LOCAL_DATA, "uploads")
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend_v2", "config.py")

def main():
    if not os.path.exists(SERVER_PATH):
        print(f"❌ 服务器路径不存在: {SERVER_PATH}")
        print("请先在文件资源管理器 → 映射网络驱动器 → 将服务器共享映射为 Z: 盘")
        print("或修改脚本中的 SERVER_PATH 为实际路径")
        sys.exit(1)

    # Create server data dirs
    server_data = os.path.join(SERVER_PATH, "data")
    server_uploads = os.path.join(server_data, "uploads")
    os.makedirs(server_uploads, exist_ok=True)

    # Copy database
    if os.path.exists(DB_FILE):
        server_db = os.path.join(server_data, "motor_pm_v2.db")
        shutil.copy2(DB_FILE, server_db)
        print(f"✅ 数据库已复制: {server_db}")
        print(f"   大小: {os.path.getsize(server_db)/1024/1024:.1f} MB")

    # Copy uploads
    if os.path.exists(UPLOADS_DIR):
        upload_count = 0
        for f in os.listdir(UPLOADS_DIR):
            src = os.path.join(UPLOADS_DIR, f)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(server_uploads, f))
                upload_count += 1
        print(f"✅ {upload_count} 个文件已复制到: {server_uploads}")

    # Update config
    server_db_url = f"sqlite:///{server_db.replace(chr(92), '/')}"
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = f.read()

    # Update DATABASE_URL
    import re
    config = re.sub(
        r'DATABASE_URL: str = "sqlite.*"',
        f'DATABASE_URL: str = "{server_db_url}"',
        config
    )
    config = re.sub(
        r'DATA_DIR: str = ""',
        f'DATA_DIR: str = "{server_data.replace(chr(92), "/")}"',
        config
    )

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(config)
    print(f"✅ 配置文件已更新: {CONFIG_PATH}")

    print()
    print("=" * 50)
    print("  迁移完成！")
    print(f"  数据位置: {server_data}")
    print(f"  重启服务器: python run_v2.py")
    print(f"  本地数据仍在: {LOCAL_DATA}（可手动删除）")
    print("=" * 50)


if __name__ == "__main__":
    main()
