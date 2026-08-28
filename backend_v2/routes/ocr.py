"""OCR + AI chat parsing — upload WeChat screenshots, extract structured content."""
import os
import uuid as _uuid
from datetime import datetime
from pathlib import Path as FilePath

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from backend_v2.database import get_db
from backend_v2.auth import get_current_user
from backend_v2.config import settings

router = APIRouter(tags=["ocr"])

# Lazy-load easyocr (heavy import, only on first use)
_reader = None


def get_reader():
    global _reader
    if _reader is None:
        try:
            import easyocr
            _reader = easyocr.Reader(["ch_sim", "en"], gpu=False, verbose=False)
        except ImportError:
            raise HTTPException(status_code=500, detail="OCR 引擎未安装，请联系管理员")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"OCR 初始化失败: {str(e)}")
    return _reader


def ai_parse_chat(text: str) -> dict:
    """Use AI (Ollama or configured provider) to extract structured info from chat text."""
    try:
        from backend_v2.ai_service import get_ai_response
    except ImportError:
        return _rule_based_parse(text)

    prompt = f"""你是一个项目管理助手。请从以下微信聊天记录中提取关键信息，按 JSON 格式返回。

聊天记录：
{text[:4000]}

请提取以下内容（找不到的字段设为 null 或空字符串）：
{{
  "weekly_items": [
    {{"line": "控制软件/控制硬件/电机结构/电机电磁/测试验证", "this_week": "本周完成内容", "next_week": "下周计划", "blocker": "阻塞/困难", "status": "normal/delayed/risk"}}
  ],
  "change_request": {{
    "title": "变更标题",
    "description": "变更描述",
    "reason": "变更原因",
    "impact": "影响评估"
  }},
  "risks": [
    {{"title": "风险/问题标题", "description": "详细描述", "severity": "高/中/低"}}
  ],
  "summary": "一句话总结"
}}

只返回 JSON，不要其他文字。"""

    try:
        response = get_ai_response(prompt)
        # Extract JSON from response
        import json
        # Find first { and last }
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(response[start:end])
        return _rule_based_parse(text)
    except Exception:
        return _rule_based_parse(text)


def _rule_based_parse(text: str) -> dict:
    """Fallback: simple keyword-based extraction when AI is unavailable."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    return {
        "weekly_items": [
            {"line": "", "this_week": l[:200], "next_week": "", "blocker": "", "status": "normal"}
            for l in lines[:20]
        ],
        "change_request": None,
        "risks": [],
        "summary": lines[0][:100] if lines else "",
        "_note": "AI 引擎不可用，使用基础文本提取。建议安装 Ollama 以获得智能解析。"
    }


@router.post("/api/ocr/parse-chat")
async def parse_chat_image(
    file: UploadFile = File(...),
    parse_type: str = Form("weekly"),  # "weekly" or "change" or "auto"
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Upload a WeChat screenshot, OCR extract text, AI parse into structured content."""
    # Validate file type
    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename else ""
    if ext not in ("png", "jpg", "jpeg", "gif", "bmp", "webp"):
        raise HTTPException(status_code=400, detail="仅支持图片格式: png/jpg/gif/bmp/webp")

    # Save uploaded image
    upload_dir = FilePath(settings.UPLOAD_DIR) / "ocr"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{_uuid.uuid4().hex[:8]}_{file.filename}"
    dest = upload_dir / safe_name
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="图片不超过 20MB")
    with open(dest, "wb") as f:
        f.write(content)

    # OCR extraction
    try:
        reader = get_reader()
        results = reader.readtext(str(dest), detail=0)
        text = "\n".join(results)
    except HTTPException:
        raise
    except Exception as e:
        text = ""
        import traceback
        traceback.print_exc()

    if not text.strip():
        return {
            "ok": False,
            "message": "未能从图片中识别到文字，请确认图片清晰且包含中文对话内容",
            "text": "",
            "parsed": None,
        }

    # AI parse
    parsed = ai_parse_chat(text)

    return {
        "ok": True,
        "message": f"识别到 {len(text)} 个字符",
        "text": text,
        "parsed": parsed,
        "image_path": str(dest.relative_to(FilePath(settings.UPLOAD_DIR).parent)),
    }
