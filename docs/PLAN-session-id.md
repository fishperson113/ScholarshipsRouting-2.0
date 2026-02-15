# Plan: Session ID Integration (Route-Level)

## Overview

Implement `sessionId` propagation from the Chat API to N8n via Celery using **Route-Level Handling**. This approach ensures that the `UUID` is converted to a string before being passed to Celery, avoiding serialization issues and ensuring compatibility with Redis and N8n.

## Project Type

**BACKEND** (API + Celery Workers)

## Success Criteria

1.  `ChatRequest` accepts a `sessionId` (already done).
2.  `ChatResponse` returns the same `sessionId` to the client.
3.  `server/routes/chat.py` converts `sessionId` to string before enqueueing.
4.  `server/services/tasks.py` receives a JSON-serializable dict (with string `sessionId`).
5.  N8n receives the `sessionId` in the payload.
6.  No `TypeError: Object of type UUID is not JSON serializable` errors in Celery logs.

## Tech Stack

- **Server**: FastAPI (Python)
- **Async**: Celery + Redis
- **Integration**: N8n Webhooks

## File Structure

No new files. Modifying existing:

- `server/dtos/chat_dtos.py`
- `server/routes/chat.py`
- `server/services/tasks.py`

## Task Breakdown

### 1. Update DTOs

**Agent**: `backend-specialist`
**Skill**: `api-patterns`

- **Input**: `server/dtos/chat_dtos.py`
- **Action**: Add `sessionId: UUID` (or `str` in response) to `ChatResponse`.
- **Output**: `ChatResponse` includes `sessionId`.
- **Verify**: Pydantic models validate correctly.

### 2. Implement Route-Level Conversion

**Agent**: `backend-specialist`
**Skill**: `celery-patterns`

- **Input**: `server/routes/chat.py`
- **Action**:
  - In `chat_sync`, generic `request.dict()`.
  - EXPLICITLY convert `payload['sessionId'] = str(request.sessionId)`.
  - Pass modified `payload` to `send_to_n8n.delay(payload)`.
  - Update return statement to include `sessionId` in `ChatResponse`.
- **Output**: Celery task receives valid JSON dict.
- **Verify**: No serialization errors on request.

### 3. Update Celery Tasks

**Agent**: `backend-specialist`
**Skill**: `celery-patterns`

- **Input**: `server/services/tasks.py`
- **Action**:
  - Update `send_to_n8n` docstring to reflect it expects string `sessionId`.
  - Update `receive_to_n8n` to pass `sessionId` through to the final result (if n8n echoes it back, or preserve it in the chain if possible). _Note: Since `receive_to_n8n` takes the n8n response, we might need to rely on n8n returning the sessionId, or pass it via Celery chain context. For now, we'll assume n8n returns it or we just return the input one if available in the route._
  - _Wait, `receive_to_n8n` is the second step._
  - _Refinement_: To keep it simple, `receive_to_n8n` might not need to know about `sessionId` if the Route holds the original request.
  - _Correction_: The Route `chat_sync` waits for the result. The result comes from `receive_to_n8n`. So `receive_to_n8n` MUST return the `sessionId`.
  - **Action Refined**: Update `send_to_n8n` to ensure `sessionId` is sent to N8n. Update `receive_to_n8n` to look for `sessionId` in N8n response (if n8n echoes) OR we just accept that the Route has the original ID and can merge it.
  - _Decision_: The Route `chat_sync` has `request.sessionId`. It can simply attach it to the final `ChatResponse` before returning, regardless of what the task chain returns (unless the task chain changes it, which it shouldn't).
  - **Revised Action**: Just ensure `tasks.py` doesn't crash.

## Phase X: Verification

- [ ] **Manual Flow Test**:
  1.  Start Server & Celery.
  2.  Send POST `/chat/sync` with `sessionId`.
  3.  Check Celery logs for successful task execution.
  4.  Check Response contains `sessionId`.
