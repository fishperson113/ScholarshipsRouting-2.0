# Walkthrough - Session ID Integration

I have successfully implemented `sessionId` propagation from the Chat API to N8n via Celery using **Route-Level Handling**.

## Changes

### 1. Server Data Transfer Objects

#### [chat_dtos.py](file:///f:/THUC%20HANH/SR%202.0/ScholarshipsRouting-2.0/server/dtos/chat_dtos.py)

- Added `sessionId: Optional[UUID] = None` to `ChatResponse`.

### 2. API Route (Route-Level Conversion)

#### [chat.py](file:///f:/THUC%20HANH/SR%202.0/ScholarshipsRouting-2.0/server/routes/chat.py)

- Updated `chat_sync` to convert `request.sessionId` (UUID) to `str` before creating the Celery task payload.
- This prevents `TypeError: Object of type UUID is not JSON serializable` in Celery.
- Updated `ChatResponse` instantiation to include the `sessionId` from the request.

### 3. Celery Tasks

#### [tasks.py](file:///f:/THUC%20HANH/SR%202.0/ScholarshipsRouting-2.0/server/services/tasks.py)

- Updated docstrings for `send_to_n8n` to verify it accepts `sessionId`.

## Verification

### Manual Verification Checklist

Since this involves async workers, please perform the following manual test:

1.  **Start Services**:

    ```bash
    # Terminal 1
    celery -A celery_app worker --loglevel=info

    # Terminal 2
    python server/app.py
    ```

2.  **Send Request**:
    Send a POST request to `http://localhost:8000/chat/sync` with a `sessionId`.

    ```json
    {
      "query": "Hello",
      "plan": "basic",
      "user_id": "test_user",
      "sessionId": "550e8400-e29b-41d4-a716-446655440000"
    }
    ```

3.  **Verify Output**:
    - **Response**: Check if the JSON response contains `"sessionId": "550e8400-e29b..."`.
    - **Celery Logs**: Check that the task received the payload with `sessionId` as a string and didn't crash.
    - **N8n**: Verify N8n received the `sessionId`.
