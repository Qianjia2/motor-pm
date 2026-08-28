"""Hybrid search: full-text + vector, across KB, BOM, product tech."""
import json, os, re
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session
from backend_v2.database import get_db
from backend_v2.auth import get_current_user
from backend_v2.models import ProjectDocument

router = APIRouter(tags=["knowledge-search"])

# Load embeddings on demand
_vectors_cache = None
def _load_vectors():
    global _vectors_cache
    if _vectors_cache is not None:
        return _vectors_cache
    from pathlib import Path
    from backend_v2.config import settings
    vec_path = Path(settings.UPLOAD_DIR).parent / "data" / "kb_vectors.json"
    try:
        _vectors_cache = json.loads(vec_path.read_text(encoding="utf-8"))
    except:
        _vectors_cache = {}
    return _vectors_cache

def _cosine_sim(a, b):
    try:
        import numpy as np
        a = np.array(a); b = np.array(b)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))
    except:
        return 0.0


def _keyword_rank(text, keywords, bonus_words=None):
    """Score a document text against search keywords."""
    if not text or not keywords:
        return 0
    text = text.lower()
    score = 0
    for kw in keywords:
        kw = kw.lower()
        count = text.count(kw)
        if count > 0:
            score += min(count, 5) * 2
            # Title match bonus
            if bonus_words and kw in bonus_words.lower():
                score += 5
    return score


def _extract_query_keywords(q):
    """Extract CJK and alphanumeric keywords from a search query."""
    # Remove stop words and punctuation
    cleaned = re.sub(r'[^一-鿿\w]', ' ', q)
    words = [w.strip() for w in cleaned.split() if len(w.strip()) >= 2]
    # If single CJK search, use character-level n-grams
    if not words and len(q) >= 2:
        words = [q[i:i+2] for i in range(len(q)-1)]
    return words[:10]


@router.get("/search/hybrid")
def hybrid_search(
    q: str = Query("", description="Search query"),
    space_id: str = Query(None),
    folder: str = Query(None),
    doc_type: str = Query(None),
    top_k: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Hybrid search: full-text matching + vector similarity, unified results."""
    if not q.strip():
        return {"results": [], "total": 0, "query": q}

    keywords = _extract_query_keywords(q)
    if not keywords:
        return {"results": [], "total": 0, "query": q}

    # 1. Full-text search: name + content + notes
    text_filters = []
    for kw in keywords[:5]:
        text_filters.append(ProjectDocument.name.contains(kw))
        text_filters.append(ProjectDocument.content.contains(kw))
        text_filters.append(ProjectDocument.notes.contains(kw))
        text_filters.append(ProjectDocument.folder.contains(kw))

    q_text = select(ProjectDocument).where(or_(*text_filters))
    if space_id: q_text = q_text.where(ProjectDocument.space_id == space_id)
    if folder: q_text = q_text.where(ProjectDocument.folder == folder)
    if doc_type: q_text = q_text.where(ProjectDocument.doc_type == doc_type)
    q_text = q_text.limit(200)

    text_results = db.execute(q_text).scalars().all()

    # 2. Score text results
    scored = {}
    for d in text_results:
        txt = f"{d.name or ''} {d.content or ''} {d.folder or ''} {d.notes or ''}"
        text_score = _keyword_rank(txt, keywords, d.name)
        if text_score > 0:
            scored[d.id] = {"doc": d, "text_score": text_score, "vector_score": 0, "final_score": text_score}

    # 3. Vector search (if embeddings exist)
    vectors = _load_vectors()
    if vectors:
        try:
            from backend_v2.routes._knowledge_core import _get_embedding as _kb_get_embedding
            query_vec = _kb_get_embedding(q)
            if query_vec:
                for doc_id_str, vec in vectors.items():
                    if not vec: continue
                    sim = _cosine_sim(query_vec, vec)
                    if sim > 0.3:
                        did = int(doc_id_str)
                        if did in scored:
                            scored[did]["vector_score"] = round(sim * 100, 1)
                            scored[did]["final_score"] = scored[did]["text_score"] * 0.4 + sim * 100 * 0.6
                        else:
                            doc = db.get(ProjectDocument, did)
                            if doc:
                                scored[did] = {"doc": doc, "text_score": 0, "vector_score": round(sim * 100, 1), "final_score": sim * 100}
        except Exception:
            pass

    # 4. Sort by final score, return top_k
    sorted_results = sorted(scored.values(), key=lambda x: -x["final_score"])[:top_k]

    results = []
    for item in sorted_results:
        d = item["doc"]
        results.append({
            "id": d.id, "title": d.name, "doc_type": d.doc_type,
            "folder": d.folder or "/", "space_id": d.space_id or "default",
            "snippet": (d.content or "")[:200],
            "text_score": item["text_score"],
            "vector_score": item.get("vector_score", 0),
            "relevance": round(item["final_score"], 1),
            "created_at": d.upload_date.isoformat() if d.upload_date else None,
        })

    return {"results": results, "total": len(results), "query": q, "keywords": keywords[:5]}
