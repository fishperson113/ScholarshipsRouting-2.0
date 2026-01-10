# Webhook & Cron Configuration

## Overview

Your project now has complete webhook and cron infrastructure configured with best practices.

## 🔗 Webhooks

### Endpoint
```
POST /api/v1/webhooks/webhook/{provider}
```

### Features
- ✅ Signature verification (HMAC-SHA256)
- ✅ Event routing system
- ✅ Background processing
- ✅ Extensible handler registry
- ✅ Error handling & logging

### Usage

#### 1. Configure Webhook Secret

Add to `.env`:
```bash
# For Stripe webhooks
WEBHOOK_SECRET_STRIPE=whsec_your_stripe_secret

# For GitHub webhooks
WEBHOOK_SECRET_GITHUB=your_github_secret

# For custom webhooks
WEBHOOK_SECRET_CUSTOM=your_custom_secret
```

#### 2. Register Event Handler

In your code (e.g., `tasks.py` or new file):
```python
from routes.webhooks import register_webhook_handler, WebhookEvent

@register_webhook_handler("user.created")
async def handle_user_created(event: WebhookEvent):
    user_data = event.data
    # Process user creation
    print(f"New user: {user_data}")
```

#### 3. Send Webhook

External services send to:
```bash
POST https://your-domain.com/api/v1/webhooks/webhook/stripe
Headers:
  X-Webhook-Signature: sha256=abc123...
  X-Event-Type: payment.completed
Body:
  {
    "event_id": "evt_123",
    "data": {...}
  }
```

### Supported Providers

Configure any provider by adding `WEBHOOK_SECRET_{PROVIDER}` to `.env`:
- Stripe: `WEBHOOK_SECRET_STRIPE`
- GitHub: `WEBHOOK_SECRET_GITHUB`
- Custom: `WEBHOOK_SECRET_CUSTOM`

---

## ⏰ Cron Jobs (Celery Beat)

### Features
- ✅ Crontab-style scheduling
- ✅ Interval-based scheduling
- ✅ Dynamic task registration
- ✅ Persistent schedule storage
- ✅ Monitoring via Flower

### Schedule Types

#### Every N Minutes
```python
from services.cron_scheduler import CronSchedule

schedule = CronSchedule.every_n_minutes(5)  # Every 5 minutes
```

#### Hourly
```python
schedule = CronSchedule.every_hour()  # Every hour at :00
```

#### Daily
```python
schedule = CronSchedule.daily(hour=9, minute=0)  # Daily at 9:00 AM
```

#### Weekly
```python
schedule = CronSchedule.weekly(day_of_week=1, hour=9)  # Monday at 9 AM
```

#### Monthly
```python
schedule = CronSchedule.monthly(day=1, hour=0)  # 1st of month at midnight
```

#### Custom Crontab
```python
# Weekdays at 9 AM
schedule = CronSchedule.custom(hour='9', minute='0', day_of_week='1-5')
```

### Adding Scheduled Tasks

Edit `services/cron_scheduler.py`:

```python
celery_app.conf.beat_schedule = {
    'daily-cleanup': {
        'task': 'tasks.cleanup_old_sessions',
        'schedule': crontab(hour=0, minute=0),  # Midnight daily
    },
    
    'hourly-sync': {
        'task': 'tasks.sync_scholarships',
        'schedule': crontab(minute=0),  # Every hour
    },
    
    'every-5-minutes': {
        'task': 'tasks.check_deadlines',
        'schedule': timedelta(minutes=5),
    },
}
```

### Create Scheduled Task

In `tasks.py`:
```python
from celery_app import celery_app

@celery_app.task(name="tasks.cleanup_old_sessions")
def cleanup_old_sessions():
    """Run daily at midnight."""
    # Your cleanup logic
    return {"cleaned": 10}
```

### Monitor Scheduled Tasks

- **Flower UI**: http://localhost:5555
- Navigate to "Tasks" → "Scheduled"
- View next run time, history, and results

---

## 🐳 Docker Services

### Services Added

```yaml
# Celery Beat (Cron Scheduler)
celery_beat:
  command: celery -A celery_app beat --loglevel=info
  # Runs scheduled tasks
```

### Start Services

```bash
docker compose up -d
```

### Check Logs

```bash
# Webhook processing
docker logs scholarships-server

# Cron scheduler
docker logs scholarships-celery-beat

# Task execution
docker logs scholarships-celery-worker
```

---

## 📋 Quick Reference

### Webhook Flow
```
External Service → POST /webhook/{provider}
                ↓
         Verify Signature
                ↓
         Parse Event
                ↓
         Queue Background Task
                ↓
         Route to Handler
                ↓
         Process Event
```

### Cron Flow
```
Celery Beat → Check Schedule
           ↓
      Task Due?
           ↓
      Queue Task
           ↓
      Celery Worker → Execute
                   ↓
                Result
```

---

## 🔒 Security

### Webhook Security
- Always verify signatures in production
- Use HTTPS for webhook endpoints
- Validate event data before processing
- Rate limit webhook endpoints

### Cron Security
- Tasks run with app permissions
- Use environment variables for secrets
- Log all scheduled task executions
- Monitor for failed tasks

---

## 📊 Monitoring

### Webhook Health
```bash
GET /api/v1/webhooks/webhook/health
```

Returns registered handlers and status.

### Cron Monitoring

Via Flower (http://localhost:5555):
- View scheduled tasks
- Check next run times
- See execution history
- Monitor failures

### Logs

```bash
# All webhook events
docker logs scholarships-server | grep "Webhook"

# All cron executions
docker logs scholarships-celery-beat

# Task results
docker logs scholarships-celery-worker
```

---

## 🚀 Production Checklist

### Webhooks
- [ ] Configure webhook secrets for all providers
- [ ] Enable HTTPS
- [ ] Set up webhook retry logic
- [ ] Monitor webhook failures
- [ ] Rate limit webhook endpoints

### Cron
- [ ] Review all scheduled tasks
- [ ] Set appropriate timezones
- [ ] Configure task timeouts
- [ ] Set up alerting for failures
- [ ] Use persistent beat scheduler

---

## 📁 File Structure

```
server/
├── routes/
│   └── webhooks.py          # Webhook endpoints & handlers
├── services/
│   └── cron_scheduler.py    # Cron configuration
├── celery_app.py            # Celery + Beat config
└── tasks.py                 # Task definitions
```

---

## ✅ What's Configured

**Webhooks:**
- Generic endpoint for any provider
- Signature verification
- Event routing
- Background processing
- Handler registry

**Cron:**
- Celery Beat scheduler
- Multiple schedule types
- Dynamic task registration
- Persistent schedules
- Monitoring integration

**Infrastructure:**
- Docker services running
- Redis for task queue
- Flower for monitoring
- Automatic restarts
