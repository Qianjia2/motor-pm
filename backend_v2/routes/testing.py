"""Test verification + prototype build management."""
import os
from datetime import datetime, date as date_type
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend_v2.database import get_db
from backend_v2.auth import get_current_user
from backend_v2.models import TestPlan, TestResult, TestIssue, PrototypeBuild, MaterialCheck, Project, BomItem
from backend_v2.config import settings
from pathlib import Path as FilePath
import uuid as _uuid

BOM_FILES_DIR = os.path.join(settings.UPLOAD_DIR, "bom_files")

def _bom_files_meta_path(build_id):
    return os.path.join(BOM_FILES_DIR, f"meta_{build_id}.json")


def _parse_dates(data, fields):
    """Convert ISO date strings to Python date objects."""
    for f in fields:
        if f in data and data[f] and isinstance(data[f], str):
            try: data[f] = date_type.fromisoformat(data[f])
            except: pass

router = APIRouter(tags=["testing"])

# ═══════════════════ Test Plans ═══════════════════

@router.get("/api/projects/{project_id}/test-plans")
def list_test_plans(project_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    result = db.execute(
        select(TestPlan).where(TestPlan.project_id == project_id).order_by(TestPlan.planned_start)
    )
    plans = result.scalars().all()
    return [{c.name: getattr(p, c.name) for c in p.__table__.columns} for p in plans]


@router.post("/api/projects/{project_id}/test-plans", status_code=201)
def create_test_plan(project_id: int, data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    _parse_dates(data, ["planned_start", "planned_end"])
    allowed = {"name", "test_type", "phase_id", "description", "planned_start", "planned_end", "status", "attachment_path"}
    tp = TestPlan(project_id=project_id, **{k: v for k, v in data.items() if k in allowed})
    db.add(tp); db.commit(); db.refresh(tp)
    return {c.name: getattr(tp, c.name) for c in tp.__table__.columns}


@router.post("/api/test-plans/{plan_id}/upload", status_code=201)
async def upload_test_plan_file(plan_id: int, file: UploadFile = File(...),
                                db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Upload a test plan document — any format."""
    tp = (db.execute(select(TestPlan).where(TestPlan.id == plan_id))).scalar_one_or_none()
    if not tp: raise HTTPException(status_code=404, detail="测试计划不存在")
    upload_dir = FilePath(settings.UPLOAD_DIR) / str(tp.project_id) / "test_plans"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{_uuid.uuid4().hex[:8]}_{file.filename}"
    dest = upload_dir / safe_name
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"文件超过 {settings.MAX_UPLOAD_SIZE_MB}MB")
    with open(dest, "wb") as f:
        f.write(content)
    rel_path = str(dest.relative_to(FilePath(settings.UPLOAD_DIR).parent))
    from sqlalchemy import update as up
    db.execute(up(TestPlan).where(TestPlan.id == plan_id).values(attachment_path=rel_path))
    db.commit()
    return {"message": "上传成功", "attachment_path": rel_path, "file_name": file.filename, "size": len(content)}


@router.put("/api/test-plans/{plan_id}")
def update_test_plan(plan_id: int, data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    from sqlalchemy import update as up
    result = db.execute(select(TestPlan).where(TestPlan.id == plan_id))
    tp = result.scalar_one_or_none()
    if not tp: raise HTTPException(status_code=404, detail="不存在")
    _parse_dates(data, ["planned_start", "planned_end", "actual_start", "actual_end"])
    allowed = {"name", "test_type", "phase_id", "description", "planned_start", "planned_end", "actual_start", "actual_end", "status"}
    upd = {k: v for k, v in data.items() if k in allowed}
    if upd: db.execute(up(TestPlan).where(TestPlan.id == plan_id).values(**upd)); db.commit()
    return {"message": "已更新"}


@router.delete("/api/test-plans/{plan_id}")
def delete_test_plan(plan_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    from sqlalchemy import delete as dl
    db.execute(dl(TestPlan).where(TestPlan.id == plan_id)); db.commit()
    return {"message": "已删除"}


# ═══════════════════ Test Results ═══════════════════

@router.get("/api/test-plans/{plan_id}/results")
def list_test_results(plan_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    result = db.execute(select(TestResult).where(TestResult.test_plan_id == plan_id).order_by(TestResult.test_date))
    return [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in result.scalars().all()]


@router.post("/api/test-plans/{plan_id}/results", status_code=201)
def create_test_result(plan_id: int, data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    tp = (db.execute(select(TestPlan).where(TestPlan.id == plan_id))).scalar_one_or_none()
    if not tp: raise HTTPException(status_code=404, detail="测试计划不存在")
    _parse_dates(data, ["test_date"])
    tr = TestResult(test_plan_id=plan_id, project_id=tp.project_id,
                    **{k: v for k, v in data.items() if k in ("name", "test_date", "result", "measured_value", "spec_value", "notes")})
    db.add(tr); db.commit(); db.refresh(tr)
    return {c.name: getattr(tr, c.name) for c in tr.__table__.columns}


@router.put("/api/test-results/{result_id}")
def update_test_result(result_id: int, data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    from sqlalchemy import update as up
    r = (db.execute(select(TestResult).where(TestResult.id == result_id))).scalar_one_or_none()
    if not r: raise HTTPException(status_code=404, detail="不存在")
    _parse_dates(data, ["test_date"])
    allowed = {"name", "test_date", "result", "measured_value", "spec_value", "notes", "attachment_path"}
    upd = {k: v for k, v in data.items() if k in allowed}
    if upd: db.execute(up(TestResult).where(TestResult.id == result_id).values(**upd)); db.commit()
    return {"message": "已更新"}


@router.delete("/api/test-results/{result_id}")
def delete_test_result(result_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    from sqlalchemy import delete as dl
    db.execute(dl(TestResult).where(TestResult.id == result_id)); db.commit()
    return {"message": "已删除"}


@router.post("/api/test-results/{result_id}/upload", status_code=201)
async def upload_test_file(result_id: int, file: UploadFile = File(...),
                           db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Upload a test report/document to a test result — any format accepted."""
    r = (db.execute(select(TestResult).where(TestResult.id == result_id))).scalar_one_or_none()
    if not r: raise HTTPException(status_code=404, detail="测试结果不存在")
    ext = FilePath(file.filename).suffix.lstrip(".").lower() if file.filename else ""
    upload_dir = FilePath(settings.UPLOAD_DIR) / str(r.project_id) / "test_reports"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{_uuid.uuid4().hex[:8]}_{file.filename}"
    dest = upload_dir / safe_name
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"文件超过 {settings.MAX_UPLOAD_SIZE_MB}MB")
    with open(dest, "wb") as f:
        f.write(content)
    rel_path = str(dest.relative_to(FilePath(settings.UPLOAD_DIR).parent))
    from sqlalchemy import update as up
    db.execute(up(TestResult).where(TestResult.id == result_id).values(attachment_path=rel_path))
    db.commit()
    return {"message": "上传成功", "attachment_path": rel_path, "file_name": file.filename, "size": len(content)}


@router.post("/api/projects/{project_id}/test-files/upload-batch", status_code=201)
async def upload_test_file_batch(project_id: int, file: UploadFile = File(...), name: str = Form(""),
                                 db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Upload a test file directly — creates a lightweight test result record."""
    upload_dir = FilePath(settings.UPLOAD_DIR) / str(project_id) / "test_reports"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{_uuid.uuid4().hex[:8]}_{file.filename}"
    dest = upload_dir / safe_name
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"文件超过 {settings.MAX_UPLOAD_SIZE_MB}MB")
    with open(dest, "wb") as f:
        f.write(content)
    rel_path = str(dest.relative_to(FilePath(settings.UPLOAD_DIR).parent))
    item_name = name or file.filename.rsplit(".", 1)[0] if file.filename else "测试文件"
    tr = TestResult(project_id=project_id, name=item_name, result="pending",
                    attachment_path=rel_path, test_date=date_type.today())
    db.add(tr); db.commit(); db.refresh(tr)
    return {"message": "上传成功", "id": tr.id, "attachment_path": rel_path, "file_name": file.filename, "size": len(content)}


@router.get("/api/projects/{project_id}/test-files")
def list_test_files(project_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """List all test results that have attached files."""
    result = db.execute(
        select(TestResult).where(
            TestResult.project_id == project_id,
            TestResult.attachment_path.isnot(None),
            TestResult.attachment_path != "",
        ).order_by(TestResult.test_date.desc())
    )
    files = []
    for r in result.scalars().all():
        files.append({
            "id": r.id, "name": r.name, "test_date": r.test_date.isoformat() if r.test_date else None,
            "result": r.result, "attachment_path": r.attachment_path,
            "plan_name": r.test_plan.name if r.test_plan else "",
        })
    return files


# ═══════════════════ Test Issues (8D) ═══════════════════

@router.get("/api/projects/{project_id}/test-issues")
def list_test_issues(project_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    result = db.execute(select(TestIssue).where(TestIssue.project_id == project_id).order_by(TestIssue.created_at.desc()))
    return [{c.name: getattr(i, c.name) for c in i.__table__.columns} for i in result.scalars().all()]


@router.post("/api/projects/{project_id}/test-issues", status_code=201)
def create_test_issue(project_id: int, data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    allowed = {"title", "description", "severity", "test_result_id",
               "d1_team", "d2_problem", "d3_containment", "d4_root_cause",
               "d5_corrective", "d6_implementation", "d7_prevention", "d8_recognition"}
    ti = TestIssue(project_id=project_id, created_at=datetime.utcnow(), **{k: v for k, v in data.items() if k in allowed})
    db.add(ti); db.commit(); db.refresh(ti)
    return {c.name: getattr(ti, c.name) for c in ti.__table__.columns}


@router.put("/api/test-issues/{issue_id}")
def update_test_issue(issue_id: int, data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    from sqlalchemy import update as up
    ti = (db.execute(select(TestIssue).where(TestIssue.id == issue_id))).scalar_one_or_none()
    if not ti: raise HTTPException(status_code=404, detail="不存在")
    allowed = {"title", "description", "severity", "status",
               "d1_team", "d2_problem", "d3_containment", "d4_root_cause",
               "d5_corrective", "d6_implementation", "d7_prevention", "d8_recognition"}
    upd = {k: v for k, v in data.items() if k in allowed}
    if data.get("status") == "closed":
        upd["closed_at"] = datetime.utcnow()
    if upd: db.execute(up(TestIssue).where(TestIssue.id == issue_id).values(**upd)); db.commit()
    return {"message": "已更新"}


@router.delete("/api/test-issues/{issue_id}")
def delete_test_issue(issue_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    from sqlalchemy import delete as dl
    db.execute(dl(TestIssue).where(TestIssue.id == issue_id)); db.commit()
    return {"message": "已删除"}


# ═══════════════════ Prototype Build ═══════════════════

@router.get("/api/projects/{project_id}/prototype-builds")
def list_builds(project_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    result = db.execute(select(PrototypeBuild).where(PrototypeBuild.project_id == project_id).order_by(PrototypeBuild.start_date))
    builds = result.scalars().all()
    data = []
    for b in builds:
        d = {c.name: getattr(b, c.name) for c in b.__table__.columns}
        # Count materials
        mc = (db.execute(select(MaterialCheck).where(MaterialCheck.prototype_build_id == b.id))).scalars().all()
        d["material_total"] = len(mc)
        d["material_ready"] = sum(1 for m in mc if m.status == "ready")
        d["material_missing"] = sum(1 for m in mc if m.status in ("missing", "urgent"))
        data.append(d)
    return data


@router.post("/api/projects/{project_id}/prototype-builds", status_code=201)
def create_build(project_id: int, data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    _parse_dates(data, ["start_date", "end_date"])
    allowed = {"batch_name", "planned_qty", "actual_qty", "start_date", "end_date", "status", "notes"}
    pb = PrototypeBuild(project_id=project_id, **{k: v for k, v in data.items() if k in allowed})
    db.add(pb); db.commit(); db.refresh(pb)
    return {c.name: getattr(pb, c.name) for c in pb.__table__.columns}


@router.put("/api/prototype-builds/{build_id}")
def update_build(build_id: int, data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    from sqlalchemy import update as up
    pb = (db.execute(select(PrototypeBuild).where(PrototypeBuild.id == build_id))).scalar_one_or_none()
    if not pb: raise HTTPException(status_code=404, detail="不存在")
    _parse_dates(data, ["start_date", "end_date"])
    allowed = {"batch_name", "planned_qty", "actual_qty", "start_date", "end_date", "status", "notes"}
    upd = {k: v for k, v in data.items() if k in allowed}
    if upd: db.execute(up(PrototypeBuild).where(PrototypeBuild.id == build_id).values(**upd)); db.commit()
    return {"message": "已更新"}


@router.delete("/api/prototype-builds/{build_id}")
def delete_build(build_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    from sqlalchemy import delete as dl
    # Cascade delete: materials, BOM items, BOM attachment files
    db.execute(dl(MaterialCheck).where(MaterialCheck.prototype_build_id == build_id))
    db.execute(dl(BomItem).where(BomItem.build_id == build_id))
    db.execute(dl(PrototypeBuild).where(PrototypeBuild.id == build_id))
    db.commit()
    # Clean up BOM attachment files on disk
    meta_path = _bom_files_meta_path(build_id)
    if os.path.exists(meta_path):
        import json as _json
        with open(meta_path, "r", encoding="utf-8") as f:
            entries = _json.load(f)
        for e in entries:
            fp = os.path.join(BOM_FILES_DIR, e.get("path", ""))
            if os.path.exists(fp):
                try:
                    os.remove(fp)
                except:
                    pass
        try:
            os.remove(meta_path)
        except:
            pass
    return {"message": "已删除"}


# ═══════════════════ Material Check ═══════════════════

@router.get("/api/prototype-builds/{build_id}/materials")
def list_materials(build_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    result = db.execute(select(MaterialCheck).where(MaterialCheck.prototype_build_id == build_id).order_by(MaterialCheck.status, MaterialCheck.material_name))
    return [{c.name: getattr(m, c.name) for c in m.__table__.columns} for m in result.scalars().all()]


@router.post("/api/prototype-builds/{build_id}/materials", status_code=201)
def create_material(build_id: int, data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    pb = (db.execute(select(PrototypeBuild).where(PrototypeBuild.id == build_id))).scalar_one_or_none()
    if not pb: raise HTTPException(status_code=404, detail="不存在")
    allowed = {"material_name", "specification", "required_qty", "available_qty", "status", "supplier", "lead_time_days", "notes"}
    mc = MaterialCheck(prototype_build_id=build_id, project_id=pb.project_id, **{k: v for k, v in data.items() if k in allowed})
    db.add(mc); db.commit(); db.refresh(mc)
    return {c.name: getattr(mc, c.name) for c in mc.__table__.columns}


@router.put("/api/materials/{mat_id}")
def update_material(mat_id: int, data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    from sqlalchemy import update as up
    m = (db.execute(select(MaterialCheck).where(MaterialCheck.id == mat_id))).scalar_one_or_none()
    if not m: raise HTTPException(status_code=404, detail="不存在")
    allowed = {"material_name", "specification", "required_qty", "available_qty", "status", "supplier", "lead_time_days", "notes"}
    upd = {k: v for k, v in data.items() if k in allowed}
    if upd: db.execute(up(MaterialCheck).where(MaterialCheck.id == mat_id).values(**upd)); db.commit()
    return {"message": "已更新"}


@router.delete("/api/materials/{mat_id}")
def delete_material(mat_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    from sqlalchemy import delete as dl
    db.execute(dl(MaterialCheck).where(MaterialCheck.id == mat_id)); db.commit()
    return {"message": "已删除"}


# ── AI BOM auto-generation from drawings ──
@router.post("/api/prototype-builds/{build_id}/bom-from-drawing")
async def generate_bom_from_drawing(build_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Upload motor/controller drawing → AI identifies components + quantities → BOM list."""
    import easyocr, numpy as np, io as _io
    from PIL import Image as _PILImage
    from backend_v2.ai_service import call_task

    pb = db.execute(select(PrototypeBuild).where(PrototypeBuild.id == build_id)).scalar_one_or_none()
    if not pb: raise HTTPException(404, detail="批次不存在")

    content = await file.read()
    fname = file.filename or "drawing"

    # 1. OCR: extract text from drawing
    text_lines = []
    try:
        ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        if ext == "pdf":
            import fitz
            doc = fitz.open(stream=content, filetype="pdf")
            reader = easyocr.Reader(['ch_sim', 'en'], gpu=False, verbose=False)
            for page in doc:
                pix = page.get_pixmap(dpi=200)
                img = _PILImage.open(_io.BytesIO(pix.tobytes("png")))
                text_lines.extend(reader.readtext(np.array(img), detail=0))
            doc.close()
        else:
            img = _PILImage.open(_io.BytesIO(content))
            reader = easyocr.Reader(['ch_sim', 'en'], gpu=False, verbose=False)
            text_lines = reader.readtext(np.array(img), detail=0)
    except Exception as e:
        raise HTTPException(400, detail=f"图纸识别失败: {str(e)[:100]}")

    ocr_text = " ".join(text_lines)[:6000]
    if not ocr_text.strip():
        raise HTTPException(400, detail="未能识别文字，请确认图纸清晰度")

    # 2. AI: identify components
    prompt = f"""你是电机/电控BOM分析专家。从图纸OCR文字中识别物料并生成BOM。

图纸文字: {ocr_text}

列出所有物料，每项包含 material_name(标准名)/specification(规格)/required_qty(数量)/category(电磁类|结构类|控制类|标准件|辅料)/notes(备注)。严格返回JSON数组。"""

    answer = ""
    try:
        answer = await call_task("summary", [{"role": "user", "content": prompt}])
        import re
        match = re.search(r'\[.*\]', answer, re.DOTALL)
        if not match: return {"items": [], "error": "AI未返回有效JSON", "raw": answer[:300]}
        items = json.loads(match.group())
    except Exception as e:
        return {"items": [], "error": f"分析失败: {str(e)[:100]}", "raw": answer[:300]}

    return {"items": items, "ocr_text": ocr_text[:800], "file_name": fname}


@router.post("/api/prototype-builds/{build_id}/materials/batch", status_code=201)
def batch_create_materials(build_id: int, data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Batch save AI-generated BOM items."""
    pb = db.execute(select(PrototypeBuild).where(PrototypeBuild.id == build_id)).scalar_one_or_none()
    if not pb: raise HTTPException(404, detail="批次不存在")
    items = data.get("items", [])
    if not items: raise HTTPException(400, detail="物料列表为空")
    created = 0
    for item in items:
        db.add(MaterialCheck(
            prototype_build_id=build_id, project_id=pb.project_id,
            material_name=item.get("material_name",""), specification=item.get("specification",""),
            required_qty=item.get("required_qty",1), status="待采购",
            supplier=item.get("supplier",""), notes=item.get("notes",""),
        )); created += 1
    db.commit()
    return {"count": created, "message": f"已生成 {created} 条物料"}
