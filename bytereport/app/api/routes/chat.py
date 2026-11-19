import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import ai_caller
from app.core.auth import AuthUser
from app.models.chat import ChatRequest, ChatResponse
from app.services.ai_chat import get_chat_response

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


@router.post("", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def chat_endpoint(
    body: ChatRequest,
    caller: AuthUser = Depends(ai_caller),
) -> ChatResponse:
    """
    Multi-turn AI-CFO chat.  Accepts full conversation history + financial
    context; returns the next AI response.
    """
    try:
        answer = await get_chat_response(
            message=body.message,
            history=body.history,
            metrics=body.metrics,
            ai_report=body.ai_report,
            business_name=body.business_name,
            business_type=body.business_type,
            currency=body.currency,
        )
        return ChatResponse(answer=answer)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception:
        logger.exception("AI-CFO chat error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка AI-CFO. Попробуйте ещё раз.",
        )
