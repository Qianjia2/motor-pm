"""Knowledge Base — multi-format parsing, vector search, auto-tagging, folders."""
import os, re, json, uuid, tempfile, hashlib
from pathlib import Path as _Path
from datetime import datetime, timedelta
from io import BytesIO
import numpy as np
from backend_v2.storage import safe_load, safe_save, atomic_write

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy import select, or_, and_, delete as sql_delete, text, null
from sqlalchemy.orm import Session
from backend_v2.database import get_db
from backend_v2.auth import get_current_user, get_optional_user, verify_token, require_admin
from backend_v2.models import ProjectDocument, Project, KbDocumentShare, UserAuth
from backend_v2.permissions import check_permission
from backend_v2.ai_service import _call_llm, call_task
from backend_v2.config import settings

import asyncio

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

# ── Permission helpers ──

ACCESS_FULL = "full"
ACCESS_LIMITED = "limited"
ACCESS_NONE = "none"
PREVIEW_CHARS_LIMITED = 200

def _get_accessible_spaces(user, db) -> set:
    """Return set of space_id strings the user can access."""
    if not user or not hasattr(user, 'id'):
        return set()
    role = getattr(user, 'role', 'member')
    if role == 'admin':
        try:
            rows = db.execute(text("SELECT id FROM kb_space")).fetchall()
            return {r[0] for r in rows} | {"default"}
        except:
            return {"default"}
    try:
        rows = db.execute(text(
            "SELECT space_id FROM kb_space_member WHERE user_id=:uid"
        ), {"uid": user.id}).fetchall()
        return {r[0] for r in rows} | {"default"}
    except:
        return {"default"}

def _get_doc_access_level(doc, user, db) -> str:
    """Determine user's access level to a document: 'full', 'limited', or 'none'."""
    if not user or not hasattr(user, 'id'):
        return ACCESS_NONE
    role = getattr(user, 'role', 'member')
    if role == 'admin':
        return ACCESS_FULL

    uid = user.id

    # Owner via owner_id column
    if doc.owner_id and doc.owner_id == uid:
        return ACCESS_FULL

    # Owner via notes JSON (backward compat)
    try:
        meta = json.loads(doc.notes or "{}")
        if str(meta.get("owner", "")) == str(uid):
            return ACCESS_FULL
    except: pass

    # Check document-level shares
    share = db.execute(
        select(KbDocumentShare).where(
            KbDocumentShare.document_id == doc.id,
            KbDocumentShare.shared_with_user_id == uid
        )
    ).scalar_one_or_none()
    if share:
        return share.access_level  # "full" or "limited"

    # Space-level access (if no explicit share, fall back to space membership)
    doc_space = (doc.space_id or "").strip() or "default"
    accessible = _get_accessible_spaces(user, db)
    if doc_space in accessible:
        visibility = (doc.ext_visibility or "").strip() or "shared"
        if visibility == "private":
            return ACCESS_NONE
        return ACCESS_FULL

    return ACCESS_NONE

def _truncate_for_level(content: str, access_level: str) -> str:
    """Truncate document content based on access level."""
    if access_level == ACCESS_FULL:
        return content or ""
    if access_level == ACCESS_LIMITED:
        return (content or "")[:PREVIEW_CHARS_LIMITED]
    return ""

def _apply_permission_filter(query, user, db):
    """SQL-level filter: docs in accessible spaces OR explicitly shared."""
    if not user or not hasattr(user, 'id'):
        return query
    role = getattr(user, 'role', 'member')
    if role == 'admin':
        return query

    accessible = _get_accessible_spaces(user, db)
    shared_doc_ids = [r[0] for r in db.execute(
        select(KbDocumentShare.document_id).where(
            KbDocumentShare.shared_with_user_id == user.id
        )
    ).fetchall()]

    conditions = []
    if accessible:
        space_cond = ProjectDocument.space_id.in_(accessible)
        if "default" in accessible:
            conditions.append(or_(
                space_cond,
                ProjectDocument.space_id == null(),
                ProjectDocument.space_id == ""
            ))
        else:
            conditions.append(space_cond)
        # Exclude private docs not owned by user (handled in post-filter)
    if shared_doc_ids:
        conditions.append(ProjectDocument.id.in_(shared_doc_ids))
    if not conditions:
        return query.where(ProjectDocument.id == -1)  # no results
    return query.where(or_(*conditions))

# ── image serving ──

@router.get("/images/{doc_id}/{filename}")
def serve_image(doc_id: int, filename: str, _user=Depends(get_current_user)):
    """Serve extracted document images (auth required, traversal-safe)."""
    img_dir = os.path.realpath(os.path.join(settings.UPLOAD_DIR, "knowledge", "images", str(doc_id)))
    img_path = os.path.realpath(os.path.join(img_dir, _Path(filename).name))
    if not img_path.startswith(img_dir + os.sep):
        raise HTTPException(status_code=404, detail="图片不存在")
    if not os.path.exists(img_path):
        raise HTTPException(status_code=404, detail="图片不存在")
    from fastapi.responses import FileResponse
    return FileResponse(img_path)

DEFAULT_CATEGORIES = ["项目类","运营类","销售类","技术类","模板类","其他"]
CATEGORY_KEYWORDS = {
    "项目类": ["项目","周报","里程碑","阶段","交付","报告","计划","进度"],
    "运营类": ["运营","管理","流程","制度","规范","标准","会议","纪要","审计"],
    "销售类": ["客户","合同","报价","销售","商务","投标","订单"],
    "技术类": ["技术","设计","电磁","结构","硬件","软件","算法","测试","验证","仿真","图纸","BOM"],
    "模板类": ["模板","模版","格式","范本","样例"],
}
CATEGORIES_FILE = os.path.join(settings.UPLOAD_DIR, "..", "data", "kb_categories.json")

# ── helpers ──

