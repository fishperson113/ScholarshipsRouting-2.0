# PLAN-n8n-response-handling

> **Goal:** Robustly handle n8n responses to prevent crashes when the upstream service returns plain text or HTML instead of JSON.

## 1. Context & Problem

- **Current Behavior:** `server/services/tasks.py` expects a JSON response from n8n (`response.json()`). If n8n times out, errors, or returns a plain text string, the Celery task crashes.
- **Route Issue:** `server/routes/chat.py` attempts to pass the raw result directly to `ChatResponse`. If the structure doesn't match the Pydantic model or the logic, it may fail validation or hide the actual message.

## 2. Solution Strategy

Combine **Option A** (Safety Wrapper at Source) and **Option B** (Smart Extraction at Consumer).

### 2.1 Option A: Task-Level Safety (`server/services/tasks.py`)

Modify `process_scholarship_sync` (and specifically `send_to_n8n` task) to catch JSON decoding errors.

- **Action:** Wrap `response.json()` in a `try...except` block.
- **Fallback:** If JSON decoding fails, return a constructed dictionary containing the raw text.

### 2.2 Option B: Route-Level Extraction (`server/routes/chat.py`)

Utilize the existing (but unused) `json_extract_reply` helper function.

- **Action:** In `chat_sync` endpoint, instead of directly passing `result` to `reply`, use `json_extract_reply(result)`.
- **Benefit:** This ensures that regardless of the dictionary structure returned by the Task (or n8n), we extract the most meaningful text string for the user.

## 3. Implementation Details

### Step 1: Modify `server/services/tasks.py`

Target function: `send_to_n8n`

```python
# Pseudo-code change
try:
    return response.json()
except ValueError:  # requests.exceptions.JSONDecodeError
    return {
        "output": response.text,
        "status": "success_with_text_fallback"
    }
```

### Step 2: Modify `server/routes/chat.py`

Target function: `chat_sync`

```python
# Pseudo-code change
return ChatResponse(
    reply=json_extract_reply(result),  # Use the helper!
    n8n_data=result if isinstance(result, dict) else {"raw": str(result)},
    status="success"
)
```

## 4. Verification Plan

### Automated Test

1.  **Mock n8n Response:**
    - Test Case 1: Valid JSON `{"output": "Hello"}` -> Expect success.
    - Test Case 2: Plain Text `Hello World` -> Expect success (no crash), reply should be "Hello World".
    - Test Case 3: 504 Gateway Timeout (HTML) -> Expect handled error or fallback text.

### Manual Verification

- Trigger the `/chat/sync` endpoint manually.
- Inspect the logs to ensure no traceback occurs on non-JSON response.
