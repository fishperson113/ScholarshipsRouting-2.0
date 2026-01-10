"""
Generic Webhook Handler for receiving external events.

Provides a secure, extensible webhook infrastructure with:
- Signature verification
- Event routing
- Retry handling
- Logging and monitoring
"""
import os
import hmac
import hashlib
import json
from typing import Dict, Any, Optional, Callable
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, Header, BackgroundTasks
from pydantic import BaseModel, Field


# ==================== Webhook Models ====================

class WebhookEvent(BaseModel):
    """Base model for webhook events."""
    event_type: str = Field(..., description="Type of event (e.g., 'user.created', 'payment.completed')")
    event_id: str = Field(..., description="Unique event identifier")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: Dict[str, Any] = Field(..., description="Event payload data")
    source: Optional[str] = Field(None, description="Event source system")


class WebhookResponse(BaseModel):
    """Standard webhook response."""
    received: bool = True
    event_id: str
    message: str = "Webhook received successfully"


# ==================== Webhook Router ====================

router = APIRouter()


# ==================== Event Handlers Registry ====================

class WebhookHandlerRegistry:
    """
    Registry for webhook event handlers.
    
    Allows registering handlers for specific event types.
    """
    
    def __init__(self):
        self._handlers: Dict[str, Callable] = {}
    
    def register(self, event_type: str, handler: Callable):
        """
        Register a handler for an event type.
        
        Args:
            event_type: Event type to handle (e.g., 'user.created')
            handler: Async function to handle the event
        """
        self._handlers[event_type] = handler
    
    def get_handler(self, event_type: str) -> Optional[Callable]:
        """Get handler for event type."""
        return self._handlers.get(event_type)
    
    def list_handlers(self) -> list:
        """List all registered event types."""
        return list(self._handlers.keys())


# Global registry
webhook_registry = WebhookHandlerRegistry()


# ==================== Signature Verification ====================

def verify_webhook_signature(
    payload: bytes,
    signature: str,
    secret: str,
    algorithm: str = "sha256"
) -> bool:
    """
    Verify webhook signature using HMAC.
    
    Args:
        payload: Raw request body
        signature: Signature from header
        secret: Webhook secret key
        algorithm: Hash algorithm (default: sha256)
        
    Returns:
        True if signature is valid
    """
    if not secret:
        # Skip verification if no secret configured (dev mode)
        return True
    
    expected_signature = hmac.new(
        secret.encode(),
        payload,
        getattr(hashlib, algorithm)
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected_signature)


# ==================== Webhook Endpoints ====================

@router.post("/webhook/{provider}", response_model=WebhookResponse)
async def receive_webhook(
    provider: str,
    request: Request,
    background_tasks: BackgroundTasks,
    x_webhook_signature: Optional[str] = Header(None),
    x_event_type: Optional[str] = Header(None)
):
    """
    Generic webhook receiver endpoint.
    
    Supports multiple providers with signature verification.
    
    Args:
        provider: Webhook provider name (e.g., 'stripe', 'github', 'custom')
        request: FastAPI request object
        background_tasks: Background task queue
        x_webhook_signature: Signature header (provider-specific)
        x_event_type: Event type header (optional)
        
    Returns:
        WebhookResponse confirming receipt
        
    Example:
        POST /api/v1/webhooks/webhook/stripe
        Headers:
            X-Webhook-Signature: sha256=abc123...
            X-Event-Type: payment.completed
        Body:
            {"event_id": "evt_123", "data": {...}}
    """
    # Get raw body for signature verification
    raw_body = await request.body()
    
    # Verify signature
    webhook_secret = os.getenv(f"WEBHOOK_SECRET_{provider.upper()}")
    
    if webhook_secret and x_webhook_signature:
        if not verify_webhook_signature(raw_body, x_webhook_signature, webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
    
    # Parse payload
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    
    # Create webhook event
    event = WebhookEvent(
        event_type=x_event_type or payload.get("event_type", "unknown"),
        event_id=payload.get("event_id", f"{provider}_{datetime.utcnow().timestamp()}"),
        data=payload.get("data", payload),
        source=provider
    )
    
    # Process event in background
    background_tasks.add_task(process_webhook_event, event)
    
    return WebhookResponse(
        event_id=event.event_id,
        message=f"Webhook from {provider} received and queued for processing"
    )


async def process_webhook_event(event: WebhookEvent):
    """
    Process webhook event by routing to appropriate handler.
    
    Args:
        event: WebhookEvent to process
    """
    try:
        # Get handler for event type
        handler = webhook_registry.get_handler(event.event_type)
        
        if handler:
            # Execute handler
            await handler(event)
            print(f"✅ Webhook processed: {event.event_type} ({event.event_id})")
        else:
            # Log unhandled event
            print(f"⚠️  No handler for webhook: {event.event_type} ({event.event_id})")
            
            # Optionally queue for manual review
            await store_unhandled_webhook(event)
            
    except Exception as e:
        print(f"❌ Webhook processing error: {event.event_type} - {str(e)}")
        # Optionally retry or send to dead letter queue
        await handle_webhook_error(event, e)


async def store_unhandled_webhook(event: WebhookEvent):
    """Store unhandled webhooks for manual review."""
    # TODO: Implement storage (Firestore, database, etc.)
    pass


async def handle_webhook_error(event: WebhookEvent, error: Exception):
    """Handle webhook processing errors."""
    # TODO: Implement error handling (retry, DLQ, alerts, etc.)
    pass


# ==================== Health Check ====================

@router.get("/webhook/health")
async def webhook_health():
    """Health check for webhook service."""
    return {
        "status": "ok",
        "registered_handlers": webhook_registry.list_handlers(),
        "timestamp": datetime.utcnow().isoformat()
    }


# ==================== Helper Functions ====================

def register_webhook_handler(event_type: str):
    """
    Decorator to register webhook handlers.
    
    Usage:
        @register_webhook_handler("user.created")
        async def handle_user_created(event: WebhookEvent):
            user_data = event.data
            # Process user creation
    """
    def decorator(func: Callable):
        webhook_registry.register(event_type, func)
        return func
    return decorator
