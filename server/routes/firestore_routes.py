"""
Firestore API routes for uploading and querying collections.

Provides endpoints to:
- Upload documents to Firestore collections (async via Celery)
- Query documents from Firestore collections
- Batch operations
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query, Body
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from services.firestore_svc import save_one_raw, save_with_id, get_one_raw
from datetime import datetime


router = APIRouter()


# ==================== Request/Response Models ====================

class DocumentData(BaseModel):
    """Model for document data without collection."""
    data: Dict[str, Any] = Field(..., description="Document data")
    doc_id: Optional[str] = Field(None, description="Optional document ID (auto-generated if not provided)")


class BulkDocumentData(BaseModel):
    """Model for bulk document upload without collection."""
    documents: List[Dict[str, Any]] = Field(..., description="List of documents to upload")


class UploadResponse(BaseModel):
    """Response for document upload."""
    status: str
    message: str
    task_id: Optional[str] = None
    doc_id: Optional[str] = None
    doc_ids: Optional[List[str]] = None


class QueryResponse(BaseModel):
    """Response for document query."""
    collection: str
    doc_id: str
    data: Optional[Dict[str, Any]]
    found: bool


# ==================== Upload Endpoints (Async with Celery) ====================

@router.post("/upload/{collection}", response_model=UploadResponse)
async def upload_document(collection: str, request: DocumentData):
    """
    Upload a single document to Firestore (async via Celery).
    
    The upload is queued as a background task and processed by Celery worker.
    Cache is invalidated after upload (write-around pattern).
    
    Args:
        collection: Collection name (URL path parameter)
        request: Document data
        
    Returns:
        Upload response with task ID for tracking
        
    Example:
        POST /api/v1/firestore/upload/scholarships
        {
            "data": {"name": "Test Scholarship", "amount": 5000},
            "doc_id": "optional-custom-id"
        }
    """
    try:
        from services.tasks import upload_document_task
        
        # Queue upload task
        task = upload_document_task.delay(
            collection=collection,
            data=request.data,
            doc_id=request.doc_id
        )
        
        # Invalidate cache (write-around pattern)
        try:
            from services.redis_manager import redis_manager
            if request.doc_id:
                redis_manager.invalidate(f"firestore:{collection}:{request.doc_id}")
            else:
                redis_manager.invalidate_pattern(f"firestore:{collection}:*")
        except:
            pass
        
        return UploadResponse(
            status="queued",
            message=f"Document upload queued for collection '{collection}'",
            task_id=task.id
        )
        
    except ImportError:
        # Fallback: synchronous upload if Celery not configured
        if request.doc_id:
            doc_id = save_with_id(collection, request.doc_id, request.data)
        else:
            doc_id = save_one_raw(collection, request.data)
        
        # Invalidate cache
        try:
            from services.redis_manager import redis_manager
            redis_manager.invalidate(f"firestore:{collection}:{doc_id}")
        except:
            pass
        
        return UploadResponse(
            status="completed",
            message=f"Document uploaded to collection '{collection}'",
            doc_id=doc_id
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.post("/upload/{collection}/bulk", response_model=UploadResponse)
async def upload_documents_bulk(collection: str, request: BulkDocumentData):
    """
    Upload multiple documents to Firestore (async via Celery).
    
    Bulk uploads are processed in batches by Celery worker for better performance.
    Cache is invalidated after upload (write-around pattern).
    
    Args:
        collection: Collection name (URL path parameter)
        request: Bulk document data
        
    Returns:
        Upload response with task ID for tracking
        
    Example:
        POST /api/v1/firestore/upload/scholarships/bulk
        {
            "documents": [
                {"name": "Scholarship 1", "amount": 5000},
                {"name": "Scholarship 2", "amount": 10000}
            ]
        }
    """
    try:
        from services.tasks import upload_documents_bulk_task
        
        # Queue bulk upload task
        task = upload_documents_bulk_task.delay(
            collection=collection,
            documents=request.documents
        )
        
        # Invalidate cache (write-around pattern)
        try:
            from services.redis_manager import redis_manager
            redis_manager.invalidate_pattern(f"firestore:{collection}:*")
        except:
            pass
        
        return UploadResponse(
            status="queued",
            message=f"Bulk upload of {len(request.documents)} documents queued for collection '{collection}'",
            task_id=task.id
        )
        
    except ImportError:
        # Fallback: synchronous bulk upload if Celery not configured
        from services.firestore_svc import save_many_raw
        doc_ids = save_many_raw(collection, request.documents)
        
        # Invalidate cache
        try:
            from services.redis_manager import redis_manager
            redis_manager.invalidate_pattern(f"firestore:{collection}:*")
        except:
            pass
        
        return UploadResponse(
            status="completed",
            message=f"Uploaded {len(doc_ids)} documents to collection '{collection}'",
            doc_ids=doc_ids
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bulk upload failed: {str(e)}")


# ==================== Query Endpoints ====================

@router.get("/query/{collection}/{doc_id}", response_model=QueryResponse)
async def query_document(
    collection: str,
    doc_id: str
):
    """
    Query a single document from Firestore by ID with Redis caching.
    
    Implements cache-aside pattern at API layer.
    
    Args:
        collection: Collection name
        doc_id: Document ID
        
    Returns:
        Document data if found
        
    Example:
        GET /api/v1/firestore/query/scholarships/abc123
    """
    cache_key = f"firestore:{collection}:{doc_id}"
    
    try:
        from services.redis_manager import redis_manager
        
        # Cache-aside pattern: check cache first
        def fetch_from_firestore():
            return get_one_raw(collection, doc_id)
        
        data = redis_manager.get_cached(
            key=cache_key,
            fetch_func=fetch_from_firestore,
            ttl=3600  # 1 hour
        )
        
        return QueryResponse(
            collection=collection,
            doc_id=doc_id,
            data=data,
            found=data is not None
        )
        
    except:
        # Fallback: direct query if Redis unavailable
        data = get_one_raw(collection, doc_id)
        
        return QueryResponse(
            collection=collection,
            doc_id=doc_id,
            data=data,
            found=data is not None
        )


@router.get("/query/{collection}")
async def query_collection(
    collection: str,
    limit: int = Query(10, ge=1, le=100, description="Maximum documents to return"),
    offset: int = Query(0, ge=0, description="Number of documents to skip")
):
    """
    Query multiple documents from a Firestore collection with Redis caching.
    
    Implements cache-aside pattern at API layer.
    Cache key includes collection, limit, and offset for proper pagination caching.
    
    Args:
        collection: Collection name
        limit: Maximum number of documents to return (1-100)
        offset: Number of documents to skip (for pagination)
        
    Returns:
        List of documents
        
    Example:
        GET /api/v1/firestore/query/scholarships?limit=20&offset=0
    """
    # Create cache key including pagination params
    cache_key = f"firestore:collection:{collection}:limit:{limit}:offset:{offset}"
    
    def fetch_from_firestore():
        from firebase_admin import firestore
        
        db = firestore.client()
        query = db.collection(collection).limit(limit).offset(offset)
        docs = query.stream()
        
        results = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id  # Include document ID
            results.append(data)
        
        return {
            "collection": collection,
            "count": len(results),
            "limit": limit,
            "offset": offset,
            "documents": results
        }
    
    try:
        from services.redis_manager import redis_manager
        
        # Cache-aside pattern: check cache first
        return redis_manager.get_cached(
            key=cache_key,
            fetch_func=fetch_from_firestore,
            ttl=1800  # 30 minutes (collection queries change less frequently)
        )
        
    except:
        # Fallback: direct query if Redis unavailable
        return fetch_from_firestore()


# ==================== Task Status Endpoint ====================

@router.get("/upload/status/{task_id}")
async def get_upload_status(task_id: str):
    """
    Check the status of an async upload task.
    
    Args:
        task_id: Task ID returned from upload endpoint
        
    Returns:
        Task status and result
        
    Example:
        GET /api/v1/firestore/upload/status/abc-123-def
    """
    try:
        from celery.result import AsyncResult
        from celery_app import celery_app
        
        task = AsyncResult(task_id, app=celery_app)
        
        response = {
            "task_id": task_id,
            "status": task.state,
            "ready": task.ready(),
        }
        
        if task.ready():
            if task.successful():
                response["result"] = task.result
            else:
                response["error"] = str(task.info)
        
        return response
        
    except ImportError:
        raise HTTPException(status_code=503, detail="Celery not configured")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Status check failed: {str(e)}")


# ==================== Health Check ====================

@router.get("/health")
async def firestore_health():
    """Health check for Firestore service."""
    try:
        from firebase_admin import firestore
        
        db = firestore.client()
        # Try to access a collection to verify connection
        db.collection("_health_check").limit(1).get()
        
        return {
            "status": "ok",
            "service": "firestore",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "status": "error",
            "service": "firestore",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
