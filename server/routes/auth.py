from fastapi import APIRouter, HTTPException, Depends
from services.auth_svc import (
    register_user,
    create_guest_session,
    verify_token, 
    get_profile, 
    update_profile,
    verify_firebase_user,
    require_user_ownership,
    verify_bot_token,
    AuthenticatedUser
)
from dtos.auth_dtos import RegisterRequest, VerifyRequest, UpdateProfileRequest
from typing import Dict, Any

router = APIRouter()

@router.post("/guest", summary="Create temporary guest session")
def create_guest():
    """Create a temporary guest session with 24-hour expiration. No database storage."""
    try:
        return create_guest_session()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/register", summary="Register new user (with bot protection)")
async def register(
    req: RegisterRequest,
    bot_verified: bool = Depends(verify_bot_token)
):
    """Register with bot protection to prevent automated signups"""
    try:
        # lấy toàn bộ field (ngoại trừ email/password/display_name)
        extra_fields = req.dict(exclude={"email", "password", "display_name"}, exclude_unset=True)
        user = register_user(req.email, req.password, req.display_name, extra_fields)
        return user
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/verify")
def verify(req: VerifyRequest):
    payload = verify_token(req.id_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


@router.get("/profile/{uid}", summary="Get user profile (Protected)")
async def get_user_profile(
    uid: str,
    current_user: AuthenticatedUser = Depends(verify_firebase_user)
):
    """Get profile - user can only access their own data"""
    require_user_ownership(current_user, uid)
    
    profile = get_profile(uid)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    return profile


@router.put("/profile/{uid}", summary="Update user profile (Protected)")
async def update_user_profile(
    uid: str,
    req: UpdateProfileRequest,
    current_user: AuthenticatedUser = Depends(verify_firebase_user)
):
    """Update profile - user can only update their own data"""
    require_user_ownership(current_user, uid)
    
    try:
        fields = req.dict(exclude_unset=True)
        updated = update_profile(uid, fields)
        return updated
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
