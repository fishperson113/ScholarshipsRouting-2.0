from firebase_admin import firestore
from datetime import datetime
import hashlib
from dtos.application_dtos import ApplicationCreate, ApplicationUpdate
from services.event_manager import event_bus
from services.pubsub import pubsub, RedisPubSub
import logging

logger = logging.getLogger(__name__)

# ==================== Configuration & Helpers ====================

NOTIFICATION_RULES = {
    0: ("DEADLINE_TODAY", "Deadline Today!", "URGENT: Scholarship '{name}' deadline is TODAY ({date}). Submit now!"),
    1: ("DEADLINE_1_DAY", "1 Day Left", "Hurry! Scholarship '{name}' ends tomorrow ({date})."),
    3: ("DEADLINE_3_DAYS", "3 Days Left", "Scholarship '{name}' has 3 days left. Deadline: {date}."),
    7: ("DEADLINE_7_DAYS", "1 Week Left", "Scholarship '{name}' has 1 week left. Ends on {date}.")
}

def get_notification_config(days: int):
    """Lấy Metadata của thông báo dựa vào số ngày (Rules dictionary)"""
    if days < 0:
        return ("DEADLINE_MISSED", "Deadline Missed", 'The scholarship "{name}" ended on {date}. Unfortunately, you missed the deadline.')
    return NOTIFICATION_RULES.get(days)

def generate_idempotent_id(uid: str, app_id: str, type_name: str, target_date: str) -> str:
    """Tạo Document ID duy nhất bằng Hash MD5 để chống Spam"""
    raw_str = f"{uid}_{app_id}_{type_name}_{target_date}"
    return hashlib.md5(raw_str.encode('utf-8')).hexdigest()

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
        'title': 'New Application Started',
        'message': f'You have started an application for "{app_name}". Remember to update your progress!',
        'isRead': False,
        'createdAt': firestore.SERVER_TIMESTAMP,
        'link': '/app/applications',
        'metadata': payload
    }
    
    update_time, doc_ref = db.collection('notifications').add(notification_data)
    logger.info(f"🔔 Notification sent to {uid} for new application")

    # Real-time publish
    try:
        realtime_payload = notification_data.copy()
        realtime_payload['id'] = doc_ref.id
        realtime_payload['createdAt'] = datetime.utcnow().isoformat()
        pubsub.publish(RedisPubSub.channel_user_notifications(uid), realtime_payload)
    except Exception as e:
        logger.error(f"Failed to publish realtime notification: {e}")

async def handle_deadline_approaching(payload: dict):
    """
    Listener: When deadline is near OR passed -> Send notification using Idempotent Key.
    """
    db = firestore.client()
    uid = payload.get('user_id')
    try:
        days = int(payload.get('days_left'))
    except (ValueError, TypeError):
        logger.error(f"Invalid days_left in payload: {payload.get('days_left')}")
        return

    name = payload.get('scholarship_name', 'Unknown')
    app_id = payload.get('application_id')
    deadline_date_str = payload.get('deadline_date', 'N/A')
    
    # 1. Format the deadline date for display
    try:
        if 'T' in deadline_date_str:
             deadline_dt = datetime.fromisoformat(deadline_date_str.replace('Z', ''))
        else:
             deadline_dt = datetime.strptime(deadline_date_str, "%Y-%m-%d")
        formatted_date = deadline_dt.strftime("%B %d, %Y")
    except:
        formatted_date = deadline_date_str

    # 2. Get Notification Rule
    config = get_notification_config(days)
    if not config:
        return  # Bỏ qua nếu không đúng mốc thời gian báo (vd: >7 ngày, hay 2,4,5,6 ngày)
        
    notif_type, title, message_tpl = config
    message = message_tpl.format(name=name, date=formatted_date)

    # 3. Create Idempotency Key
    idempotent_id = generate_idempotent_id(uid, app_id, notif_type, deadline_date_str)
    
    # 4. Check & Create Notification (Anti-Spam Shield)
    doc_ref = db.collection('notifications').document(idempotent_id)
    
    # Firebase Firestore read (1 doc read is extremely cheap and fast)
    if doc_ref.get().exists:
        logger.info(f"🚫 Anti-spam: Notification '{notif_type}' for app {app_id} already exists. Skipping.")
        return
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
    
    # Notice: using .set() with the generated ID instead of .add()
    doc_ref.set(notification_data)
    logger.info(f"🔔 Notification sent to {uid}: {title}")

    # 5. Real-time publish
    try:
        realtime_payload = notification_data.copy()
        realtime_payload['id'] = idempotent_id
        realtime_payload['createdAt'] = datetime.utcnow().isoformat()
        pubsub.publish(RedisPubSub.channel_user_notifications(uid), realtime_payload)
    except Exception as e:
        logger.error(f"Failed to publish realtime notification: {e}")

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
        from services.tasks import process_single_application
        
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

# ==================== Notification Services (API Proxy) ====================

def get_user_notifications(uid: str, limit: int = 50):
    """
    Retrieve user notifications via Backend API (Bypassing Firestore Client Rules).
    """
    db = firestore.client()
    try:
        # Query notifications for the user
        # Note: Backend Admin SDK has full access, so no security rules apply here.
        docs = db.collection('notifications')\
            .where('userId', '==', uid)\
            .order_by('createdAt', direction=firestore.Query.DESCENDING)\
            .limit(limit)\
            .stream()
            
        notifications = []
        for doc in docs:
            data = doc.to_dict()
            # Convert timestamp to ISO string for JSON serialization
            if data.get('createdAt'):
                data['createdAt'] = data['createdAt'].isoformat()
            
            notifications.append({**data, 'id': doc.id})
            
        return notifications
    except Exception as e:
        logger.error(f"Error fetching notifications for {uid}: {e}")
        return []

def mark_notification_read(uid: str, notification_id: str):
    """
    Mark a notification as read. Verifies ownership first.
    """
    db = firestore.client()
    try:
        ref = db.collection('notifications').document(notification_id)
        doc = ref.get()
        
        if not doc.exists:
            return False
            
        data = doc.to_dict()
        # Security Check: Ensure the notification belongs to the user
        if data.get('userId') != uid:
            logger.warning(f"Unauthorized read attempt by {uid} on notif {notification_id}")
            return False
            
        ref.update({'isRead': True})
        return True
    except Exception as e:
        logger.error(f"Error marking notification read: {e}")
        return False
