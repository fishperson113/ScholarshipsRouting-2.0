from typing import Any, Dict, Iterable, List, Optional, Literal
from elasticsearch import Elasticsearch, helpers

def ensure_index(client: Elasticsearch, index: str) -> str:
    if not client.indices.exists(index=index):
        client.indices.create(
            index=index,
            settings={
                "analysis": {
                    "analyzer": {
                        "en_std": {"type": "standard", "stopwords": "_english_"}
                    }
                }
            },
            mappings={
                "properties": {
                    "collection": {"type": "keyword"},
                    "__text": {"type": "text", "analyzer": "en_std"},
                    "Scholarship_Name": {
                        "type": "text",
                        "analyzer": "en_std",
                        "fields": {"raw": {"type": "keyword"}},
                    },
                    "Country": {
                        "type": "text",
                        "analyzer": "en_std",
                        "fields": {"raw": {"type": "keyword"}},
                    },
                    "country": {
                        "type": "text",
                        "analyzer": "en_std",
                        "fields": {"raw": {"type": "keyword"}},
                    },
                    "Funding_Level": {
                        "type": "text",
                        "analyzer": "en_std",
                        "fields": {"raw": {"type": "keyword"}},
                    },
                    "Scholarship_Type": {
                        "type": "text",
                        "analyzer": "en_std",
                        "fields": {"raw": {"type": "keyword"}},
                    },
                    "degreeLevel": {
                        "type": "text",
                        "analyzer": "en_std",
                        "fields": {"raw": {"type": "keyword"}},
                    },
                    "Required_Degree": {
                        "type": "text",
                        "analyzer": "en_std",
                        "fields": {"raw": {"type": "keyword"}},
                    },
                    "fieldOfStudy": {
                        "type": "text",
                        "analyzer": "en_std",
                        "fields": {"raw": {"type": "keyword"}},
                    },
                    "Eligible_Fields": {
                        "type": "text",
                        "analyzer": "en_std",
                        "fields": {"raw": {"type": "keyword"}},
                    },
                    "Eligible_Field_Group": {
                        "type": "text",
                        "analyzer": "en_std",
                        "fields": {"raw": {"type": "keyword"}},
                    },
                    "Wanted_Degree": {
                        "type": "text",
                        "analyzer": "en_std",
                        "fields": {"raw": {"type": "keyword"}},
                    },
                    "Language_Certificate": {
                        "type": "text",
                        "analyzer": "en_std",
                    },
                    "Min_Gpa": {
                        "type": "text",
                        "analyzer": "en_std",
                    },
                    "Experience_Years": {
                        "type": "text",
                        "analyzer": "en_std",
                    },
                    "Funding_Details": {
                        "type": "text",
                        "analyzer": "en_std",
                    },
                    "Eligibility_Criteria": {
                        "type": "text",
                        "analyzer": "en_std",
                    },
                    "Other_Requirements": {
                        "type": "text",
                        "analyzer": "en_std",
                    },
                    "End_Date": {
                        "type": "text",
                        "analyzer": "en_std",
                    },
                    "Start_Date": {
                        "type": "text",
                        "analyzer": "en_std",
                    },
                }
            },
        )
    return index


def _catch_all(doc: Dict[str, Any]) -> str:
    vals: List[str] = []

    def walk(x):
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        else:
            if isinstance(x, (str, int, float, bool)):
                vals.append(str(x))

    walk(doc)
    return " ".join(vals)


def index_one(
    client: Elasticsearch,
    doc: Dict[str, Any],
    *,
    index: str,
    id: Optional[str] = None,
    collection: Optional[str] = None,
) -> str:
    ensure_index(client, index)

    payload = dict(doc)
    payload["__text"] = _catch_all(payload)
    if collection:
        payload["collection"] = collection

    # Ưu tiên dùng Firestore doc.id để tránh trùng
    es_id = id or doc.get("id") or doc.get("doc_id")

    res = client.index(index=index, id=es_id, document=payload)
    return res["_id"]


