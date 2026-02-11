"""
Background tasks for the Scholarships Routing application.
Place your Celery tasks here.
"""
from celery_app import celery_app
from typing import Dict, Any, List
import requests
import os
import json
import logging
import asyncio
from services.event_manager import event_bus

logger = logging.getLogger(__name__)

DAYS_BEFORE_DEADLINE = 3


# ==================== Sync Tasks ====================

@celery_app.task(name="tasks.process_scholarship_sync")
def process_scholarship_sync(collection: str) -> Dict[str, Any]:
    """
    Background task to sync Firestore collection to Elasticsearch.

    Args:
        collection: Name of the Firestore collection to sync

    Returns:
        Dict with sync results
    """
    from elasticsearch import Elasticsearch
    from services.es_svc import index_many
    import os

    try:
        # Get Firestore data
        db = firestore.client()
        docs = db.collection(collection).stream()
        items = [{"id": doc.id, **doc.to_dict()} for doc in docs]

        if not items:
            return {"status": "ok", "message": f"No documents in collection '{collection}'"}

        # Index to Elasticsearch
        ES_HOST = os.getenv("ELASTICSEARCH_HOST")
        ES_USER = os.getenv("ELASTIC_USER")
        ES_PASS = os.getenv("ELASTIC_PASSWORD")

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

            # Invalidate cache after successful sync
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


@celery_app.task(name="tasks.sync_firestore_to_elasticsearch")
def sync_firestore_to_elasticsearch(collection: str, index: str = None) -> Dict[str, Any]:
    """
    Async task to sync Firestore collection to Elasticsearch.

    This is the new dedicated task for ES sync operations.

    Args:
        collection: Firestore collection name
        index: Elasticsearch index name (defaults to collection name)

    Returns:
        Dict with sync results
    """
    from elasticsearch import Elasticsearch
    from services.es_svc import index_many
    import os

    index_name = index or collection

    try:
        # Get Firestore data
        db = firestore.client()
        docs = db.collection(collection).stream()
        items = [{"id": doc.id, **doc.to_dict()} for doc in docs]

        if not items:
            return {
                "status": "ok",
                "message": f"No documents in collection '{collection}'",
                "total_documents": 0
            }

        # Index to Elasticsearch
        ES_HOST = os.getenv("ELASTICSEARCH_HOST")
        ES_USER = os.getenv("ELASTIC_USER")
        ES_PASS = os.getenv("ELASTIC_PASSWORD")

        es = Elasticsearch(
            hosts=[ES_HOST],
            basic_auth=(ES_USER, ES_PASS),
            verify_certs=False,
            max_retries=30,
            retry_on_timeout=True,
            request_timeout=30,
        )

        try:
            result = index_many(es, items, index=index_name, collection=collection)

            # Invalidate cache after successful sync
            try:
                from services.redis_manager import redis_manager
                redis_manager.invalidate_pattern(f"es:search:*")
                redis_manager.invalidate_pattern(f"firestore:{collection}:*")
            except:
                pass

            return {
                "status": "success",
                "collection": collection,
                "index": index_name,
                "total_documents": len(items),
                "indexed": result["success"],
                "failed": result["failed"],
                "failed_records": result.get("failed_ids", [])
            }
        finally:
            es.close()

    except Exception as e:
        return {
            "status": "error",
            "collection": collection,
            "index": index_name,
            "error": str(e),
            "error_type": type(e).__name__
        }


@celery_app.task(name="tasks.sync_all_collections")
def sync_all_collections() -> Dict[str, Any]:
    """
    Sync all Firestore collections to Elasticsearch.

    Discovers all top-level collections in Firestore and syncs each one
    by dispatching individual sync_firestore_to_elasticsearch tasks.

    Returns:
        Dict with task IDs for each collection
    """
    try:
        db = firestore.client()
        collections = [col.id for col in db.collections()]

        if not collections:
            return {"status": "ok", "message": "No collections found in Firestore", "tasks": {}}

        task_map = {}
        for col_name in collections:
            task = sync_firestore_to_elasticsearch.apply_async(
                kwargs={"collection": col_name, "index": col_name}
            )
            task_map[col_name] = task.id

        return {
            "status": "queued",
            "total_collections": len(collections),
            "tasks": task_map,
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__,
        }


