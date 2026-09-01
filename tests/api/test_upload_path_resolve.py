"""uploads 目录迁移后 stored_path 失效时,按命名规则重建路径的兜底逻辑测试。

历史问题:product_tech / bom 附件元数据里存的是上传时的绝对路径,
uploads 目录整体迁移到 NAS 后旧路径全部失效,导致预览/下载 404。
兜底按上传命名规则在 UPLOAD_DIR 下重建路径。
"""
import os

from backend_v2.config import settings
from backend_v2.routes.product_tech import _resolve_attach_path
from backend_v2.routes.bom_lists import _resolve_att_path


def test_product_tech_resolve_rebuilds_after_migration(tmp_path):
    up = settings.UPLOAD_DIR
    item_dir = os.path.join(up, "product_tech_files", "56")
    os.makedirs(item_dir, exist_ok=True)
    real = os.path.join(item_dir, "56_7_电机物料清单.pdf")
    with open(real, "wb") as f:
        f.write(b"%PDF-1.4 test")

    att = {
        "id": 7, "item_id": 56, "filename": "电机物料清单.pdf",
        # 模拟迁移后失效的旧绝对路径
        "stored_path": r"D:\old\data\uploads\product_tech_files\56\56_7_电机物料清单.pdf",
    }
    resolved = _resolve_attach_path(att)
    assert resolved == real
    assert os.path.exists(resolved)

    # stored_path 有效时直接用原路径
    att["stored_path"] = real
    assert _resolve_attach_path(att) == real

    # 完全不存在时返回原路径(调用方负责 404)
    att2 = dict(att, stored_path=r"D:\missing\a.pdf", filename="不存在.pdf")
    assert _resolve_attach_path(att2) == att2["stored_path"]


def test_bom_resolve_rebuilds_after_migration(tmp_path):
    att_dir = os.path.join(settings.UPLOAD_DIR, "bom_files")
    os.makedirs(att_dir, exist_ok=True)
    real = os.path.join(att_dir, "6_1_1785222943.xlsx")
    with open(real, "wb") as f:
        f.write(b"PK test xlsx")

    att = {
        "id": 1, "list_id": "6", "filename": "CM02_BOM.xlsx",
        "stored_name": "6_1_1785222943.xlsx",
        "stored_path": r"D:\old\data\uploads\bom_files\6_1_1785222943.xlsx",
    }
    resolved = _resolve_att_path(att)
    assert resolved == real
    assert os.path.exists(resolved)

    # stored_path 有效时直接用原路径
    att["stored_path"] = real
    assert _resolve_att_path(att) == real