def index_many(
    client: Elasticsearch,
    docs: Iterable[Dict[str, Any]],
    *,
    index: str,
    collection: Optional[str] = None,
) -> Dict[str, Any]:
    ensure_index(client, index)
    
    failed_docs = []
    doc_ids_seen = set()
    duplicate_count = 0

    def gen():
        nonlocal duplicate_count
        for d in docs:
            try:
                # Lấy id từ Firestore doc.id nếu có
                es_id = d.get("id") or d.get("doc_id")
                
                # Check for duplicate IDs
                if es_id in doc_ids_seen:
                    duplicate_count += 1
                    print(f"⚠️  Duplicate ID detected: {es_id}")
                    continue
                doc_ids_seen.add(es_id)
                
                src = {**d, "__text": _catch_all(d)}
                if collection:
                    src["collection"] = collection

                yield {"_op_type": "index", "_index": index, "_id": es_id, "_source": src}
            except Exception as e:
                doc_id = d.get("id") or d.get("doc_id") or "unknown"
                failed_docs.append({"id": doc_id, "error": str(e)})
                print(f"❌ Error preparing doc {doc_id}: {e}")
                continue

    success, errors = helpers.bulk(client, gen(), stats_only=False, raise_on_error=False)
    
    # Add bulk operation errors to failed_docs
    if errors:
        for error in errors:
            error_info = error.get("index", {})
            doc_id = error_info.get("_id", "unknown")
            error_msg = error_info.get("error", {})
            if isinstance(error_msg, dict):
                error_msg = error_msg.get("reason", str(error_msg))
            failed_docs.append({"id": doc_id, "error": str(error_msg)})
            print(f"❌ Bulk error for doc {doc_id}: {error_msg}")
    
    # Log summary
    total_attempted = len(doc_ids_seen) + duplicate_count + len(failed_docs)
    print(f"📊 Index Summary: Total={total_attempted}, Success={success}, Failed={len(failed_docs)}, Duplicates={duplicate_count}")
    
    return {
        "success": success,
        "failed": len(failed_docs),
        "duplicates": duplicate_count,
        "failed_ids": [{"id": f["id"], "error": f["error"]} for f in failed_docs]
    }


def search_keyword(
    client: Elasticsearch,
    q: str,
    *,
    index: str,
    size: int = 10,
    offset: int = 0,
    collection: Optional[str] = None,
) -> Dict[str, Any]:
    ensure_index(client, index)

    must = [
        {
            "match": {
                "__text": {
                "query": q,
                "operator": "or",
                "fuzziness": "AUTO"
                }
            }
        }
    ]
    if collection:
        must.append({"term": {"collection": collection}})

    res = client.search(
        index=index,
        query={"bool": {"must": must}},
        size=size,
        from_=offset,
    )
    hits = [
        {"id": h["_id"], "score": h["_score"], "source": h["_source"]}
        for h in res["hits"]["hits"]
    ]
    return {"total": res["hits"]["total"]["value"], "items": hits}

