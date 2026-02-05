from fastapi import APIRouter, HTTPException, Depends
from dtos.application_dtos import ApplicationCreate, ApplicationUpdate, ApplicationResponse
from services.auth_svc import verify_firebase_user, AuthenticatedUser
from services import application_svc
from typing import List

router = APIRouter()

@router.get("/{uid}", response_model=List[ApplicationResponse])
def list_my_applications(
    uid: str,
    user: AuthenticatedUser = Depends(verify_firebase_user)
):
    if user.uid != uid:
        raise HTTPException(status_code=403, detail="Not authorized")
    return application_svc.get_user_applications(uid)

@router.post("/{uid}/add", response_model=ApplicationResponse)
async def add_application(
    uid: str,
    data: ApplicationCreate,
    user: AuthenticatedUser = Depends(verify_firebase_user)
):
    if user.uid != uid:
        raise HTTPException(status_code=403, detail="Not authorized")
    try:
        return await application_svc.create_application(uid, data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/{uid}/{app_id}", response_model=ApplicationResponse)
async def update_application(
    uid: str,
    app_id: str,
    data: ApplicationUpdate,
    user: AuthenticatedUser = Depends(verify_firebase_user)
):
    if user.uid != uid:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    result = await application_svc.update_application(uid, app_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Application not found")
    return result

@router.delete("/{uid}/{app_id}")
def delete_application(
    uid: str,
    app_id: str,
    user: AuthenticatedUser = Depends(verify_firebase_user)
):
    if user.uid != uid:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    application_svc.delete_application(uid, app_id)
    return {"status": "success", "message": "Application deleted"}
