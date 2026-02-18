# routes/search.py
import os
import hashlib
import json
from typing import Any, Dict, List, Union, Optional, Literal
from fastapi import APIRouter, Body, Query, Depends
from elasticsearch import Elasticsearch
from services.es_svc import search_keyword, index_many, filter_advanced, delete_index
from services.auth_svc import get_current_user_or_guest
from firebase_admin import firestore
from dtos.search_dtos import FilterItem

router = APIRouter()
ES_HOST = os.getenv("ELASTICSEARCH_HOST")
ES_USER = os.getenv("ELASTIC_USER")
ES_PASS = os.getenv("ELASTIC_PASSWORD")

@router.get("/search")
def search(
    q: str = Query(..., description="Từ khóa full-text"),
    size: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    collection: str = Query(..., description="Tên collection cần search"),
    current_user: dict = Depends(get_current_user_or_guest)
):
    """
    Full-text search with Redis-based debounce to minimize API calls.
    
    Requires authentication (Firebase user or guest token).
    Uses Redis as a buffer to prevent excessive calls during typing.
    If the same search is requested within the debounce window (300ms), 
    it returns a "debounced" status instead of executing the search.
    
    This prevents 3-4 API calls when users are typing/correcting typos.
    Debounce is per-user to prevent cross-user interference.
    
    Args:
        q: Search query
        size: Results per page
        offset: Pagination offset
        collection: Collection to search
        current_user: Authenticated user (injected)
        
    Returns:
        Search results or debounced status
        
    Example:
        GET /api/v1/es/search?q=engineering&collection=scholarships
        Headers: Authorization: Bearer <token>
    """
    import time
    
    # Backend-controlled debounce window (300ms)
    DEBOUNCE_MS = 300
    
    # Get user ID for per-user debouncing
    user_id = current_user.get("uid") or current_user.get("guest_id", "anonymous")
    
    # Create debounce key with user_id for per-user rate limiting
    debounce_key = f"search:debounce:{user_id}:{collection}:{q}:{size}:{offset}"
    
    try:
        from services.redis_manager import redis_manager
        
        # Check if this exact search was recently requested by this user
        last_search_time = redis_manager.client.get(debounce_key)
        current_time = int(time.time() * 1000)  # milliseconds
        
        if last_search_time:
            last_time = int(last_search_time)
            time_diff = current_time - last_time
            
            # If within debounce window, return debounced status
            if time_diff < DEBOUNCE_MS:
                return {
                    "status": "debounced",
                    "message": "Search request debounced to prevent excessive calls",
                    "wait_ms": DEBOUNCE_MS - time_diff,
                    "query": q
                }
        
        # Update debounce timestamp
        # TTL is 2x debounce window to allow for cleanup
        redis_manager.client.setex(
            debounce_key,
            int((DEBOUNCE_MS * 2) / 1000) + 1,  # Convert to seconds
            str(current_time)
        )
        
    except Exception as e:
        # If Redis fails, continue with search (fail-open)
        print(f"Debounce check failed: {e}")
    
    # Execute the search
    es = Elasticsearch(
        hosts=[ES_HOST],
        basic_auth=(ES_USER, ES_PASS),
        verify_certs=False,
        max_retries=30,
        retry_on_timeout=True,
        request_timeout=30,
    )
    try:
        return search_keyword(
            es, q,
            index=collection, 
            size=size,
            offset=offset,
            collection=collection
        )
    finally:
        es.close()


@router.post("/sync")
def sync_firestore_to_es(
    collection: str = Query(..., description="Tên Firestore collection cần sync"),
    index: Optional[str] = Query(None, description="ES index name (defaults to collection name)")
):
    """
    Sync Firestore to Elasticsearch asynchronously via Celery.
    
    This endpoint always queues the sync operation as a background task
    for optimal performance with large datasets.
    
    Invalidates all search caches after sync (write-around pattern).
    
    Args:
        collection: Firestore collection name
        index: Elasticsearch index name (optional, defaults to collection)
        
    Returns:
        Task ID for tracking sync progress
        
    Example:
        POST /api/v1/es/sync?collection=scholarships
        
    Response:
        {
            "status": "queued",
            "task_id": "abc-123-def",
            "check_status": "/api/v1/firestore/upload/status/abc-123-def"
        }
    """
    from services.tasks import sync_firestore_to_elasticsearch
    
    index_name = index or collection
    
    # Always queue to Celery for async processing
    task = sync_firestore_to_elasticsearch.apply_async(
        kwargs={
            "collection": collection,
            "index": index_name
        }
    )
    
    return {
        "status": "queued",
        "message": f"Sync task queued for collection '{collection}' to index '{index_name}'",
        "task_id": task.id,
        "collection": collection,
        "index": index_name,
        "check_status": f"/api/v1/firestore/upload/status/{task.id}"
    }