def filter_advanced(
    client: Elasticsearch,
    *,
    index: str,
    filters: List[Dict[str, Any]],
    collection: Optional[str] = None,
    inter_field_operator: Literal["AND", "OR"] = "AND",
    size: int = 10,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Hàm lọc tổng quát, hỗ trợ logic kết hợp linh hoạt và lọc theo collection.
    """
    ensure_index(client, index)

    # Xây dựng các mệnh đề lọc từ input `filters`
    clauses = []
    
    # Fields that contain descriptive text and should use text search instead of exact match
    text_search_fields = ["Language_Certificate", "Min_Gpa", "Experience_Years", 
                          "Funding_Details", "Eligibility_Criteria", "Other_Requirements"]
    
    # Fields that contain comma-separated values and need partial text matching
    multi_value_fields = ["Eligible_Fields", "Funding_Level", "Scholarship_Type", 
                          "Danh_Sách_Nhóm_Ngành", "Application_Mode", "Eligible_Field_Group"]
    
    # Fields that need case-insensitive exact matching
    case_insensitive_fields = ["Wanted_Degree", "Country"]
    
    for f in filters:
        field = f["field"]
        values = f["values"]
        intra_operator = f.get("operator", "OR").lower()
        
        # Determine if we should use text search or exact keyword matching
        if field in text_search_fields or field in multi_value_fields:
            # Use match_phrase query for exact phrase matching in comma-separated values
            if intra_operator == "or":
                # OR logic: any value matches
                should_clauses = []
                for value in values:
                    should_clauses.append(
                        {"match_phrase": {field: str(value)}}
                    )
                clauses.append({
                    "bool": {
                        "should": should_clauses,
                        "minimum_should_match": 1
                    }
                })
            else:  # AND logic: all values must match
                for value in values:
                    clauses.append(
                        {"match_phrase": {field: str(value)}}
                    )
        elif field in case_insensitive_fields:
            # Use match query for case-insensitive exact matching
            if intra_operator == "or":
                # OR logic: any value matches
                should_clauses = []
                for value in values:
                    should_clauses.append(
                        {"match": {field: {"query": str(value), "operator": "and"}}}
                    )
                clauses.append({
                    "bool": {
                        "should": should_clauses,
                        "minimum_should_match": 1
                    }
                })
            else:  # AND logic: all values must match
                for value in values:
                    clauses.append(
                        {"match": {field: {"query": str(value), "operator": "and"}}}
                    )
        else:
            # Use term/terms query for exact matching with keyword field
            keyword_field = f"{field}.raw" if field not in ["collection", "__text"] else field
            
            if len(values) == 1:
                # Single value - use term query
                clauses.append(
                    {"term": {keyword_field: values[0]}}
                )
            else:
                # Multiple values - use terms query
                if intra_operator == "or":
                    clauses.append(
                        {"terms": {keyword_field: values}}
                    )
                else:  # AND logic
                    clauses.append(
                        {"terms": {keyword_field: values}}
                    )
    
    query_body: Dict[str, Any] = {"bool": {}}
    
    # Logic kết hợp các mệnh đề lọc chính
    if clauses:
        if inter_field_operator == "AND":
            query_body["bool"]["filter"] = clauses
        else: # inter_field_operator == "OR"
            query_body["bool"]["should"] = clauses
            query_body["bool"]["minimum_should_match"] = 1
            
    # Luôn áp dụng bộ lọc `collection` như một điều kiện AND (nếu có)
    # bằng cách thêm nó vào mệnh đề 'filter'.
    # Đây là cách hiệu quả nhất để kết hợp.
    if collection:
        # Nếu 'filter' chưa tồn tại, tạo mới
        if "filter" not in query_body["bool"]:
            query_body["bool"]["filter"] = []
        # Thêm điều kiện lọc collection
        query_body["bool"]["filter"].append({"term": {"collection": collection}})


    # Trả về rỗng nếu không có bất kỳ điều kiện nào
    if not query_body["bool"]:
        return {"total": 0, "items": []}

    # Thực thi query
    res = client.search(
        index=index,
        query=query_body,
        size=size,
        from_=offset,
    )
    hits = [
        {"id": h["_id"], "score": h["_score"], "source": h["_source"]}
        for h in res["hits"]["hits"]
    ]
    return {"total": res["hits"]["total"]["value"], "items": hits}


def delete_index(client: Elasticsearch, index: str) -> dict:
    """
    Delete an Elasticsearch index.
    
    Args:
        client: Elasticsearch client
        index: Index name to delete
        
    Returns:
        Dict with deletion status
        
    Example:
        >>> es = Elasticsearch(...)
        >>> result = delete_index(es, "scholarships")
        >>> print(result)
        {"status": "deleted", "index": "scholarships"}
    """
    try:
        if client.indices.exists(index=index):
            client.indices.delete(index=index)
            return {
                "status": "deleted",
                "index": index,
                "message": f"Index '{index}' deleted successfully"
            }
        else:
            return {
                "status": "not_found",
                "index": index,
                "message": f"Index '{index}' does not exist"
            }
    except Exception as e:
        return {
            "status": "error",
            "index": index,
            "error": str(e)
        }
