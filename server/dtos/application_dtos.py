from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class ApplicationBase(BaseModel):
    scholarship_id: str = Field(..., description="ID of the scholarship")
    scholarship_name: str = Field(..., description="Name of the scholarship")
    apply_date: Optional[str] = Field(None, description="Target date to apply (ISO format)")
    status: str = Field("draft", description="Status: draft, submitted, approved, rejected")
    note: Optional[str] = Field(None, description="Personal notes")

class ApplicationCreate(ApplicationBase):
    pass

class ApplicationUpdate(BaseModel):
    apply_date: Optional[str] = None
    status: Optional[str] = None
    note: Optional[str] = None

class ApplicationResponse(ApplicationBase):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
