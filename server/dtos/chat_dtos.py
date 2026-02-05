from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class ChatRequest(BaseModel):
    query: str = Field(..., description="The user's message/query")
    plan: str = Field(..., description="The plan context or identifier")
    user_id: str = Field(..., description="The ID of the user sending the message")

class ChatResponse(BaseModel):
    reply: str
    status: str
