# routes/search.py
import os
import hashlib
import json
from typing import Any, Dict, List, Union, Optional, Literal
from fastapi import APIRouter, Body, Query
from elasticsearch import Elasticsearch
from services.es_svc import search_keyword, index_many, filter_advanced
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
):
    """
    Full-text search with Redis caching at API layer.
    
    Cache key is based on query parameters hash.
    """
    # Create cache key from search parameters
    cache_params = json.dumps({"q": q, "collection": collection, "size": size, "offset": offset}, sort_keys=True)
    cache_key_hash = hashlib.md5(cache_params.encode()).hexdigest()
    cache_key = f"es:search:{cache_key_hash}"
    
    def fetch_from_elasticsearch():
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
    
    # Try cache-aside pattern with 30-minute TTL
    try:
        from services.redis_manager import redis_manager
        return redis_manager.get_cached(
            key=cache_key,
            fetch_func=fetch_from_elasticsearch,
            ttl=1800  # 30 minutes
        )
    except:
        # Fallback: direct ES query if Redis unavailable
        return fetch_from_elasticsearch()


@router.post("/sync")
def sync_firestore_to_es(
    collection: str = Query(..., description="Tên Firestore collection cần sync"),
):
    """
    Sync Firestore to Elasticsearch with cache invalidation.
    
    Invalidates all search caches after sync (write-around pattern).
    """
    try:
        db = firestore.client()
        docs = db.collection(collection).stream()
        items = [{"id": doc.id, **doc.to_dict()} for doc in docs]

        if not items:
            return {"status": "ok", "message": f"No documents in collection '{collection}'"}

        es = Elasticsearch(
            hosts=[ES_HOST],
            basic_auth=(ES_USER, ES_PASS),
            verify_certs=False,
            max_retries=30,
            retry_on_timeout=True,
            request_timeout=30,
        )
        try:
            result = index_many(es, items, index=collection, collection=collection)
            
            # Invalidate search cache after sync (write-around pattern)
            try:
                from services.redis_manager import redis_manager
                redis_manager.invalidate_pattern(f"es:search:*")
                redis_manager.invalidate_pattern(f"firestore:{collection}:*")
            except:
                pass
            
            return {
                "status": "ok",
                "total_documents": len(items),
                "indexed": result["success"],
                "failed": result["failed"],
                "failed_records": result["failed_ids"],
                "collection": collection
            }
        finally:
            es.close()
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "collection": collection,
            "error_type": type(e).__name__
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
    filters: List[FilterItem] = Body(..., example=filter_example)
):
    """
    API để lọc document với các điều kiện phức tạp.
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