# ==================== Notification Tasks ====================

@shared_task(name="tasks.check_application_deadlines")
def check_application_deadlines():
    """
    Periodic task: Scans for expiring applications and emits events.
    It does NOT create notifications directly (SOC: Separation of Concerns).
    """
    logger.info("⏰ Starting deadline check task (Event-Driven)...")

    try:
        db = firestore.client()
        # Note: In production, use Collection Group Index for better performance:
        # db.collection_group('applications').where(...)

        users = db.collection('users').stream()
        processed_count = 0

        for user in users:
            uid = user.id
            apps_ref = db.collection('users').document(uid).collection('applications')
            # Check ALL applications regardless of status (submitted, saved, etc.)
            apps = apps_ref.stream()

            for app in apps:
                process_single_application(uid, app)
                processed_count += 1

        logger.info(f"✅ Deadline check completed. Scanned {processed_count} apps.")
        return {"status": "success", "scanned": processed_count}

    except Exception as e:
        logger.error(f"❌ Error in deadline check task: {str(e)}")
        return {"status": "error", "error": str(e)}


def process_single_application(uid, app):
    """Check dates and emit event if needed."""
    data = app.to_dict()

    # Priority: Use 'apply_date' (User target) -> Fallback to 'deadline' (Official)
    target_date_str = data.get('apply_date') or data.get('deadline')
    if not target_date_str:
        return

    try:
        # Import internally to allow cross-service usage
        from services.event_manager import event_bus
        import asyncio

        # Parse date (handle ISO format)
        if 'T' in target_date_str:
            target_date = datetime.fromisoformat(target_date_str.replace('Z', '')).date()
        else:
            target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()

        today = datetime.utcnow().date()
        delta = (target_date - today).days

        print(f"🔍 [Deadline Check] App: {app.id} | Deadline: {target_date} | Today: {today} | Delta: {delta} days")

        # Trigger if days left is less than or equal to DAYS_BEFORE_DEADLINE
        # This handles both upcoming deadlines (0 to 3 days) and missed deadlines (negative days)
        if delta <= DAYS_BEFORE_DEADLINE:
            print(f"🚀 [Triggering Event] DEADLINE_APPROACHING for App: {app.id}")
            payload = {
                'user_id': uid,
                'application_id': app.id,
                'scholarship_name': data.get('scholarship_name', 'Unknown'),
                'days_left': delta,
                'deadline_date': target_date.isoformat()
            }

            # Fire and forget event
            try:
                loop = asyncio.get_running_loop()
                # If running in an event loop (e.g., FastAPI), schedule execution
                loop.create_task(event_bus.emit("DEADLINE_APPROACHING", payload))
            except RuntimeError:
                # If no running loop (e.g., Celery Worker), run synchronously
                asyncio.run(event_bus.emit("DEADLINE_APPROACHING", payload))

    except ValueError as e:
        print(f"❌ [Notification Error] Hiện tại đang lỗi ở process_single_application (ValueError). App ID: {app.id}. Vì ngày tháng không đúng định dạng: '{target_date_str}'. Chi tiết: {e}")
    except Exception as e:
        print(f"❌ [Notification Error] Hiện tại đang lỗi ở process_single_application (Exception). App ID: {app.id}. Vì lỗi không xác định: {e}")
        logger.error(f"Error processing app {app.id}: {e}")


# ==================== Utility Tasks ====================

@celery_app.task(name="tasks.cleanup_old_guest_sessions")
def cleanup_old_guest_sessions() -> Dict[str, Any]:
    """
    Periodic task to clean up expired guest sessions.
    This is a placeholder - implement based on your needs.
    """
    # TODO: Implement cleanup logic
    return {"status": "ok", "cleaned": 0}


