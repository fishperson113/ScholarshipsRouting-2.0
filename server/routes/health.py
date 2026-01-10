from fastapi import APIRouter
from elasticsearch import Elasticsearch
import os

router = APIRouter()

ES_HOST = os.getenv("ELASTICSEARCH_HOST")
ES_USER = os.getenv("ELASTIC_USER")
ES_PASS = os.getenv("ELASTIC_PASSWORD")

@router.get("/live")
def live():
    return {"status": "ok"}

@router.get("/ready")
def ready():
    es = Elasticsearch(
        hosts=[ES_HOST],
        basic_auth=(ES_USER, ES_PASS),  # nếu có auth
        verify_certs=False,
        max_retries=30,
        retry_on_timeout=True,
        request_timeout=30,
    )
    try:
        if es.ping():
            info = es.info()
            return {
                "status": "ok",
                "elasticsearch": {
                    "name": info.get("name"),
                    "cluster_name": info.get("cluster_name"),
                    "version": info.get("version", {}).get("number"),
                }
            }
        else:
            return {"status": "degraded", "elasticsearch": "ping failed"}
    except Exception as e:
        return {"status": "error", "elasticsearch": str(e)}
    finally:
        es.close()
