from pydantic import BaseModel
from typing import Any


class ChatMessage(BaseModel):
    role: str   # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    metrics: dict[str, Any]
    ai_report: dict[str, Any] | None = None
    business_name: str | None = None
    business_type: str | None = None
    currency: str = "UZS"
    history: list[ChatMessage] = []


class ChatResponse(BaseModel):
    answer: str
