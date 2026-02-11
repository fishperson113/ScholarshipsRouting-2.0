from typing import Dict, Any

# Mocking the function logic directly to avoid Celery dependency on host
def receive_from_n8n_logic(n8n_response: Dict[str, Any]) -> Dict[str, Any]:
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

def test_logic():
    print("Testing logic standalone...")
    
    # Case 1: Standard
    res1 = receive_from_n8n_logic({"output": "hi", "status": "success"})
    print(res1)
    assert res1["reply"] == "hi"
    assert res1["celery"] == True
    
    # Case 2: Error
    res2 = receive_from_n8n_logic({"status": "error", "message": "fail"})
    print(res2)
    assert res2["status"] == "error"
    assert res2["reply"] == "fail"
    
    print("Standalone logic tests passed!")

if __name__ == "__main__":
    test_logic()
