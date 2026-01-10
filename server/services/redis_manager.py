"""
Redis Manager with Cache-Aside and Write-Around patterns.

This module provides a centralized Redis connection manager and implements
common caching patterns for the application.
"""
import os
import json
import redis
from typing import Any, Optional, Callable, Union
from datetime import timedelta
from functools import wraps


class RedisManager:
    """
    Singleton Redis connection manager with caching patterns.
    
    Implements:
    - Cache-Aside (Lazy Loading): Read from cache, if miss then read from source and populate cache
    - Write-Around: Write to source directly, invalidate cache
    """
    
    _instance: Optional['RedisManager'] = None
    _client: Optional[redis.Redis] = None
    
    def __new__(cls):
        """Singleton pattern to ensure single Redis connection pool."""
        if cls._instance is None:
            cls._instance = super(RedisManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize Redis connection if not already initialized."""
        if self._client is None:
            self._connect()
    
    def _connect(self):
        """Establish Redis connection with configuration from environment."""
        redis_host = os.getenv("REDIS_HOST", "redis")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        redis_password = os.getenv("REDIS_PASSWORD", "redis_pass")
        redis_db = int(os.getenv("REDIS_DB", "0"))
        
        self._client = redis.Redis(
            host=redis_host,
            port=redis_port,
            password=redis_password,
            db=redis_db,
            decode_responses=True,  # Auto-decode bytes to strings
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30,
        )
        
        # Test connection
        try:
            self._client.ping()
            print(f"✅ Redis connected: {redis_host}:{redis_port}")
        except redis.ConnectionError as e:
            print(f"❌ Redis connection failed: {e}")
            raise
    
    @property
    def client(self) -> redis.Redis:
        """Get Redis client instance."""
        if self._client is None:
            self._connect()
        return self._client
    
    # ==================== Cache-Aside Pattern ====================
    
    def get_cached(
        self,
        key: str,
        fetch_func: Optional[Callable[[], Any]] = None,
        ttl: Optional[int] = 3600,
        deserializer: Callable[[str], Any] = json.loads
    ) -> Optional[Any]:
        """
        Cache-Aside (Lazy Loading) pattern.
        
        1. Try to get data from cache
        2. If cache miss and fetch_func provided, fetch from source
        3. Store in cache and return
        
        Args:
            key: Cache key
            fetch_func: Function to fetch data if cache miss (optional)
            ttl: Time-to-live in seconds (default: 1 hour)
            deserializer: Function to deserialize cached value (default: json.loads)
            
        Returns:
            Cached or fetched data, or None if not found
            
        Example:
            >>> def get_user_from_db(user_id):
            ...     return db.query(User).filter_by(id=user_id).first()
            >>> 
            >>> user = redis_mgr.get_cached(
            ...     key=f"user:{user_id}",
            ...     fetch_func=lambda: get_user_from_db(user_id),
            ...     ttl=3600
            ... )
        """
        try:
            # Step 1: Try cache first
            cached_value = self.client.get(key)
            
            if cached_value is not None:
                # Cache hit
                return deserializer(cached_value)
            
            # Step 2: Cache miss - fetch from source if function provided
            if fetch_func is not None:
                fresh_data = fetch_func()
                
                if fresh_data is not None:
                    # Step 3: Populate cache
                    self.set_cached(key, fresh_data, ttl=ttl)
                
                return fresh_data
            
            return None
            
        except redis.RedisError as e:
            print(f"Redis error in get_cached: {e}")
            # Fallback: fetch from source if available
            if fetch_func is not None:
                return fetch_func()
            return None
    
    def set_cached(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = 3600,
        serializer: Callable[[Any], str] = json.dumps
    ) -> bool:
        """
        Set value in cache with TTL.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (default: 1 hour, None = no expiration)
            serializer: Function to serialize value (default: json.dumps)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            serialized = serializer(value)
            if ttl is not None:
                return self.client.setex(key, ttl, serialized)
            else:
                return self.client.set(key, serialized)
        except redis.RedisError as e:
            print(f"Redis error in set_cached: {e}")
            return False
    
    # ==================== Write-Around Pattern ====================
    
    def invalidate(self, key: str) -> bool:
        """
        Write-Around pattern: Invalidate cache entry.
        
        Use this when writing to the source database to ensure
        cache doesn't serve stale data.
        
        Args:
            key: Cache key to invalidate
            
        Returns:
            True if key was deleted, False otherwise
            
        Example:
            >>> # Update database
            >>> db.update_user(user_id, new_data)
            >>> # Invalidate cache
            >>> redis_mgr.invalidate(f"user:{user_id}")
        """
        try:
            return bool(self.client.delete(key))
        except redis.RedisError as e:
            print(f"Redis error in invalidate: {e}")
            return False
    
    def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate all keys matching a pattern.
        
        Args:
            pattern: Redis key pattern (e.g., "user:*", "session:*")
            
        Returns:
            Number of keys deleted
            
        Example:
            >>> # Invalidate all user caches
            >>> redis_mgr.invalidate_pattern("user:*")
        """
        try:
            keys = self.client.keys(pattern)
            if keys:
                return self.client.delete(*keys)
            return 0
        except redis.RedisError as e:
            print(f"Redis error in invalidate_pattern: {e}")
            return 0
    
    # ==================== Utility Methods ====================
    
    def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        try:
            return bool(self.client.exists(key))
        except redis.RedisError as e:
            print(f"Redis error in exists: {e}")
            return False
    
    def get_ttl(self, key: str) -> int:
        """
        Get remaining TTL for a key.
        
        Returns:
            TTL in seconds, -1 if no expiration, -2 if key doesn't exist
        """
        try:
            return self.client.ttl(key)
        except redis.RedisError as e:
            print(f"Redis error in get_ttl: {e}")
            return -2
    
    def extend_ttl(self, key: str, additional_seconds: int) -> bool:
        """
        Extend TTL of an existing key.
        
        Args:
            key: Cache key
            additional_seconds: Seconds to add to current TTL
            
        Returns:
            True if successful, False otherwise
        """
        try:
            current_ttl = self.client.ttl(key)
            if current_ttl > 0:
                new_ttl = current_ttl + additional_seconds
                return bool(self.client.expire(key, new_ttl))
            return False
        except redis.RedisError as e:
            print(f"Redis error in extend_ttl: {e}")
            return False
    
    def flush_all(self) -> bool:
        """
        Flush all keys in current database.
        
        WARNING: Use with caution! This deletes ALL cached data.
        """
        try:
            self.client.flushdb()
            return True
        except redis.RedisError as e:
            print(f"Redis error in flush_all: {e}")
            return False
    
    # ==================== Decorator for Cache-Aside ====================
    
    def cached(
        self,
        key_prefix: str,
        ttl: int = 3600,
        key_builder: Optional[Callable] = None
    ):
        """
        Decorator for automatic cache-aside pattern.
        
        Args:
            key_prefix: Prefix for cache key
            ttl: Time-to-live in seconds
            key_builder: Custom function to build cache key from function args
            
        Example:
            >>> @redis_mgr.cached(key_prefix="user", ttl=3600)
            >>> def get_user(user_id: str):
            ...     return db.query(User).filter_by(id=user_id).first()
            >>> 
            >>> # First call: cache miss, fetches from DB
            >>> user = get_user("123")
            >>> # Second call: cache hit, returns from Redis
            >>> user = get_user("123")
        """
        def decorator(func: Callable):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Build cache key
                if key_builder:
                    cache_key = key_builder(*args, **kwargs)
                else:
                    # Default: use function name and first argument
                    arg_str = str(args[0]) if args else str(kwargs)
                    cache_key = f"{key_prefix}:{arg_str}"
                
                # Try cache first
                def fetch_func():
                    return func(*args, **kwargs)
                
                return self.get_cached(
                    key=cache_key,
                    fetch_func=fetch_func,
                    ttl=ttl
                )
            
            return wrapper
        return decorator


# ==================== Global Instance ====================

# Singleton instance for application-wide use
redis_manager = RedisManager()