@router.post("/sync-all")
def sync_all_collections():
    """
    Sync all Firestore collections to Elasticsearch in one click.

    Discovers every top-level Firestore collection and queues a sync
    task for each one via Celery.

    Returns:
        Task ID of the parent task and per-collection sub-task IDs

    Example:
        POST /api/v1/es/sync-all
    """
    from services.tasks import sync_all_collections as sync_all_task

    task = sync_all_task.apply_async()

    return {
        "status": "queued",
        "message": "Sync-all task queued — each collection will be synced in parallel",
        "task_id": task.id,
        "check_status": f"/api/v1/firestore/upload/status/{task.id}",
    }


filter_example = [
    {
      "field": "Country",
      "values": ["Hà Lan", "Đức"],
      "operator": "OR"
    },
    {
      "field": "Funding_Level",
      "values": ["Toàn phần"],
      "operator": "OR"
    }
]

@router.post("/filter")
def filter_documents(
    # --- Các tham số Query Parameter ---
    collection: str = Query(..., description="Tên collection cần filter"),
    size: int = Query(10, ge=1, le=100, description="Số lượng kết quả trả về"),
    offset: int = Query(0, ge=0, description="Vị trí bắt đầu lấy kết quả"),
    inter_field_operator: Literal["AND", "OR"] = Query("AND", description="Toán tử kết hợp các bộ lọc với nhau"),
    
    # --- Request body giờ là một danh sách FilterItem ---
    filters: List[FilterItem] = Body(..., example=filter_example),
    
    # --- Authentication ---
    current_user: dict = Depends(get_current_user_or_guest)
):
    """
    API để lọc document với các điều kiện phức tạp.
    
    Requires authentication (Firebase user or guest token).
    
    Args:
        collection: Collection name to filter
        size: Number of results to return
        offset: Pagination offset
        inter_field_operator: Operator to combine filters (AND/OR)
        filters: List of filter conditions
        current_user: Authenticated user (injected)
        
    Example:
        POST /api/v1/es/filter?collection=scholarships
        Headers: Authorization: Bearer <token>
    """
    es = Elasticsearch(
        hosts=[ES_HOST],
        basic_auth=(ES_USER, ES_PASS),
        verify_certs=False,
        max_retries=30,
        retry_on_timeout=True,
        request_timeout=30,
    )
    try:
        # Chuyển đổi list các Pydantic model thành list các dict
        filters_dict = [item.model_dump() for item in filters]

        return filter_advanced(
            client=es,
            index=collection,
            collection=collection,
            filters=filters_dict,
            inter_field_operator=inter_field_operator,
            size=size,
            offset=offset
        )
    finally:
        es.close()


@router.delete("/index/{index_name}")
def delete_index_endpoint(
    index_name: str,
):
    """
    Delete an Elasticsearch index and invalidate all related caches.
    
    This is useful for:
    - Removing old/unused indices
    - Clearing corrupted data
    - Resetting search indices
    
    Args:
        index_name: Name of the index to delete
        
    Returns:
        Deletion status
        
    Example:
        DELETE /api/v1/es/index/scholarships
    """
    from services.es_svc import delete_index
    
    es = Elasticsearch(
        hosts=[ES_HOST],
        basic_auth=(ES_USER, ES_PASS),
        verify_certs=False,
        max_retries=30,
        retry_on_timeout=True,
        request_timeout=30,
    )
    
    try:
        result = delete_index(es, index_name)
        
        # Invalidate all search caches after index deletion
        if result["status"] == "deleted":
            try:
                from services.redis_manager import redis_manager
                redis_manager.invalidate_pattern(f"es:search:*")
                redis_manager.invalidate_pattern(f"firestore:{index_name}:*")
            except:
                pass
        
        return result
    finally:
        es.close()
