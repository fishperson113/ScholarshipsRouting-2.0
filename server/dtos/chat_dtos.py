from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from uuid import UUID, uuid4

class ChatRequest(BaseModel):
    query: str = Field(..., description="The user's message/query")
    plan: str = Field(..., description="The plan context or identifier")
    user_id: str = Field(..., description="The ID of the user sending the message")
    
    # Whether to use user profile information in chatbot response
    # Frontend sends: use_profile: selectedPlan === 'pro' ? useProfile : false
    use_profile: bool = False

    # UUIDv4 session id for n8n Redis Chat Memory
    sessionId: UUID = Field(
        default_factory=uuid4,
        description="UUIDv4 session id used as n8n Redis Chat Memory session key"
    )
class ChatResponse(BaseModel):
    reply: str
    status: str
    celery: bool = True
    sessionId: Optional[UUID] = None