from fastapi import APIRouter, HTTPException
from dtos.chat_dtos import ChatRequest, ChatResponse
from services.tasks import send_to_n8n, receive_to_n8n
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
        # Enqueue task chain
        task_chain = send_to_n8n.s(request.dict()) | receive_to_n8n.s()
        task = task_chain.apply_async()
        
        # Wait for result (in a threadpool to not block event loop if not using rpc backend properly)
        # Note: In a real async connection pool environment, celery's .get() might block the loop 
        # unless we wrap it or use the asyncio compatible backend.
        # For simplicity/compatibility, we wrap the blocking call.
        
        loop = asyncio.get_event_loop()
        # Wait up to 30s
        try:
            result = await loop.run_in_executor(None, lambda: task.get(timeout=300))
        except Exception as e:
            # Timeout or other error
            raise HTTPException(status_code=504, detail="Upstream service timed out")
            
        if result.get("status") == "error":
             raise HTTPException(status_code=500, detail=result.get("message"))
             
        return ChatResponse(
            reply=result.get("reply", ""),
            status=result.get("status", "success"),
            celery=result.get("celery", True)
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