@celery_app.task(name="tasks.send_notification")
def send_notification(user_id: str, message: str, notification_type: str = "info") -> Dict[str, Any]:
    """
    Send notification to user (email, push, etc.)

    Args:
        user_id: User ID to send notification to
        message: Notification message
        notification_type: Type of notification (info, warning, error)

    Returns:
        Dict with send status
    """
    # TODO: Implement notification logic
    print(f"Sending {notification_type} notification to {user_id}: {message}")

    return {
        "status": "sent",
        "user_id": user_id,
        "type": notification_type
    }


# ==================== Firestore Upload Tasks ====================

@celery_app.task(name="tasks.upload_document_task")
def upload_document_task(collection: str, data: Dict[str, Any], doc_id: str = None) -> Dict[str, Any]:
    """
    Async task to upload a single document to Firestore.

    Args:
        collection: Collection name
        data: Document data
        doc_id: Optional document ID

    Returns:
        Upload result with document ID
    """
    from services.firestore_svc import save_one_raw, save_with_id

    try:
        if doc_id:
            result_id = save_with_id(collection, doc_id, data)
        else:
            result_id = save_one_raw(collection, data)

        return {
            "status": "success",
            "collection": collection,
            "doc_id": result_id,
            "message": f"Document uploaded successfully to '{collection}'"
        }

    except Exception as e:
        return {
            "status": "error",
            "collection": collection,
            "error": str(e),
            "error_type": type(e).__name__
        }


@celery_app.task(name="tasks.upload_documents_bulk_task")
def upload_documents_bulk_task(collection: str, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Async task to upload multiple documents to Firestore in batches.

    Args:
        collection: Collection name
        documents: List of documents to upload

    Returns:
        Upload result with document IDs
    """
    from services.firestore_svc import save_many_raw

    try:
        doc_ids = save_many_raw(collection, documents)

        return {
            "status": "success",
            "collection": collection,
            "doc_ids": doc_ids,
            "count": len(doc_ids),
            "message": f"Uploaded {len(doc_ids)} documents to '{collection}'"
        }

    except Exception as e:
        return {
            "status": "error",
            "collection": collection,
            "error": str(e),
            "error_type": type(e).__name__
        }


@celery_app.task(name="tasks.send_to_n8n")
def send_to_n8n(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send message payload to n8n webhook.
    
    Args:
        payload: Dict containing query, plan, user_id
        
    Returns:
        Dict response from n8n
    """
    webhook_url = os.getenv("N8N_WEBHOOK_URL")
    if not webhook_url:
        return {
            "status": "error",
            "message": "N8N_WEBHOOK_URL not configured"
        }
        
    try:
        # Use a timeout of 30 seconds for the request itself
        response = requests.post(webhook_url, json=payload, timeout=30)
        response.raise_for_status()
        
        try:
            return response.json()
        except ValueError:
            # If n8n returns text (or HTML error), wrap it
            return {
                "output": response.text,
                "status": "success_text"
            }
        
    except requests.exceptions.Timeout:
        return {
            "status": "error", 
            "message": "Request to n8n timed out"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


@celery_app.task(name="tasks.receive_to_n8n")
def receive_to_n8n(n8n_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process raw response from n8n and format for ChatResponse.
    
    Args:
        n8n_response: Raw response from send_to_n8n task
        
    Returns:
        Dict matching ChatResponse DTO structure
    """
    # Helper to extract text reply
    def json_extract_reply(data: dict) -> str:
        if isinstance(data, dict) and data:
            # Try to find 'output', 'text', 'reply' or just first value
            if "output" in data:
                return str(data["output"])
            if "text" in data:
                return str(data["text"])
            if "reply" in data:
                return str(data["reply"])
            return str(next(iter(data.values())))
        return str(data)

    status = n8n_response.get("status", "success")
    
    # If there was an error in the previous task, propagate it
    if status == "error":
        return {
            "reply": n8n_response.get("message", "Unknown error"),
            "status": "error",
            "celery": True
        }
        
    return {
        "reply": json_extract_reply(n8n_response),
        "status": status,
        "celery": True
    }
