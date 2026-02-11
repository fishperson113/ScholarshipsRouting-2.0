"""
Cron Job Scheduler using Celery Beat.

Provides scheduled task infrastructure with:
- Periodic task scheduling
- Crontab-style scheduling
- Dynamic task registration
- Monitoring and logging
"""
from celery import Celery
from celery.schedules import crontab, schedule
from datetime import timedelta
from typing import Dict, Any, Optional
import os


# ==================== Celery Beat Configuration ====================

def configure_celery_beat(celery_app: Celery):
    """
    Configure Celery Beat with periodic tasks.
    
    Args:
        celery_app: Celery application instance
    """
    
    # Beat schedule configuration
    celery_app.conf.beat_schedule = {
        
        # ==================== Example Schedules ====================
        
        # Every minute
        # 'task-every-minute': {
        #     'task': 'tasks.example_periodic_task',
        #     'schedule': 60.0,  # seconds
        # },
        
        # Every 5 minutes
        # 'task-every-5-minutes': {
        #     'task': 'tasks.cleanup_task',
        #     'schedule': timedelta(minutes=5),
        # },
        
        # Every hour
        # 'task-hourly': {
        #     'task': 'tasks.hourly_sync',
        #     'schedule': crontab(minute=0),  # Run at minute 0 of every hour
        # },
        
        # Daily at midnight
        # 'task-daily-midnight': {
        #     'task': 'tasks.daily_report',
        #     'schedule': crontab(hour=0, minute=0),
        # },
        
        # Daily at specific time
        # 'task-daily-9am': {
        #     'task': 'tasks.morning_sync',
        #     'schedule': crontab(hour=9, minute=0),
        # },
        
        # Weekly on Monday at 9 AM
        # 'task-weekly-monday': {
        #     'task': 'tasks.weekly_report',
        #     'schedule': crontab(hour=9, minute=0, day_of_week=1),
        # },
        
        # Monthly on 1st at midnight
        # 'task-monthly': {
        #     'task': 'tasks.monthly_cleanup',
        #     'schedule': crontab(hour=0, minute=0, day_of_month=1),
        # },
        
        # Custom interval
        # 'task-custom-interval': {
        #     'task': 'tasks.custom_task',
        #     'schedule': schedule(run_every=timedelta(hours=2, minutes=30)),
        # },
        
    }
    
    # Beat scheduler settings
    celery_app.conf.update(
        # Timezone for cron schedules
        timezone='UTC',
        
        # Enable UTC
        enable_utc=True,
        
        # Beat scheduler backend (default: in-memory)
        # For production, use persistent backend like Redis or database
        beat_scheduler='celery.beat:PersistentScheduler',
        
        # Beat schedule filename (for PersistentScheduler)
        beat_schedule_filename='/tmp/celerybeat-schedule',
        
        # Maximum number of tasks to run per beat iteration
        beat_max_loop_interval=5,
    )


# ==================== Schedule Helpers ====================
from celery.schedules import crontab
from typing import Dict, Any

class CronSchedule:
    """Helper class to create various schedule types."""
    
    @staticmethod
    def every_n_minutes(n: int):
        """Run every N minutes."""
        return {"schedule": n * 60.0}
    
    @staticmethod
    def hourly(minute: int = 0):
        """Run every hour at specified minute."""
        return {"schedule": crontab(minute=minute)}
    
    @staticmethod
    def daily(hour: int = 0, minute: int = 0):
        """Run daily at specified time."""
        return {"schedule": crontab(hour=hour, minute=minute)}
    
    @staticmethod
    def weekly(day_of_week: int = 0, hour: int = 0, minute: int = 0):
        """
        Run weekly on specified day.
        day_of_week: 0=Monday, 6=Sunday
        """
        return {"schedule": crontab(day_of_week=day_of_week, hour=hour, minute=minute)}
    
    @staticmethod
    def monthly(day_of_month: int = 1, hour: int = 0, minute: int = 0):
        """Run monthly on specified day."""
        return {"schedule": crontab(day_of_month=day_of_month, hour=hour, minute=minute)}
    
    @staticmethod
    def custom(minute='*', hour='*', day_of_week='*', day_of_month='*', month_of_year='*'):
        """Create custom crontab schedule."""
        return {
            "schedule": crontab(
                minute=minute,
                hour=hour,
                day_of_week=day_of_week,
                day_of_month=day_of_month,
                month_of_year=month_of_year
            )
        }


