"""Shared fixtures for motor-pm unit tests."""
import os
import sys
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# 内部模板固定夹具: 仓库根 data/ 下的真实公司模板(git 已跟踪, CI 可用)
TEMPLATE_XLS = REPO_ROOT / "data" / "bom_internal_template.xls"


def _template_bytes():
    if not TEMPLATE_XLS.exists():
        raise FileNotFoundError(f"模板夹具缺失: {TEMPLATE_XLS}")
    return TEMPLATE_XLS.read_bytes()


import pytest


@pytest.fixture(scope="session")
def template_bytes():
    return _template_bytes()


@pytest.fixture(scope="session")
def template_meta(template_bytes):
    from backend_v2.routes.bom_lists import _parse_internal_template
    return _parse_internal_template(template_bytes, "bom_internal_template.xls")
