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
    Listener: When deadline is near OR passed -> Send notification.
    Payload: { 
        'user_id': uid, 
        'application_id': app_id, 
        'scholarship_name': name, 
        'days_left': delta,
        'deadline_date': 'YYYY-MM-DD' 
    }
    """
    db = firestore.client()
    uid = payload.get('user_id')
    days = payload.get('days_left')
    name = payload.get('scholarship_name')
    app_id = payload.get('application_id')
    deadline_date_str = payload.get('deadline_date', 'N/A')
    
    # 1. Format the deadline date for display
    try:
        if 'T' in deadline_date_str:
             deadline_dt = datetime.fromisoformat(deadline_date_str.replace('Z', ''))
        else:
             deadline_dt = datetime.strptime(deadline_date_str, "%Y-%m-%d")
        formatted_date = deadline_dt.strftime("ngày %d tháng %m năm %Y")
    except:
        formatted_date = deadline_date_str

    # 2. Determine Notification Type and Check Logic
    if days < 0:
        # --- CASE 1: LATE DEADLINE (Quote: "chỉ báo 1 lần") ---
        notif_type = 'DEADLINE_MISSED'
        
        # Check if ANY notification of this type exists for this application
        existing_docs = db.collection('notifications')\
            .where('userId', '==', uid)\
            .where('type', '==', notif_type)\
            .where('metadata.application_id', '==', app_id)\
            .limit(1).stream()
            
        if any(existing_docs):
            logger.info(f"🚫 Anti-spam: 'Late' notification for app {app_id} already exists. Skipping.")
            return

        title = '⚠️ Đã quá hạn nộp!'
        message = f'Học bổng "{name}" đã kết thúc vào {formatted_date}. Rất tiếc bạn đã lỡ hạn nộp.'

    else:
        # --- CASE 2: UPCOMING DEADLINE (Quote: "mỗi ngày báo 1 lần") ---
        notif_type = 'DEADLINE_WARNING'
        
        # Check if notification exists TODAY
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        
        existing_docs = db.collection('notifications')\
            .where('userId', '==', uid)\
            .where('type', '==', notif_type)\
            .where('metadata.application_id', '==', app_id)\
            .where('createdAt', '>=', today_start)\
            .limit(1).stream()

        if any(existing_docs):
            logger.info(f"🚫 Anti-spam: 'Upcoming' notification for app {app_id} already sent TODAY. Skipping.")
            return

        title = '🔥 Sắp hết hạn nộp!'
        message = f'Bạn có học bổng "{name}" sắp tới hạn. Hạn nộp là {formatted_date} (giờ gốc).'

    # 3. Create Notification
    notification_data = {
        'userId': uid,
        'type': notif_type,
        'title': title,
        'message': message,
        'isRead': False,
        'createdAt': firestore.SERVER_TIMESTAMP,
        'link': '/app/applications',
        'metadata': payload
    }
    
    db.collection('notifications').add(notification_data)
    logger.info(f"🔔 Notification sent to {uid}: {title}")

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
    
    # Remove debug logs and add duplicate check
    
    # Check if application already exists for this scholarship
    existing_docs = db.collection('users').document(uid).collection('applications')\
        .where('scholarship_id', '==', data.scholarship_id).limit(1).stream()
    
    for doc in existing_docs:
        # If exists, return existing application instead of creating duplicate
        print(f"DEBUG: Application for scholarship {data.scholarship_id} already exists. Skipping create.")
        return {**doc.to_dict(), 'id': doc.id}

    # Save to Firestore if not exists
    doc_ref = db.collection('users').document(uid).collection('applications').document()
    doc_ref.set(new_app)
    
    result = {**new_app, 'id': doc_ref.id}
    
    # 📢 EMIT EVENT (The "Webhook" trigger)
    # This decouples the notification logic from the saving logic
    await event_bus.emit("APPLICATION_CREATED", result)
    
    # --- IMMEDIATE DEADLINE CHECK (For Testing & Real-time feedback) ---
    try:
        from services.tasks.notification_tasks import process_single_application
        
        # Create a mock object similar to Firestore DocumentSnapshot
        class MockDoc:
            def __init__(self, data, doc_id):
                self._data = data
                self.id = doc_id
            def to_dict(self):
                return self._data
                
        mock_app_doc = MockDoc(result, doc_ref.id)
        
        # Run check immediately (synchronously or awaitable if converted)
        # Since process_single_application emits an async event, we can just call it
        process_single_application(uid, mock_app_doc)
        logger.info(f"⚡ Instant deadline check triggered for {doc_ref.id}")
        
    except Exception as e:
        logger.error(f"Failed instant deadline check: {e}")
    
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

def delete_application_by_scholarship_id(uid: str, scholarship_id: str):
    db = firestore.client()
    apps_ref = db.collection('users').document(uid).collection('applications')
    
    # Query for documents with this scholarship_id
    docs = apps_ref.where('scholarship_id', '==', scholarship_id).stream()
    
    deleted_count = 0
    for doc in docs:
        doc.reference.delete()
        deleted_count += 1
        
    return deleted_count > 0
