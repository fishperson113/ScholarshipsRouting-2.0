
from celery import shared_task
from firebase_admin import firestore
from datetime import datetime, timedelta
import logging
import asyncio
from services.event_manager import event_bus

logger = logging.getLogger(__name__)

DAYS_BEFORE_DEADLINE = 3

@shared_task(name="tasks.check_application_deadlines")
def check_application_deadlines():
    """
    Periodic task: Scans for expiring applications and emits events.
    It does NOT create notifications directly (SOC: Separation of Concerns).
    """
    logger.info("⏰ Starting deadline check task (Event-Driven)...")
    
    try:
        db = firestore.client()
        # Note: In production, use Collection Group Index for better performance:
        # db.collection_group('applications').where(...)
        
        users = db.collection('users').stream()
        processed_count = 0
        
        for user in users:
            uid = user.id
            apps_ref = db.collection('users').document(uid).collection('applications')
            # Check ALL applications regardless of status (submitted, saved, etc.)
            apps = apps_ref.stream()
            
            for app in apps:
                process_single_application(uid, app)
                processed_count += 1
                
        logger.info(f"✅ Deadline check completed. Scanned {processed_count} apps.")
        return {"status": "success", "scanned": processed_count}
        
    except Exception as e:
        logger.error(f"❌ Error in deadline check task: {str(e)}")
        return {"status": "error", "error": str(e)}

def process_single_application(uid, app):
    """Check dates and emit event if needed."""
    data = app.to_dict()
    
    # Priority: Use 'apply_date' (User target) -> Fallback to 'deadline' (Official)
    target_date_str = data.get('apply_date') or data.get('deadline')
    if not target_date_str:
        return

    try:
        # Import internally to allow cross-service usage
        from services.event_manager import event_bus
        import asyncio

        # Parse date (handle ISO format)
        if 'T' in target_date_str:
            target_date = datetime.fromisoformat(target_date_str.replace('Z', '')).date()
        else:
            target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
            
        today = datetime.utcnow().date()
        delta = (target_date - today).days
        
        # Trigger if days left is less than or equal to DAYS_BEFORE_DEADLINE
        # This handles both upcoming deadlines (0 to 3 days) and missed deadlines (negative days)
        if delta <= DAYS_BEFORE_DEADLINE:
            payload = {
                'user_id': uid,
                'application_id': app.id,
                'scholarship_name': data.get('scholarship_name', 'Unknown'),
                'days_left': delta,
                'deadline_date': target_date.isoformat()
            }
            
            # Fire and forget event
            # Fire and forget event
            try:
                loop = asyncio.get_running_loop()
                # If running in an event loop (e.g., FastAPI), schedule execution
                loop.create_task(event_bus.emit("DEADLINE_APPROACHING", payload))
            except RuntimeError:
                # If no running loop (e.g., Celery Worker), run synchronously
                asyncio.run(event_bus.emit("DEADLINE_APPROACHING", payload))
            
    except ValueError as e:
        print(f"❌ [Notification Error] Hiện tại đang lỗi ở process_single_application (ValueError). App ID: {app.id}. Vì ngày tháng không đúng định dạng: '{target_date_str}'. Chi tiết: {e}")
    except Exception as e:
        print(f"❌ [Notification Error] Hiện tại đang lỗi ở process_single_application (Exception). App ID: {app.id}. Vì lỗi không xác định: {e}")
        logger.error(f"Error processing app {app.id}: {e}")