def configure_celery_beat(celery_app):
    """
    Configure Celery Beat with scheduled tasks.
    
    Schedule Analysis for Elasticsearch Sync:
    
    Scholarship Data Characteristics:
    - Deadlines: Typically 1-6 months in advance
    - Application periods: Usually open for weeks/months
    - Data volatility: Low to medium (new scholarships added periodically)
    - Search freshness requirement: Within hours is acceptable
    
    Sync Strategy:
    - Primary sync: Every 6 hours (4 times/day)
      * Balances freshness with resource usage
      * Catches new scholarships within reasonable time
      * Reduces load on Firestore and Elasticsearch
    
    - Off-peak optimization: Sync at 2 AM, 8 AM, 2 PM, 8 PM
      * 2 AM: Minimal user activity, good for maintenance
      * 8 AM: Before morning peak usage
      * 2 PM: After lunch, before afternoon peak
      * 8 PM: Evening update for night users
    
    Alternative schedules (commented out):
    - Hourly: Too frequent, unnecessary load
    - Daily: Too infrequent, users may see stale data
    - Every 12 hours: Good balance but less responsive
    """
    
    celery_app.conf.beat_schedule = {
        # ==================== Elasticsearch Sync ====================
        'sync-elasticsearch-scholarships': {
            'task': 'tasks.sync_firestore_to_elasticsearch',
            'schedule': crontab(hour='2,8,14,20', minute=0),  # Every 6 hours
            'kwargs': {
                'collection': 'scholarships_403',
                'index': 'scholarships_403'
            },
            'options': {
                'expires': 3600,  # Task expires after 1 hour if not executed
            }
        },
        
        # ==================== Guest Session Cleanup ====================
        # Clean up expired guest sessions daily at 3 AM
        'cleanup-guest-sessions': {
            'task': 'tasks.cleanup_old_guest_sessions',
            'schedule': crontab(hour=3, minute=0),
            'options': {
                'expires': 7200,  # 2 hours
            }
        },

        # ==================== DEADLINE NOTIFICATIONS ====================
        # Check for upcoming deadlines daily at 00:00 (Midnight)
        'check-application-deadlines': {
            'task': 'tasks.check_application_deadlines',
            'schedule': crontab(hour=0, minute=0),
            'options': {
                'expires': 3600,
            }
        },
        
        # ==================== Example: Additional Collections ====================
        # Uncomment and configure for other collections as needed
        
        # 'sync-elasticsearch-universities': {
        #     'task': 'tasks.sync_firestore_to_elasticsearch',
        #     'schedule': crontab(hour='3,9,15,21', minute=0),  # Every 6 hours, offset by 1 hour
        #     'kwargs': {
        #         'collection': 'universities',
        #         'index': 'universities'
        #     }
        # },
        
        # ==================== Monitoring & Health Checks ====================
        # Add health check tasks here if needed
        
        # 'health-check-services': {
        #     'task': 'tasks.check_service_health',
        #     'schedule': CronSchedule.every_n_minutes(15)['schedule'],
        # },
    }
    
    # Set timezone for schedule
    celery_app.conf.timezone = 'Asia/Bangkok'  # UTC+7 (Vietnam/Thailand)
    
    return celery_app


# ==================== Dynamic Task Registration ====================

def register_dynamic_sync_task(celery_app, collection: str, index: str = None, schedule_hours: str = '2,8,14,20'):
    """
    Dynamically register a sync task for a collection.
    
    Args:
        celery_app: Celery application instance
        collection: Firestore collection name
        index: Elasticsearch index name (defaults to collection)
        schedule_hours: Comma-separated hours (e.g., '2,8,14,20')
        
    Example:
        register_dynamic_sync_task(celery_app, 'universities', schedule_hours='3,9,15,21')
    """
    index_name = index or collection
    task_name = f'sync-elasticsearch-{collection}'
    
    if not hasattr(celery_app.conf, 'beat_schedule'):
        celery_app.conf.beat_schedule = {}
    
    celery_app.conf.beat_schedule[task_name] = {
        'task': 'tasks.sync_firestore_to_elasticsearch',
        'schedule': crontab(hour=schedule_hours, minute=0),
        'kwargs': {
            'collection': collection,
            'index': index_name
        },
        'options': {
            'expires': 3600,
        }
    }
    
    return celery_app


# ==================== Schedule Monitoring ====================

def get_scheduled_tasks(celery_app) -> Dict[str, Any]:
    """
    Get all scheduled tasks for monitoring.
    
    Returns:
        Dict of task names and their schedules
    """
    if not hasattr(celery_app.conf, 'beat_schedule'):
        return {}
    
    schedules = {}
    for task_name, config in celery_app.conf.beat_schedule.items():
        schedules[task_name] = {
            'task': config['task'],
            'schedule': str(config['schedule']),
            'kwargs': config.get('kwargs', {}),
        }
    
    return schedules
