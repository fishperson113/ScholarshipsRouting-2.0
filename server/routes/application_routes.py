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

@router.delete("/{uid}/scholarship/{scholarship_id}")
def delete_application_by_scholarship(
    uid: str,
    scholarship_id: str,
    user: AuthenticatedUser = Depends(verify_firebase_user)
):
    if user.uid != uid:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    result = application_svc.delete_application_by_scholarship_id(uid, scholarship_id)
    if not result:
        # Nếu không tìm thấy để xóa cũng không sao (Idempotent), nhưng cứ báo 404 để biết
        # Tuy nhiên, trong UX toggle, trả về 200 tốt hơn.
        # Nhưng để chuẩn logic debug, tôi raise 404 nếu không có gì để xóa.
        pass 
        
    return {"status": "success", "message": "Application deleted"}


# ==================== TEST ENDPOINTS ====================
@router.post("/test/trigger-deadline-check")
def test_trigger_deadline_check(
    user: AuthenticatedUser = Depends(verify_firebase_user)
):
    """
    MANUAL TRIGGER: Run the deadline check immediately.
    Useful for testing notifications without waiting for midnight.
    """
    try:
        from services.tasks.notification_tasks import check_application_deadlines
        
        # Run the task synchronously (in threadpool or directly)
        result = check_application_deadlines()
        
        return {
            "status": "triggered", 
            "message": "Deadline check task executed manually",
            "result": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== NOTIFICATION ENDPOINTS ====================

@router.get("/{uid}/notifications")
def get_user_notifications(
    uid: str,
    user: AuthenticatedUser = Depends(verify_firebase_user)
):
    """
    Get backend-driven notifications (bypassing Client SDK Rules).
    """
    if user.uid != uid:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    return application_svc.get_user_notifications(uid)

@router.put("/{uid}/notifications/{id}/read")
def mark_notification_read(
    uid: str,
    id: str,
    user: AuthenticatedUser = Depends(verify_firebase_user)
):
    """
    Mark a notification as read.
    """
    if user.uid != uid:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    success = application_svc.mark_notification_read(uid, id)
    if not success:
         raise HTTPException(status_code=404, detail="Notification not found or unauthorized")
         
    return {"status": "success", "id": id}
