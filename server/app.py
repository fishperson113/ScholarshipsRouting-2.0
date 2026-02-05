import os
from fastapi import FastAPI
from routes import health, search, auth, webhooks, firestore_routes, realtime, application_routes, chat
import firebase_admin
from firebase_admin import credentials
from fastapi.middleware.cors import CORSMiddleware

# --- Firebase init ---
cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
if not firebase_admin._apps:
    if not cred_path or not os.path.exists(cred_path):
        raise RuntimeError("Missing GOOGLE_APPLICATION_CREDENTIALS env")
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)

# CORS origins from environment
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

# --- FastAPI app ---
app = FastAPI(
    title="Scholarships Routing API 2.0",
    description="Backend API for scholarship routing with authentication and search",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== Startup Event ====================

@app.on_event("startup")
async def startup_event():
    """Initialize connections on startup."""
    print("🚀 Starting Scholarships Routing API 2.0...")
    
    # Initialize Redis connection
    try:
        from services.redis_manager import redis_manager
        redis_manager.client.ping()
        print("✅ Redis connection verified")
    except Exception as e:
        print(f"⚠️  Redis connection failed: {e}")
        print("   Application will continue without caching")

# Include routers
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(search.router, prefix="/api/v1/es", tags=["elasticsearch"])
app.include_router(webhooks.router, prefix="/api/v1/webhooks", tags=["webhooks"])
app.include_router(firestore_routes.router, prefix="/api/v1/firestore", tags=["firestore"])
app.include_router(realtime.router, prefix="/api/v1/realtime", tags=["realtime"])
app.include_router(application_routes.router, prefix="/api/v1/user/applications", tags=["applications"])
app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])

@app.get("/", tags=["root"])
def root():
    return {
        "message": "Scholarships Routing API 2.0",
        "docs": "/docs",
        "health": "/health/live",
        "flower": "http://localhost:5555 (Celery monitoring)",
        "websocket": "ws://localhost:8000/api/v1/realtime/ws/updates/{channel}"
    }


# ===================== Celery Task Endpoints (Commented Out) =====================
# Uncomment when tasks are configured
# from fastapi import BackgroundTasks, HTTPException
# from pydantic import BaseModel

# class TaskResponse(BaseModel):
#     task_id: str
#     status: str
#     message: str

# @app.post("/api/v1/tasks/example", response_model=TaskResponse, tags=["tasks"])
# async def trigger_example_task(x: int, y: int):
#     """
#     Trigger an example Celery task that adds two numbers.
#     Check task status in Flower: http://localhost:5555
#     """
#     try:
#         from celery_app import example_task
#         task = example_task.delay(x, y)
#         return TaskResponse(
#             task_id=task.id,
#             status="queued",
#             message=f"Task queued to add {x} + {y}. Check Flower for status."
#         )
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


# @app.post("/api/v1/tasks/sync-collection", response_model=TaskResponse, tags=["tasks"])
# async def trigger_sync_task(collection: str):
#     """
#     Trigger background sync of Firestore collection to Elasticsearch.
#     Check task status in Flower: http://localhost:5555
#     """
#     try:
#         from tasks import process_scholarship_sync
#         task = process_scholarship_sync.delay(collection)
#         return TaskResponse(
#             task_id=task.id,
#             status="queued",
#             message=f"Sync task queued for collection '{collection}'. Check Flower for status."
#         )
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")
