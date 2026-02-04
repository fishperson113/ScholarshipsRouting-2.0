
from celery import shared_task
import firebase_admin
from firebase_admin import firestore
from datetime import datetime, timedelta
import logging

# Setup Logger
logger = logging.getLogger(__name__)

# Constants
DAYS_BEFORE_DEADLINE = 3  # Notify 3 days before deadline

@shared_task(name="tasks.check_application_deadlines")
def check_application_deadlines():
    """
    Periodic task to check scholarship applications near deadline.
    Runs daily (configured in cron_scheduler.py).
    
    Logic:
    1. Scan all users' applications.
    2. Identify applications with deadline in X days (e.g., 3 days).
    3. Filter for status != 'submitted'.
    4. Create notification in Firestore.
    """
    logger.info("⏰ Starting deadline check task...")
    
    try:
        db = firestore.client()
        
        # We need to iterate through all users to find their applications
        # Note: This is a simple implementation. For huge user base, consider Collection Group Query.
        users_ref = db.collection('users')
        users = users_ref.stream()
        
        notification_count = 0
        
        for user in users:
            uid = user.id
            process_user_applications(db, uid, notification_count)

        logger.info(f"✅ Deadline check completed. Sent {notification_count} notifications.")
        return {"status": "success", "notifications_sent": notification_count}
        
    except Exception as e:
        logger.error(f"❌ Error in deadline check task: {str(e)}")
        return {"status": "error", "error": str(e)}

def process_user_applications(db, uid, notification_count):
    """Helper to process applications for a single user."""
    try:
        # Get user's applications subcollection
        apps_ref = db.collection('users').document(uid).collection('applications')
        # Filter: Only check applications that are NOT submitted yet (draft, in_progress, etc)
        # Assuming status 'submitted' means we don't need to remind.
        # If you want to remind even if submitted (unlikely), remove this filter.
        apps = apps_ref.where('status', '!=', 'submitted').stream()
        
        today = datetime.now().date()
        target_date = today + timedelta(days=DAYS_BEFORE_DEADLINE)
        
        for app in apps:
            data = app.to_dict()
            deadline_str = data.get('deadline') # Expecting ISO string or YYYY-MM-DD
            scholarship_name = data.get('scholarship_name', 'Unknown Scholarship')
            
            if not deadline_str:
                continue
                
            # Parse deadline (handle differences in format)
            try:
                # Try parsing ISO format first
                if 'T' in deadline_str:
                    deadline_date = datetime.fromisoformat(deadline_str.replace('Z', '')).date()
                else:
                    deadline_date = datetime.strptime(deadline_str, "%Y-%m-%d").date()
            except ValueError:
                # Fallback or invalid date format
                continue
            
            # Check if deadline matches target date (exactly 3 days away)
            # You can change to <= if you want persistent reminders
            if deadline_date == target_date:
                send_deadline_notification(db, uid, app.id, scholarship_name, DAYS_BEFORE_DEADLINE)
                notification_count += 1
                
    except Exception as e:
        logger.warning(f"⚠️ Error processing user {uid}: {e}")

def send_deadline_notification(db, uid, app_id, scholarship_name, days_left):
    """Create a notification document in Firestore."""
    notification_data = {
        'userId': uid,
        'type': 'DEADLINE_WARNING',
        'title': 'Hồ sơ sắp hết hạn!',
        'message': f'Hồ sơ học bổng "{scholarship_name}" sẽ hết hạn trong {days_left} ngày nữa. Hãy nộp ngay!',
        'isRead': False,
        'createdAt': firestore.SERVER_TIMESTAMP,
        'link': '/app/applications',
        'metadata': {
            'applicationId': app_id,
            'daysLeft': days_left,
            'isUrgent': True
        }
    }
    
    db.collection('notifications').add(notification_data)
    logger.info(f"🔔 Notification sent to {uid} for {scholarship_name}")
