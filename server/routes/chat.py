from fastapi import APIRouter, HTTPException, BackgroundTasks
from dtos.chat_dtos import ChatRequest, ChatResponse
from services.tasks import send_to_n8n, receive_to_n8n
from celery.result import AsyncResult
from celery import chain
import asyncio

router = APIRouter()

@router.post("/sync", response_model=ChatResponse)
async def chat_sync(request: ChatRequest):
    """
    Synchronous chat endpoint that delegates to Celery/N8n.
    Waits for the result up to 30 seconds.
    """
    try:
        # Enqueue task
        # Convert Pydantic model to dict and handle UUID serialization for Celery/Redis
        # We explicitly convert UUID to string here because standard JSON serialization
        # used by Celery does not support UUID objects.
        # Note: sessionId always exists (auto-generated via default_factory=uuid4 if not provided)
        payload = request.dict()
        payload['sessionId'] = str(request.sessionId)

        # Enqueue task chain
        task_chain = chain(send_to_n8n.s(payload) | receive_to_n8n.s())
        task = task_chain.apply_async()
        
        
        loop = asyncio.get_event_loop()
        # Wait up to 30s
        try:
            result = await loop.run_in_executor(None, lambda: task.get(timeout=30))
        except Exception as e:
            # Timeout or other error
            raise HTTPException(status_code=504, detail="Upstream service timed out")
            
        if result.get("status") == "error":
             raise HTTPException(status_code=500, detail=result.get("message"))
             
        return ChatResponse(
            reply=result.get("reply", ""),
            status=result.get("status", "success"),
            celery=result.get("celery", True),
            sessionId=request.sessionId
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

