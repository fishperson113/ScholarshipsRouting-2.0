from firebase_admin import firestore
from datetime import datetime
from dtos.application_dtos import ApplicationCreate, ApplicationUpdate
from services.event_manager import event_bus
import logging

logger = logging.getLogger(__name__)

# ==================== Event Handlers (The "Webhook" Logic) ====================

async def handle_application_created(payload: dict):
    """
    Listener: When an application is created -> Send visible notification.
    """
    db = firestore.client()
    uid = payload.get('user_id')
    app_name = payload.get('scholarship_name')
    
    notification_data = {
        'userId': uid,
        'type': 'APPLICATION_ADDED',
        'title': 'Đã thêm hồ sơ mới',
        'message': f'Bạn đã bắt đầu hồ sơ cho học bổng "{app_name}". Hãy nhớ cập nhật tiến độ nhé!',
        'isRead': False,
        'createdAt': firestore.SERVER_TIMESTAMP,
        'link': '/app/applications',
        'metadata': payload
    }
    
    db.collection('notifications').add(notification_data)
    logger.info(f"🔔 Notification sent to {uid} for new application")

async def handle_deadline_approaching(payload: dict):
    """
    Listener: When deadline is near -> Send generic warning notification.
    Payload: { 'user_id': uid, 'application_id': app_id, 'scholarship_name': name, 'days_left': 3 }
    """
    db = firestore.client()
    uid = payload.get('user_id')
    days = payload.get('days_left')
    name = payload.get('scholarship_name')
    
    notification_data = {
        'userId': uid,
        'type': 'DEADLINE_WARNING',
        'title': '🔥 Sắp hết hạn nộp!',
        'message': f'Học bổng "{name}" sẽ đóng đơn trong {days} ngày nữa. Hoàn thiện ngay kẻo lỡ!',
        'isRead': False,
        'createdAt': firestore.SERVER_TIMESTAMP,
        'link': '/app/applications',
        'metadata': payload
    }
    
    db.collection('notifications').add(notification_data)
    logger.info(f"⏰ Deadline alert sent to {uid} for {name}")

# Register the handlers
event_bus.subscribe("APPLICATION_CREATED", handle_application_created)
event_bus.subscribe("DEADLINE_APPROACHING", handle_deadline_approaching)


# ==================== Core Service Logic ====================

def get_user_applications(uid: str):
    db = firestore.client()
    docs = db.collection('users').document(uid).collection('applications').stream()
    return [{**doc.to_dict(), 'id': doc.id} for doc in docs]

async def create_application(uid: str, data: ApplicationCreate):
    db = firestore.client()
    
    new_app = data.dict()
    new_app['user_id'] = uid
    new_app['created_at'] = datetime.utcnow().isoformat()
    new_app['updated_at'] = datetime.utcnow().isoformat()
    
    # Save to Firestore
    doc_ref = db.collection('users').document(uid).collection('applications').document()
    doc_ref.set(new_app)
    
    result = {**new_app, 'id': doc_ref.id}
    
    # 📢 EMIT EVENT (The "Webhook" trigger)
    # This decouples the notification logic from the saving logic
    await event_bus.emit("APPLICATION_CREATED", result)
    
    return result

async def update_application(uid: str, app_id: str, data: ApplicationUpdate):
    db = firestore.client()
    doc_ref = db.collection('users').document(uid).collection('applications').document(app_id)
    
    doc = doc_ref.get()
    if not doc.exists:
        return None
        
    updates = data.dict(exclude_unset=True)
    updates['updated_at'] = datetime.utcnow().isoformat()
    
    doc_ref.update(updates)
    
    # Can emit UPDATE event here if needed
    # await event_bus.emit("APPLICATION_UPDATED", {**updates, 'id': app_id, 'user_id': uid})
    
    return {**doc.to_dict(), **updates, 'id': app_id}

def delete_application(uid: str, app_id: str):
    db = firestore.client()
    db.collection('users').document(uid).collection('applications').document(app_id).delete()
    return True
