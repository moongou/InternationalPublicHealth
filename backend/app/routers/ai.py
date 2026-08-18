from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import Principal, get_session, require_roles
from ..llm import LlmProviderError
from ..models import LlmProvider
from ..schemas import AiEventAnalysisRequest


router = APIRouter(prefix="/ai", tags=["ai"])
analysis_access = require_roles("system_admin", "data_analyst", "port_operator", "auditor", "read_only")


@router.post("/analyze-event")
async def analyze_event(
    body: AiEventAnalysisRequest, request: Request,
    _: Principal = Depends(analysis_access), session: Session = Depends(get_session),
) -> dict[str, Any]:
    if body.provider_id:
        provider = session.get(LlmProvider, body.provider_id)
    else:
        provider = session.scalar(
            select(LlmProvider).where(LlmProvider.enabled.is_(True), LlmProvider.is_default.is_(True)).limit(1)
        ) or session.scalar(select(LlmProvider).where(LlmProvider.enabled.is_(True)).order_by(LlmProvider.created_at).limit(1))
    if not provider or not provider.enabled:
        raise HTTPException(409, "尚未配置并启用大语言模型供应商")
    model = body.model or provider.selected_model
    if not model:
        raise HTTPException(409, "大语言模型供应商尚未选择模型")
    event = body.model_dump(mode="json", exclude={"provider_id", "model", "focus"})
    prompt = (
        "你是公共卫生风险研判助手。仅依据给定事件输出中文研判，必须区分事实与建议，不得补造数字。"
        "内容包括：事实摘要、可信度与局限、输入性风险、口岸关注点、后续核验清单。\n"
        f"事件数据：{json.dumps(event, ensure_ascii=False)}"
    )
    if body.focus:
        prompt += f"\n用户关注点：{body.focus}"
    try:
        content = await request.app.state.llm_gateway.chat(provider, model, prompt, max_tokens=1600)
    except LlmProviderError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "provider_id": provider.provider_id, "provider": provider.name,
        "model": model, "analysis": content.strip(),
    }
