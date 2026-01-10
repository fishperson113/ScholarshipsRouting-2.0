"""
Redis Pub/Sub implementation for real-time updates.

Provides publish/subscribe pattern for:
- Real-time notifications
- Event broadcasting
- Cache invalidation coordination
- WebSocket message distribution
"""
import json
from typing import Callable, Dict, Any, Optional
from services.redis_manager import redis_manager
import threading


class RedisPubSub:
    """
    Redis Pub/Sub manager for real-time messaging.
    
    Implements publisher/subscriber pattern for event-driven architecture.
    """
    
    def __init__(self):
        self._pubsub = redis_manager.client.pubsub()
        self._subscribers: Dict[str, list] = {}
        self._listener_thread: Optional[threading.Thread] = None
        self._running = False
    
    # ==================== Publisher Methods ====================
    
    def publish(self, channel: str, message: Dict[str, Any]) -> int:
        """
        Publish message to a channel.
        
        Args:
            channel: Channel name
            message: Message data (will be JSON serialized)
            
        Returns:
            Number of subscribers that received the message
            
        Example:
            pubsub.publish("document.updated", {
                "collection": "scholarships",
                "doc_id": "abc123",
                "action": "update"
            })
        """
        try:
            serialized = json.dumps(message)
            return redis_manager.client.publish(channel, serialized)
        except Exception as e:
            print(f"Publish error: {e}")
            return 0
    
    def publish_document_update(self, collection: str, doc_id: str, action: str = "update"):
        """
        Publish document update event.
        
        Args:
            collection: Collection name
            doc_id: Document ID
            action: Action type (create, update, delete)
        """
        self.publish(f"firestore.{collection}", {
            "collection": collection,
            "doc_id": doc_id,
            "action": action,
            "timestamp": None  # Will be set by JSON serializer
        })
    
    def publish_cache_invalidation(self, pattern: str):
        """
        Publish cache invalidation event.
        
        Useful for distributed cache invalidation across multiple servers.
        
        Args:
            pattern: Cache key pattern to invalidate
        """
        self.publish("cache.invalidate", {
            "pattern": pattern
        })
    
    # ==================== Subscriber Methods ====================
    
    def subscribe(self, channel: str, callback: Callable[[Dict[str, Any]], None]):
        """
        Subscribe to a channel with callback.
        
        Args:
            channel: Channel name to subscribe to
            callback: Function to call when message received
            
        Example:
            def on_document_update(message):
                print(f"Document updated: {message}")
            
            pubsub.subscribe("firestore.scholarships", on_document_update)
        """
        if channel not in self._subscribers:
            self._subscribers[channel] = []
            self._pubsub.subscribe(channel)
        
        self._subscribers[channel].append(callback)
        
        # Start listener thread if not running
        if not self._running:
            self.start_listening()
    
    def unsubscribe(self, channel: str):
        """Unsubscribe from a channel."""
        if channel in self._subscribers:
            self._pubsub.unsubscribe(channel)
            del self._subscribers[channel]
    
    def start_listening(self):
        """Start background thread to listen for messages."""
        if self._running:
            return
        
        self._running = True
        self._listener_thread = threading.Thread(target=self._listen, daemon=True)
        self._listener_thread.start()
    
    def stop_listening(self):
        """Stop listening for messages."""
        self._running = False
        if self._listener_thread:
            self._listener_thread.join(timeout=5)
    
    def _listen(self):
        """Background listener loop."""
        for message in self._pubsub.listen():
            if not self._running:
                break
            
            if message['type'] == 'message':
                channel = message['channel']
                if isinstance(channel, bytes):
                    channel = channel.decode('utf-8')
                
                # Deserialize message
                try:
                    data = json.loads(message['data'])
                except:
                    data = message['data']
                
                # Call all subscribers for this channel
                if channel in self._subscribers:
                    for callback in self._subscribers[channel]:
                        try:
                            callback(data)
                        except Exception as e:
                            print(f"Subscriber callback error: {e}")
    
    # ==================== Predefined Channels ====================
    
    @staticmethod
    def channel_document_updates(collection: str) -> str:
        """Get channel name for document updates."""
        return f"firestore.{collection}"
    
    @staticmethod
    def channel_cache_invalidation() -> str:
        """Get channel name for cache invalidation."""
        return "cache.invalidate"
    
    @staticmethod
    def channel_user_notifications(user_id: str) -> str:
        """Get channel name for user notifications."""
        return f"user.{user_id}.notifications"


# ==================== Global Instance ====================

# Singleton instance
pubsub = RedisPubSub()


# ==================== Helper Functions ====================

def notify_document_change(collection: str, doc_id: str, action: str = "update"):
    """
    Notify subscribers about document changes.
    
    Use this in your Firestore write operations.
    
    Example:
        save_with_id("scholarships", "abc123", data)
        notify_document_change("scholarships", "abc123", "update")
    """
    pubsub.publish_document_update(collection, doc_id, action)


def invalidate_cache_globally(pattern: str):
    """
    Invalidate cache across all servers.
    
    Useful in distributed deployments.
    
    Example:
        invalidate_cache_globally("firestore:scholarships:*")
    """
    pubsub.publish_cache_invalidation(pattern)
