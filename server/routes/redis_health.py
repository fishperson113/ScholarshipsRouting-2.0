"""
Redis health check endpoint.
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/redis")
async def redis_health():
    """Check Redis connection status."""
    try:
        from services.redis_manager import redis_manager
        
        # Test connection
        redis_manager.client.ping()
        
        # Get info
        info = redis_manager.client.info("server")
        
        return {
            "status": "connected",
            "redis_version": info.get("redis_version"),
            "uptime_seconds": info.get("uptime_in_seconds"),
            "connected_clients": info.get("connected_clients")
        }
    except Exception as e:
        return {
            "status": "disconnected",
            "error": str(e)
        }
