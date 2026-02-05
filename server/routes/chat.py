from fastapi import APIRouter, HTTPException, BackgroundTasks
from dtos.chat_dtos import ChatRequest, ChatResponse
from services.tasks import send_to_n8n
from celery.result import AsyncResult
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
        task = send_to_n8n.delay(request.dict())
        
        # Wait for result (in a threadpool to not block event loop if not using rpc backend properly)
        # Note: In a real async connection pool environment, celery's .get() might block the loop 
        # unless we wrap it or use the asyncio compatible backend.
        # For simplicity/compatibility, we wrap the blocking call.
        
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
            reply=json_extract_reply(result), # Helper to extract text
            status="success"
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def json_extract_reply(data: dict) -> str:
    """Helper to try and find a text reply in common n8n structures"""
    # Adjust this based on your actual n8n output structure
    if isinstance(data, dict) and data:
        return str(next(iter(data.values())))
    return str(data)