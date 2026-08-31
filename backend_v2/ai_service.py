"""AI Service: Multi-engine LLM provider with intelligent routing."""
import json, os, aiohttp
from typing import Optional, AsyncGenerator
from backend_v2.storage import atomic_write

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "ai_config.json")

DEFAULT_CONFIG = {
    "provider": "ollama",
    "model": "qwen2.5:7b",
    "base_url": "http://localhost:11434/v1",
    "api_key": "",
    "temperature": 0.7,
    "max_tokens": 2048,
    "enabled": True,
    "system_prompt": "你是电机设计项目管理AI助手。回答简洁专业。",
    "engines": {
        "deepseek": {"api_key": "", "model": "deepseek-chat", "base_url": "https://api.deepseek.com/v1"},
        "tongyi":   {"api_key": "", "model": "qwen-turbo", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
        "kimi":     {"api_key": "", "model": "moonshot-v1-8k", "base_url": "https://api.moonshot.cn/v1"},
        "baidu_ocr":{"api_key": "", "secret_key": ""},
    },
    "routing": {
        "qa": "ollama", "summary": "deepseek", "report": "deepseek",
        "qa_gen": "deepseek", "chat": "ollama", "ocr": "easyocr",
        "chat_model": "qwen2.5:0.5b",
    }
}

MOTOR_DOMAIN_CONTEXT = """
背景：这是一个电机系统设计项目管理平台，涉及6条技术线：
1. 控制算法（FOC控制、弱磁控制、参数辨识、电流环/速度环设计）
2. 控制软件（DSP/ARM代码、CAN通信、Flash刷写、上位机）
3. 控制硬件（功率模块、驱动电路、PCB设计、EMC）
4. 电机结构（3D设计、机械强度、散热分析、NVH）
5. 电机电磁（磁路设计、绕组优化、效率MAP、转矩波动）
6. 测试验证（台架测试、标定、耐久测试、环境试验）
项目阶段：P0需求→PP0方案→PP1设计→PP2验证→PP3试制→PP4量产
"""

def load_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    except FileNotFoundError:
        _save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG

def _save_config(cfg: dict):
    atomic_write(CONFIG_PATH, cfg)

def save_config(cfg: dict):
    current = load_config()
    current.update(cfg)
    _save_config(current)

async def _call_llm(messages: list, stream: bool = False) -> str:
    return await _call_engine("ollama", messages, task_type="qa")

async def call_task(task_type: str, messages: list) -> str:
    cfg = load_config()
    routing = cfg.get("routing", {})
    engine = routing.get(task_type, "ollama")
    return await _call_engine(engine, messages, task_type=task_type)

async def _call_engine(engine: str, messages: list, task_type: str = "qa") -> str:
    """Call a specific AI engine. Falls back to Ollama if engine not configured."""
    cfg = load_config()
    routing = cfg.get("routing", {})
    engines = cfg.get("engines", {})
    ecfg = engines.get(engine, {})

    if ecfg and ecfg.get("api_key"):
        base_url = ecfg.get("base_url", "")
        model = ecfg.get("model", cfg["model"])
        api_key = ecfg.get("api_key", "")
    elif engine == "ollama" or not ecfg:
        base_url = cfg.get("base_url", "http://localhost:11434/v1")
        model = cfg.get("model", "qwen2.5:7b")
        api_key = cfg.get("api_key", "")
    else:
        return await _call_engine("ollama", messages, task_type=task_type)

    # 任务级模型覆盖: chat 用快模型, report 用强模型(能力优先)
    if task_type == "chat":
        model = routing.get("chat_model", model)
    elif task_type == "report":
        model = routing.get("report_model", model)

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    body = {
        "model": model,
        "messages": messages,
        "temperature": cfg.get("temperature", 0.7),
        "max_tokens": cfg.get("chat_max_tokens", 400) if task_type == "chat" else cfg.get("max_tokens", 2048),
        "stream": False,
    }

    url = f"{base_url.rstrip('/')}/chat/completions"
    timeout = aiohttp.ClientTimeout(total=cfg.get("timeout", 300))
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=body, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    if engine != "ollama":
                        return await _call_engine("ollama", messages, task_type=task_type)
                    return f"[AI调用失败: {resp.status} {text[:200]}]"
                data = await resp.json()
                return data["choices"][0]["message"]["content"]
    except Exception as e:
        if engine != "ollama":
            return await _call_engine("ollama", messages, task_type=task_type)
        return f"[AI连接失败: {str(e)[:200]}]"

def get_engines_status() -> dict:
    cfg = load_config()
    engines_cfg = cfg.get("engines", {})
    routing = cfg.get("routing", {})
    result = {}
    engine_names = {"deepseek":"DeepSeek V3","tongyi":"通义千问","kimi":"Kimi Moonshot",
                    "baidu_ocr":"百度 OCR","ollama":"Ollama 本地"}
    for task_type, engine in routing.items():
        if task_type == "chat_model": continue
        task_name = {"qa":"问答","summary":"摘要","report":"报告","qa_gen":"QA对生成","chat":"客户问答","ocr":"OCR识别"}.get(task_type, task_type)
        ecfg = engines_cfg.get(engine, {})
        available = bool(ecfg.get("api_key")) if engine != "ollama" else cfg.get("enabled", True)
        result[task_type] = {"engine":engine,"name":engine_names.get(engine,engine),"available":available,"task_name":task_name}
    return result

async def generate_weekly_report(project_name: str, lines_data: list) -> str:
    cfg = load_config()
    lines_text = "\n".join([f"- {l['line']}: {l.get('progress','无')}" for l in lines_data])
    messages = [{"role":"system","content":cfg["system_prompt"]+"\n"+MOTOR_DOMAIN_CONTEXT},
                {"role":"user","content":f"请为电机项目「{project_name}」生成本周周报。\n各技术线进展：\n{lines_text}\n请输出本周总体进展、重点完成事项、需要关注的问题、下周重点计划。"}]
    return await _call_llm(messages)

async def analyze_risk(title: str, description: str, project_context: str = "") -> str:
    cfg = load_config()
    messages = [{"role":"system","content":cfg["system_prompt"]+"\n"+MOTOR_DOMAIN_CONTEXT},
                {"role":"user","content":f"""请分析以下电机项目风险并给出建议：\n风险标题：{title}\n风险描述：{description}\n请输出风险等级评估、可能影响、建议缓解措施、建议责任人。"""}]
    return await _call_llm(messages)

async def diagnose_project(project_data: dict) -> str:
    cfg = load_config()
    ms_text = "\n".join([f"- {m['name']}" for m in project_data.get("milestones", [])[:10]])
    messages = [{"role":"system","content":cfg["system_prompt"]+"\n"+MOTOR_DOMAIN_CONTEXT},
                {"role":"user","content":f"""请对电机项目进行健康诊断：\n项目名称：{project_data.get('name','')}\n完成率：{project_data.get('completion_pct',0)}%\n里程碑：\n{ms_text}\n请输出整体健康评分、关键风险点、改进建议。"""}]
    return await _call_llm(messages)

async def chat_about_projects(question: str, context_data: str) -> str:
    cfg = load_config()
    messages = [{"role":"system","content":cfg["system_prompt"]+"\n"+MOTOR_DOMAIN_CONTEXT},
                {"role":"user","content":f"基于以下项目数据回答问题：\n{context_data}\n问题：{question}\n请简洁回答（200字以内）。"}]
    return await _call_llm(messages)

async def extract_risks_from_reports(reports_text: str, project_name: str = "") -> list:
    EXTRACTION_PROMPT = """你是电机研发项目风险识别专家。从周报中提取所有存在的问题和风险。只返回JSON数组。"""
    messages = [{"role":"system","content":EXTRACTION_PROMPT},
                {"role":"user","content":f"项目数据：\n{reports_text[:16000]}\n\n提取所有风险项，返回JSON数组。"}]
    result = await _call_llm(messages)
    try:
        text = result.strip()
        if text.startswith("```"): text = text.split("```")[1]
        if text.startswith("json"): text = text[4:]
        parsed = json.loads(text)
        if not isinstance(parsed, list): return []
        return [item for item in parsed if item.get("title", "").strip()]
    except:
        return []
