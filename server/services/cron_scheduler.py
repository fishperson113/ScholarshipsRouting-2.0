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

class CronSchedule:
    """Helper class for creating cron schedules."""
    
    @staticmethod
    def every_minute():
        """Run every minute."""
        return 60.0
    
    @staticmethod
    def every_n_minutes(n: int):
        """Run every N minutes."""
        return timedelta(minutes=n)
    
    @staticmethod
    def every_hour():
        """Run every hour at minute 0."""
        return crontab(minute=0)
    
    @staticmethod
    def every_n_hours(n: int):
        """Run every N hours."""
        return timedelta(hours=n)
    
    @staticmethod
    def daily(hour: int = 0, minute: int = 0):
        """Run daily at specific time."""
        return crontab(hour=hour, minute=minute)
    
    @staticmethod
    def weekly(day_of_week: int, hour: int = 0, minute: int = 0):
        """
        Run weekly on specific day.
        
        Args:
            day_of_week: 0=Monday, 6=Sunday
            hour: Hour (0-23)
            minute: Minute (0-59)
        """
        return crontab(hour=hour, minute=minute, day_of_week=day_of_week)
    
    @staticmethod
    def monthly(day: int = 1, hour: int = 0, minute: int = 0):
        """Run monthly on specific day."""
        return crontab(hour=hour, minute=minute, day_of_month=day)
    
    @staticmethod
    def custom(
        minute: str = '*',
        hour: str = '*',
        day_of_week: str = '*',
        day_of_month: str = '*',
        month_of_year: str = '*'
    ):
        """
        Create custom crontab schedule.
        
        Args:
            minute: Minute (0-59 or *)
            hour: Hour (0-23 or *)
            day_of_week: Day of week (0-6 or *)
            day_of_month: Day of month (1-31 or *)
            month_of_year: Month (1-12 or *)
            
        Example:
            # Every weekday at 9 AM
            CronSchedule.custom(hour='9', minute='0', day_of_week='1-5')
        """
        return crontab(
            minute=minute,
            hour=hour,
            day_of_week=day_of_week,
            day_of_month=day_of_month,
            month_of_year=month_of_year
        )


# ==================== Dynamic Task Registration ====================

class CronTaskRegistry:
    """Registry for dynamically adding cron tasks."""
    
    def __init__(self, celery_app: Celery):
        self.celery_app = celery_app
        self._tasks: Dict[str, Dict[str, Any]] = {}
    
    def register(
        self,
        name: str,
        task: str,
        schedule: Any,
        args: tuple = (),
        kwargs: dict = None,
        options: dict = None
    ):
        """
        Register a periodic task.
        
        Args:
            name: Unique task name
            task: Task path (e.g., 'tasks.my_task')
            schedule: Schedule (crontab, timedelta, or seconds)
            args: Task arguments
            kwargs: Task keyword arguments
            options: Additional options
        """
        task_config = {
            'task': task,
            'schedule': schedule,
        }
        
        if args:
            task_config['args'] = args
        if kwargs:
            task_config['kwargs'] = kwargs
        if options:
            task_config['options'] = options
        
        self._tasks[name] = task_config
        
        # Update beat schedule
        if hasattr(self.celery_app.conf, 'beat_schedule'):
            self.celery_app.conf.beat_schedule[name] = task_config
    
    def unregister(self, name: str):
        """Remove a periodic task."""
        if name in self._tasks:
            del self._tasks[name]
            if hasattr(self.celery_app.conf, 'beat_schedule'):
                self.celery_app.conf.beat_schedule.pop(name, None)
    
    def list_tasks(self) -> Dict[str, Dict[str, Any]]:
        """List all registered periodic tasks."""
        return self._tasks.copy()


# ==================== Monitoring ====================

def get_scheduled_tasks(celery_app: Celery) -> Dict[str, Any]:
    """
    Get all scheduled tasks with their next run time.
    
    Returns:
        Dictionary of task schedules
    """
    if not hasattr(celery_app.conf, 'beat_schedule'):
        return {}
    
    return {
        name: {
            'task': config['task'],
            'schedule': str(config['schedule']),
            'args': config.get('args', ()),
            'kwargs': config.get('kwargs', {}),
        }
        for name, config in celery_app.conf.beat_schedule.items()
    }
