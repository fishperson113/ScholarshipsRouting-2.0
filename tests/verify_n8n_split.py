import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'server'))

from services.tasks import receive_to_n8n
from dtos.chat_dtos import ChatResponse
import json
import uuid

def test_receive_logic():
    print("Testing receive_to_n8n logic...")
    
    dummy_uuid = str(uuid.uuid4())
    
    # Case 1: Standard n8n output with 'output' key
    input1 = {"output": "Hello from n8n", "status": "success", "sessionId": dummy_uuid}
    result1 = receive_to_n8n(input1)
    print(f"Result 1: {result1}")
    assert result1["reply"] == "Hello from n8n"
    assert result1["celery"] == True
    assert result1.get("sessionId") == dummy_uuid
    
    # Validate with DTO
    dto1 = ChatResponse(**result1)
    print(f"DTO 1: {dto1}")
    assert dto1.celery == True
    assert str(dto1.sessionId) == dummy_uuid

    # Case 2: n8n returning text key
    input2 = {"text": "Alternative reply"}
    result2 = receive_to_n8n(input2)
    print(f"Result 2: {result2}")
    assert result2["reply"] == "Alternative reply"
    
    # Case 3: Error case
    input3 = {"status": "error", "message": "Something went wrong"}
    result3 = receive_to_n8n(input3)
    print(f"Result 3: {result3}")
    assert result3["status"] == "error"
    assert result3["reply"] == "Something went wrong"
    
    print("\nAll logic tests passed!")

if __name__ == "__main__":
    test_receive_logic()
