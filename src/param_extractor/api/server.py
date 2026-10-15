"""API 服务入口（设计 §3.8；决策 D6）。

`POST /v1/extract`：LLM 失败**一律返回 200**（`status=FALLBACK`）；仅服务自身故障才 5xx。
"""
from typing import Optional

from fastapi import FastAPI, HTTPException

from ..config import Settings, load_settings
from ..contracts.request import ExtractionRequest
from ..ingestion.ingest import is_over_limit, normalize
from ..pipeline.orchestrator import run_pipeline

app = FastAPI(title="ParamExtrator")

_state: dict = {"client": None, "settings": None}


def configure(client=None, settings: Optional[Settings] = None) -> None:
    """测试/部署注入点。"""
    _state["client"] = client
    _state["settings"] = settings


def _settings() -> Settings:
    return _state["settings"] or load_settings()


def _client():
    if _state["client"] is not None:
        return _state["client"]
    import instructor
    from openai import OpenAI

    from ..extraction.provider import InstructorClient

    s = _settings()
    base = OpenAI(api_key=s.llm_api_key, base_url=s.llm_base_url)
    return InstructorClient(instructor.from_openai(base), s.llm_model)


@app.post("/v1/extract")
def extract(req: ExtractionRequest):
    settings = _settings()
    if is_over_limit(req, settings.max_input_bytes):
        raise HTTPException(status_code=400, detail="content exceeds max_input_bytes")
    result = run_pipeline(normalize(req), _client(), settings)
    return result.model_dump(mode="json")