def load_categories():
    try:
        with open(CATEGORIES_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("categories", DEFAULT_CATEGORIES)
    except:
        return DEFAULT_CATEGORIES[:]

def save_categories(cats):
    atomic_write(CATEGORIES_FILE, {"categories": cats})

def _call_llm_sync(messages, task="qa"):
    """Call LLM with task-aware routing. task: qa/summary/report/qa_gen/chat"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(call_task(task, messages))
    finally:
        loop.close()

# ── vector store (file-based for simplicity) ──
VECTOR_FILE = os.path.join(settings.UPLOAD_DIR, "..", "data", "kb_vectors.json")

def _load_vectors():
    try:
        with open(VECTOR_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def _save_vectors(vecs):
    atomic_write(VECTOR_FILE, vecs)

# ── image extraction ──

def _extract_images(content: bytes, filename: str, doc_id: int) -> list:
    """Extract embedded images from documents. Returns list of relative image paths."""
    import zipfile, shutil
    ext = (filename.rsplit(".", 1)[-1].lower() if "." in filename else "").strip()
    img_dir = os.path.join(settings.UPLOAD_DIR, "knowledge", "images", str(doc_id))
    os.makedirs(img_dir, exist_ok=True)
    images = []

    try:
        # DOCX: extract images from /word/media/
        if ext in ("docx",):
            with zipfile.ZipFile(BytesIO(content)) as zf:
                for name in zf.namelist():
                    if "media" in name.lower() and any(name.lower().endswith(e) for e in (".png",".jpg",".jpeg",".gif",".bmp",".webp")):
                        img_data = zf.read(name)
                        img_name = os.path.basename(name)
                        img_path = os.path.join(img_dir, img_name)
                        with open(img_path, "wb") as f: f.write(img_data)
                        images.append(f"images/{doc_id}/{img_name}")

        # PPTX: extract images from /ppt/media/
        elif ext in ("pptx",):
            with zipfile.ZipFile(BytesIO(content)) as zf:
                for name in zf.namelist():
                    if "media" in name.lower() and any(name.lower().endswith(e) for e in (".png",".jpg",".jpeg",".gif",".bmp",".webp")):
                        img_data = zf.read(name)
                        img_name = os.path.basename(name)
                        img_path = os.path.join(img_dir, img_name)
                        with open(img_path, "wb") as f: f.write(img_data)
                        images.append(f"images/{doc_id}/{img_name}")

        # PDF: try to render first page as PNG using pdf2image (if available)
        elif ext == "pdf":
            try:
                from pdf2image import convert_from_bytes
                pages = convert_from_bytes(content[:5*1024*1024], first_page=1, last_page=1, dpi=100)
                if pages:
                    thumb_path = os.path.join(img_dir, "thumb.png")
                    pages[0].save(thumb_path, "PNG")
                    images.append(f"images/{doc_id}/thumb.png")
            except ImportError:
                pass

    except Exception as e:
        pass

    return images


def _get_embedding(text: str) -> list:
    """Get embedding vector from Ollama nomic-embed-text."""
    import urllib.request
    data = json.dumps({"model": "nomic-embed-text:latest", "prompt": text[:2000]}).encode()
    req = urllib.request.Request("http://localhost:11434/api/embeddings", data=data,
        headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=30)
    return json.loads(resp.read())["embedding"]

def _cosine_sim(a, b):
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))

# ── multi-format text extractor ──

def extract_text(content: bytes, filename: str) -> str:
    """Extract text from PDF/Word/Excel/PPT/TXT/CSV with table preservation."""
    ext = (filename.rsplit(".", 1)[-1].lower() if "." in filename else "").strip()
    text = ""

    # Plain text
    if ext in ("txt","md","py","js","ts","vue","yaml","yml","json","xml","html","csv"):
        try:
            text = content.decode("utf-8")[:50000]
        except:
            try:
                text = content.decode("gbk")[:50000]
            except:
                text = f"[二进制文件: {filename}]"

    # PDF — PyMuPDF for fast text extraction (OCR only on demand)
    elif ext == "pdf":
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(stream=content, filetype="pdf")
            parts = []
            for page in doc:
                t = page.get_text()
                if t.strip():
                    parts.append(t.strip())
            text = "\n".join(parts)[:50000]
            doc.close()
            if not text.strip():
                text = f"PDF文档: {filename} (未提取到文字，可用OCR重识别)"
        except Exception as e:
            # Fallback to PyPDF2
            try:
                from PyPDF2 import PdfReader
                reader = PdfReader(BytesIO(content))
                parts = []
                for p in reader.pages:
                    t = p.extract_text()
                    if t: parts.append(t)
                text = "\n".join(parts)[:50000]
            except:
                text = f"PDF文档: {filename} (解析异常: {str(e)[:60]})"

    # Word
    elif ext in ("docx","doc"):
        try:
            from docx import Document
            doc = Document(BytesIO(content))
            parts = []
            for para in doc.paragraphs:
                if para.text.strip():
                    parts.append(para.text)
            # Extract tables too
            for table in doc.tables:
                for row in table.rows:
                    cells = [cell.text.strip() for cell in row.cells]
                    parts.append(" | ".join(cells))
            text = "\n".join(parts)[:50000]
        except:
            try:
                text = content.decode("utf-8", errors="replace")[:50000]
            except:
                text = f"[Word附件: {filename}]"

    # Excel — preserve table structure
    elif ext in ("xlsx","xls"):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
            lines = []
            for ws in wb.worksheets:
                lines.append(f"\n=== Sheet: {ws.title} ===")
                for row in ws.iter_rows(values_only=True):
                    cells = [str(c) if c is not None else "" for c in row]
                    # Skip fully empty rows
                    if any(c.strip() for c in cells):
                        lines.append(" | ".join(cells))
            text = "\n".join(lines)[:50000]
        except:
            text = f"[Excel附件: {filename}]"

    # PowerPoint
    elif ext in ("pptx","ppt"):
        try:
            from pptx import Presentation
            prs = Presentation(BytesIO(content))
            parts = []
            for i, slide in enumerate(prs.slides):
                parts.append(f"\n--- Slide {i+1} ---")
                for shape in slide.shapes:
                    if shape.has_text_frame:
                        for para in shape.text_frame.paragraphs:
                            t = para.text.strip()
                            if t: parts.append(t)
                    if shape.has_table:
                        table = shape.table
                        for row in table.rows:
                            cells = [cell.text.strip() for cell in row.cells]
                            parts.append(" | ".join(cells))
            text = "\n".join(parts)[:50000]
        except:
            text = f"[PPT附件: {filename}]"

    else:
        text = f"[附件: {filename}]"

    return text or f"[空文档: {filename}]"

# ── AI auto-tagging ──

def auto_generate_tags(text: str, filename: str) -> list:
    """Generate tags from document content using keyword matching (fast, offline)."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    tags = [ext.upper() + "文档"] if ext else []
    for cat, kws in CATEGORY_KEYWORDS.items():
        for kw in kws:
            if kw in text[:3000] and kw not in tags:
                tags.append(kw)
                if len(tags) >= 6: break
        if len(tags) >= 6: break
    if not tags:
        tags = [ext.upper() + "文档"] if ext else ["文档"]
    return tags[:6]

def ai_generate_tags(text: str, filename: str) -> dict:
    """Use LLM to generate intelligent tags and category for a document.
    Returns {'tags': [...], 'category': str, 'summary': str}
    """
    if not text or len(text.strip()) < 20:
        return {"tags": auto_generate_tags(text, filename), "category": "其他", "summary": ""}
    try:
        snippet = text[:2500]
        prompt = f"""分析以下文档内容，返回JSON格式（不要markdown代码块，直接返回JSON）:

{{
  "tags": ["标签1", "标签2", "标签3"],  // 3-5个中文标签，从内容中提炼关键主题词
  "category": "分类名称",  // 从以下选一：项目类、运营类、销售类、技术类、模板类、其他
  "summary": "一句话摘要（30字以内）"  // 用中文概括核心内容
}}

文档标题: {filename}
文档内容（前2500字）:
{snippet}"""
        rsp = _call_llm_sync([{"role": "user", "content": prompt}], task="summary")
        raw = (rsp or "").strip()
        # Parse JSON from response (handle markdown code block)
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()
        data = json.loads(raw)
        if not isinstance(data, dict):
            data = {}
        # Merge: AI tags + keyword fallback
        ai_tags = data.get("tags", [])
        kw_tags = auto_generate_tags(text, filename)
        combined = []
        for t in ai_tags + kw_tags:
            t = t.strip()[:15]
            if t and t not in combined:
                combined.append(t)
            if len(combined) >= 8:
                break
        return {
            "tags": combined[:8],
            "category": data.get("category", "其他"),
            "summary": data.get("summary", "")[:80],
        }
    except Exception:
        return {"tags": auto_generate_tags(text, filename), "category": "其他", "summary": ""}

def ai_split_document(text: str, title: str) -> list:
    """Split a long document into individual knowledge points using LLM."""
    if not text or len(text) < 500:
        return []
    try:
        # Split into chunks first (~1000 chars each), then use LLM on manageable chunks
        chunks = _chunk_text(text, 3000)
        all_points = []
        for chunk in chunks[:5]:  # Max 5 chunks to avoid excessive LLM calls
            prompt = f"""从以下文档片段中提取独立的知识点。返回JSON数组格式（不要markdown代码块，直接返回JSON数组）:

[
  {{"title": "知识点标题（15字以内）", "content": "知识点详细内容（保留原文关键信息）", "tags": ["标签1", "标签2"]}},
  ...
]

要求：
- 每个知识点应独立完整，可单独阅读
- 标题简洁，内容保留原文措辞
- 如果片段中没有明显知识点，返回空数组 []
- 最多提取5个知识点

文档标题: {title}
片段内容:
{chunk[:2500]}"""
            rsp = _call_llm_sync([{"role": "user", "content": prompt}], task="summary")
            raw = (rsp or "").strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()
            try:
                points = json.loads(raw)
                if isinstance(points, list):
                    all_points.extend(points)
            except Exception:
                continue
        return all_points[:15]
    except Exception:
        return []

def ai_extract_weekly_insights(report_text: str, project_name: str) -> list:
    """Extract lessons learned, decisions, and risks from weekly reports."""
    if not report_text or len(report_text) < 50:
        return []
    try:
        prompt = f"""从以下周报中提取可沉淀为知识的关键信息。返回JSON数组（不要markdown代码块）:

[
  {{"type": "lesson/decision/risk/achievement", "title": "标题（20字以内）", "content": "详细内容（100字以内）", "tags": ["标签1", "标签2"]}}
]

要求：
- lesson: 经验教训、踩坑记录
- decision: 关键决策及原因
- risk: 识别的风险及应对措施
- achievement: 重要成果里程碑

项目: {project_name}
周报内容:
{report_text[:2500]}"""
        rsp = _call_llm_sync([{"role": "user", "content": prompt}], task="summary")
        raw = (rsp or "").strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()
        try:
            return json.loads(raw) if isinstance(json.loads(raw), list) else []
        except Exception:
            return []
    except Exception:
        return []

def ai_recommend_for_project(project_name: str, project_type: str = "", db=None) -> list:
    """Recommend relevant knowledge items for a project context."""
    try:
        # Build a query from project context
        query = f"项目: {project_name}"
        if project_type:
            query += f" 类型: {project_type}"

        # Use vector search for semantic matching
        try:
            embedding = _get_embedding(query)
        except Exception:
            embedding = None

        results = []
        if embedding and len(embedding) > 0:
            results = _vector_search(embedding, top_k=8)

        if not results and db:
            # Fallback to keyword search
            all_docs = db.execute(
                select(ProjectDocument).where(
                    ProjectDocument.project_id == _kb_project_id(db),
                    ProjectDocument.status == "active",
                )
            ).scalars().all()
            keywords = [w for w in project_name if len(w) >= 2]
            scored = []
            for doc in all_docs:
                score = 0
                content = (doc.content or "") + (doc.name or "")
                for kw in keywords:
                    if kw in content:
                        score += 1
                if score > 0:
                    scored.append((score, doc))
            scored.sort(key=lambda x: -x[0])
            results = [
                {"doc_id": d.id, "title": d.name, "score": s / max(1, len(keywords)),
                 "snippet": (d.content or "")[:150]}
                for s, d in scored[:8]
            ]

        return results
    except Exception:
        return []

def ai_search_across_sources(query: str, db, space="default", limit=8) -> dict:
    """Unified AI search across knowledge base + BOM + product tech library."""
    results = {"kb": [], "bom": [], "product_tech": [], "summary": ""}
    try:
        # KB search
        try:
            embedding = _get_embedding(query)
        except Exception:
            embedding = None
        if embedding:
            kb_results = _vector_search(embedding, top_k=limit)
            results["kb"] = kb_results
        else:
            # Keyword fallback
            docs = db.execute(
                select(ProjectDocument).where(
                    ProjectDocument.project_id == _kb_project_id(db),
                    ProjectDocument.status == "active",
                ).limit(limit)
            ).scalars().all()
            results["kb"] = [{"doc_id": d.id, "title": d.name, "snippet": (d.content or "")[:150]} for d in docs]

        # BOM search via keyword matching
        try:
            from backend_v2.storage import safe_load
            bom_data = safe_load("bom_materials", [])
            bom_match = []
            for item in bom_data:
                text = f"{item.get('name','')} {item.get('spec','')} {item.get('brand','')} {item.get('supplier','')}"
                if any(kw in text for kw in query.split()):
                    bom_match.append({"name": item.get("name",""), "spec": item.get("spec",""), "brand": item.get("brand","")})
                    if len(bom_match) >= 5:
                        break
            results["bom"] = bom_match
        except Exception:
            pass

        # Product tech search
        try:
            from backend_v2.storage import safe_load
            pt_data = safe_load("product_tech_items", [])
            pt_match = []
            for item in pt_data:
                text = f"{item.get('name','')} {item.get('product_model','')} {item.get('product_type','')}"
                if any(kw in text for kw in query.split()):
                    pt_match.append({"name": item.get("name",""), "model": item.get("product_model",""), "type": item.get("product_type","")})
                    if len(pt_match) >= 5:
                        break
            results["product_tech"] = pt_match
        except Exception:
            pass

        # AI summary
        total_hits = len(results["kb"]) + len(results["bom"]) + len(results["product_tech"])
        if total_hits > 0:
            snippets = []
            for r in results["kb"][:3]:
                snippets.append(f"[知识库] {r.get('title','')}: {r.get('snippet','')[:100]}")
            for r in results["bom"][:2]:
                snippets.append(f"[物料] {r.get('name','')} {r.get('spec','')}")
            for r in results["product_tech"][:2]:
                snippets.append(f"[产品] {r.get('name','')} {r.get('model','')}")
            context = "\n".join(snippets)
            prompt = f"用户提问: {query}\n\n相关结果:\n{context}\n\n请用1-2句话综合回答用户的问题（50字以内），引用上述结果中的关键信息。"
            try:
                results["summary"] = _call_llm_sync([{"role": "user", "content": prompt}], task="summary") or ""
            except Exception:
                pass

        return results
    except Exception:
        return results

# ── API endpoints ──

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    category: str = Form("其他"),
    folder: str = Form("/"),
    title: str = Form(""),
    space: str = Form("default"),
    visibility: str = Form("shared"),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Upload single document with auto-parsing and tagging."""
    content = await file.read()
    fname = os.path.basename(file.filename or "unknown")

    # Dedup by filename
    user_id = str(_user.id) if hasattr(_user, 'id') else str(_user.get('id',''))
    kb_project = db.execute(select(Project).where(Project.name == "__knowledge_base__")).scalar_one_or_none()
    if kb_project:
        exist = db.execute(select(ProjectDocument).where(
            ProjectDocument.name == fname,
            ProjectDocument.project_id == kb_project.id
        )).scalar_one_or_none()
        if exist:
            return {"ok": True, "title": fname, "tags": [], "msg": "已存在，跳过", "id": exist.id, "duplicate": True}

    text = extract_text(content, fname)
    tags = auto_generate_tags(text, fname)

    # Save file
    upload_dir = os.path.join(settings.UPLOAD_DIR, "knowledge")
    os.makedirs(upload_dir, exist_ok=True)
    saved_name = f"{uuid.uuid4().hex[:8]}_{fname}"
    saved_path = os.path.join(upload_dir, saved_name)
    with open(saved_path, "wb") as f:
        f.write(content)

    # Database
    kb_project = db.execute(select(Project).where(Project.name == "__knowledge_base__")).scalar_one_or_none()
    if not kb_project:
        kb_project = Project(name="__knowledge_base__", code="__KB__", overall_status="active")
        db.add(kb_project); db.commit(); db.refresh(kb_project)

    user_id = str(_user.id) if hasattr(_user, 'id') else str(_user.get('id',''))
    doc = ProjectDocument(
        project_id=kb_project.id,
        name=title or fname,
        doc_type=category,
        content=text,
        file_path=str(_Path(saved_path).relative_to(_Path(settings.UPLOAD_DIR).parent)),
        folder=_norm_folder(folder),
        space_id=space,
        ext_visibility=visibility,
        owner_id=int(user_id) if user_id and str(user_id).isdigit() else None,
        notes=json.dumps({"folder": _norm_folder(folder), "tags": tags, "filename": fname, "space": space,
                          "owner": user_id, "visibility": visibility}),
        upload_date=datetime.now().date(),
    )
    db.add(doc); db.commit(); db.refresh(doc)

    # Auto-create folder in tree

    # Extract images
    images = _extract_images(content, fname, doc.id)
    if images:
        meta = json.loads(doc.notes or "{}")
        meta["images"] = images
        doc.notes = json.dumps(meta, ensure_ascii=False)
        db.commit()

    # Vectorize
    try:
        vecs = _load_vectors()
        vecs[str(doc.id)] = _get_embedding(text[:2000])
        _save_vectors(vecs)
    except:
        pass

    return {"ok": True, "id": doc.id, "title": doc.name, "category": category,
            "folder": _norm_folder(folder), "tags": tags, "size": len(content), "images": images}


@router.post("/upload-batch")
async def batch_upload(
    files: list[UploadFile] = File(...),
    category: str = Form("其他"),
    folder: str = Form("/"),
    space: str = Form("default"),
    visibility: str = Form("shared"),
    folder_paths: str = Form("[]"),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Upload multiple documents at once. folder_paths is a JSON array of per-file folder paths."""
    import json as _json
    per_file_folders = _json.loads(folder_paths) if folder_paths else []
    results = []
    user_id = str(_user.id) if hasattr(_user, 'id') else ''
    for i, file in enumerate(files):
        content = await file.read()
        fname = os.path.basename(file.filename or "unknown")
        text = extract_text(content, fname)
        tags = auto_generate_tags(text, fname)

        # Per-file folder path if provided, otherwise fall back to global folder
        file_folder = per_file_folders[i] if i < len(per_file_folders) and per_file_folders[i] else folder

        upload_dir = os.path.join(settings.UPLOAD_DIR, "knowledge")
        os.makedirs(upload_dir, exist_ok=True)
        saved_name = f"{uuid.uuid4().hex[:8]}_{fname}"
        saved_path = os.path.join(upload_dir, saved_name)
        with open(saved_path, "wb") as f:
            f.write(content)

        kb_project = db.execute(select(Project).where(Project.name == "__knowledge_base__")).scalar_one_or_none()
        if not kb_project:
            kb_project = Project(name="__knowledge_base__", code="__KB__", overall_status="active")
            db.add(kb_project); db.commit(); db.refresh(kb_project)

        doc = ProjectDocument(
            project_id=kb_project.id, name=fname, doc_type=category,
            content=text, file_path=str(_Path(saved_path).relative_to(_Path(settings.UPLOAD_DIR).parent)),
            folder=_norm_folder(file_folder),
            space_id=space,
            ext_visibility=visibility,
            owner_id=int(user_id) if user_id and str(user_id).isdigit() else None,
            notes=json.dumps({"folder": _norm_folder(file_folder), "tags": tags, "filename": fname, "space": space,
                              "owner": user_id, "visibility": visibility}),
            upload_date=datetime.now().date(),
        )
        db.add(doc); db.commit(); db.refresh(doc)

        try:
            vecs = _load_vectors()
            vecs[str(doc.id)] = _get_embedding(text[:2000])
            _save_vectors(vecs)
        except:
            pass

        results.append({"id": doc.id, "filename": fname, "tags": tags, "size": len(content)})

    return {"ok": True, "count": len(results), "items": results}


@router.get("/documents")
def list_documents(
    category: str = Query(None),
    folder: str = Query(None),
    search: str = Query(None),
    tag: str = Query(None),
    space: str = Query(None),
    limit: int = Query(100),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """List documents with filters — permission-aware."""
    q = select(ProjectDocument)
    if space:
        q = q.where(ProjectDocument.space_id == space)
    if category:
        q = q.where(ProjectDocument.doc_type == category)
    if search:
        q = q.where(or_(
            ProjectDocument.name.contains(search),
            ProjectDocument.content.contains(search),
        ))

    q = _apply_permission_filter(q, _user, db)
    q = q.order_by(ProjectDocument.id.desc()).limit(limit)
    docs = db.execute(q).scalars().all()
    # Post-filter: remove private docs not owned by user + shared docs user can't access
    if getattr(_user, 'role', 'member') != 'admin':
        uid = _user.id if hasattr(_user, 'id') else None
        filtered = []
        for d in docs:
            access = _get_doc_access_level(d, _user, db)
            if access == ACCESS_NONE:
                continue
            d._access_level = access
            filtered.append(d)
        docs = filtered
    else:
        for d in docs:
            d._access_level = ACCESS_FULL

    all_cats = load_categories()
    results = []
    # Map project docs to their project names (for KB badges / delete hints)
    pid_map = {}
    for pid in {d.project_id for d in docs if d.project_id}:
        proj = db.get(Project, pid)
        if proj:
            pid_map[pid] = proj.name
    for d in docs:
        meta = {}
        try:
            meta = json.loads(d.notes or "{}")
        except:
            meta = {"folder": "/", "tags": [], "filename": d.name}

        # category fallback
        auto_cat = d.doc_type if d.doc_type in all_cats else "其他"
        if auto_cat == "其他":
            text_snippet = (d.name or "") + " " + (d.content or "")[:200]
            for cat, keywords in CATEGORY_KEYWORDS.items():
                if any(kw in text_snippet for kw in keywords):
                    auto_cat = cat; break

        # Filter by folder
        # Folder priority: native column > notes JSON > default "/"
        doc_folder = d.folder or meta.get("folder", "/")
        if not doc_folder or doc_folder == "":
            doc_folder = "/"
        # Auto-organize project documents under project name folder
        if d.project_id and doc_folder == "/":
            from backend_v2.models import Project as _P
            proj = db.get(_P, d.project_id)
            if proj:
                doc_folder = (proj.name or f"项目{d.project_id}")
        # Strip network share prefix (same as tree builder)
        doc_folder = doc_folder.replace("\\", "/")
        import re as _re
        m = _re.match(r'^(?://)?([^/]+)/([^/]+)/(.+)$', doc_folder.strip("/"))
        if m and _re.match(r'^\d+\.\d+\.\d+\.\d+$', m.group(1)):
            doc_folder = "/" + m.group(3)
        # Normalize for comparison
        doc_path = doc_folder.strip("/")
        filter_path = (folder or "").strip("/")
        if folder and doc_path != filter_path:
            continue

        # Filter by tag
        doc_tags = meta.get("tags", [])
        if tag and tag not in doc_tags:
            continue

        access = getattr(d, '_access_level', ACCESS_FULL)
        results.append({
            "id": d.id, "title": d.name, "doc_type": d.doc_type,
            "category": auto_cat,
            "folder": "/" + doc_path if doc_path else "/", "tags": doc_tags,
            "images": meta.get("images", []),
            "filename": meta.get("filename", d.name),
            "content": _truncate_for_level(d.content or "", access),
            "access_level": access,
            "owner_id": d.owner_id,
            "created_at": d.upload_date.isoformat() if d.upload_date else None,
            "file_path": d.file_path,
            "project_id": d.project_id,
            "project_name": pid_map.get(d.project_id),
        })
    return results


@router.get("/folders")
def list_folders(
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Get all folder paths from knowledge docs."""
    q = select(ProjectDocument).order_by(ProjectDocument.id.desc()).limit(500)
    docs = db.execute(q).scalars().all()
    folders = set()
    for d in docs:
        f = d.folder  # prefer native column
        if not f:
            try:
                meta = json.loads(d.notes or "{}")
                f = meta.get("folder", "/")
            except:
                f = "/"
        if not f or f == "/":
            if d.project_id:
                from backend_v2.models import Project as _P
                proj = db.get(_P, d.project_id)
                if proj:
                    f = (proj.name or f"项目{d.project_id}")
        f = (f or "/").strip("/")
        folders.add("/" + f if f else "/")
    result = sorted(folders)
    if "/" not in result:
        result.insert(0, "/")
    return result


@router.get("/tags")
def list_tags(
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Get all tags from knowledge docs (aggregated)."""
    q = select(ProjectDocument).order_by(ProjectDocument.id.desc()).limit(500)
    docs = db.execute(q).scalars().all()
    tag_counts = {}
    for d in docs:
        try:
            meta = json.loads(d.notes or "{}")
            for t in meta.get("tags", []):
                tag_counts[t] = tag_counts.get(t, 0) + 1
        except:
            pass
    return [{"tag": k, "count": v} for k, v in sorted(tag_counts.items(), key=lambda x: -x[1])]


@router.post("/documents/{doc_id}/tags")
def add_doc_tag(doc_id: int, data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Add or update tags for a document."""
    doc = db.execute(select(ProjectDocument).where(ProjectDocument.id == doc_id)).scalar_one_or_none()
    if not doc: raise HTTPException(status_code=404, detail="文档不存在")
    meta = {}
    try: meta = json.loads(doc.notes or "{}")
    except: pass
    tags = data.get("tags", meta.get("tags", []))
    meta["tags"] = tags
    doc.notes = json.dumps(meta, ensure_ascii=False)
    db.commit()
    return {"id": doc_id, "tags": tags}


@router.put("/documents/{doc_id}")
def update_document(doc_id: int, data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Update document title, category, folder, or tags."""
    doc = db.execute(select(ProjectDocument).where(ProjectDocument.id == doc_id)).scalar_one_or_none()
    if not doc: raise HTTPException(status_code=404, detail="文档不存在")
    meta = {}
    try: meta = json.loads(doc.notes or "{}")
    except: pass
    if "title" in data: doc.name = data["title"]
    if "category" in data: doc.doc_type = data["category"]
    if "folder" in data: meta["folder"] = data["folder"]
    if "tags" in data: meta["tags"] = data["tags"]
    if "content" in data: doc.content = data["content"]
    doc.notes = json.dumps(meta, ensure_ascii=False)
    db.commit()
    return {"ok": True}


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Delete a knowledge document and its vectors. Project docs: admin only."""
    doc = db.execute(select(ProjectDocument).where(ProjectDocument.id == doc_id)).scalar_one_or_none()
    if not doc: raise HTTPException(status_code=404, detail="文档不存在")
    # Project docs deletable only by admin / kb_admin / users with knowledge delete permission
    can_manage = (getattr(_user, 'role', 'member') == 'admin'
                  or getattr(_user, 'kb_admin', False)
                  or check_permission(_user, 'knowledge', 'delete'))
    kb_proj = db.execute(select(Project).where(Project.name == "__knowledge_base__")).scalar_one_or_none()
    if not can_manage and kb_proj and doc.project_id != kb_proj.id:
        raise HTTPException(status_code=400, detail="不能通过知识库删除项目文档，请在项目详情页操作")
    if doc.file_path:
        from pathlib import Path as _Path
        upload_root = _Path(settings.UPLOAD_DIR).parent
        fp = str(upload_root / doc.file_path.replace("\\", "/"))
        if not os.path.exists(fp):
            fp = doc.file_path  # try absolute path
        if os.path.exists(fp):
            try: os.remove(fp)
            except: pass
    db.delete(doc); db.commit()
    # Remove vector
    try:
        vecs = _load_vectors()
        vecs.pop(str(doc_id), None)
        _save_vectors(vecs)
    except: pass
    return {"ok": True}


@router.post("/documents/batch-delete")
def batch_delete_documents(data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Batch delete documents. Project docs: admin only."""
    doc_ids = data.get("ids", [])
    if not doc_ids: raise HTTPException(400, detail="请提供要删除的文档ID列表")
    kb_proj = db.execute(select(Project).where(Project.name == "__knowledge_base__")).scalar_one_or_none()
    kb_proj_id = kb_proj.id if kb_proj else None
    docs = db.execute(select(ProjectDocument).where(ProjectDocument.id.in_(doc_ids))).scalars().all()
    # Users without kb_admin / knowledge delete permission: only KB documents
    can_manage = (getattr(_user, 'role', 'member') == 'admin'
                  or getattr(_user, 'kb_admin', False)
                  or check_permission(_user, 'knowledge', 'delete'))
    skipped = 0
    kb_docs = []
    for d in docs:
        if not can_manage and kb_proj_id and d.project_id != kb_proj_id:
            skipped += 1
        else:
            kb_docs.append(d)
    docs = kb_docs
    vecs = _load_vectors()
    for doc in docs:
        if doc.file_path:
            from pathlib import Path as _Path
            upload_root = _Path(settings.UPLOAD_DIR).parent
            fp = str(upload_root / doc.file_path.replace("\\", "/"))
            if not os.path.exists(fp):
                fp = doc.file_path
            if os.path.exists(fp):
                try: os.remove(fp)
                except: pass
        vecs.pop(str(doc.id), None)
        db.delete(doc)
    db.commit()
    _save_vectors(vecs)
    return {"deleted": len(docs), "skipped": skipped}


@router.post("/vector-search")
def vector_search(data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Semantic vector search over knowledge base."""
    question = data.get("question", "")
    top_k = data.get("top_k", 5)
    if not question: return {"results": [], "summary": "请输入问题"}

    # Get embedding for query
    try:
        q_vec = _get_embedding(question[:2000])
    except Exception as e:
        return {"results": [], "summary": f"向量模型不可用: {str(e)[:100]}"}

    # Compare with all stored vectors
    vecs = _load_vectors()
    scores = []
    for doc_id, v in vecs.items():
        try:
            scores.append((int(doc_id), _cosine_sim(q_vec, v)))
        except:
            pass
    scores.sort(key=lambda x: -x[1])
    top = scores[:top_k]

    # Get document details
    results = []
    for doc_id, score in top:
        doc = db.execute(select(ProjectDocument).where(ProjectDocument.id == doc_id)).scalar_one_or_none()
        if doc:
            meta = {}
            try: meta = json.loads(doc.notes or "{}")
            except: pass
            results.append({
                "id": doc.id, "title": doc.name, "score": round(score, 3),
                "content": (doc.content or "")[:400],
                "tags": meta.get("tags", []),
                "folder": meta.get("folder", "/"),
            })

    # Generate AI summary of results
    summary = ""
    if results:
        ctx = "\n".join([f"{i+1}.《{r['title']}》(相关度:{r['score']})\n{r['content'][:200]}" for i, r in enumerate(results)])
        prompt = f"""你是知识库检索助手。根据用户问题和搜索结果，给出1-2句话的总结和建议。

用户问题: {question}

搜索结果:
{ctx}

回复格式: 🔍 找到N篇相关文档。关键信息: ...（1-2句话）"""
        try:
            summary = _call_llm_sync([{"role":"user","content":prompt}])
        except:
            summary = f"找到{len(results)}篇相关文档"

    return {"results": results, "summary": summary, "total": len(results)}


@router.post("/ai-search")
def ai_search(data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Full-context AI search (keyword + vector hybrid)."""
    question = data.get("question", "")
    if not question: return {"results": [], "summary": "请输入问题"}

    docs = db.execute(select(ProjectDocument).order_by(ProjectDocument.id.desc()).limit(50)).scalars().all()
    if not docs: return {"results": [], "summary": "知识库中暂无文档"}

    # Build context
    doc_list = []
    for i, d in enumerate(docs):
        meta = {}
        try: meta = json.loads(d.notes or "{}")
        except: pass
        doc_list.append({
            "index": i+1, "id": d.id, "title": d.name or "无标题",
            "type": d.doc_type or "通用", "tags": meta.get("tags", []),
            "folder": meta.get("folder", "/"),
            "content": (d.content or "")[:600],
        })

    context_str = "\n\n---\n\n".join([
        f"文档{d['index']} [{d['type']}]《{d['title']}》(标签:{','.join(d['tags'][:5])})\n{d['content']}"
        for d in doc_list
    ])

    # Try vector search first
    vec_results = []
    try:
        q_vec = _get_embedding(question[:2000])
        vecs = _load_vectors()
        scores = []
        for did, v in vecs.items():
            try: scores.append((int(did), _cosine_sim(q_vec, v)))
            except: pass
        scores.sort(key=lambda x: -x[1])
        for did, score in scores[:5]:
            for d in doc_list:
                if d["id"] == did: vec_results.append(f"[VS:{score:.2f}] {d['title']}")
    except:
        pass

    prompt = f"""你是电机行业技术知识库检索专家。

=== 知识库文档 ===
{context_str}

{"=== 向量检索预筛选 ===" if vec_results else ""}
{chr(10).join(vec_results) if vec_results else ""}

=== 用户查询 ===
{question}

=== 任务 ===
1. 理解用户技术需求
2. 按相关度列出最匹配的文档
3. 回复格式:

{chr(10).join(["🔍 检索结果","（总结）","","📄 匹配文档：","1. **《文档标题》** [类型] — 匹配原因","...（最多5个）","","💡 建议（如有）"])}"""

    try:
        reply = _call_llm_sync([{"role":"system","content":"你是电机技术知识库专家。"},{"role":"user","content":prompt}])
        return {"summary": reply, "question": question, "total_docs": len(docs)}
    except Exception as e:
        return {"summary": f"[AI检索暂不可用: {str(e)[:100]}]", "question": question}


@router.post("/ask-table")
def ask_table(data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Ask questions about tables within documents."""
    question = data.get("question", "")
    doc_ids = data.get("doc_ids", [])
    if not question: return {"answer": "请输入问题"}

    # Get specific docs or all
    if doc_ids:
        docs = db.execute(select(ProjectDocument).where(ProjectDocument.id.in_(doc_ids))).scalars().all()
    else:
        docs = db.execute(select(ProjectDocument).order_by(ProjectDocument.id.desc()).limit(30)).scalars().all()

    # Extract table-like content (lines with | separators)
    tables = []
    for d in docs:
        lines = (d.content or "").split("\n")
        table_lines = [l for l in lines if "|" in l and len(l.split("|")) >= 3]
        if table_lines:
            tables.append(f"=== {d.name} ===\n" + "\n".join(table_lines[:30]))

    if not tables:
        return {"answer": "文档中未找到表格数据"}

    table_text = "\n\n".join(tables)[:8000]
    prompt = f"""你是表格数据分析助手。根据以下文档中的表格数据回答问题。

=== 表格数据 ===
{table_text}

=== 问题 ===
{question}

请基于表格数据给出准确回答。如果数据不足，说明缺少哪些信息。"""

    try:
        answer = _call_llm_sync([{"role":"system","content":"你是表格分析专家。"},{"role":"user","content":prompt}])
        return {"answer": answer}
    except Exception as e:
        return {"answer": f"[表格问答暂不可用: {str(e)[:100]}]"}


# ── category management ──

@router.get("/categories")
def get_categories(_user=Depends(get_current_user)):
    return load_categories()

@router.post("/categories")
def add_category(data: dict, _user=Depends(get_current_user)):
    name = data.get("name","").strip()
    if not name: raise HTTPException(400, detail="名称不能为空")
    cats = load_categories()
    if name in cats: raise HTTPException(400, detail="分类已存在")
    cats.append(name); save_categories(cats)
    return cats

@router.delete("/categories/{name}")
def delete_category(name: str, _user=Depends(get_current_user)):
    cats = load_categories()
    if name not in cats: raise HTTPException(404, detail="分类不存在")
    cats.remove(name); save_categories(cats)
    return cats

@router.put("/categories/order")
def reorder_categories(data: dict, _user=Depends(get_current_user)):
    cats = data.get("categories", [])
    if not isinstance(cats, list) or not cats:
        raise HTTPException(400, detail="无效的分类列表")
    save_categories(cats)
    return cats


# ── re-vectorize all ──

@router.post("/re-vectorize")
def re_vectorize_all(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Re-generate vectors for all documents."""
    docs = db.execute(select(ProjectDocument)).scalars().all()
    vecs = {}
    for d in docs:
        try:
            vecs[str(d.id)] = _get_embedding((d.content or "")[:2000])
        except Exception as e:
            print(f"Vectorize error for doc {d.id}: {e}")
    _save_vectors(vecs)
    return {"ok": True, "count": len(vecs)}


# ── Smart Summary ──

@router.post("/summarize")
def smart_summary(data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Generate intelligent summary for a document or set of documents.
    data: {doc_ids: [], mode: str, requirement: str}"""
    doc_ids = data.get("doc_ids", [])
    mode = data.get("mode", "brief")  # brief / detailed / keypoints
    requirement = data.get("requirement", "").strip()

    if doc_ids:
        docs = db.execute(select(ProjectDocument).where(ProjectDocument.id.in_(doc_ids))).scalars().all()
    else:
        docs = db.execute(select(ProjectDocument).order_by(ProjectDocument.id.desc()).limit(20)).scalars().all()

    if not docs:
        return {"summary": "无可用文档"}

    content_parts = []
    for d in docs:
        content_parts.append(f"### {d.name}\n{(d.content or '')[:2000]}")

    full_text = "\n\n".join(content_parts)[:15000]

    mode_prompts = {
        "brief": "生成一份简洁摘要（150字以内），概括核心内容",
        "detailed": "生成一份详细摘要（500字以内），包含关键数据、技术参数和结论",
        "keypoints": "提取5-10个关键要点，以编号列表形式呈现，每个要点20字以内"
    }
    base_instruction = mode_prompts.get(mode, mode_prompts['brief'])

    if requirement:
        prompt = f"""你是文档分析专家。请严格按照用户要求处理以下文档内容。

【用户要求】{requirement}

=== 文档内容 ===
{full_text}"""
    else:
        prompt = f"""你是文档分析专家。基于以下文档内容，{base_instruction}

=== 文档内容 ===
{full_text}"""

    try:
        summary = _call_llm_sync([{"role":"system","content":"你是专业文档分析专家。回复简洁准确。"},{"role":"user","content":prompt}])
        return {"summary": summary, "doc_count": len(docs)}
    except Exception as e:
        return {"summary": f"[摘要生成暂不可用: {str(e)[:100]}]", "doc_count": len(docs)}


# ── Enhanced Q&A with source citations ──

def _chunk_text(text: str, chunk_size: int = 1200) -> list:
    """Split text into overlapping chunks (50% overlap) for better retrieval."""
    paragraphs = text.split("\n")
    # First try to keep paragraphs intact
    chunks = []
    current = ""
    for p in paragraphs:
        p = p.strip()
        if not p: continue
        if len(current) + len(p) < chunk_size:
            current += p + "\n"
        else:
            if current: chunks.append(current.strip())
            current = p + "\n"
    if current: chunks.append(current.strip())
    if not chunks: return [text[:chunk_size]]
    # Add overlapping chunks for better context
    overlapped = []
    for i, c in enumerate(chunks):
        overlapped.append(c)
        if i > 0:
            # Create overlap from previous + current
            prev_end = chunks[i-1][-200:] if len(chunks[i-1]) > 200 else chunks[i-1]
            overlapped.append((prev_end + "\n" + c)[:chunk_size])
    return overlapped


def _find_relevant_chunks(question: str, space: str, db, top_k: int = 6,
                          folders: list = None, doc_ids: list = None) -> list:
    """Find relevant text chunks for a question, filtered by space + optional whitelist."""
    from sqlalchemy import select as _sel
    q = _sel(ProjectDocument).order_by(ProjectDocument.id.desc()).limit(500)
    all_docs = db.execute(q).scalars().all()

    # Filter by space, then by whitelist
    docs = []
    for d in all_docs:
        meta = {}
        try: meta = json.loads(d.notes or "{}")
        except: pass
        if meta.get("space", "default") != space:
            continue
        # Folder whitelist: doc's folder must match or be under a whitelisted folder
        doc_folder = meta.get("folder", "/")
        if folders and len(folders) > 0:
            matched = False
            for f in folders:
                if doc_folder == f or doc_folder.startswith(f + "/"):
                    matched = True
                    break
            if not matched: continue
        # Document whitelist: doc must be in the list
        if doc_ids and len(doc_ids) > 0:
            if str(d.id) not in [str(x) for x in doc_ids]:
                continue
        docs.append(d)

    if not docs:
        return []

    # Helper to clean garbled PDF text (single-char-per-line artifacts)
    import re as _re
    def _clean_text(t):
        # Collapse single-char-per-line patterns (common in poorly formatted PDFs)
        lines = t.split('\n')
        cleaned = []
        buf = ''
        for line in lines:
            stripped = line.strip()
            # If line is a single CJK char, buffer it
            if len(stripped) == 1 and '一' <= stripped <= '鿿':
                buf += stripped
            else:
                if buf:
                    cleaned.append(buf)
                    buf = ''
                if stripped:
                    cleaned.append(stripped)
        if buf: cleaned.append(buf)
        result = ' '.join(cleaned)
        # Normalize whitespace
        result = _re.sub(r'\s+', ' ', result)
        return result.strip()

    # Hybrid: keyword first (better for factual queries), then vector to supplement
    chunks = []
    chunk_ids = set()

    # 1. Keyword search (prioritized — better for factual/entity queries in Chinese)
    kdocs = _keyword_search(question, docs, top_k + 4)
    for d in kdocs:
        if d.content and d.id not in chunk_ids:
            cleaned = _clean_text(d.content[:3000])
            if len(cleaned) > 30:  # Skip near-empty chunks
                chunks.append(cleaned)
                chunk_ids.add(d.id)
        if len(chunks) >= top_k: break

    # 2. Vector search (semantic supplement)
    try:
        q_vec = _get_embedding(question[:2000])
        vecs = _load_vectors()
        scores = []
        for did, v in vecs.items():
            try: scores.append((int(did), _cosine_sim(q_vec, v)))
            except: pass
        scores.sort(key=lambda x: -x[1])
        for did, score in scores[:top_k]:
            if score < 0.25: continue
            if did in chunk_ids: continue
            for d in docs:
                if d.id == did and d.content and d.id not in chunk_ids:
                    cleaned = _clean_text(d.content[:3000])
                    if len(cleaned) > 30:
                        chunks.append(cleaned)
                        chunk_ids.add(d.id)
                        break
            if len(chunks) >= top_k + 2: break
    except:
        pass

    return chunks[:top_k + 2]


def _keyword_search(question: str, docs, top_k: int = 10) -> list:
    """Improved Chinese keyword search with stopword filtering and title bonus."""
    import re
    # Chinese stopwords
    stopwords = {'的','了','在','是','我','有','和','就','不','人','都','一','一个',
                 '上','也','很','到','说','要','去','你','会','着','没有','看','好','自己',
                 '这','他','她','它','们','那','什么','怎么','哪','为什么','如何','吗','呢','吧','啊',
                 '可以','还是','只是','如果','因为','所以','但是','虽然','不过','然后','已经',
                 '这个','那个','这些','那些','什么','怎么','怎样','哪里','谁','多少','几',
                 '里面','外面','前面','后面','上面','下面','旁边','中间','之间',
                 '吗','嗯','呀','哦','哈','呵呵'}
    # Extract meaningful keywords
    keywords = []
    # CJK bigrams (skipping stopwords)
    cjk = re.findall(r'[一-鿿]+', question)
    for seg in cjk:
        for i in range(len(seg)):
            if i < len(seg) - 1:
                bigram = seg[i:i+2]
                if bigram not in stopwords and all(c not in stopwords for c in bigram):
                    keywords.append(bigram)
            # Always add single chars (important for Chinese)
            ch = seg[i]
            if ch not in stopwords:
                keywords.append(ch)
    # Add English/numbers
    en = re.findall(r'[a-zA-Z0-9]+', question)
    keywords.extend([k.lower() for k in en if len(k) >= 2])

    if not keywords: return docs[:top_k]

    # Deduplicate and count frequency
    from collections import Counter
    kw_counter = Counter(keywords)
    # Boost rare but specific keywords
    keywords = list(kw_counter.keys())

    scored = []
    for d in docs:
        content = ((d.name or "") + " " + (d.content or "")[:3000]).lower()
        name_lower = (d.name or "").lower()
        score = 0
        for kw in keywords:
            cnt = content.count(kw.lower())
            # Title match bonus (3x)
            if kw.lower() in name_lower:
                cnt += 3
            score += cnt
        if score > 0: scored.append((d, score))
    scored.sort(key=lambda x: -x[1])
    return [d for d, _ in scored[:top_k]]


@router.post("/qa")
def enhanced_qa(data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Enhanced Q&A with hybrid retrieval, multiple modes, source citations."""
    question = data.get("question", "")
    if not question:
        return {"answer": "请输入问题", "sources": []}

    mode = data.get("mode", "kb")
    doc_ids = data.get("doc_ids", [])
    session_id = data.get("session_id", "")

    # ── Document Retrieval ──
    if mode == "single" and doc_ids:
        docs = db.execute(select(ProjectDocument).where(ProjectDocument.id == doc_ids[0])).scalars().all()
    elif mode == "selected" and doc_ids:
        docs = db.execute(select(ProjectDocument).where(ProjectDocument.id.in_(doc_ids))).scalars().all()
    else:
        # Hybrid: vector search + keyword search
        all_docs = list(db.execute(select(ProjectDocument).order_by(ProjectDocument.id.desc()).limit(200)).scalars().all())
        if not all_docs:
            return {"answer": "知识库中暂无文档，请先上传文档", "sources": [], "mode": mode}

        vec_docs = []; kw_docs = []; score_map = {}

        # Strategy 1: Vector search
        try:
            q_vec = _get_embedding(question[:2000])
            vecs = _load_vectors()
            scores = []
            for did, v in vecs.items():
                try: scores.append((int(did), _cosine_sim(q_vec, v)))
                except: pass
            scores.sort(key=lambda x: -x[1])
            # Filter: only keep docs with similarity > 0.3
            good_scores = [(did, s) for did, s in scores if s > 0.3]
            if good_scores:
                top_ids = [s[0] for s in good_scores[:10]]
                for s in good_scores: score_map[s[0]] = s[1]
                vec_docs = [d for d in all_docs if d.id in top_ids]
        except:
            pass

        # Strategy 2: Keyword search (always as supplement)
        kw_docs = _keyword_search(question, all_docs, top_k=10)

        # Merge: vector first, then keyword (deduplicated)
        seen = set()
        docs = []
        for d in vec_docs:
            if d.id not in seen: docs.append(d); seen.add(d.id)
        for d in kw_docs:
            if d.id not in seen: docs.append(d); seen.add(d.id)

        # If still nothing, fall back to recent docs
        if not docs:
            docs = all_docs[:10]

    if not docs:
        return {"answer": "知识库中暂无相关文档，请先上传一些文档到知识库", "sources": [], "mode": mode}

    # ── Build Rich Context ──
    context_parts = []
    all_sources = []
    for d in docs[:15]:
        content = (d.content or "")
        # For single/selected mode, include more content
        max_content = 4000 if mode in ("single", "selected") else 1500
        snippet = content[:max_content]
        # Get tags
        meta = {}
        try: meta = json.loads(d.notes or "{}")
        except: pass
        tags_str = " | 标签: " + ", ".join(meta.get("tags", [])[:5]) if meta.get("tags") else ""
        context_parts.append(f"### 《{d.name}》[{d.doc_type or '通用'}]{tags_str}\n{snippet}")
        all_sources.append({"id": d.id, "title": d.name, "snippet": snippet[:300]})

    context = "\n\n---\n\n".join(context_parts)[:15000]

    # ── Conversation History ──
    history = ""
    if session_id:
        try:
            session_file = os.path.join(settings.UPLOAD_DIR, "..", "data", f"kb_session_{session_id}.json")
            if os.path.exists(session_file):
                with open(session_file, "r", encoding="utf-8") as f:
                    hist = json.load(f)
                    recent = hist[-4:]
                    history = "\n".join([f"用户: {h['q']}\n助手: {h['a'][:200]}" for h in recent])
        except: pass

    # ── Prompt ──
    prompt = f"""你是知识库智能问答助手。以下是从知识库检索到的文档内容，请仔细阅读后回答用户问题。

## 回答原则
1. **优先从文档中找答案** — 只要文档中有相关信息，就基于文档回答
2. **不要轻易说"未找到"** — 即使不是完全匹配，也尝试提供相关信息和关联内容
3. **具体引用** — 提及文档名称和具体段落
4. **如果确实完全无关** — 说明已搜索但未找到，建议用户提供更多线索或上传相关文档

{chr(10)+'## 对话历史'+chr(10)+history+chr(10) if history else ''}
## 检索到的文档 ({len(docs)}篇)
{context}

## 用户问题
{question}

请用中文回答。格式：
**回答**：（内容）
**参考文档**：
- 《文档名》— 相关段落摘要"""

    messages = [
        {"role": "system", "content": "你是知识库问答专家。优先从提供的文档中找答案，不要轻易说找不到。即使非完全匹配也提供相关信息。使用中文，回答专业详细。"},
        {"role": "user", "content": prompt},
    ]

    try:
        answer = _call_llm_sync(messages)
    except Exception as e:
        answer = f"[AI问答暂不可用: {str(e)[:100]}]"

    # ── Sources ──
    sources = []
    seen_ids = set()
    for s in all_sources:
        if s["id"] not in seen_ids and s["title"] in answer:
            seen_ids.add(s["id"])
            sources.append(s)
    if not sources:
        sources = all_sources[:5]

    # ── Save session ──
    if session_id:
        try:
            session_file = os.path.join(settings.UPLOAD_DIR, "..", "data", f"kb_session_{session_id}.json")
            os.makedirs(os.path.dirname(session_file), exist_ok=True)
            hist = []
            if os.path.exists(session_file):
                with open(session_file, "r", encoding="utf-8") as f:
                    hist = json.load(f)
            hist.append({"q": question, "a": answer[:1000], "ts": datetime.utcnow().isoformat()})
            if len(hist) > 20: hist = hist[-20:]
            atomic_write(session_file, hist)
        except: pass

    return {"answer": answer, "sources": sources, "mode": mode, "doc_count": len(docs),
            "session_id": session_id}


# ── Session management ──

@router.get("/sessions")
def list_sessions(_user=Depends(get_current_user)):
    """List saved Q&A sessions."""
    sess_dir = os.path.join(settings.UPLOAD_DIR, "..", "data")
    sessions = []
    for fname in os.listdir(sess_dir):
        if fname.startswith("kb_session_") and fname.endswith(".json"):
            sid = fname.replace("kb_session_", "").replace(".json", "")
            try:
                with open(os.path.join(sess_dir, fname), "r", encoding="utf-8") as f:
                    hist = json.load(f)
                    title = hist[0]["q"][:40] if hist else "空会话"
                    sessions.append({"id": sid, "title": title, "count": len(hist),
                                     "updated": hist[-1]["ts"] if hist else None})
            except:
                pass
    return sorted(sessions, key=lambda x: x.get("updated", ""), reverse=True)


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, _user=Depends(get_current_user)):
    """Delete a Q&A session."""
    session_file = os.path.join(settings.UPLOAD_DIR, "..", "data", f"kb_session_{session_id}.json")
    if os.path.exists(session_file):
        os.remove(session_file)
    return {"ok": True}


# ── Prompt configuration ──

PROMPT_CONFIG_FILE = os.path.join(settings.UPLOAD_DIR, "..", "kb_prompts.json")

def _load_prompt_config():
    defaults = {
        "system_prompt": "你是知识库问答专家。严格基于文档回答，不编造。使用中文。",
        "qa_template": "基于文档回答问题。引用来源。",
        "summary_mode": "brief",
        "temperature": 0.3,
        "max_context_chars": 12000,
        "top_k_docs": 8,
        "max_file_size_mb": 50,
        "public_url": "",
        "auto_import_folders": {
            "project": "/项目导入",
            "url": "/",
            "upload": "/",
        },
    }
    try:
        with open(PROMPT_CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            defaults.update(cfg)
    except:
        pass
    return defaults


@router.get("/config")
def get_config(_user=Depends(get_current_user)):
    return _load_prompt_config()


@router.put("/config")
def update_config(data: dict, _user=Depends(get_current_user)):
    current = _load_prompt_config()
    for k in ("system_prompt","qa_template","summary_mode","temperature","max_context_chars","top_k_docs","max_file_size_mb","public_url","auto_import_folders"):
        if k in data: current[k] = data[k]
    atomic_write(PROMPT_CONFIG_FILE, current)
    return current

# ── Share Links (public Q&A for customers) ──
SHARE_FILE = os.path.join(settings.UPLOAD_DIR, "..", "data", "kb_shares.json")

def _load_shares():
    return safe_load(SHARE_FILE, [])

def _save_shares(shares):
    safe_save(SHARE_FILE, shares)

@router.get("/share-links")
def list_share_links(_user=Depends(get_current_user)):
    return _load_shares()

@router.post("/share-links")
def create_share_link(data: dict, _user=Depends(get_current_user)):
    """Create a new share link. data: {name, space, welcome, folders, doc_ids, password}"""
    import uuid, secrets
    shares = _load_shares()
    share = {
        "id": str(uuid.uuid4())[:8],
        "token": secrets.token_urlsafe(16),
        "name": data.get("name", "客户问答"),
        "space": data.get("space", "default"),
        "welcome": data.get("welcome", "您好！我是智能问答助手，可以回答产品相关问题。"),
        "folders": data.get("folders", []),    # whitelist: only these folders
        "doc_ids": data.get("doc_ids", []),    # whitelist: only these documents
        "password": data.get("password", ""),  # optional access password
        "enabled": True,
        "created_at": datetime.utcnow().isoformat(),
        "question_count": 0,
    }
    shares.append(share)
    _save_shares(shares)
    return share

@router.put("/share-links/{share_id}")
def update_share_link(share_id: str, data: dict, _user=Depends(get_current_user)):
    shares = _load_shares()
    for s in shares:
        if s["id"] == share_id:
            for k in ("name","welcome","space","enabled","folders","doc_ids","password"):
                if k in data: s[k] = data[k]
            _save_shares(shares)
            return s
    raise HTTPException(404, detail="分享链接不存在")

@router.delete("/share-links/{share_id}")
def delete_share_link(share_id: str, _user=Depends(get_current_user)):
    shares = _load_shares()
    _save_shares([s for s in shares if s["id"] != share_id])
    return {"ok": True}


# ── Auto-generate QA pairs from documents ──

QA_FILE = os.path.join(settings.UPLOAD_DIR, "..", "data", "kb_qa_pairs.json")

@router.post("/generate-qa")
def generate_qa(data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Auto-generate Q&A pairs from documents for training/robot use.
    data: {doc_ids: [], count: 10}"""
    doc_ids = data.get("doc_ids", [])
    count = data.get("count", 10)

    if doc_ids:
        docs = db.execute(select(ProjectDocument).where(ProjectDocument.id.in_(doc_ids))).scalars().all()
    else:
        docs = db.execute(select(ProjectDocument).order_by(ProjectDocument.id.desc()).limit(10)).scalars().all()

    if not docs:
        return {"qa_pairs": [], "message": "无可用文档"}

    # Build document context
    parts = []
    for d in docs:
        parts.append(f"### 《{d.name}》\n{(d.content or '')[:1500]}")
    full_text = "\n\n".join(parts)[:10000]

    prompt = f"""你是知识工程专家。根据以下文档内容，生成{count}个高质量问答对（QA pairs）。
要求：
1. 问题覆盖事实性、推理性、总结性问题，涵盖不同难度
2. 答案简洁准确（30-80字），必须基于文档内容
3. 每个QA对标注来源文档

返回JSON数组格式（只返回JSON，不要其他文字）：
[{{"q":"问题","a":"答案","source":"文档名","type":"事实/推理/总结","difficulty":"简单/中等/困难"}}, ...]

=== 文档内容 ===
{full_text}"""

    try:
        reply = _call_llm_sync([{"role":"system","content":"你是知识工程专家。只返回JSON数组。"},{"role":"user","content":prompt}])
        # Extract JSON
        import re
        match = re.search(r'\[.*\]', reply, re.DOTALL)
        if match:
            qa_pairs = json.loads(match.group())
            # Save to file
            existing = []
            try:
                with open(QA_FILE, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except: pass
            for qa in qa_pairs:
                qa["id"] = str(uuid.uuid4().hex[:8])
                qa["created_at"] = datetime.utcnow().isoformat()
            existing.extend(qa_pairs)
            os.makedirs(os.path.dirname(QA_FILE), exist_ok=True)
            atomic_write(QA_FILE, existing)
            return {"qa_pairs": qa_pairs, "total_saved": len(existing)}
    except Exception as e:
        pass

    return {"qa_pairs": [], "message": "生成失败，请重试"}


@router.get("/qa-pairs")
def list_qa_pairs(_user=Depends(get_current_user)):
    """List all generated QA pairs."""
    try:
        with open(QA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


@router.delete("/qa-pairs")
def clear_qa_pairs(_user=Depends(get_current_user)):
    """Clear all QA pairs."""
    atomic_write(QA_FILE, [])
    return {"ok": True}


# ── Knowledge Report ──

REPORT_FILE = os.path.join(settings.UPLOAD_DIR, "..", "data", "kb_reports.json")

@router.post("/report")
def generate_report(data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Generate a structured knowledge report from documents.
    data: {doc_ids: [], title: str, requirement: str}"""
    doc_ids = data.get("doc_ids", [])
    title = data.get("title", "").strip() or "知识报告"
    requirement = data.get("requirement", "").strip()

    if doc_ids:
        docs = db.execute(select(ProjectDocument).where(ProjectDocument.id.in_(doc_ids))).scalars().all()
    else:
        docs = db.execute(select(ProjectDocument).order_by(ProjectDocument.id.desc()).limit(30)).scalars().all()

    if not docs:
        return {"report": "无可用文档", "sections": []}

    parts = []
    for d in docs:
        parts.append(f"### 《{d.name}》[{d.doc_type or '通用'}]\n{(d.content or '')[:1000]}")
    full_text = "\n\n".join(parts)[:8000]

    if requirement:
        prompt = f"""你是知识管理顾问。用户提出了以下要求，请严格按照要求生成报告。

【报告标题】{title}
【用户要求】{requirement}

基于以下{len(docs)}篇文档内容，生成一份满足上述要求的报告（Markdown格式）。
注意：用户要求优先于任何默认模板，请精准回应要求，不要生成无关内容。

=== 文档内容 ===
{full_text}"""
    else:
        prompt = f"""你是知识管理顾问。基于以下{len(docs)}篇文档，生成一份结构化的知识报告《{title}》。

报告格式（Markdown）：

## 📊 知识概览
（2-3句话概括文档集合的主题和覆盖范围）

## 🔑 核心观点（5-8条）
- **观点1标题**: 说明（基于哪些文档）
- **观点2标题**: 说明
...

## 📈 知识分布
- 按主题分类统计
- 文档类型分布

## ⚠️ 知识缺口
（指出哪些重要主题在文档中缺少）

## 💡 应用建议
（这些知识可以用于哪些业务场景）

=== 文档内容 ===
{full_text}"""

    try:
        report = _call_llm_sync([{"role":"system","content":"你是知识管理顾问。生成专业的知识报告。"},{"role":"user","content":prompt}])
        # Save
        entry = {"id": str(uuid.uuid4().hex[:8]), "title": title, "report": report,
                 "doc_count": len(docs), "created_at": datetime.utcnow().isoformat()}
        existing = []
        try:
            with open(REPORT_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except: pass
        existing.insert(0, entry)
        os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
        atomic_write(REPORT_FILE, existing)
        return {"report": report, "id": entry["id"], "sections": ["知识概览","核心观点","知识分布","知识缺口","应用建议"]}
    except Exception as e:
        return {"report": f"报告生成失败: {str(e)[:100]}", "sections": []}


@router.get("/reports")
def list_reports(_user=Depends(get_current_user)):
    try:
        with open(REPORT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


# ── Smart Recommendations ──

RECOMMEND_LOG = os.path.join(settings.UPLOAD_DIR, "..", "data", "kb_view_log.json")

def _log_view(doc_id: int):
    """Log document view for recommendation engine."""
    try:
        log = []
        if os.path.exists(RECOMMEND_LOG):
            with open(RECOMMEND_LOG, "r", encoding="utf-8") as f:
                log = json.load(f)
        log.append({"doc_id": doc_id, "ts": datetime.utcnow().isoformat()})
        if len(log) > 200:
            log = log[-200:]
        os.makedirs(os.path.dirname(RECOMMEND_LOG), exist_ok=True)
        atomic_write(RECOMMEND_LOG, log)
    except: pass


@router.post("/documents/{doc_id}/view")
def log_doc_view(doc_id: int, _user=Depends(get_current_user)):
    _log_view(doc_id)
    return {"ok": True}


@router.get("/recommend")
def recommend_docs(limit: int = Query(5), db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Recommend documents based on view history and content similarity."""
    # Get recently viewed docs
    recent_ids = []
    try:
        if os.path.exists(RECOMMEND_LOG):
            with open(RECOMMEND_LOG, "r", encoding="utf-8") as f:
                log = json.load(f)
            counts = {}
            for entry in log[-50:]:
                did = entry["doc_id"]
                counts[did] = counts.get(did, 0) + 1
            recent_ids = [k for k, v in sorted(counts.items(), key=lambda x: -x[1])[:5]]
    except: pass

    # Get all docs
    all_docs = db.execute(select(ProjectDocument).order_by(ProjectDocument.id.desc()).limit(100)).scalars().all()

    if not recent_ids:
        # No history, return most recent
        results = []
        for d in all_docs[:limit]:
            results.append({"id": d.id, "title": d.name, "reason": "最新文档", "score": 1.0})
        return results

    # Get embeddings for recently viewed docs
    vecs = _load_vectors()
    recent_vecs = []
    for did in recent_ids:
        if str(did) in vecs:
            recent_vecs.append(vecs[str(did)])

    if not recent_vecs:
        return [{"id": d.id, "title": d.name, "reason": "最新"} for d in all_docs[:limit]]

    # Average vector of recently viewed
    avg_vec = np.mean(recent_vecs, axis=0).tolist()

    # Score all docs by similarity
    scored = []
    for d in all_docs:
        if d.id in recent_ids: continue
        if str(d.id) in vecs:
            sim = _cosine_sim(avg_vec, vecs[str(d.id)])
            reason = "相似内容" if sim > 0.7 else "相关推荐" if sim > 0.5 else "探索发现"
            scored.append({"id": d.id, "title": d.name, "score": round(sim, 3), "reason": reason})

    scored.sort(key=lambda x: -x["score"])
    return scored[:limit]


# ── Core Points Extraction ──

@router.post("/extract-points")
def extract_core_points(data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """One-click extract core viewpoints and key takeaways from documents.
    data: {doc_ids: [], requirement: str}"""
    doc_ids = data.get("doc_ids", [])
    requirement = data.get("requirement", "").strip()

    if doc_ids:
        docs = db.execute(select(ProjectDocument).where(ProjectDocument.id.in_(doc_ids))).scalars().all()
    else:
        docs = db.execute(select(ProjectDocument).order_by(ProjectDocument.id.desc()).limit(10)).scalars().all()

    if not docs:
        return {"points": [], "overview": "无可用文档"}

    parts = []
    for d in docs:
        parts.append(f"### 《{d.name}》\n{(d.content or '')[:1200]}")
    full_text = "\n\n".join(parts)[:12000]

    if requirement:
        prompt = f"""你是知识提炼专家。请严格按照用户要求从以下{len(docs)}篇文档中提取内容。

【用户要求】{requirement}

返回JSON（只返回JSON）：
{{
  "overview": "全文概要（100字以内）",
  "points": [
    {{"title":"要点标题","detail":"详细说明（30字）","importance":"高/中/低","category":"技术/管理/市场/其他"}},
    ...（8-12个）
  ]
}}

=== 文档内容 ===
{full_text}"""
    else:
        prompt = f"""你是知识提炼专家。从以下{len(docs)}篇文档中提取核心要点。

返回JSON（只返回JSON）：
{{
  "overview": "全文概要（100字以内）",
  "points": [
    {{"title":"要点标题","detail":"详细说明（30字）","importance":"高/中/低","category":"技术/管理/市场/其他"}},
    ...（8-12个）
  ]
}}

=== 文档内容 ===
{full_text}"""

    try:
        reply = _call_llm_sync([{"role":"system","content":"你是知识提炼专家。只返回JSON。"},{"role":"user","content":prompt}])
        match = re.search(r'\{.*\}', reply, re.DOTALL)
        if match:
            result = json.loads(match.group())
            return result
    except: pass
    return {"points": [], "overview": "提取失败"}


# ═══════════════════════════════════════════
# ── Knowledge Spaces (领域知识库) ──
# ═══════════════════════════════════════════

SPACES_FILE = os.path.join(settings.UPLOAD_DIR, "..", "data", "kb_spaces.json")

def _load_spaces():
    defaults = [{"id": "default", "name": "通用知识库", "description": "默认知识空间",
                 "icon": "📚", "created_at": datetime.utcnow().isoformat()}]
    try:
        with open(SPACES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if data else defaults
    except:
        return defaults

def _save_spaces(spaces):
    atomic_write(SPACES_FILE, spaces)


@router.get("/spaces")
def list_spaces(_user=Depends(get_current_user)):
    return _load_spaces()


@router.post("/spaces")
def create_space(data: dict, _user=Depends(get_current_user)):
    name = data.get("name", "").strip()
    if not name: raise HTTPException(400, detail="名称不能为空")
    user_id = str(_user.id) if hasattr(_user, 'id') else str(_user.get('id',''))
    spaces = _load_spaces()
    sid = data.get("id") or str(uuid.uuid4().hex[:8])
    space = {
        "id": sid, "name": name, "description": data.get("description", ""),
        "icon": data.get("icon", "📁"), "created_at": datetime.utcnow().isoformat(),
        "creator": user_id,
        "admins": [user_id],
        "collaborators": [],
        "viewers": [],
        "is_public": data.get("is_public", False),
    }
    spaces.append(space)
    _save_spaces(spaces)
    return space


@router.put("/spaces/{space_id}")
def update_space(space_id: str, data: dict, _user=Depends(get_current_user)):
    spaces = _load_spaces()
    for s in spaces:
        if s["id"] == space_id:
            for k in ("name","description","icon","is_public"):
                if k in data: s[k] = data[k]
            _save_spaces(spaces)
            return s
    raise HTTPException(404, detail="空间不存在")


@router.delete("/spaces/{space_id}")
def delete_space(space_id: str, _user=Depends(get_current_user)):
    if space_id == "default": raise HTTPException(400, detail="不能删除默认空间")
    user_id = str(_user.id) if hasattr(_user, 'id') else str(_user.get('id',''))
    spaces = _load_spaces()
    for s in spaces:
        if s["id"] == space_id and s.get("creator") != user_id:
            raise HTTPException(403, detail="只有创建者可以删除空间")
    spaces = [s for s in spaces if s["id"] != space_id]
    _save_spaces(spaces)
    return {"ok": True}


# ── Space Members ──
def _get_user_role(space, user_id):
    """Get user's role in a space: creator/admin/collaborator/viewer/None"""
    uid = str(user_id)
    if space.get("creator") == uid: return "creator"
    if uid in [str(x) for x in space.get("admins", [])]: return "admin"
    if uid in [str(x) for x in space.get("collaborators", [])]: return "collaborator"
    if uid in [str(x) for x in space.get("viewers", [])]: return "viewer"
    if space.get("is_public"): return "viewer"  # public space grants view access
    return None

def _check_perm(space, user_id, min_role="viewer"):
    """Check if user has at least min_role permission. Raises 403 if not."""
    role = _get_user_role(space, user_id)
    if role is None:
        raise HTTPException(403, detail="无权访问此空间")
    hierarchy = {"creator": 4, "admin": 3, "collaborator": 2, "viewer": 1}
    if hierarchy.get(role, 0) < hierarchy.get(min_role, 0):
        raise HTTPException(403, detail=f"权限不足，需要{min_role}及以上")
    return role


@router.get("/spaces/{space_id}/members")
def list_members(space_id: str, _user=Depends(get_current_user)):
    spaces = _load_spaces()
    for s in spaces:
        if s["id"] == space_id:
            return {
                "creator": s.get("creator", ""),
                "admins": s.get("admins", []),
                "collaborators": s.get("collaborators", []),
                "viewers": s.get("viewers", []),
                "is_public": s.get("is_public", False),
            }
    raise HTTPException(404, detail="空间不存在")


@router.post("/spaces/{space_id}/members")
def add_member(space_id: str, data: dict, _user=Depends(get_current_user)):
    """Add/update a member. data: {user_id, role} — role: admin/collaborator/viewer"""
    user_id = str(_user.id) if hasattr(_user, 'id') else str(_user.get('id',''))
    target = str(data.get("user_id", ""))
    role = data.get("role", "viewer")
    if not target: raise HTTPException(400, detail="请指定用户")
    if role not in ("admin", "collaborator", "viewer"): raise HTTPException(400, detail="无效角色")

    spaces = _load_spaces()
    for s in spaces:
        if s["id"] == space_id:
            _check_perm(s, user_id, "admin")  # Only creator/admin can manage members
            # Remove from all lists first
            for lst in ("admins", "collaborators", "viewers"):
                s[lst] = [x for x in s.get(lst, []) if str(x) != target]
            # Add to correct list
            s[role + "s"].append(target)
            _save_spaces(spaces)
            return {"ok": True, "user_id": target, "role": role}
    raise HTTPException(404)


@router.delete("/spaces/{space_id}/members/{target_id}")
def remove_member(space_id: str, target_id: str, _user=Depends(get_current_user)):
    """Remove a member from the space."""
    user_id = str(_user.id) if hasattr(_user, 'id') else str(_user.get('id',''))
    spaces = _load_spaces()
    for s in spaces:
        if s["id"] == space_id:
            _check_perm(s, user_id, "admin")
            for lst in ("admins", "collaborators", "viewers"):
                s[lst] = [x for x in s.get(lst, []) if str(x) != target]
            _save_spaces(spaces)
            return {"ok": True}
    raise HTTPException(404)


@router.get("/spaces/{space_id}/stats")
def space_stats(space_id: str, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Get statistics for a knowledge space."""
    q = select(ProjectDocument).order_by(ProjectDocument.id.desc()).limit(500)
    docs = db.execute(q).scalars().all()
    count = 0; total_size = 0; categories = set()
    for d in docs:
        meta = {}
        try: meta = json.loads(d.notes or "{}")
        except: pass
        doc_space = meta.get("space", "default")
        if doc_space == space_id:
            count += 1
            total_size += len(d.content or "")
            categories.add(d.doc_type or "其他")
    return {"doc_count": count, "total_chars": total_size, "categories": list(categories)}


# ── Quick document overview ──

@router.post("/quick-overview")
def quick_overview(data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Generate a quick overview card for a document (title, summary, keywords, reading time)."""
    doc_id = data.get("doc_id")
    if not doc_id: raise HTTPException(400, detail="需要doc_id")
    doc = db.execute(select(ProjectDocument).where(ProjectDocument.id == doc_id)).scalar_one_or_none()
    if not doc: raise HTTPException(404, detail="文档不存在")

    content = (doc.content or "")[:3000]
    chars = len(doc.content or "")
    reading_time = max(1, chars // 500)

    prompt = f"""分析以下文档，返回JSON（只返回JSON）：
{{
  "summary": "一句话摘要（40字）",
  "keywords": ["关键词1","关键词2",...5个],
  "topics": ["主题1","主题2",...3个],
  "score": 评分1-10（信息密度/质量）
}}

文档: {doc.name}
内容: {content[:2000]}"""

    try:
        reply = _call_llm_sync([{"role":"system","content":"只返回JSON。"},{"role":"user","content":prompt}])
        match = re.search(r'\{.*\}', reply, re.DOTALL)
        if match:
            info = json.loads(match.group())
            info["reading_time"] = f"{reading_time}分钟"
            info["chars"] = chars
            info["title"] = doc.name
            return info
    except: pass
    return {"summary": "AI分析暂不可用", "keywords": [], "topics": [], "score": 0,
            "reading_time": f"{reading_time}分钟", "chars": chars, "title": doc.name}


# ── Update existing endpoints to support space ──

# Patch the upload endpoint to accept space parameter
# The upload endpoint already exists, so we add a space-aware version

@router.get("/spaces/{space_id}/documents")
def list_space_documents(
    space_id: str,
    category: str = Query(None),
    search: str = Query(None),
    folder: str = Query(None),
    limit: int = Query(100),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """List documents in a specific knowledge space."""
    q = select(ProjectDocument).order_by(ProjectDocument.id.desc())
    docs = db.execute(q).scalars().all()

    results = []
    for d in docs:
        if len(results) >= limit: break
        meta = {}
        try: meta = json.loads(d.notes or "{}")
        except: pass
        doc_space = meta.get("space", "default")
        if doc_space != space_id: continue

        if category and d.doc_type != category: continue
        # Folder: native column > notes JSON > auto project folder
        df = d.folder or meta.get("folder", "/")
        if (not df or df == "/") and d.project_id:
            proj = db.get(Project, d.project_id)
            if proj and proj.name:
                df = proj.name
        if not df: df = "/"
        # Filter by folder (strip / for comparison)
        if folder:
            dfp = df.strip("/")
            fp = folder.strip("/")
            if dfp != fp and not dfp.startswith(fp + "/"):
                continue
        if search:
            qs = search.lower()
            if qs not in (d.name or "").lower() and qs not in (d.content or "").lower():
                continue

        tags = meta.get("tags", [])
        results.append({
            "id": d.id, "title": d.name, "doc_type": d.doc_type,
            "category": d.doc_type, "folder": "/" + df.strip("/") if df.strip("/") else "/",
            "tags": tags, "space": doc_space,
            "filename": meta.get("filename", d.name),
            "content": (d.content or "")[:800],
            "created_at": d.upload_date.isoformat() if d.upload_date else None,
            "file_path": d.file_path,
            "owner": meta.get("owner", ""),
            "visibility": meta.get("visibility", "shared"),
            "access_level": getattr(d, '_access_level', ACCESS_FULL),
        })
    return results[:limit]


# ══════════════════════════════
# ── Document Sharing Endpoints ──
# ══════════════════════════════

@router.get("/shared-with-me")
def list_shared_with_me(limit: int = Query(100), db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """List documents shared with the current user (not own docs)."""
    uid = _user.id
    rows = db.execute(
        select(ProjectDocument, KbDocumentShare).join(
            KbDocumentShare, KbDocumentShare.document_id == ProjectDocument.id
        ).where(
            KbDocumentShare.shared_with_user_id == uid,
            ProjectDocument.owner_id != uid
        ).order_by(KbDocumentShare.created_at.desc()).limit(limit)
    ).all()
    return [{
        "id": r.ProjectDocument.id, "title": r.ProjectDocument.name,
        "doc_type": r.ProjectDocument.doc_type,
        "access_level": r.KbDocumentShare.access_level,
        "content": _truncate_for_level(r.ProjectDocument.content or "", r.KbDocumentShare.access_level),
        "folder": r.ProjectDocument.folder or "/",
        "shared_by": r.KbDocumentShare.shared_by_user_id,
        "shared_at": r.KbDocumentShare.created_at.isoformat() if r.KbDocumentShare.created_at else None,
        "file_path": r.ProjectDocument.file_path, "owner_id": r.ProjectDocument.owner_id,
    } for r in rows]


@router.get("/documents/{doc_id}/shares")
def list_document_shares(doc_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """List users this document is shared with. Owner/admin only."""
    doc = db.get(ProjectDocument, doc_id)
    if not doc: raise HTTPException(404, detail="文档不存在")
    is_admin = getattr(_user, 'role', 'member') == 'admin'
    if not is_admin and doc.owner_id != _user.id:
        raise HTTPException(403, detail="无权查看分享信息")
    shares = db.execute(
        select(KbDocumentShare, UserAuth).join(
            UserAuth, KbDocumentShare.shared_with_user_id == UserAuth.id
        ).where(KbDocumentShare.document_id == doc_id)
    ).all()
    return [{
        "user_id": s.KbDocumentShare.shared_with_user_id,
        "username": s.UserAuth.username,
        "access_level": s.KbDocumentShare.access_level,
        "shared_at": s.KbDocumentShare.created_at.isoformat() if s.KbDocumentShare.created_at else None,
    } for s in shares]


@router.post("/documents/{doc_id}/share")
def share_document(doc_id: int, data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Share doc with users. {user_ids:[], access_level:'limited'|'full'}"""
    doc = db.get(ProjectDocument, doc_id)
    if not doc: raise HTTPException(404, detail="文档不存在")
    is_admin = getattr(_user, 'role', 'member') == 'admin'
    if not is_admin and doc.owner_id != _user.id:
        raise HTTPException(403, detail="只有文档所有者可以分享")
    user_ids = data.get("user_ids", [])
    access_level = data.get("access_level", "limited")
    if access_level not in ("limited", "full"):
        raise HTTPException(400, detail="access_level 必须是 'limited' 或 'full'")
    added = []
    for uid in user_ids:
        if uid == _user.id: continue
        existing = db.execute(select(KbDocumentShare).where(
            KbDocumentShare.document_id == doc_id,
            KbDocumentShare.shared_with_user_id == uid
        )).scalar_one_or_none()
        if existing:
            existing.access_level = access_level
        else:
            db.add(KbDocumentShare(document_id=doc_id, shared_with_user_id=uid,
                                    access_level=access_level, shared_by_user_id=_user.id))
        added.append(uid)
    db.commit()
    return {"ok": True, "added": added, "access_level": access_level}


@router.delete("/documents/{doc_id}/shares/{user_id}")
def remove_document_share(doc_id: int, user_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Revoke a user's access to a document."""
    doc = db.get(ProjectDocument, doc_id)
    if not doc: raise HTTPException(404, detail="文档不存在")
    if getattr(_user, 'role', 'member') != 'admin' and doc.owner_id != _user.id:
        raise HTTPException(403, detail="无权管理分享")
    db.execute(sql_delete(KbDocumentShare).where(
        KbDocumentShare.document_id == doc_id,
        KbDocumentShare.shared_with_user_id == user_id
    ))
    db.commit()
    return {"ok": True}


@router.get("/users/search")
def search_users(q: str = Query(""), db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Search users for share dialog."""
    rows = db.execute(
        select(UserAuth.id, UserAuth.username).where(
            UserAuth.username.contains(q), UserAuth.is_active == True
        ).limit(20)
    ).all()
    return [{"id": r[0], "username": r[1]} for r in rows]


# ═══════════════════════════════════════════
# ── Enhanced Folder Management ──
# ═══════════════════════════════════════════

FOLDER_TREE_FILE = os.path.join(settings.UPLOAD_DIR, "..", "kb_folders.json")
PERSONAL_FOLDERS_FILE = os.path.join(settings.UPLOAD_DIR, "..", "kb_personal_folders.json")

def _load_folder_paths(personal=False):
    """Load flat list of folder paths. personal=True loads personal folders."""
    defaults = ["/"]
    ffile = PERSONAL_FOLDERS_FILE if personal else FOLDER_TREE_FILE
    try:
        with open(ffile, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                if data and isinstance(data[0], str):
                    return data
                return [d["path"] for d in data if d.get("path")]
            return defaults
    except:
        return defaults

def _save_folder_paths(paths, personal=False):
    ffile = PERSONAL_FOLDERS_FILE if personal else FOLDER_TREE_FILE
    atomic_write(ffile, sorted(set(paths)))

def _norm_folder(path):
    """Normalize folder path: always starts with /, no trailing /."""
    if not path: return "/"
    path = path.replace("\\", "/").strip()
    if not path.startswith("/"): path = "/" + path
    return path.rstrip("/") or "/"

def _auto_register_folder(folder_path, personal=False):
    """Auto-create folder in tree if it doesn't exist."""
    if not folder_path or folder_path == "/":
        return
    folder_path = folder_path.replace("\\", "/")
    if not folder_path.startswith("/"):
        folder_path = "/" + folder_path
    folder_path = folder_path.rstrip("/")
    if folder_path == "/":
        return
    paths = _load_folder_paths(personal)
    parts = folder_path.split("/")
    changed = False
    for i in range(1, len(parts) + 1):
        sub = "/".join(parts[:i]) or "/"
        if sub not in paths:
            paths.append(sub)
            changed = True
    if changed:
        _save_folder_paths(paths, personal)

def _build_folder_tree_from_db(db=None, personal=False, user=None):
    """Build a hierarchical folder tree directly from document folder paths."""
    if db is None:
        from backend_v2.database import SessionLocal
        tmp_db = SessionLocal()
    else:
        tmp_db = db

    try:
        from backend_v2.models import Project, ProjectDocument
        from sqlalchemy import select as _sel, func as _func
        import json as _json, re as _re

        kb_proj = tmp_db.execute(_sel(Project).where(Project.name == "__knowledge_base__")).scalar_one_or_none()
        kb_proj_id = kb_proj.id if kb_proj else None

        accessible = None
        if user and hasattr(user, 'id') and getattr(user, 'role', 'member') != 'admin':
            accessible = _get_accessible_spaces(user, tmp_db)
        user_id_str = str(user.id) if (user and hasattr(user, 'id')) else None

        docs = tmp_db.execute(_sel(ProjectDocument.folder, ProjectDocument.project_id, ProjectDocument.notes, ProjectDocument.space_id, ProjectDocument.ext_visibility)).all()

        all_folders = {}
        for folder_col, proj_id, notes, space_id, ext_vis in docs:
            # 知识库文件夹树只聚合知识库文档，项目文档不显示在树中（否则删除按钮无法删除且易误操作）
            if kb_proj_id is not None and proj_id != kb_proj_id:
                continue
            if accessible is not None:
                doc_space = (space_id or "default")
                if doc_space not in accessible:
                    continue
            vis = (ext_vis or "").strip()
            if vis == "private" and user_id_str:
                owner = None
                try: owner = _json.loads(notes or "{}").get("owner")
                except: pass
                if owner and str(owner) != user_id_str:
                    continue

            f = folder_col
            if not f:
                try: f = _json.loads(notes or "\"{}\"").get("folder", "/")
                except: f = "/"
            if (not f or f == "/") and proj_id and proj_id != kb_proj_id:
                proj = tmp_db.get(Project, proj_id)
                if proj and proj.name:
                    f = proj.name
            f = (f or "/").strip("/")
            if not f:
                continue

            # Normalize: strip network share prefix
            f = f.replace("\\", "/")
            m = _re.match(r'^(?://)?([^/]+)/([^/]+)/(.+)$', f)
            if m:
                seg1 = m.group(1)
                if _re.match(r'^\d+\.\d+\.\d+\.\d+$', seg1):
                    f = m.group(3)

            all_folders[f] = all_folders.get(f, 0) + 1

        # Build tree: folder hierarchy directly
        root = {"path": "/", "name": "根目录", "count": sum(all_folders.values()), "children": []}
        node_map = {"/": root}

        for fpath, count in sorted(all_folders.items()):
            fp = "/" + fpath
            parts = fp.split("/")
            parent_path = "/"
            for i in range(1, len(parts)):
                seg = parts[i]
                cur_path = "/".join(parts[:i+1])
                if cur_path not in node_map:
                    node = {"path": cur_path, "name": seg, "count": 0, "children": []}
                    node_map[cur_path] = node
                    parent = node_map.get(parent_path, root)
                    parent["children"].append(node)
                if i == len(parts) - 1:
                    node_map[cur_path]["count"] = (node_map[cur_path].get("count", 0) or 0) + count
                parent_path = cur_path

        # Filter folders by user permissions (non-admin only, skip the root "/")
        if user and hasattr(user, 'id') and getattr(user, 'role', 'member') != 'admin':
            def filter_children(node):
                if "children" in node:
                    node["children"] = [
                        c for c in node["children"]
                        if _user_can_access_folder(user, tmp_db, c["path"])
                    ]
                    for c in node["children"]:
                        filter_children(c)
            filter_children(root)

        return [root]
    finally:
        if db is None:
            tmp_db.close()


@router.post("/documents/{doc_id}/send-to-kb")
def send_to_knowledge_base(doc_id: int, data: dict = {}, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Copy a project document into the knowledge base. Original stays in project."""
    doc = db.get(ProjectDocument, doc_id)
    if not doc: raise HTTPException(404, detail="文档不存在")
    kb_proj = db.execute(select(Project).where(Project.name == "__knowledge_base__")).scalar_one_or_none()
    if not kb_proj:
        kb_proj = Project(name="__knowledge_base__", code="__KB__", overall_status="active")
        db.add(kb_proj); db.commit(); db.refresh(kb_proj)

    # Don't duplicate if already KB doc
    if doc.project_id == kb_proj.id:
        raise HTTPException(400, detail="已经是知识库文档")

    folder = data.get("folder", doc.folder or "/")
    new_doc = ProjectDocument(
        project_id=kb_proj.id,
        name=doc.name,
        doc_type=doc.doc_type,
        content=doc.content,
        file_path=doc.file_path,
        file_size=doc.file_size,
        folder=folder,
        notes=doc.notes,
        upload_date=datetime.now().date(),
        space_id='',
        ext_visibility='shared',
        owner_id=_user.id if hasattr(_user, 'id') else None,
    )
    db.add(new_doc); db.commit(); db.refresh(new_doc)
    return {"ok": True, "id": new_doc.id, "title": new_doc.name, "msg": "已复制到知识库，原项目文档不变"}


# ── KB Member Management ──

def _ensure_kb_member_table(db):
    """Ensure kb_space_member table has the kb entry."""
    try:
        db.execute(text("INSERT OR IGNORE INTO kb_space(id,name,is_public) VALUES('kb','知识库成员',1)"))
        db.commit()
    except: pass


@router.get("/members")
def list_kb_members(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """List all KB members with their roles."""
    _ensure_kb_member_table(db)
    rows = db.execute(text(
        "SELECT m.user_id, u.username, u.role as platform_role, m.role as kb_role "
        "FROM kb_space_member m JOIN user_auth u ON m.user_id=u.id WHERE m.space_id='kb'"
    )).fetchall()
    return [{"user_id": r[0], "username": r[1], "platform_role": r[2], "kb_role": r[3]} for r in rows]


@router.post("/members")
def add_kb_member(data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Add or update a KB member. data: {user_id, role: 'admin'|'editor'|'viewer'}"""
    if getattr(_user, 'role', 'member') != 'admin':
        raise HTTPException(403, "只有管理员可以管理成员")
    _ensure_kb_member_table(db)
    user_id = data.get("user_id")
    role = data.get("role", "viewer")
    if not user_id: raise HTTPException(400, "请提供user_id")
    db.execute(text(
        "INSERT OR REPLACE INTO kb_space_member(space_id,user_id,role) VALUES('kb',:uid,:role)"
    ), {"uid": user_id, "role": role})
    db.commit()
    return {"ok": True}


@router.delete("/members/{user_id}")
def remove_kb_member(user_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Remove a KB member."""
    if getattr(_user, 'role', 'member') != 'admin':
        raise HTTPException(403, "只有管理员可以管理成员")
    db.execute(text("DELETE FROM kb_space_member WHERE space_id='kb' AND user_id=:uid"), {"uid": user_id})
    db.commit()
    return {"ok": True}


@router.get("/users/list")
def list_all_users(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """List all platform users (for member picker)."""
    rows = db.execute(text("SELECT id, username, role FROM user_auth WHERE is_active=1")).fetchall()
    return [{"id": r[0], "username": r[1], "role": r[2]} for r in rows]


# ── Folder-level Permissions ──

def _get_folder_members(db, folder_path: str):
    """Get members for a folder."""
    rows = db.execute(text(
        "SELECT fm.user_id, u.username, fm.role FROM kb_folder_member fm "
        "JOIN user_auth u ON fm.user_id=u.id WHERE fm.folder_path=:fp"
    ), {"fp": folder_path}).fetchall()
    return [{"user_id": r[0], "username": r[1], "role": r[2]} for r in rows]


def _user_can_access_folder(user, db, folder_path: str) -> bool:
    """Check if user can access a folder. No members = public."""
    if not user or not hasattr(user, 'id'):
        return True
    if getattr(user, 'role', 'member') == 'admin':
        return True
    # Check if folder has any members
    has_members = db.execute(text(
        "SELECT COUNT(*) FROM kb_folder_member WHERE folder_path=:fp"
    ), {"fp": folder_path}).fetchone()[0]
    if not has_members:
        return True  # No restrictions = public
    # Check if user is a member
    is_member = db.execute(text(
        "SELECT COUNT(*) FROM kb_folder_member WHERE folder_path=:fp AND user_id=:uid"
    ), {"fp": folder_path, "uid": user.id}).fetchone()[0]
    return is_member > 0


@router.get("/folders/{path:path}/members")
def list_folder_members(path: str, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """List members of a folder."""
    if getattr(_user, 'role', 'member') != 'admin':
        raise HTTPException(403, "只有管理员可以管理文件夹权限")
    return _get_folder_members(db, path)


@router.post("/folders/{path:path}/members")
def add_folder_member(path: str, data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Add a member to a folder. data: {user_id, role}"""
    if getattr(_user, 'role', 'member') != 'admin':
        raise HTTPException(403, "只有管理员可以管理文件夹权限")
    user_id = data.get("user_id")
    role = data.get("role", "viewer")
    if not user_id: raise HTTPException(400, "请提供user_id")
    db.execute(text(
        "INSERT OR REPLACE INTO kb_folder_member(folder_path,user_id,role) VALUES(:fp,:uid,:r)"
    ), {"fp": path, "uid": user_id, "r": role})
    db.commit()
    return {"ok": True}


@router.delete("/folders/{path:path}/members/{user_id}")
def remove_folder_member(path: str, user_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Remove a member from a folder."""
    if getattr(_user, 'role', 'member') != 'admin':
        raise HTTPException(403, "只有管理员可以管理文件夹权限")
    db.execute(text("DELETE FROM kb_folder_member WHERE folder_path=:fp AND user_id=:uid"),
               {"fp": path, "uid": user_id})
    db.commit()
    return {"ok": True}


@router.get("/folder-tree")
def get_folder_tree(personal: bool = Query(False), db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Live folder tree from database — permission-aware."""
    return _build_folder_tree_from_db(db, personal, _user)


@router.post("/folders")
def create_folder(data: dict, _user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Create a new folder via placeholder document so it appears in the tree."""
    path = data.get("path", "").strip()
    if not path: raise HTTPException(400, detail="路径不能为空")
    path = path.replace("\\", "/")
    if not path.startswith("/"): path = "/" + path
    path = path.rstrip("/")
    if path == "/": raise HTTPException(400, detail="不能创建根目录")
    name = data.get("name", "").strip() or path.rsplit("/", 1)[-1]
    # Ensure KB project exists
    kb_project = db.execute(select(Project).where(Project.name == "__knowledge_base__")).scalar_one_or_none()
    if not kb_project:
        kb_project = Project(name="__knowledge_base__", code="__KB__", overall_status="active")
        db.add(kb_project); db.commit(); db.refresh(kb_project)
    # Create placeholder doc to make folder appear in tree
    doc = ProjectDocument(
        project_id=kb_project.id, name=f".folder_{name}", doc_type="其他",
        content="", folder=path, upload_date=datetime.now().date(),
    )
    db.add(doc); db.commit()
    return {"path": path, "name": name, "created": True}


@router.put("/folders/{path:path}")
def rename_folder(path: str, data: dict, _user=Depends(get_current_user)):
    """Rename a folder."""
    new_name = data.get("name", "").strip()
    personal = data.get("personal", False)
    if not new_name: raise HTTPException(400, detail="名称不能为空")
    path = "/" + path if not path.startswith("/") else path
    path = path.rstrip("/")
    if path == "/": raise HTTPException(400, detail="不能重命名根目录")
    paths = _load_folder_paths(personal)
    if path not in paths: raise HTTPException(404, detail="文件夹不存在")
    parent = "/".join(path.split("/")[:-1]) or "/"
    new_path = parent + "/" + new_name if parent != "/" else "/" + new_name
    new_paths = []
    for p in paths:
        if p == path: new_paths.append(new_path)
        elif p.startswith(path + "/"): new_paths.append(new_path + p[len(path):])
        else: new_paths.append(p)
    _save_folder_paths(new_paths, personal)
    return {"ok": True, "new_path": new_path}


@router.delete("/folders/{path:path}")
def delete_folder(path: str, personal: bool = Query(False), db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Delete a folder, all sub-folders, and all documents within them."""
    path = "/" + path if not path.startswith("/") else path
    path = path.rstrip("/")
    if path == "/": raise HTTPException(400, detail="不能删除根目录")
    if path in ("/通用知识库", "/default", "/default/"):
        raise HTTPException(400, detail="不能删除默认知识空间，如需清空请进入空间逐个删除文档")

    norm = _norm_folder(path)
    norm_no_slash = norm.lstrip("/")

    kb_proj = db.execute(select(Project).where(Project.name == "__knowledge_base__")).scalar_one_or_none()
    kb_proj_id = kb_proj.id if kb_proj else None

    # Safety: only scan docs in this space if path includes space prefix
    space_id = None
    path_parts = path.strip("/").split("/")
    if path_parts and path_parts[0] in ("default", "pm", "tech", "ops", "hr"):
        space_id = path_parts[0]
        if len(path_parts) > 1:
            norm_no_slash = "/".join(path_parts[1:])
            norm = "/" + norm_no_slash
        else:
            # Deleting entire space: match all docs in that space
            norm_no_slash = ""
            norm = "/"

    all_docs = db.execute(select(ProjectDocument)).scalars().all()
    deleted_ids = []
    for doc in all_docs:
        # Only delete KB documents, never project documents
        if doc.project_id != kb_proj_id:
            continue
        # Space filter
        if space_id:
            doc_space = (doc.space_id or "").strip() or "default"
            if doc_space != space_id:
                continue

        doc_folder = (doc.folder or "").strip("/")
        if (not doc_folder or doc_folder == "/") and doc.project_id and doc.project_id != kb_proj_id:
            proj = db.get(Project, doc.project_id)
            if proj and proj.name:
                doc_folder = proj.name.strip("/")
        doc_norm = "/" + doc_folder if doc_folder else ""

        # Match: exact path OR sub-folder path (prefix match)
        if norm_no_slash:
            matched = (doc_norm == norm or doc_norm.startswith(norm + "/") or
                       doc_folder == norm_no_slash or doc_folder.startswith(norm_no_slash + "/"))
        else:
            # Deleting entire space: match all docs in the space (space_id filter handles scope)
            matched = True
        if matched:
            deleted_ids.append(doc.id)
            if doc.file_path and os.path.exists(doc.file_path):
                try: os.remove(doc.file_path)
                except: pass

    # Safety: refuse mass deletion
    if len(deleted_ids) > 500:
        raise HTTPException(400, detail=f"安全限制：此操作将删除 {len(deleted_ids)} 篇文档（超过500篇上限）。请分批删除或联系管理员。")

    for did in deleted_ids:
        db.execute(sql_delete(ProjectDocument).where(ProjectDocument.id == did))
    db.commit()

    # If this was a space-level folder with 0 docs, remove the space entirely
    if space_id and len(deleted_ids) == 0:
        try:
            db.execute(text("DELETE FROM kb_folder WHERE space_id=:sid"), {"sid": space_id})
            db.execute(text("DELETE FROM kb_space_member WHERE space_id=:sid"), {"sid": space_id})
            db.execute(text("DELETE FROM kb_space WHERE id=:sid"), {"sid": space_id})
            db.commit()
        except:
            pass

    return {"ok": True, "deleted": path, "docs_deleted": len(deleted_ids)}


@router.post("/folders/move")
def move_folder(data: dict, _user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Move a folder (and children) under a new parent folder.
    data: {path: '/旧路径', target: '/新父文件夹'} — target为'/'表示移到根目录"""
    src = data.get("path", "").strip().strip("/")
    target = data.get("target", "/").strip().strip("/")
    if not src: raise HTTPException(400, detail="缺少源路径")
    if src == "/" or src == "": raise HTTPException(400, detail="不能移动根目录")

    # Prevent moving into self or child
    if target.startswith(src + "/") or target == src:
        raise HTTPException(400, detail="不能移动到自身或子文件夹下")

    # New basename = last segment of src
    basename = src.split("/")[-1] if "/" in src else src
    new_path = (target + "/" + basename) if target else basename

    # Update documents in the moved folder — scan ALL docs, match both column and notes
    all_docs = db.execute(select(ProjectDocument)).scalars().all()
    kb_proj = db.execute(select(Project).where(Project.name == "__knowledge_base__")).scalar_one_or_none()
    kb_proj_id = kb_proj.id if kb_proj else None
    updated = 0
    src_norm = src.strip("/")
    for d in all_docs:
        doc_folder = (d.folder or "").strip("/")
        # Handle project-name-derived folders
        if (not doc_folder or doc_folder == "/") and d.project_id and d.project_id != kb_proj_id:
            proj = db.get(Project, d.project_id)
            if proj and proj.name:
                doc_folder = proj.name.strip("/")
        if doc_folder == src_norm:
            d.folder = new_path
            updated += 1
        elif doc_folder.startswith(src_norm + "/"):
            d.folder = new_path + doc_folder[len(src_norm):]
            updated += 1
    db.commit()

    return {"ok": True, "from": src, "to": new_path, "docs_updated": updated}


@router.post("/documents/{doc_id}/move")
def move_document(doc_id: int, data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Move a document to a different folder."""
    target_folder = data.get("folder", "/")
    doc = db.execute(select(ProjectDocument).where(ProjectDocument.id == doc_id)).scalar_one_or_none()
    if not doc: raise HTTPException(404, detail="文档不存在")
    meta = {}
    try: meta = json.loads(doc.notes or "{}")
    except: pass
    doc.folder = target_folder  # Update native column too
    meta["folder"] = target_folder
    meta["moved_by"] = _user.get("username", "")
    meta["moved_at"] = datetime.utcnow().isoformat()
    doc.notes = json.dumps(meta, ensure_ascii=False)
    db.commit()
    return {"ok": True, "folder": target_folder}


@router.post("/documents/batch-move")
def batch_move_documents(data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Batch move documents to a folder. If all docs are from the same source folder, move that folder as a subfolder."""
    doc_ids = data.get("doc_ids", [])
    target_folder = data.get("folder", "/")
    new_space = data.get("space", "")
    docs = db.execute(select(ProjectDocument).where(ProjectDocument.id.in_(doc_ids))).scalars().all()

    # Detect if all docs are from the same folder → only append folder name if moving to DIFFERENT parent
    source_folder = ""
    if docs:
        folders = set()
        for d in docs:
            meta = {}
            try: meta = json.loads(d.notes or "{}")
            except: pass
            f = (d.folder or meta.get("folder", "/")).strip("/")
            if f and f != "/": folders.add(f)
        if len(folders) == 1:
            source_folder = list(folders)[0]

    target_clean = target_folder.strip("/")
    if source_folder and target_clean:
        src_base = source_folder.split("/")[-1]
        # Only append source folder name if target is truly different
        if target_clean != source_folder and not target_clean.endswith("/" + src_base):
            target_folder = target_clean + "/" + src_base
        else:
            target_folder = target_clean
    elif target_clean:
        target_folder = target_clean
    else:
        target_folder = "/"

    for d in docs:
        meta = {}
        try: meta = json.loads(d.notes or "{}")
        except: pass
        d.folder = target_folder
        meta["folder"] = target_folder
        if new_space:
            meta["space"] = new_space
        d.notes = json.dumps(meta, ensure_ascii=False)
    db.commit()
    return {"moved": len(docs), "folder": target_folder, "is_folder_move": bool(source_folder)}


@router.post("/folders/move-to-space")
def move_folder_to_space(data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Move all documents in a folder to a different knowledge space."""
    source_folder = data.get("folder", "").strip()
    target_space = data.get("space", "").strip()
    if not source_folder: raise HTTPException(400, detail="请指定源文件夹")
    if not target_space: raise HTTPException(400, detail="请指定目标空间")

    docs = db.execute(select(ProjectDocument)).scalars().all()
    moved = 0
    for d in docs:
        meta = {}
        try: meta = json.loads(d.notes or "{}")
        except: pass
        doc_folder = d.folder or meta.get("folder", "/")
        src = source_folder.strip("/")
        df = doc_folder.strip("/")
        if df == src or df.startswith(src + "/"):
            meta["space"] = target_space
            d.notes = json.dumps(meta, ensure_ascii=False)
            moved += 1
    if moved: db.commit()
    return {"moved": moved, "from_folder": source_folder, "to_space": target_space}


# ═══════════════════════════════════════════
# ── Permissions & Collaboration ──
# ═══════════════════════════════════════════

@router.post("/documents/{doc_id}/permission")
def set_doc_permission(doc_id: int, data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Set document access level. data: {level: 'public'|'team'|'private', shared_with: []}"""
    doc = db.execute(select(ProjectDocument).where(ProjectDocument.id == doc_id)).scalar_one_or_none()
    if not doc: raise HTTPException(404, detail="文档不存在")
    meta = {}
    try: meta = json.loads(doc.notes or "{}")
    except: pass
    meta["permission"] = data.get("level", "team")
    meta["shared_with"] = data.get("shared_with", [])
    meta["owner"] = _user.get("username", "")
    doc.notes = json.dumps(meta, ensure_ascii=False)
    db.commit()
    return {"ok": True, "permission": meta["permission"]}


# ── Activity Log ──

ACTIVITY_FILE = os.path.join(settings.UPLOAD_DIR, "..", "data", "kb_activity.json")

def _log_activity(action: str, doc_id: int, doc_name: str, user: str):
    entry = {"action": action, "doc_id": doc_id, "doc_name": doc_name,
             "user": user, "ts": datetime.utcnow().isoformat()}
    try:
        log = []
        if os.path.exists(ACTIVITY_FILE):
            with open(ACTIVITY_FILE, "r", encoding="utf-8") as f:
                log = json.load(f)
        log.insert(0, entry)
        if len(log) > 200: log = log[:200]
        os.makedirs(os.path.dirname(ACTIVITY_FILE), exist_ok=True)
        atomic_write(ACTIVITY_FILE, log)
    except: pass


@router.get("/activity")
def get_activity(limit: int = Query(50), _user=Depends(get_current_user)):
    try:
        with open(ACTIVITY_FILE, "r", encoding="utf-8") as f:
            log = json.load(f)
            return log[:limit]
    except:
        return []


# Patch upload endpoints to log activity
# We hook into the existing upload by overriding in the frontend — or we just add logging calls.
# For simplicity, the frontend can call /activity-log or we auto-log on upload.
# Auto-log on document listing (when user views a doc).

@router.post("/activity-log")
def log_user_activity(data: dict, _user=Depends(get_current_user)):
    """Log a user action. data: {action, doc_id, doc_name}"""
    _log_activity(
        data.get("action", "view"),
        data.get("doc_id", 0),
        data.get("doc_name", ""),
        _user.get("username", "anonymous")
    )
    return {"ok": True}


# ═══════════════════════════════════════════
# ── Knowledge Graph ──
# ═══════════════════════════════════════════

@router.get("/graph")
def knowledge_graph(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Generate knowledge graph: document nodes and tag/topic edges."""
    docs = db.execute(select(ProjectDocument).order_by(ProjectDocument.id.desc()).limit(200)).scalars().all()
    nodes = []; tag_docs = {}
    for d in docs:
        meta = {}
        try: meta = json.loads(d.notes or "{}")
        except: pass
        tags = meta.get("tags", [])
        nodes.append({"id": str(d.id), "label": (d.name or "")[:20], "type": "doc",
                       "tags": tags, "category": d.doc_type or "其他"})
        for t in tags:
            if t not in tag_docs: tag_docs[t] = []
            tag_docs[t].append(str(d.id))
    edges = []
    for tag, doc_ids in tag_docs.items():
        if len(doc_ids) >= 2:
            tid = f"tag_{tag}"
            nodes.append({"id": tid, "label": tag, "type": "tag", "size": len(doc_ids)})
            for did in doc_ids:
                edges.append({"source": did, "target": tid})
    for i in range(len(nodes)):
        for j in range(i+1, len(nodes)):
            if nodes[i]["type"] == "doc" and nodes[j]["type"] == "doc":
                shared = set(nodes[i].get("tags",[])) & set(nodes[j].get("tags",[]))
                if len(shared) >= 2:
                    edges.append({"source": nodes[i]["id"], "target": nodes[j]["id"],
                                   "label": ",".join(list(shared)[:2])})
    return {"nodes": nodes[:100], "edges": edges[:200], "tag_count": len(tag_docs)}


# ═══════════════════════════════════════════
# ── Version History ──
# ═══════════════════════════════════════════

VERSION_DIR = os.path.join(settings.UPLOAD_DIR, "..", "data", "kb_versions")

@router.get("/preview-file/{doc_id}")
def preview_file_html(doc_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Convert document to HTML for inline preview (Word/Excel/PPT/PDF/text)."""
    from fastapi.responses import HTMLResponse
    doc = db.get(ProjectDocument, doc_id)
    if not doc: raise HTTPException(404, detail="文档不存在")
    access = _get_doc_access_level(doc, _user, db)
    if access == ACCESS_NONE:
        raise HTTPException(403, detail="无权预览此文档")
    if access == ACCESS_LIMITED:
        raise HTTPException(403, detail="受限访问：仅200字预览和AI问答可用，不支持文件预览")
    # Resolve actual file path (local or network source)
    fpath = doc.file_path
    # Resolve relative paths against upload directory
    if fpath:
        from pathlib import Path as _Path
        upload_root = _Path(settings.UPLOAD_DIR).parent
        full = upload_root / fpath
        if full.exists():
            fpath = str(full)
    if not fpath or not os.path.exists(fpath):
        meta = {}
        try: meta = json.loads(doc.notes or "{}")
        except: pass
        src = meta.get("source", "")
        # Try network source (with timeout to avoid hanging)
        if src and src.startswith("network:"):
            import threading
            net_dir = src[8:]
            fname = meta.get("filename", doc.name)
            net_found = [None]  # mutable container for thread result
            def _search_net():
                try:
                    net_path = os.path.join(net_dir, fname)
                    if os.path.exists(net_path):
                        net_found[0] = net_path
                    else:
                        for root, dirs, files in os.walk(net_dir):
                            if fname in files:
                                net_found[0] = os.path.join(root, fname); break
                except: pass
            t = threading.Thread(target=_search_net, daemon=True)
            t.start(); t.join(timeout=3)  # Max 3 seconds
            if net_found[0]: fpath = net_found[0]

    # If still no valid file, fallback to text
    if not fpath or not os.path.exists(fpath):
        text = doc.content or "(无内容)"
        text = text.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
        html = f"<html><head><meta charset='utf-8'><style>body{{font-family:sans-serif;padding:20px;line-height:1.8;white-space:pre-wrap;word-break:break-word;max-width:900px;margin:0 auto;font-size:14px}}</style></head><body><p style='color:#e6a23c;margin-bottom:16px'>⚠️ 原始文件不在本地，仅显示提取的文字。重新上传原文件可获得完整预览。</p>{text}</body></html>"
        return HTMLResponse(html)
    ext = fpath.rsplit(".", 1)[-1].lower() if "." in fpath else ""
    html = ""

    # Word
    if ext in ("docx", "doc"):
        try:
            from docx import Document
            from docx.opc.constants import RELATIONSHIP_TYPE as RT
            import zipfile, io as _io2
            d = Document(fpath)

            # Extract images from docx zip
            image_map = {}
            try:
                with zipfile.ZipFile(fpath) as zf:
                    for name in zf.namelist():
                        if 'media' in name.lower() and any(name.lower().endswith(e) for e in ('.png','.jpg','.jpeg','.gif','.bmp','.webp')):
                            img_data = zf.read(name)
                            b64 = __import__('base64').b64encode(img_data).decode()
                            ext_i = name.rsplit('.',1)[-1].lower()
                            mime = {'png':'image/png','jpg':'image/jpeg','jpeg':'image/jpeg','gif':'image/gif','webp':'image/webp','bmp':'image/bmp'}.get(ext_i,'image/png')
                            image_map[name] = f"data:{mime};base64,{b64}"
            except: pass

            parts = ["<html><head><meta charset='utf-8'><style>body{font-family:sans-serif;padding:20px;max-width:900px;margin:0 auto}p{margin:6px 0;line-height:1.7}h1,h2,h3{margin:12px 0 6px}table{border-collapse:collapse;width:100%;margin:8px 0}td,th{border:1px solid #ddd;padding:6px;font-size:13px}img{max-width:100%;height:auto;margin:8px 0}</style></head><body>"]

            # Collect inline image references
            img_refs = set()
            for rel in d.part.rels.values():
                if "image" in str(rel.reltype):
                    img_refs.add(rel.target_ref)

            for p in d.paragraphs:
                # Check for inline images
                for run in p.runs:
                    if run._element.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}drawing'):
                        for img_path, b64 in image_map.items():
                            if img_path not in img_refs:
                                parts.append(f'<img src="{b64}" />')
                                img_refs.add(img_path)

                style = p.style.name if p.style else ""
                txt = p.text.strip()
                if not txt: parts.append("<br>"); continue
                if "Heading 1" in style: parts.append(f"<h1>{txt}</h1>")
                elif "Heading 2" in style: parts.append(f"<h2>{txt}</h2>")
                elif "Heading 3" in style: parts.append(f"<h3>{txt}</h3>")
                else: parts.append(f"<p>{txt}</p>")

            for t in d.tables:
                parts.append("<table>")
                for row in t.rows:
                    parts.append("<tr>" + "".join(f"<td>{c.text}</td>" for c in row.cells) + "</tr>")
                parts.append("</table>")

            # Append any remaining images at the end
            for ipath, b64 in image_map.items():
                if ipath not in img_refs:
                    parts.append(f'<img src="{b64}" /><br>')

            parts.append("</body></html>")
            html = "".join(parts)
        except: pass

    # Excel
    elif ext in ("xlsx", "xls"):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(fpath, data_only=True)
            parts = ["<html><head><meta charset='utf-8'><style>body{font-family:sans-serif;padding:12px}.sheet{margin-bottom:16px}h3{font-size:14px;margin:8px 0}table{border-collapse:collapse;font-size:12px;width:max-content}td,th{border:1px solid #ccc;padding:4px 8px;max-width:300px;overflow:hidden}</style></head><body>"]
            for ws in wb.worksheets:
                parts.append(f"<div class='sheet'><h3>📊 {ws.title}</h3><table>")
                for row in ws.iter_rows(values_only=True):
                    parts.append("<tr>" + "".join(f"<td>{c if c is not None else ''}</td>" for c in row) + "</tr>")
                parts.append("</table></div>")
            parts.append("</body></html>")
            html = "".join(parts)
        except: pass

    # PowerPoint — render slides as images via LibreOffice + PDF rendering
    elif ext in ("pptx", "ppt"):
        try:
            import tempfile, shutil, fitz, base64

            # Try LibreOffice headless conversion to PDF
            libre_paths = [
                r"C:\Program Files\LibreOffice\program\soffice.exe",
                r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
                "/usr/bin/soffice", "/usr/bin/libreoffice",
            ]
            libre_bin = None
            for lp in libre_paths:
                if os.path.exists(lp):
                    libre_bin = lp
                    break

            pdf_bytes = None
            if libre_bin:
                # Convert PPTX to PDF via LibreOffice headless
                tmp_dir = tempfile.mkdtemp()
                shutil.copy2(fpath, os.path.join(tmp_dir, os.path.basename(fpath)))
                try:
                    import subprocess
                    result = subprocess.run(
                        [libre_bin, "--headless", "--convert-to", "pdf", "--outdir", tmp_dir, os.path.join(tmp_dir, os.path.basename(fpath))],
                        capture_output=True, timeout=60,
                    )
                    # Find the generated PDF
                    for fname in os.listdir(tmp_dir):
                        if fname.lower().endswith(".pdf"):
                            with open(os.path.join(tmp_dir, fname), "rb") as pf:
                                pdf_bytes = pf.read()
                            break
                except Exception:
                    pass
                finally:
                    try: shutil.rmtree(tmp_dir, ignore_errors=True)
                    except: pass

            if pdf_bytes:
                # Render PDF pages as images
                pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                parts = ["<html><head><meta charset='utf-8'><style>body{background:#525659;padding:12px;text-align:center}.page{margin-bottom:8px;box-shadow:0 2px 8px rgba(0,0,0,.3)}.page img{max-width:100%;height:auto;display:block}.page-label{color:#aaa;font-size:12px;padding:4px 0}</style></head><body>"]
                for page_num in range(len(pdf_doc)):
                    page = pdf_doc[page_num]
                    pix = page.get_pixmap(dpi=150)
                    img_bytes = pix.tobytes("png")
                    b64 = base64.b64encode(img_bytes).decode()
                    parts.append(f'<div class="page"><img src="data:image/png;base64,{b64}" /></div>')
                pdf_doc.close()
                parts.append("</body></html>")
                html = "".join(parts)
            else:
                raise Exception("LibreOffice not available for PPTX conversion")

        except Exception as e:
            # Fallback: styled HTML with positioning from python-pptx
            pass

    # PDF: render pages as images for full-fidelity viewing
    elif ext == "pdf":
        try:
            import fitz  # PyMuPDF
            import base64
            pdf_doc = fitz.open(fpath)
            parts = ["<html><head><meta charset='utf-8'><style>body{background:#525659;padding:12px;text-align:center}.page{margin-bottom:8px;box-shadow:0 2px 8px rgba(0,0,0,.3)}img{max-width:100%;height:auto}</style></head><body>"]
            for page_num in range(len(pdf_doc)):
                page = pdf_doc[page_num]
                pix = page.get_pixmap(dpi=150)
                img_bytes = pix.tobytes("png")
                b64 = base64.b64encode(img_bytes).decode()
                parts.append(f'<div class="page"><img src="data:image/png;base64,{b64}" /></div>')
            pdf_doc.close()
            parts.append("</body></html>")
            html = "".join(parts)
        except:
            return download_document(doc_id, inline=True, db=db, _user=_user)

    # Images: direct serve
    elif ext in ("jpg","jpeg","png","gif","webp","bmp","svg"):
        # Return HTML wrapper with embedded image (works in iframe srcdoc)
        import base64 as _b64
        with open(fpath, "rb") as f_img:
            img_data = _b64.b64encode(f_img.read()).decode()
        mime_map = {"jpg":"image/jpeg","jpeg":"image/jpeg","png":"image/png","gif":"image/gif","webp":"image/webp","bmp":"image/bmp","svg":"image/svg+xml"}
        mime = mime_map.get(ext, "image/png")
        html = f"<html><head><meta charset='utf-8'><style>body{{margin:0;display:flex;justify-content:center;background:#f0f0f0;min-height:100vh;align-items:center}}img{{max-width:100%;max-height:95vh;object-fit:contain}}</style></head><body><img src='data:{mime};base64,{img_data}' /></body></html>"
        return HTMLResponse(html)

    # Text/code: wrap in HTML
    # CSV as table
    elif ext == "csv":
        try:
            import csv as _csv, io as _io
            for enc in ("utf-8","gbk","gb18030","latin-1"):
                try:
                    with open(fpath, "r", encoding=enc) as f_:
                        reader = _csv.reader(f_)
                        rows = list(reader)[:200]
                    break
                except: continue
            parts = ["<table style='border-collapse:collapse;font-size:12px'><thead><tr>"]
            for h in rows[0] if rows else []:
                parts.append(f"<th style='border:1px solid #ddd;padding:4px 8px;background:#f5f6f7'>{h}</th>")
            parts.append("</tr></thead><tbody>")
            for row in rows[1:]:
                parts.append("<tr>"+"".join(f"<td style='border:1px solid #eee;padding:3px 8px'>{c}</td>" for c in row)+"</tr>")
            parts.append("</tbody></table>")
            html = f"<html><head><meta charset='utf-8'><style>body{{font-family:sans-serif;padding:12px}}</style></head><body>{''.join(parts)}</body></html>"
        except: pass

    elif ext in ("txt","md","rst","py","js","ts","jsx","tsx","json","xml","yaml","yml","toml","html","htm","css","scss","less","sql","sh","bat","ps1","cmd","c","cpp","h","hpp","cs","java","go","rs","swift","kt","ini","cfg","conf","log","env"):
        for enc in ("utf-8","gbk","gb18030","latin-1"):
            try:
                with open(fpath, "r", encoding=enc, errors="replace") as f_:
                    txt = f_.read()
                break
            except: continue
        txt = txt.replace('&','&amp;').replace('<','&lt;')
        html = f"<html><head><meta charset='utf-8'><style>body{{font-family:'Consolas','Courier New',monospace;padding:20px;white-space:pre-wrap;line-height:1.6;font-size:13px;background:#1e1e1e;color:#d4d4d4}}</style></head><body>{txt}</body></html>"
        return HTMLResponse(html)

    if html:
        return HTMLResponse(html)

    # Image types not in the exact list
    if ext in ("svg","ico","tiff","tif"):
        from fastapi.responses import FileResponse
        return FileResponse(fpath)

    # For all other formats, serve the raw file inline
    # Browsers can natively render many types (videos, audio, etc.)
    # If they can't, they'll show a download prompt
    mime, _ = __import__('mimetypes').guess_type(fpath)
    if mime:
        from fastapi.responses import FileResponse
        return FileResponse(fpath, media_type=mime, headers={"Content-Disposition": "inline"})

    # Last resort: show file info + download link
    size_mb = os.path.getsize(fpath) / (1024*1024) if os.path.exists(fpath) else 0
    html = f"""<html><head><meta charset='utf-8'><style>body{{font-family:sans-serif;padding:40px;text-align:center}}
    .box{{border:1px solid #e5e6e8;border-radius:12px;padding:40px;max-width:400px;margin:0 auto}}
    h2{{margin:0 0 8px}}p{{color:#646a73;margin:4px 0}}
    a{{display:inline-block;margin-top:16px;padding:10px 24px;background:#3370ff;color:#fff;border-radius:6px;text-decoration:none;font-size:14px}}</style></head><body>
    <div class='box'><h2>{doc.name}</h2><p>类型: .{ext} | 大小: {size_mb:.1f} MB</p>
    <p style='color:#8f959e'>此格式不支持在线预览</p>
    <a href='/api/knowledge/download/{doc.id}'>下载原文件</a></div></body></html>"""
    return HTMLResponse(html)


@router.get("/download/{doc_id}")
def download_document(doc_id: int, inline: bool = Query(False), token: str = Query(""), db: Session = Depends(get_db), _user=Depends(get_optional_user)):
    """Download or inline-view the original uploaded file. token param for iframe access."""
    from fastapi.responses import FileResponse
    doc = db.get(ProjectDocument, doc_id)
    if not doc: raise HTTPException(404, detail="文档不存在")
    # Permission: only full access can download
    user = _user
    if token:
        # token 参数用于纯链接/iframe（无 Authorization 头），解析为真实用户
        try:
            payload = verify_token(token)
            if payload.get("type") != "access":
                raise HTTPException(401, "请使用 access_token")
            user = db.execute(select(UserAuth).where(
                UserAuth.username == payload["sub"], UserAuth.is_active == True
            )).scalar_one_or_none()
            if user is None:
                raise HTTPException(401, "用户不存在或已禁用")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(401, "需要登录")
    access = _get_doc_access_level(doc, user, db) if user else ACCESS_NONE
    if access != ACCESS_FULL:
        raise HTTPException(403, detail="无权下载此文档（需要完整访问权限）")
    fpath = doc.file_path
    if fpath:
        from pathlib import Path as _P
        upload_root = _P(settings.UPLOAD_DIR).parent
        full = upload_root / fpath
        if full.exists():
            fpath = str(full)
    if not fpath or not os.path.exists(fpath):
        raise HTTPException(404, detail="原始文件不存在")

    # Determine media type from actual file path (name may not have extension)
    actual_name = os.path.basename(fpath).lower()
    media_map = {'.pdf':'application/pdf','.jpg':'image/jpeg','.jpeg':'image/jpeg','.png':'image/png',
                 '.gif':'image/gif','.webp':'image/webp','.txt':'text/plain','.csv':'text/csv',
                 '.md':'text/markdown','.json':'application/json','.xml':'text/xml','.html':'text/html'}
    ext = '.' + actual_name.rsplit('.',1)[-1] if '.' in actual_name else ''
    media_type = media_map.get(ext, 'application/octet-stream')

    headers = {}
    if inline:
        headers['Content-Disposition'] = 'inline'
    return FileResponse(fpath, filename=os.path.basename(fpath),
                        media_type=media_type, headers=headers)

@router.get("/documents/{doc_id}")
def get_document_full(doc_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Get full document content — permission-checked with access levels."""
    doc = db.get(ProjectDocument, doc_id)
    if not doc: raise HTTPException(404, detail="文档不存在")
    access = _get_doc_access_level(doc, _user, db)
    if access == ACCESS_NONE:
        raise HTTPException(403, detail="无权访问此文档")
    meta = {}
    try: meta = json.loads(doc.notes or "{}")
    except: pass
    return {
        "id": doc.id, "title": doc.name, "category": doc.doc_type,
        "content": _truncate_for_level(doc.content or "", access),
        "access_level": access,
        "folder": meta.get("folder", "/"), "tags": meta.get("tags", []),
        "space": meta.get("space", "default"), "file_path": doc.file_path,
        "owner": meta.get("owner", ""), "visibility": meta.get("visibility", "shared"),
        "owner_id": doc.owner_id,
        "created_at": doc.upload_date.isoformat() if doc.upload_date else None,
    }

@router.get("/documents/{doc_id}/versions")
def doc_versions(doc_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    ver_file = os.path.join(VERSION_DIR, f"{doc_id}.json")
    try:
        with open(ver_file, "r", encoding="utf-8") as f: return json.load(f)
    except: return []

@router.post("/documents/{doc_id}/save-version")
def save_doc_version(doc_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    doc = db.execute(select(ProjectDocument).where(ProjectDocument.id == doc_id)).scalar_one_or_none()
    if not doc: raise HTTPException(404, detail="文档不存在")
    snapshot = {"title": doc.name, "content_preview": (doc.content or "")[:500],
                "saved_by": _user.get("username", ""), "ts": datetime.utcnow().isoformat()}
    os.makedirs(VERSION_DIR, exist_ok=True)
    ver_file = os.path.join(VERSION_DIR, f"{doc_id}.json")
    versions = []
    if os.path.exists(ver_file):
        with open(ver_file, "r", encoding="utf-8") as f: versions = json.load(f)
    versions.insert(0, snapshot)
    if len(versions) > 20: versions = versions[:20]
    atomic_write(ver_file, versions)
    return {"version": snapshot, "total": len(versions)}


# ═══════════════════════════════════════════
# ── Health Dashboard ──
# ═══════════════════════════════════════════

@router.get("/health")
def knowledge_health(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    docs = db.execute(select(ProjectDocument).order_by(ProjectDocument.id.desc()).limit(500)).scalars().all()
    if not docs: return {"score": 0, "message": "知识库为空"}
    total = len(docs); total_chars = sum(len(d.content or "") for d in docs)
    with_tags = 0
    for d in docs:
        try: meta = json.loads(d.notes or "{}"); tags = meta.get("tags", []); with_tags += 1 if tags else 0
        except: pass
    categories = set(d.doc_type for d in docs if d.doc_type)
    dates = [d.upload_date for d in docs if d.upload_date]
    days_span = (max(dates) - min(dates)).days + 1 if dates else 0
    recent_7 = sum(1 for d in docs if d.upload_date and (datetime.now().date() - d.upload_date).days <= 7)
    cov = min(100, len(categories) * 15); cont = min(100, int(total_chars / 50000 * 100))
    tag_s = min(100, int(with_tags / max(total, 1) * 100)); rec = min(100, recent_7 * 10)
    avg = total_chars // max(total, 1)
    suggestions = []
    if total < 10: suggestions.append("上传更多文档丰富知识库")
    if with_tags < total * 0.5: suggestions.append(f"为文档添加标签（当前{with_tags}/{total}）")
    if len(categories) < 3: suggestions.append("覆盖更多类别")
    if recent_7 == 0: suggestions.append("近期无更新，建议上传新文档")
    return {"total_docs": total, "total_chars": total_chars, "avg_chars_per_doc": avg,
            "categories": sorted(categories), "days_span": days_span, "recent_7_days": recent_7,
            "tag_coverage_pct": round(with_tags / max(total, 1) * 100, 1),
            "scores": {"覆盖度": cov, "内容丰富度": cont, "标签化率": tag_s, "更新频率": rec},
            "total_score": round((cov + cont + tag_s + rec) / 4, 1), "suggestions": suggestions}


# ═══════════════════════════════════════════
# ── Batch Export ──
# ═══════════════════════════════════════════

@router.post("/export")
def export_knowledge(data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    doc_ids = data.get("doc_ids", []); space_id = data.get("space_id"); fmt = data.get("format", "json")
    if doc_ids:
        docs = db.execute(select(ProjectDocument).where(ProjectDocument.id.in_(doc_ids))).scalars().all()
    else:
        q = select(ProjectDocument).order_by(ProjectDocument.id.desc()).limit(500)
        docs = list(db.execute(q).scalars().all())
        if space_id:
            docs = [d for d in docs if (lambda m: m.get("space","default")==space_id)(json.loads(d.notes or "{}") or {})]
    if fmt == "markdown":
        lines = [f"# 知识库导出\n导出时间: {datetime.utcnow().isoformat()}\n文档数: {len(docs)}\n"]
        for d in docs:
            meta = {}
            try: meta = json.loads(d.notes or "{}")
            except: pass
            lines.append(f"## {d.name}")
            lines.append(f"- 类型: {d.doc_type or '通用'} | 标签: {', '.join(meta.get('tags',[]))}")
            lines.append(f"\n{d.content or '(无内容)'}\n")
        return {"content": "\n\n".join(lines), "format": "markdown"}
    if fmt == "excel":
        import openpyxl, io as _io
        wb = openpyxl.Workbook(); ws = wb.active; ws.title = "知识库文档"
        from openpyxl.styles import Font, PatternFill
        hdr_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
        hdr_font = Font(color="FFFFFF", bold=True)
        headers = ["序号","文档名称","类型","标签","文件夹","字数","上传日期","内容摘要"]
        for i, h in enumerate(headers, 1):
            c = ws.cell(row=1, column=i, value=h); c.fill = hdr_fill; c.font = hdr_font
        for ri, d in enumerate(docs, 2):
            meta = {}
            try: meta = json.loads(d.notes or "{}")
            except: pass
            ws.cell(row=ri, column=1, value=ri-1)
            ws.cell(row=ri, column=2, value=d.name)
            ws.cell(row=ri, column=3, value=d.doc_type or "通用")
            ws.cell(row=ri, column=4, value=", ".join(meta.get("tags",[])))
            ws.cell(row=ri, column=5, value=meta.get("folder","/"))
            ws.cell(row=ri, column=6, value=len(d.content or ""))
            ws.cell(row=ri, column=7, value=d.upload_date.isoformat() if d.upload_date else "")
            ws.cell(row=ri, column=8, value=(d.content or "")[:200])
        for col in range(1,9): ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = 20
        ws.column_dimensions['B'].width = 40; ws.column_dimensions['H'].width = 40
        ws.auto_filter.ref = f"A1:H{len(docs)+1}"
        buf = _io.BytesIO(); wb.save(buf); buf.seek(0)
        return {"content": buf.read().hex(), "format": "excel", "filename": f"知识库导出_{datetime.utcnow().strftime('%Y%m%d')}.xlsx", "binary": True}
    result = [{"id": d.id, "title": d.name, "type": d.doc_type,
               "tags": (json.loads(d.notes or "{}") or {}).get("tags", []),
               "content": (d.content or "")[:5000],
               "date": d.upload_date.isoformat() if d.upload_date else None} for d in docs]
    return {"content": json.dumps(result, ensure_ascii=False, indent=2), "format": "json", "count": len(result)}


# ═══════════════════════════════════════════
# ── Tag Merge ──
# ═══════════════════════════════════════════

@router.post("/tags/merge")
def merge_tags(data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    src = data.get("source_tag", "").strip(); dst = data.get("target_tag", "").strip()
    if not src or not dst: raise HTTPException(400, detail="需要source_tag和target_tag")
    docs = db.execute(select(ProjectDocument)).scalars().all()
    updated = 0
    for d in docs:
        meta = {}
        try: meta = json.loads(d.notes or "{}")
        except: pass
        tags = meta.get("tags", [])
        if src in tags:
            tags = [dst if t == src else t for t in tags]
            tags = list(set(tags))
            meta["tags"] = tags; d.notes = json.dumps(meta, ensure_ascii=False); updated += 1
    if updated: db.commit()
    return {"merged": updated, "from": src, "to": dst}


# ═══════════════════════════════════════════
# ── External Knowledge Integration ──
# ═══════════════════════════════════════════

@router.post("/reprocess-ocr")
def reprocess_ocr(data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Re-extract text from existing docs with OCR, for image-based PDFs."""
    doc_ids = data.get("doc_ids", [])
    limit = data.get("limit", 20)
    docs = []
    if doc_ids:
        for did in doc_ids:
            d = db.get(ProjectDocument, did)
            if d: docs.append(d)
    else:
        # Find docs with very short content (likely image-based PDFs)
        all_docs = db.execute(select(ProjectDocument).order_by(ProjectDocument.id.desc()).limit(200)).scalars().all()
        for d in all_docs:
            if d.name.lower().endswith(".pdf") and len(d.content or "") < 200:
                docs.append(d)
        docs = docs[:limit]

    if not docs:
        return {"ok": True, "processed": 0, "msg": "没有找到需要OCR的文档"}

    processed = 0
    for d in docs:
        try:
            # Re-extract from original source if available, or re-read file
            meta = {}
            try: meta = json.loads(d.notes or "{}")
            except: pass
            src = meta.get("source", "")
            fname = meta.get("filename", d.name)
            new_text = ""

            if d.file_path and os.path.exists(d.file_path):
                with open(d.file_path, "rb") as f:
                    new_text = extract_text(f.read(), fname)
            elif src and src.startswith("network:") and os.path.exists(src[8:]):
                # Original network source still exists
                fpath = os.path.join(src[8:], fname)
                if os.path.exists(fpath):
                    with open(fpath, "rb") as f:
                        new_text = extract_text(f.read(), fname)
                else:
                    # Search for file in network path
                    net_dir = src[8:]
                    for root, dirs, files in os.walk(net_dir):
                        if fname in files:
                            with open(os.path.join(root, fname), "rb") as f:
                                new_text = extract_text(f.read(), fname)
                            break

            if new_text and len(new_text) > 50 and not new_text.startswith("PDF文档:"):
                d.content = new_text
                db.commit()
                processed += 1
        except Exception as e:
            pass

    return {"ok": True, "processed": processed, "total_checked": len(docs)}


@router.post("/import-url")
def import_url(data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Import webpage content from URL into knowledge base."""
    url = data.get("url", "").strip()
    if not url: raise HTTPException(400, detail="请输入URL")
    category = data.get("category", "技术类")
    folder = data.get("folder", "/")
    space = data.get("space", "default")
    tags = data.get("tags", [])

    # Fetch URL content
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=15).read()
        # Simple HTML to text
        from html.parser import HTMLParser
        class TextExtractor(HTMLParser):
            def __init__(self): super().__init__(); self.text = []
            def handle_data(self, d): self.text.append(d.strip())
        parser = TextExtractor()
        try: parser.feed(html.decode("utf-8"))
        except: parser.feed(html.decode("gbk", errors="replace"))
        text = "\n".join([t for t in parser.text if t])[:30000]
        # Extract title
        title = url.split("/")[-1][:60] or url[:60]
        import re
        match = re.search(r'<title>(.+?)</title>', html.decode("utf-8", errors="replace"), re.I)
        if match: title = match.group(1)[:80]
    except Exception as e:
        raise HTTPException(400, detail=f"抓取失败: {str(e)[:100]}")

    if not text.strip():
        raise HTTPException(400, detail="页面无文本内容")

    # Auto-generate tags
    ai_tags = auto_generate_tags(text[:3000], title)

    # Save
    kb_project = db.execute(select(Project).where(Project.name == "__knowledge_base__")).scalar_one_or_none()
    if not kb_project:
        kb_project = Project(name="__knowledge_base__", code="__KB__", overall_status="active")
        db.add(kb_project); db.commit(); db.refresh(kb_project)

    doc = ProjectDocument(
        project_id=kb_project.id, name=title, doc_type=category,
        content=text, file_path=None, folder=_norm_folder(folder),
        space_id=space,
        notes=json.dumps({"folder": _norm_folder(folder), "tags": tags or ai_tags, "space": space, "source_url": url}),
        upload_date=datetime.now().date(),
    )
    db.add(doc); db.commit(); db.refresh(doc)

    # Vectorize
    try:
        vecs = _load_vectors()
        vecs[str(doc.id)] = _get_embedding(text[:2000])
        _save_vectors(vecs)
    except: pass

    return {"ok": True, "id": doc.id, "title": title, "tags": ai_tags, "url": url}


@router.post("/qa-web")
def qa_with_web_search(data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Enhanced Q&A with optional web search fallback."""
    question = data.get("question", "")
    use_web = data.get("use_web", False)
    if not question: return {"answer": "请输入问题", "sources": []}

    # First try local knowledge base
    local_result = None
    try:
        from fastapi import Query
        all_docs = list(db.execute(select(ProjectDocument).order_by(ProjectDocument.id.desc()).limit(100)).scalars().all())
        if all_docs:
            # Quick keyword match
            kw_docs = _keyword_search(question, all_docs, top_k=5)
            if kw_docs:
                parts = [f"### 《{d.name}》\n{(d.content or '')[:1000]}" for d in kw_docs[:5]]
                local_result = "\n\n".join(parts)[:8000]
    except: pass

    # Web search fallback
    web_result = ""
    if use_web:
        try:
            import urllib.request, urllib.parse
            q = urllib.parse.quote(question[:200])
            url = f"https://html.duckduckgo.com/html/?q={q}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            html = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", errors="replace")
            # Extract snippets
            import re
            snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
            web_text = "\n".join([re.sub(r'<[^>]+>', '', s).strip() for s in snippets[:8]])[:5000]
            if web_text.strip():
                web_result = f"## 网络搜索结果\n{web_text}"
        except: pass

    if not local_result and not web_result:
        return {"answer": "未找到相关信息。请尝试上传相关文档到知识库，或启用网络搜索。", "sources": []}

    context = (local_result or "") + "\n\n" + web_result
    prompt = f"""你是知识问答助手。基于以下信息回答用户问题。

{("优先使用本地知识库文档，网络搜索结果为补充参考。" if web_result else "基于本地知识库文档回答。")}

{context}

用户问题: {question}

请用中文回答。如有引用来源请标注。"""

    try:
        answer = _call_llm_sync([
            {"role":"system","content":"你是知识问答助手。基于提供的信息回答。使用中文。"},
            {"role":"user","content":prompt}
        ])
        return {"answer": answer, "sources": [],
                "has_local": bool(local_result), "has_web": bool(web_result)}
    except Exception as e:
        return {"answer": f"[AI问答暂不可用: {str(e)[:100]}]", "sources": []}


# ═══════════════════════════════════════════
# ── External Data Sources ──
# ═══════════════════════════════════════════

EXTSRC_FILE = os.path.join(settings.UPLOAD_DIR, "..", "data", "kb_external_sources.json")

def _load_sources():
    return safe_load(EXTSRC_FILE, [])

def _save_sources(srcs):
    safe_save(EXTSRC_FILE, srcs)


@router.get("/external-sources")
def list_external_sources(_user=Depends(get_current_user)):
    return _load_sources()


@router.post("/external-sources")
def add_external_source(data: dict, _user=Depends(get_current_user)):
    """Add an external data source: dingtalk / network_folder / webdav.
    data: {type: 'dingtalk'|'network'|'webdav', name, config: {...}, sync_interval_hours}"""
    stype = data.get("type", "").strip()
    if stype not in ("dingtalk", "network", "webdav"):
        raise HTTPException(400, detail="type must be: dingtalk, network, webdav")
    name = data.get("name", "").strip() or stype
    src = {
        "id": uuid.uuid4().hex[:8],
        "type": stype,
        "name": name,
        "config": data.get("config", {}),
        "sync_interval_hours": data.get("sync_interval_hours", 24),
        "enabled": data.get("enabled", True),
        "last_sync": None,
        "doc_count": 0,
        "created_at": datetime.utcnow().isoformat(),
    }
    srcs = _load_sources()
    srcs.append(src)
    _save_sources(srcs)
    return src


@router.put("/external-sources/{src_id}")
def update_external_source(src_id: str, data: dict, _user=Depends(get_current_user)):
    srcs = _load_sources()
    for s in srcs:
        if s["id"] == src_id:
            for k in ("name", "config", "sync_interval_hours", "enabled"):
                if k in data: s[k] = data[k]
            _save_sources(srcs)
            return s
    raise HTTPException(404, detail="数据源不存在")


@router.delete("/external-sources/{src_id}")
def delete_external_source(src_id: str, _user=Depends(get_current_user)):
    srcs = _load_sources()
    srcs = [s for s in srcs if s["id"] != src_id]
    _save_sources(srcs)
    return {"ok": True}


@router.post("/external-sources/{src_id}/sync")
def sync_external_source(src_id: str, db: Session = Depends(get_db), _user=Depends(get_current_user), async_mode: bool = Query(False)):
    """Manually trigger sync from an external source. async_mode=True returns immediately."""
    if async_mode:
        import threading
        from backend_v2.database import SessionLocal as _SL
        def _bg_sync():
            bg_db = _SL()
            try:
                _sync_impl(src_id, bg_db)
            finally:
                bg_db.close()
        threading.Thread(target=_bg_sync, daemon=True).start()
        return {"ok": True, "async": True, "msg": "后台同步已启动"}

    return _sync_impl(src_id, db)


def _sync_impl(src_id: str, db):
    srcs = _load_sources()
    src = next((s for s in srcs if s["id"] == src_id), None)
    if not src: raise HTTPException(404, detail="数据源不存在")

    imported_count = 0; messages = []
    cfg = src.get("config", {})

    if src["type"] == "dingtalk":
        # DingTalk: try to pull from DingTalk API or use webhook config
        webhook = cfg.get("webhook_url", "")
        app_key = cfg.get("app_key", "")
        app_secret = cfg.get("app_secret", "")
        if not app_key:
            messages.append("钉钉需配置 AppKey/AppSecret 才能拉取文档。已配置 Webhook 仅用于推送。")
        else:
            # Try to get DingTalk access_token and pull department docs
            try:
                import urllib.request
                tk_url = f"https://oapi.dingtalk.com/gettoken?appkey={app_key}&appsecret={app_secret}"
                tk_resp = json.loads(urllib.request.urlopen(tk_url, timeout=10).read())
                if tk_resp.get("errcode") == 0:
                    token = tk_resp["access_token"]
                    # Get department list
                    dept_url = f"https://oapi.dingtalk.com/topapi/v2/department/listsub?access_token={token}"
                    dept_req = urllib.request.Request(dept_url, data=b"{}", headers={"Content-Type":"application/json"})
                    depts = json.loads(urllib.request.urlopen(dept_req, timeout=10).read())
                    messages.append(f"钉钉连接成功: {len(depts.get('result',[]))} 个部门")
                    # For now, just verify connection works
                    imported_count += 1
                else:
                    messages.append(f"钉钉认证失败: {tk_resp.get('errmsg','')}")
            except Exception as e:
                messages.append(f"钉钉连接失败: {str(e)[:100]}")

    elif src["type"] == "network":
        # Network folder: scan and import files
        path = cfg.get("path", "")
        if not path:
            messages.append("请配置网络文件夹路径")
        elif not os.path.exists(path):
            # Try to diagnose the issue
            messages.append(f"路径不可达: {path}")
            if path.startswith("\\\\") or path.startswith("//"):
                messages.append("提示: 网络共享路径需要确保服务器有访问权限，请检查网络连接和共享凭据")
            elif not os.path.isabs(path):
                messages.append("提示: 请使用绝对路径（如 D:\\共享\\文档 或 \\\\server\\share）")
            # Try listing parent dir to see if it's accessible
            parent = os.path.dirname(path)
            if parent and os.path.exists(parent):
                messages.append(f"上级目录可访问但目标路径不存在: {parent}")
        else:
            imported = 0; skipped_dup = 0; skipped_parse = 0; skipped_size = 0
            total_scanned = 0
            for root, dirs, files in os.walk(path):
                for fname in files:
                    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
                    if ext not in ("pdf","docx","doc","xlsx","xls","pptx","ppt","txt","csv","md"):
                        continue
                    if ext in ("mp4","mp3","avi","mov","wav"): continue
                    total_scanned += 1
                    fpath = os.path.join(root, fname)
                    err = None
                    try:
                        fsize = os.path.getsize(fpath)
                        max_size = _load_prompt_config().get("max_file_size_mb", 50) * 1024 * 1024
                        if fsize > max_size:
                            messages.append(f"跳过(>{max_size//1024//1024}MB): {os.path.basename(fname)}")
                            skipped_size += 1
                            continue
                        with open(fpath, "rb") as f:
                            content = f.read()
                        text = extract_text(content, fname)
                        if not text or (text.startswith("[") and text.endswith("]")):
                            err = f"无法解析: {fname}"
                            skipped_parse += 1
                            continue
                        # Use keyword-based tags (fast, no AI call needed)
                        tags = []
                        for cat, kws in CATEGORY_KEYWORDS.items():
                            for kw in kws:
                                if kw in text[:2000] and kw not in tags:
                                    tags.append(kw)
                                    if len(tags) >= 5: break
                            if len(tags) >= 5: break
                        if not tags:
                            tags = [ext.upper() + "文档"]
                        rel_path = os.path.relpath(fpath, path)
                        folder = "/" + os.path.dirname(rel_path).replace("\\", "/")

                        kb_project = db.execute(select(Project).where(Project.name == "__knowledge_base__")).scalar_one_or_none()
                        if not kb_project:
                            kb_project = Project(name="__knowledge_base__", code="__KB__", overall_status="active")
                            db.add(kb_project); db.commit(); db.refresh(kb_project)

                        existing = db.execute(select(ProjectDocument).where(
                            ProjectDocument.name == fname,
                            ProjectDocument.project_id == kb_project.id
                        )).scalar_one_or_none()
                        if existing: skipped_dup += 1; continue

                        # Save a local copy for preview
                        import shutil as _shutil
                        local_dir = os.path.join(settings.UPLOAD_DIR, "knowledge")
                        os.makedirs(local_dir, exist_ok=True)
                        local_name = f"{uuid.uuid4().hex[:8]}_{fname}"
                        local_path = os.path.join(local_dir, local_name)
                        _shutil.copy2(fpath, local_path)

                        # Use source's configured space
                        space_id = src.get("space", "default")

                        doc = ProjectDocument(
                            project_id=kb_project.id, name=fname, doc_type="技术类",
                            content=text, file_path=local_path, folder=_norm_folder(folder),
                            notes=json.dumps({"folder": _norm_folder(folder), "tags": tags, "space": space_id,
                                              "source": f"network:{path}", "filename": fname}, ensure_ascii=False),
                            upload_date=datetime.now().date(),
                        )
                        db.add(doc); db.commit(); imported += 1
                        _auto_register_folder(_norm_folder(folder))
                    except Exception as ex:
                        err = f"{fname}: {str(ex)[:80]}"
                    if err: messages.append(err)
            # Build detailed summary
            parts = [f"扫描 {total_scanned} 个文件，导入 {imported} 个新文档"]
            if skipped_dup: parts.append(f"{skipped_dup} 个已存在(跳过)")
            if skipped_parse: parts.append(f"{skipped_parse} 个无法解析")
            if skipped_size: parts.append(f"{skipped_size} 个超大(>30MB)")
            messages.append("；".join(parts))
            imported_count = imported

    elif src["type"] == "webdav":
        messages.append("WebDAV 连接暂未实现，请使用网络文件夹方式")

    # Update last sync
    for s in srcs:
        if s["id"] == src_id:
            s["last_sync"] = datetime.utcnow().isoformat()
            s["doc_count"] = (s.get("doc_count", 0) + imported_count)
    _save_sources(srcs)

    return {"ok": True, "imported": imported_count, "messages": messages}


# ═══════════════════════════════════════════
# ── DingTalk Config Helper ──
# ═══════════════════════════════════════════

@router.get("/dingtalk-config")
def get_dingtalk_config(_user=Depends(get_current_user)):
    """Get current DingTalk configuration status."""
    config_file = os.path.join(settings.UPLOAD_DIR, "..", "dingtalk_config.json")
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            return {"configured": bool(cfg.get("webhook_url")), "has_app_key": bool(cfg.get("app_key")),
                    "webhook_url": cfg.get("webhook_url","")[:30]+"..." if cfg.get("webhook_url") else ""}
    except:
        return {"configured": False, "has_app_key": False, "webhook_url": ""}


@router.put("/dingtalk-config")
def update_dingtalk_config(data: dict, _user=Depends(get_current_user)):
    """Update DingTalk configuration."""
    config_file = os.path.join(settings.UPLOAD_DIR, "..", "dingtalk_config.json")
    cfg = {}
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except: pass
    for k in ("webhook_url", "app_key", "app_secret"):
        if k in data: cfg[k] = data[k]
    atomic_write(config_file, cfg)
    return {"ok": True, "configured": bool(cfg.get("webhook_url"))}


# ═══════════════════════════════════════════
# ── Bidirectional Links ──
# ═══════════════════════════════════════════

import re as _re_mod

def _parse_wikilinks(text: str) -> list:
    """Extract [[target]] and [[target|alias]] from text."""
    return [(m.group(1).split('|')[0].strip(), m.group(1).split('|')[1].strip() if '|' in m.group(1) else m.group(1).strip())
            for m in _re_mod.finditer(r'\[\[(.+?)\]\]', text or '')]


@router.get("/documents/{doc_id}/links")
def get_doc_links(doc_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Get outgoing links from a document ([[links]] in content)."""
    doc = db.execute(select(ProjectDocument).where(ProjectDocument.id == doc_id)).scalar_one_or_none()
    if not doc: raise HTTPException(404, detail="文档不存在")
    content = doc.content or ""
    raw_links = _parse_wikilinks(content)
    # Try to resolve to real doc IDs
    all_docs = list(db.execute(select(ProjectDocument).order_by(ProjectDocument.id.desc()).limit(200)).scalars().all())
    links = []
    for target, alias in raw_links:
        matched = None
        for d in all_docs:
            if d.name == target or (d.name or "").startswith(target):
                matched = d; break
        links.append({"target": target, "alias": alias,
                       "resolved_id": matched.id if matched else None,
                       "resolved_title": matched.name if matched else None})
    return {"links": links, "count": len(links)}


@router.get("/documents/{doc_id}/backlinks")
def get_doc_backlinks(doc_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Get backlinks: documents that link TO this document via [[doc_name]]."""
    doc = db.execute(select(ProjectDocument).where(ProjectDocument.id == doc_id)).scalar_one_or_none()
    if not doc: raise HTTPException(404, detail="文档不存在")
    all_docs = db.execute(select(ProjectDocument).order_by(ProjectDocument.id.desc()).limit(200)).scalars().all()
    backlinks = []
    for d in all_docs:
        if d.id == doc_id: continue
        links = _parse_wikilinks(d.content or "")
        targets = [t for t, a in links]
        if doc.name in targets or any(doc.name.startswith(t) for t in targets):
            backlinks.append({"id": d.id, "title": d.name,
                               "matched": next((t for t in targets if doc.name == t or doc.name.startswith(t)), doc.name)})
    return {"backlinks": backlinks, "count": len(backlinks)}


# ═══════════════════════════════════════════════════════
# ── Personal Knowledge Base (user-owned private spaces) ──
# ═══════════════════════════════════════════════════════

@router.get("/my-documents")
def list_my_documents(limit: int = Query(100), folder: str = Query(None), db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """List current user's private documents + shared ones."""
    q = select(ProjectDocument).order_by(ProjectDocument.id.desc()).limit(500)
    docs = db.execute(q).scalars().all()
    results = []
    user_id = _user.id if hasattr(_user, 'id') else _user.get('id','')
    for d in docs:
        meta = {}
        try: meta = json.loads(d.notes or "{}")
        except: pass
        owner = meta.get("owner", "")
        visibility = meta.get("visibility", "shared")
        # Folder filter
        if folder:
            df = meta.get("folder", "/")
            if df != folder and not df.startswith(folder + "/"):
                continue
        # Show: shared docs OR user's own docs
        if visibility == "shared" or str(owner) == str(user_id):
            results.append({
                "id": d.id, "title": d.name, "doc_type": d.doc_type,
                "folder": meta.get("folder", "/"), "tags": meta.get("tags", []),
                "space": meta.get("space", "default"),
                "owner": str(owner), "visibility": visibility,
                "content": (d.content or "")[:500],
                "created_at": d.upload_date.isoformat() if d.upload_date else None,
            })
    return results[:limit]

@router.put("/documents/{doc_id}/visibility")
def toggle_doc_visibility(doc_id: int, data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Toggle document visibility between 'shared' and 'private'."""
    doc = db.get(ProjectDocument, doc_id)
    if not doc: raise HTTPException(404, detail="文档不存在")
    meta = {}
    try: meta = json.loads(doc.notes or "{}")
    except: pass
    user_id = _user.id if hasattr(_user, 'id') else _user.get('id','')
    meta["owner"] = str(user_id)
    meta["visibility"] = data.get("visibility", "private")
    doc.notes = json.dumps(meta, ensure_ascii=False)
    db.commit()
    return {"ok": True, "visibility": meta["visibility"]}


# ═══════════════════════════════
# ── Note Editor (Markdown notes) ──
# ═══════════════════════════════

NOTES_FILE = os.path.join(settings.UPLOAD_DIR, "..", "data", "kb_notes.json")

def _load_notes():
    return safe_load(NOTES_FILE, [])

def _save_notes(notes):
    safe_save(NOTES_FILE, notes)

@router.get("/notes")
def list_notes(space: str = Query("default"), db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """List all notes."""
    notes = _load_notes()
    user_id = str(_user.id) if hasattr(_user, 'id') else ''
    return [n for n in notes if n.get("space") == space and (n.get("owner","") == user_id or n.get("visibility") == "shared")]

@router.post("/notes")
def create_note(data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Create a new markdown note."""
    import uuid
    notes = _load_notes()
    user_id = str(_user.id) if hasattr(_user, 'id') else ''
    note = {
        "id": str(uuid.uuid4())[:8],
        "title": data.get("title", "未命名笔记"),
        "content": data.get("content", ""),
        "space": data.get("space", "default"),
        "folder": data.get("folder", "/"),
        "tags": data.get("tags", []),
        "owner": user_id,
        "visibility": data.get("visibility", "private"),
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    notes.append(note)
    _save_notes(notes)
    return note

@router.put("/notes/{note_id}")
def update_note(note_id: str, data: dict, _user=Depends(get_current_user)):
    """Update a markdown note (title, content, tags, folder)."""
    notes = _load_notes()
    for n in notes:
        if n["id"] == note_id:
            for k in ("title","content","tags","folder","visibility"):
                if k in data: n[k] = data[k]
            n["updated_at"] = datetime.utcnow().isoformat()
            _save_notes(notes)
            return n
    raise HTTPException(404, detail="笔记不存在")

@router.delete("/notes/{note_id}")
def delete_note(note_id: str, _user=Depends(get_current_user)):
    notes = _load_notes()
    _save_notes([n for n in notes if n["id"] != note_id])
    return {"ok": True}


# ═══════════════════════════
# ── Web Clipper (bookmarklet) ──
# ═══════════════════════════

@router.post("/clip-url")
def clip_url(data: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Enhanced URL clipping with readability-like extraction."""
    url = data.get("url", "").strip()
    if not url: raise HTTPException(400, detail="请提供URL")

    # Fetch and extract content
    try:
        import urllib.request as _ureq
        import ssl
        from html.parser import HTMLParser

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        req = _ureq.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Encoding": "identity"  # Prevent gzip for simplicity
        })
        resp = _ureq.urlopen(req, timeout=15, context=ctx)
        raw = resp.read()
        # Try to decompress if gzipped
        try:
            import gzip
            raw = gzip.decompress(raw)
        except: pass
        html = raw.decode("utf-8", errors="replace")

        # Extract title
        title = ""
        tmatch = __import__('re').search(r'<title[^>]*>(.*?)</title>', html, __import__('re').IGNORECASE | __import__('re').DOTALL)
        if tmatch: title = tmatch.group(1).strip()[:200]

        # Strip HTML tags for clean text
        clean = __import__('re').sub(r'<script[^>]*>.*?</script>', '', html, flags=__import__('re').IGNORECASE | __import__('re').DOTALL)
        clean = __import__('re').sub(r'<style[^>]*>.*?</style>', '', clean, flags=__import__('re').IGNORECASE | __import__('re').DOTALL)
        clean = __import__('re').sub(r'<[^>]+>', ' ', clean)
        clean = __import__('re').sub(r'\s+', ' ', clean).strip()[:30000]

        # Extract description from meta
        desc = ""
        dmatch = __import__('re').search(r'<meta[^>]*name="description"[^>]*content="([^"]*)"', html, __import__('re').IGNORECASE)
        if dmatch: desc = dmatch.group(1)[:500]

        # Auto-tag based on content keywords
        tags = []
        kw_map = {"电机": "电机", "驱": "驱动", "控制": "控制", "AI": "AI", "仿真": "仿真",
                  "设计": "设计", "测试": "测试", "制造": "制造", "电源": "电源"}
        for kw, tag in kw_map.items():
            if kw.lower() in clean[:3000].lower() and tag not in tags:
                tags.append(tag)
                if len(tags) >= 5: break

    except Exception as e:
        raise HTTPException(400, detail=f"抓取失败: {str(e)[:100]}")

    # Save as document
    user_id = str(_user.id) if hasattr(_user, 'id') else ''
    kb_project = db.execute(select(Project).where(Project.name == "__knowledge_base__")).scalar_one_or_none()
    if not kb_project:
        kb_project = Project(name="__knowledge_base__", code="__KB__", overall_status="active")
        db.add(kb_project); db.commit(); db.refresh(kb_project)

    doc_folder = _norm_folder(data.get("folder", "/网页剪藏"))
    doc_space = data.get("space", "default")
    doc_vis = data.get("visibility", "private")
    doc = ProjectDocument(
        project_id=kb_project.id, name=title or url[:80], doc_type="网页剪藏",
        content=clean, folder=doc_folder,
        space_id=doc_space,
        ext_visibility=doc_vis,
        owner_id=int(user_id) if user_id and str(user_id).isdigit() else None,
        notes=json.dumps({
            "folder": doc_folder, "tags": tags,
            "space": doc_space, "source": url,
            "owner": str(user_id), "visibility": doc_vis,
            "description": desc,
        }, ensure_ascii=False),
        upload_date=datetime.now().date(),
    )
    db.add(doc); db.commit(); db.refresh(doc)
    return {"ok": True, "id": doc.id, "title": title, "tags": tags, "text_len": len(clean)}


# ═══════════════════════════
# ── Bookmarklet generator ──
# ═══════════════════════════

@router.get("/bookmarklet")
def get_bookmarklet(space: str = "default", folder: str = "/网页剪藏", _user=Depends(get_current_user)):
    """Generate a JavaScript bookmarklet for one-click web clipping."""
    token = _user.id if hasattr(_user, 'id') else ''
    base = "http://localhost:5002"  # Will be overridden by frontend BASE
    js = f"""javascript:(function(){{
var u=encodeURIComponent(location.href);
var t=encodeURIComponent(document.title);
var s='{space}';var f='{folder}';
var token=localStorage.getItem('access_token')||'';
var h='{base}';
fetch(h+'/api/knowledge/clip-url',{{method:'POST',
headers:{{'Content-Type':'application/json','Authorization':'Bearer '+token}},
body:JSON.stringify({{url:decodeURIComponent(u),title:decodeURIComponent(t),space:s,folder:f}})}})
.then(r=>r.json()).then(d=>{{if(d.ok)alert('已保存到知识库!');else alert('失败:'+JSON.stringify(d));}})
.catch(e=>alert('剪藏失败'));
}})();"""
    return {"bookmarklet": js, "usage": "将上方代码保存为浏览器书签，浏览网页时点击即可剪藏"}


# ═══════════════════════════
# ── Multi-format Quick Import ──
# ═══════════════════════════

@router.post("/quick-import")
async def quick_import(
    file: UploadFile = File(None),
    url: str = Form(""),
    import_type: str = Form("auto"),  # auto/audio/image/wechat/file
    folder: str = Form("/"),
    space: str = Form("default"),
    visibility: str = Form("shared"),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Unified import: audio→text, image→OCR, url→clip, file→parse."""
    user_id = str(_user.id) if hasattr(_user, 'id') else str(_user.get('id', ''))
    results = []

    # 1. URL import (WeChat articles, web pages)
    if url:
        # Check for existing URL (dedup)
        exist = db.execute(select(ProjectDocument).order_by(ProjectDocument.id.desc()).limit(100)).scalars().all()
        for ed in exist:
            em = {}
            try: em = json.loads(ed.notes or "{}")
            except: pass
            if em.get("source") == url:
                results.append({"type": "url", "status": "dup", "title": ed.name, "msg": "该链接已导入过"})
                url = ""  # Skip
                break

    if url:
        import urllib.request as _ureq
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        try:
            req = _ureq.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; KB-Clipper/1.0)"})
            resp = _ureq.urlopen(req, timeout=15, context=ctx)
            raw = resp.read()
            try:
                import gzip; raw = gzip.decompress(raw)
            except: pass
            html = raw.decode("utf-8", errors="replace")

            # Extract content from URL
            title = ""; clean = ""
            import re as _re

            # Try title from <title> tag (always works for any page)
            tmatch = _re.search(r'<title[^>]*>(.*?)</title>', html, _re.IGNORECASE|_re.DOTALL)
            if tmatch: title = _re.sub(r'\s+', ' ', tmatch.group(1).strip())[:200]

            if "mp.weixin.qq.com" in url:
                # WeChat article: try multiple extraction methods
                # Method 1: JS variables (newer format)
                tmatch2 = _re.search(r'var\s+msg_title\s*=\s*[\'"]([^\'"]*?)[\'"]', html)
                if tmatch2: title = tmatch2.group(1).strip()[:200] or title

                cmatch = _re.search(r'var\s+msg_content\s*=\s*[\'"]([^\'"]*?)[\'"]', html)
                if cmatch:
                    try:
                        clean = cmatch.group(1).encode('latin-1').decode('unicode-escape', errors='replace')
                    except:
                        clean = cmatch.group(1)

                # Method 2: rich_media_content div
                if not clean or len(clean) < 200:
                    bmatch = _re.search(r'<div[^>]*class="[^"]*rich_media_content[^"]*"[^>]*>(.*?)</div>', html, _re.DOTALL|_re.IGNORECASE)
                    if bmatch:
                        body = bmatch.group(1)
                        # Extract text from HTML, preserving paragraph breaks
                        body = _re.sub(r'</?p[^>]*>', '\n', body)
                        body = _re.sub(r'<br[^>]*>', '\n', body)
                        body = _re.sub(r'<[^>]+>', ' ', body)
                        clean = _re.sub(r'\n\s*\n', '\n', body)

                # Method 3: js_content variable
                if not clean or len(clean) < 200:
                    jmatch = _re.search(r'var\s+js_content\s*=\s*[\'"]([^\'"]*)[\'"]', html)
                    if jmatch:
                        try:
                            clean = jmatch.group(1).encode('latin-1').decode('unicode-escape', errors='replace')
                        except:
                            clean = jmatch.group(1)

                # Method 4: og:description meta
                if not clean or len(clean) < 200:
                    ogm = _re.search(r'<meta[^>]*property="og:description"[^>]*content="([^"]*)"', html, _re.IGNORECASE)
                    if ogm:
                        clean = f"摘要: {ogm.group(1)}\n(文章正文未能完整提取，请尝试粘贴全文)"

                # Method 5: full page text (last resort)
                if not clean or len(clean) < 100:
                    body = _re.sub(r'<script[^>]*>.*?</script>', '', html, flags=_re.IGNORECASE|_re.DOTALL)
                    body = _re.sub(r'<style[^>]*>.*?</style>', '', body, flags=_re.IGNORECASE|_re.DOTALL)
                    body = _re.sub(r'<[^>]+>', ' ', body)
                    clean = _re.sub(r'\s+', ' ', body).strip()
            else:
                # Regular web page
                body = _re.sub(r'<script[^>]*>.*?</script>', '', html, flags=_re.IGNORECASE|_re.DOTALL)
                body = _re.sub(r'<style[^>]*>.*?</style>', '', body, flags=_re.IGNORECASE|_re.DOTALL)
                body = _re.sub(r'<[^>]+>', ' ', body)
                clean = _re.sub(r'\s+', ' ', body).strip()

            clean = clean[:50000] if clean else ""

            if clean and len(clean) > 50:
                tags = _wechat_tags(title, clean)
                results.append(_save_imported(db, user_id, title or url[:80], clean, "网页剪藏", folder, space, visibility, tags, url))
            elif url:
                results.append({"type": "url", "status": "fail", "error": f"无法提取内容，请确认链接有效或尝试复制文章全文粘贴"})
        except Exception as e:
            err_msg = str(e)[:150]
            if "urlopen error" in err_msg or "timeout" in err_msg or "connection" in err_msg.lower():
                err_msg = "无法访问该链接，微信文章可能需要特殊权限。建议: 在微信中打开文章 → 复制全文 → 粘贴到笔记中保存"
            results.append({"type": "url", "status": "fail", "error": err_msg})

    # 2. File import
    if file:
        content = await file.read()
        fname = os.path.basename(file.filename or "unknown")
        ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""

        # Audio: whisper transcription
        if ext in ("mp3", "wav", "m4a", "ogg", "flac", "aac", "wma"):
            try:
                import whisper, tempfile, os as _os
                tmp = tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False)
                tmp.write(content); tmp.close()
                model = whisper.load_model("base")
                result = model.transcribe(tmp.name, language="zh", verbose=False)
                _os.unlink(tmp.name)
                text = result["text"].strip()
                if text:
                    tags = ["音频转录", ext.upper()]
                    results.append(_save_imported(db, user_id, f"录音: {fname}", text, "音频转录", folder, space, visibility, tags))
            except Exception as e:
                results.append({"type": "audio", "filename": fname, "status": "fail", "error": str(e)[:100]})

        # Image: OCR
        elif ext in ("png", "jpg", "jpeg", "gif", "bmp", "webp", "tiff"):
            try:
                from PIL import Image as _PILImage
                import io as _io, numpy as _np
                img = _PILImage.open(_io.BytesIO(content))
                arr = _np.array(img)
                import easyocr
                reader = easyocr.Reader(['ch_sim', 'en'], gpu=False, verbose=False)
                ocr_results = reader.readtext(arr, detail=0)
                text = " ".join(ocr_results) if ocr_results else ""
                if text:
                    tags = ["图片识别", "OCR"]
                    results.append(_save_imported(db, user_id, f"图片: {fname}", text, "图片OCR", folder, space, visibility, tags))
            except Exception as e:
                results.append({"type": "image", "filename": fname, "status": "fail", "error": str(e)[:100]})

        # Regular document (PDF/Word/Excel/etc.)
        else:
            text = extract_text(content, fname)
            if text and not text.startswith("["):
                tags = auto_generate_tags(text, fname)
                # Save to disk
                import uuid as _uuid
                upload_dir_p = os.path.join(settings.UPLOAD_DIR, "knowledge")
                os.makedirs(upload_dir_p, exist_ok=True)
                saved_name = f"{_uuid.uuid4().hex[:8]}_{fname}"
                saved_path = os.path.join(upload_dir_p, saved_name)
                with open(saved_path, "wb") as f:
                    f.write(content)
                results.append(_save_imported(db, user_id, fname, text, "文件导入", folder, space, visibility, tags, file_path=saved_path))

    return {"ok": True, "results": results}


def _wechat_tags(title, text):
    """Generate tags for WeChat articles."""
    tags = []
    kw_map = {"电机": "电机", "驱动": "驱动", "控制": "控制", "AI": "AI", "仿真": "仿真",
              "新能源": "新能源", "汽车": "汽车", "机器人": "机器人", "电源": "电源",
              "物联网": "物联网", "数字化": "数字化", "智能": "智能"}
    for kw, tag in kw_map.items():
        if kw in title or kw in text[:2000]:
            if tag not in tags: tags.append(tag)
        if len(tags) >= 5: break
    if not tags: tags = ["微信文章"]
    return tags


def _save_imported(db, user_id, name, content, doc_type, folder, space, visibility, tags, source="", file_path=None):
    """Helper to save imported content to DB."""
    kb_project = db.execute(select(Project).where(Project.name == "__knowledge_base__")).scalar_one_or_none()
    if not kb_project:
        kb_project = Project(name="__knowledge_base__", code="__KB__", overall_status="active")
        db.add(kb_project); db.commit(); db.refresh(kb_project)
    doc = ProjectDocument(
        project_id=kb_project.id, name=name, doc_type=doc_type,
        content=content, file_path=file_path,
        folder=_norm_folder(folder),
        space_id=space,
        ext_visibility=visibility,
        owner_id=int(user_id) if user_id and str(user_id).isdigit() else None,
        notes=json.dumps({"folder": _norm_folder(folder), "tags": tags, "space": space,
                          "owner": user_id, "visibility": visibility,
                          "source": source}),
        upload_date=datetime.now().date(),
    )
    db.add(doc); db.commit(); db.refresh(doc)
    # Auto-create folder in tree
    return {"id": doc.id, "title": name, "type": doc_type, "tags": tags, "status": "ok"}


# ── Helper functions for AI enhancement APIs ──

def _kb_project_id(db):
    """Get or create the magic knowledge-base pseudo-project."""
    kb = db.execute(select(Project).where(Project.name == "__knowledge_base__")).scalar_one_or_none()
    if not kb:
        kb = Project(name="__knowledge_base__", code="__KB__", overall_status="active")
        db.add(kb); db.commit(); db.refresh(kb)
    return kb.id

def _get_doc_space(doc):
    """Extract space name from document notes JSON."""
    try:
        notes = json.loads(doc.notes or "{}")
        return notes.get("space", "default")
    except:
        return "default"

def _get_tags(doc):
    """Extract tags from document notes JSON."""
    try:
        notes = json.loads(doc.notes or "{}")
        return notes.get("tags", [])
    except:
        return []


# ═══════════════════════════════════════════
#  AI Knowledge Enhancement APIs
# ═══════════════════════════════════════════

@router.post("/ai-tag")
def api_ai_tag(data: dict, current_user=Depends(get_current_user)):
    """AI generate tags and category for given text. Returns {tags, category, summary}."""
    text = data.get("text", "")
    filename = data.get("filename", "文档")
    return ai_generate_tags(text, filename)


@router.post("/split-document")
def api_split_document(data: dict, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Split a long document into knowledge points and save them."""
    doc_id = data.get("doc_id")
    if not doc_id:
        raise HTTPException(400, "缺少 doc_id")

    doc = db.execute(select(ProjectDocument).where(ProjectDocument.id == int(doc_id))).scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "文档不存在")

    points = ai_split_document(doc.content or "", doc.name)
    if not points:
        return {"points": [], "message": "未提取到知识点"}

    saved = []
    for pt in points:
        d = _save_imported(db, current_user.id, pt.get("title", "知识点"),
                           pt.get("content", ""), "技术类", "/AI拆分",
                           _get_doc_space(doc), "team", pt.get("tags", []),
                           source="ai_split", file_path=None)
        saved.append(d)

    return {"points": saved, "count": len(saved), "message": f"已生成 {len(saved)} 个知识点"}


@router.get("/project-recommend")
def api_project_recommend(project_name: str = "", project_type: str = "", db: Session = Depends(get_db)):
    """Get knowledge recommendations for a project."""
    if not project_name:
        return []
    return ai_recommend_for_project(project_name, project_type, db)


@router.post("/import-from-project")
def api_import_from_project(data: dict, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Import project document/deliverable as knowledge entry."""
    title = data.get("title", "")
    content = data.get("content", "")
    tags = data.get("tags", [])
    category = data.get("category", "项目类")
    project_name = data.get("project_name", "")

    # Smart routing: if project_name provided, auto-route to /项目知识库/{project}/
    # Otherwise use explicit folder > config default
    if not data.get("folder") and project_name:
        folder = f"/项目知识库/{project_name}"
    else:
        config = _load_prompt_config()
        default_folder = config.get("auto_import_folders", {}).get("project", "/项目导入")
        folder = data.get("folder", default_folder)

    if not title or not content:
        raise HTTPException(400, "标题和内容不能为空")

    # AI enhance tags if auto mode
    if data.get("auto_tag", True):
        ai_result = ai_generate_tags(content, title)
        tags = ai_result.get("tags", tags)
        if ai_result.get("category"):
            category = ai_result["category"]

    return _save_imported(db, current_user.id, title, content, category, folder,
                          "default", "team", tags, source="project_import")


@router.post("/extract-from-weekly")
def api_extract_weekly(data: dict, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Extract knowledge points from weekly reports."""
    report_text = data.get("content", "")
    project_name = data.get("project_name", "")
    auto_save = data.get("auto_save", False)

    insights = ai_extract_weekly_insights(report_text, project_name)
    if not insights:
        return {"insights": [], "message": "未提取到可沉淀的知识点"}

    if auto_save:
        saved = []
        config = _load_prompt_config()
        default_folder = config.get("auto_import_folders", {}).get("weekly", "/周报提取")
        folder = data.get("folder", default_folder)
        for item in insights:
            d = _save_imported(db, current_user.id, item.get("title", "知识点"),
                               item.get("content", ""), "项目类", folder,
                               "default", "team", item.get("tags", []),
                               source="weekly_extract", file_path=None)
            saved.append(d)
        return {"insights": insights, "saved": saved, "count": len(saved)}

    return {"insights": insights, "message": f"提取到 {len(insights)} 个知识点（预览模式，未入库）"}


@router.get("/search-unified")
def api_unified_search(q: str = "", db: Session = Depends(get_db)):
    """AI-powered unified search across KB, BOM, and product tech."""
    if not q.strip():
        return {"kb": [], "bom": [], "product_tech": [], "summary": ""}
    return ai_search_across_sources(q, db)


@router.get("/relevant-updates")
def api_relevant_updates(project_name: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Get recent KB additions relevant to user's projects."""
    try:
        all_docs = db.execute(
            select(ProjectDocument).where(
                ProjectDocument.project_id == _kb_project_id(db),
                ProjectDocument.status == "active",
            ).order_by(ProjectDocument.id.desc()).limit(30)
        ).scalars().all()

        if not project_name:
            return [{"id": d.id, "title": d.name, "date": str(d.upload_date or ""),
                     "tags": _get_tags(d), "snippet": (d.content or "")[:120]} for d in all_docs[:8]]

        # Filter by project relevance
        keywords = [w.strip() for w in project_name if len(w.strip()) >= 2]
        matched = []
        for doc in all_docs:
            content = (doc.content or "") + (doc.name or "")
            score = sum(1 for kw in keywords if kw in content)
            if score > 0:
                matched.append({
                    "id": doc.id, "title": doc.name,
                    "date": str(doc.upload_date or ""),
                    "tags": _get_tags(doc),
                    "snippet": (doc.content or "")[:120],
                    "relevance": score,
                })
        matched.sort(key=lambda x: -x["relevance"])
        return matched[:10]
    except Exception as e:
        return []


# ═══════════════════════════════════════════
# ── SQLite Backup System ──
# ═══════════════════════════════════════════

import sqlite3 as _sqlite3
import shutil
import threading
import time as _time
from pathlib import Path as _Path

BACKUP_DIR = _Path(settings.UPLOAD_DIR).parent / "backups"
BACKUP_CONFIG_FILE = _Path(settings.UPLOAD_DIR).parent / "data" / "kb_backup_config.json"
BACKUP_RETENTION = 7
BACKUP_INTERVAL_HOURS = 24

_backup_timer = None


def _get_backup_config():
    try:
        if BACKUP_CONFIG_FILE.exists():
            return json.loads(BACKUP_CONFIG_FILE.read_text(encoding="utf-8"))
    except: pass
    return {"enabled": True, "interval_hours": 24, "retention_count": 7, "last_backup": None, "next_backup": None}


def _save_backup_config(cfg):
    BACKUP_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    BACKUP_CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def _do_backup():
    """Perform a single SQLite backup using sqlite3 .backup API."""
    import time
    cfg = _get_backup_config()
    if not cfg.get("enabled", True):
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    db_path = str(_Path(settings.DATABASE_URL.replace("sqlite:///", "")))
    if not _Path(db_path).is_absolute():
        db_path = str(_Path(__file__).parent.parent.parent / db_path)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"motor_pm_v2_{timestamp}.db"

    try:
        src = _sqlite3.connect(db_path)
        dst = _sqlite3.connect(str(backup_path))
        src.backup(dst)
        dst.close()
        src.close()

        # Integrity check on backup
        verify = _sqlite3.connect(str(backup_path))
        result = verify.execute("PRAGMA integrity_check").fetchone()
        verify.close()
        if result[0] != "ok":
            backup_path.unlink(missing_ok=True)
            return {"error": f"Integrity check failed: {result[0]}"}

        # Clean old backups
        backups = sorted(BACKUP_DIR.glob("motor_pm_v2_*.db"), key=lambda p: p.stat().st_mtime)
        retention = cfg.get("retention_count", BACKUP_RETENTION)
        for old in backups[:-retention]:
            old.unlink(missing_ok=True)

        cfg["last_backup"] = timestamp
        cfg["next_backup"] = (datetime.utcnow() + timedelta(hours=cfg.get("interval_hours", BACKUP_INTERVAL_HOURS))).isoformat()
        _save_backup_config(cfg)

        size_mb = backup_path.stat().st_size / (1024 * 1024)
        return {"file": str(backup_path.name), "size_mb": round(size_mb, 2), "timestamp": timestamp, "ok": True}
    except Exception as e:
        return {"error": str(e)}


def _schedule_backup():
    """Schedule periodic backups in background thread."""
    global _backup_timer
    cfg = _get_backup_config()
    if not cfg.get("enabled", True):
        return
    interval = cfg.get("interval_hours", BACKUP_INTERVAL_HOURS) * 3600
    _do_backup()
    _backup_timer = threading.Timer(interval, _schedule_backup)
    _backup_timer.daemon = True
    _backup_timer.start()


@router.get("/backup/status")
def get_backup_status(_user=Depends(require_admin)):
    """Get backup system status and history."""
    cfg = _get_backup_config()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backups = []
    for p in sorted(BACKUP_DIR.glob("motor_pm_v2_*.db"), reverse=True):
        backups.append({
            "file": p.name,
            "size_mb": round(p.stat().st_size / (1024*1024), 2),
            "created_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
        })
    return {"config": cfg, "backups": backups, "dir": str(BACKUP_DIR)}


@router.post("/backup/create")
def create_backup_manual(_user=Depends(require_admin)):
    """Trigger a manual backup immediately."""
    result = _do_backup()
    if result and result.get("ok"):
        return result
    raise HTTPException(500, result.get("error", "Backup failed") if result else "Backup failed")


@router.post("/backup/restore")
def restore_backup(data: dict, _user=Depends(require_admin)):
    """Restore database from a backup file."""
    filename = data.get("file", "")
    if not filename:
        raise HTTPException(400, "Invalid backup file")
    backup_path = (BACKUP_DIR / filename).resolve()
    if backup_path.parent != BACKUP_DIR.resolve():
        raise HTTPException(400, "Invalid backup file")
    if not backup_path.exists():
        raise HTTPException(404, "备份文件不存在")

    db_path = str(_Path(settings.DATABASE_URL.replace("sqlite:///", "")))
    if not _Path(db_path).is_absolute():
        db_path = str(_Path(__file__).parent.parent.parent / db_path)

    # Emergency backup before restore
    emergency = BACKUP_DIR / f"pre_restore_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.db"
    shutil.copy2(db_path, emergency)

    try:
        # sqlite3 backup API 是事务性的: 恢复中途失败不会留下半截数据库
        src = _sqlite3.connect(str(backup_path))
        dst = _sqlite3.connect(db_path)
        src.backup(dst)
        dst.close(); src.close()
        return {"restored": filename, "emergency_backup": emergency.name, "message": "恢复成功，请重启服务器使生效"}
    except Exception as e:
        try: dst.close()
        except Exception: pass
        try: src.close()
        except Exception: pass
        # Rollback from emergency
        shutil.copy2(str(emergency), db_path)
        raise HTTPException(500, f"恢复失败，已回滚: {e}")


@router.put("/backup/config")
def update_backup_config(data: dict, _user=Depends(require_admin)):
    """Update backup schedule configuration."""
    global _backup_timer
    cfg = _get_backup_config()
    for k in ("enabled", "interval_hours", "retention_count"):
        if k in data:
            cfg[k] = data[k]
    _save_backup_config(cfg)

    if _backup_timer:
        _backup_timer.cancel()
    if cfg.get("enabled", True):
        _schedule_backup()
    return cfg
