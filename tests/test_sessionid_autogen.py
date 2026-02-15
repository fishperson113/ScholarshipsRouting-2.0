"""
Standalone test script for Chat DTOs and Session ID auto-generation.
Run with: python tests/test_sessionid_autogen.py
"""
import sys
from pathlib import Path

# Add parent directory to path to import dtos
sys.path.insert(0, str(Path(__file__).parent.parent))

from uuid import UUID
from dtos.chat_dtos import ChatRequest, ChatResponse


def test_sessionid_auto_generated_when_not_provided():
    """Test that sessionId is auto-generated when not provided."""
    print("🧪 Test 1: sessionId auto-generation when not provided")
    
    # Create request without sessionId
    request = ChatRequest(
        query="Hello",
        plan="basic",
        user_id="test_user"
        # sessionId intentionally omitted
    )
    
    # Verify
    assert request.sessionId is not None, "sessionId should not be None"
    assert isinstance(request.sessionId, UUID), f"sessionId should be UUID, got {type(request.sessionId)}"
    assert request.sessionId.version == 4, f"sessionId should be UUIDv4, got version {request.sessionId.version}"
    
    print(f"  ✅ Pass - Auto-generated sessionId: {request.sessionId}")


def test_sessionid_preserved_when_provided():
    """Test that provided sessionId is preserved."""
    print("\n🧪 Test 2: sessionId preservation when provided")
    
    custom_session_id = UUID("550e8400-e29b-41d4-a716-446655440000")
    
    request = ChatRequest(
        query="Hello",
        plan="basic",
        user_id="test_user",
        sessionId=custom_session_id
    )
    
    assert request.sessionId == custom_session_id, f"sessionId mismatch: {request.sessionId} != {custom_session_id}"
    
    print(f"  ✅ Pass - Preserved sessionId: {request.sessionId}")


def test_sessionid_converts_to_string():
    """Test that sessionId can be converted to string for Celery."""
    print("\n🧪 Test 3: sessionId string conversion")
    
    request = ChatRequest(
        query="Hello",
        plan="basic",
        user_id="test_user"
    )
    
    # Convert to dict
    request_dict = request.dict()
    assert 'sessionId' in request_dict, "sessionId should be in dict"
    assert isinstance(request_dict['sessionId'], UUID), "sessionId in dict should be UUID"
    
    # Test string conversion (what the route does)
    session_id_str = str(request.sessionId)
    assert isinstance(session_id_str, str), "Converted sessionId should be string"
    assert len(session_id_str) == 36, f"UUID string should be 36 chars, got {len(session_id_str)}"
    
    print(f"  ✅ Pass - String conversion: {session_id_str}")


def test_chat_response_includes_sessionid():
    """Test that ChatResponse can include sessionId."""
    print("\n🧪 Test 4: ChatResponse with sessionId")
    
    session_id = UUID("550e8400-e29b-41d4-a716-446655440000")
    
    response = ChatResponse(
        reply="Test reply",
        status="success",
        celery=True,
        sessionId=session_id
    )
    
    assert response.sessionId == session_id, f"sessionId mismatch in response"
    
    print(f"  ✅ Pass - Response sessionId: {response.sessionId}")


def test_multiple_requests_have_different_sessionids():
    """Test that multiple requests without sessionId get unique IDs."""
    print("\n🧪 Test 5: Unique sessionIds for multiple requests")
    
    request1 = ChatRequest(query="Hello", plan="basic", user_id="user1")
    request2 = ChatRequest(query="Hi", plan="basic", user_id="user2")
    
    assert request1.sessionId != request2.sessionId, "Auto-generated sessionIds should be unique"
    
    print(f"  ✅ Pass - Request 1: {request1.sessionId}")
    print(f"  ✅ Pass - Request 2: {request2.sessionId}")


def run_all_tests():
    """Run all tests."""
    print("="*60)
    print("Session ID Auto-Generation Tests")
    print("="*60)
    
    tests = [
        test_sessionid_auto_generated_when_not_provided,
        test_sessionid_preserved_when_provided,
        test_sessionid_converts_to_string,
        test_chat_response_includes_sessionid,
        test_multiple_requests_have_different_sessionids
    ]
    
    failed = 0
    for test in tests:
        try:
            test()
        except AssertionError as e:
            print(f"  ❌ FAIL - {e}")
            failed += 1
        except Exception as e:
            print(f"  ❌ ERROR - {e}")
            failed += 1
    
    print("\n" + "="*60)
    print(f"Results: {len(tests) - failed}/{len(tests)} tests passed")
    print("="*60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
