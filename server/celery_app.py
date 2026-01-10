"""
Celery application configuration for background tasks.
"""
import os
from celery import Celery

# Get broker and backend URLs from environment
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://:redis_pass@redis:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://:redis_pass@redis:6379/0")

# Create Celery app
celery_app = Celery(
    "scholarships_tasks",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    
    # Task execution settings
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes hard limit
    task_soft_time_limit=25 * 60,  # 25 minutes soft limit
    
    # Result backend settings
    result_expires=3600,  # Results expire after 1 hour
    result_persistent=True,
    
    # Worker settings
    worker_prefetch_multiplier=4,
    worker_max_tasks_per_child=1000,
    
    # Broker settings
    broker_connection_retry_on_startup=True,
)

# ==================== Initialize Firebase for Celery Workers ====================
# Celery workers run in separate processes and need their own Firebase initialization
import firebase_admin
from firebase_admin import credentials

if not firebase_admin._apps:
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if cred_path and os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        print(f"✅ Firebase initialized for Celery workers: {cred_path}")
    else:
        print(f"⚠️  Firebase credentials not found: {cred_path}")

# ==================== Configure Cron Scheduler ====================
# Import and configure Celery Beat for scheduled tasks
try:
    from services.cron_scheduler import configure_celery_beat
    configure_celery_beat(celery_app)
except ImportError:
    # Cron scheduler not yet configured
    pass

# ==================== Auto-discover Tasks ====================
# Discover tasks from services.tasks module
celery_app.autodiscover_tasks(['services'], force=True)