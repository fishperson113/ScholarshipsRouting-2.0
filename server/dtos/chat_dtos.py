from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
<<<<<<< HEAD
from uuid import UUID, uuid4
=======
>>>>>>> 6d6f8e271f6de622637b3af34bef0a504926516b

class ChatRequest(BaseModel):
    query: str = Field(..., description="The user's message/query")
    plan: str = Field(..., description="The plan context or identifier")
    user_id: str = Field(..., description="The ID of the user sending the message")
<<<<<<< HEAD
    
    # Whether to use user profile information in chatbot response
    # Frontend sends: use_profile: selectedPlan === 'pro' ? useProfile : false
    use_profile: bool = False

    # UUIDv4 session id for n8n Redis Chat Memory
    sessionId: UUID = Field(
        default_factory=uuid4,
        description="UUIDv4 session id used as n8n Redis Chat Memory session key"
    )
=======

>>>>>>> 6d6f8e271f6de622637b3af34bef0a504926516b
class ChatResponse(BaseModel):
    reply: str
    status: str
    celery: bool = True
<<<<<<< HEAD
    sessionId: Optional[UUID] = None
=======
>>>>>>> 6d6f8e271f6de622637b3af34bef0a504926516b
