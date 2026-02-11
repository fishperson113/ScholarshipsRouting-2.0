from typing import Dict, Any

# Mocking the function logic directly to avoid Celery dependency on host
def receive_to_n8n_logic(n8n_response: Dict[str, Any]) -> Dict[str, Any]:
    # This logic should match what's in tasks.py
    def json_extract_reply(data: dict) -> str:
        if isinstance(data, dict) and data:
            if "output" in data:
                return str(data["output"])
            if "text" in data:
                return str(data["text"])
            if "reply" in data:
                return str(data["reply"])
            return str(next(iter(data.values())))
        return str(data)

    status = n8n_response.get("status", "success")
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
    print("Testing logic receive_to_n8n...")
    
    # Case 1: Standard
    res1 = receive_to_n8n_logic({"output": "hi", "status": "success"})
    print(res1)
    assert res1["reply"] == "hi"
    assert res1["celery"] == True
    
    print("Logic tests passed!")

if __name__ == "__main__":
    test_logic()
