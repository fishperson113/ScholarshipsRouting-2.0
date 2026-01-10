import re
from typing import Optional, Dict, Any, List, Iterable
from firebase_admin import firestore

_COLLECTION_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")

def _ensure_valid_collection(collection: str) -> str:
    if not _COLLECTION_RE.match(collection):
        raise ValueError("Invalid collection name")
    return collection

def _db():
    return firestore.client()

def save_one_raw(collection: str, data: Dict[str, Any]) -> str:
    col = _ensure_valid_collection(collection)
    db = _db()
    ref = db.collection(col).document()  # auto-id
    ref.set(data)
    return ref.id

def save_with_id(collection: str, doc_id: str, data: Dict[str, Any]) -> str:
    col = _ensure_valid_collection(collection)
    db = _db()
    db.collection(col).document(doc_id).set(data)
    return doc_id

def save_many_raw(collection: str, rows: Iterable[Dict[str, Any]]) -> List[str]:
    col = _ensure_valid_collection(collection)
    db = _db()
    col_ref = db.collection(col)

    ids: List[str] = []
    batch = db.batch()
    ops = 0
    CHUNK = 400

    for row in rows:
        ref = col_ref.document()  # auto-id
        batch.set(ref, row)
        ids.append(ref.id)
        ops += 1

        if ops >= CHUNK:
            batch.commit()
            batch = db.batch()
            ops = 0

    if ops:
        batch.commit()

    return ids

def get_one_raw(collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
    col = _ensure_valid_collection(collection)
    db = _db()
    snap = db.collection(col).document(doc_id).get()
    return snap.to_dict() if snap.exists else None
