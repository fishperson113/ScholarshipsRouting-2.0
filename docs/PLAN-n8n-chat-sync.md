# Plan: N8n Chat Gateway (Synchronous)

> **Context**: We are building a "Chat Endpoint" that offloads message processing to **Celery** (for scalability) but waits for the result to provide a **Synchronous** HTTP response to the user. This corresponds to **Option B** from our brainstorming session.

## 📋 Overview

The goal is to provide a seamless chat experience where the frontend sends a message and receives a reply in a single HTTP request, while the backend uses an asynchronous worker (Celery) to communicate with the n8n workflow. This decouples the heavy lifting/network waiting from the main API thread, although the specific request handler will block while waiting for the result.

### 👥 User Story

As a Developer, I want to send a POST request with a user message to `/api/v1/chat/sync` and receive the AI/N8n response in the body, so that I can easily integrate it into a standard chat UI.

### ❓ Socratic Decisions (Phase 0)

- **N8n URL**: Using `N8N_WEBHOOK_URL` from `.env`.
- **Timeout**: Defaulting to **30 seconds**. If n8n takes longer, we return a 504 Gateway Timeout.
- **Protocol**: HTTP Sync (Blocking). The API thread will suspend (using `AsyncResult.get`) but not block the event loop if implemented correctly, but standard Celery `clean get` is blocking. We will use `celery_task.get(timeout=30)` inside a threadpool or rely on FastAPIs async capabilities for concurrent request handling.

---

## 🏗️ Project Structure

**Project Type:** BACKEND (Python/FastAPI/Celery)

### 🧱 Tech Stack

- **Framework**: FastAPI
- **Queue**: Celery + Redis
- **External**: n8n (via Webhook)
- **HTTP Client**: `httpx` (inside Celery worker)

---

## 🛠️ File Structure

```
server/
├── dtos/
│   └── chat_dtos.py      # [NEW] Pydantic models for chat
├── routes/
│   └── chat.py           # [NEW] Chat endpoints
├── services/
│   └── tasks.py          # [MODIFY] Add send_to_n8n_task
└── app.py                # [MODIFY] Register new router
```

---

## 📝 Task Breakdown

### Phase 1: Foundation (DTOs & Worker)

#### Task 1.1: Create Chat DTOs

Define the input/output contract to ensure type safety.

- **File**: `server/dtos/chat_dtos.py`
- **Input**: `ChatRequest` (query, plan, user_id)
- **Output**: `ChatResponse` (reply, n8n_data, status)
- **Verify**: Can import classes in shell.
- **Agent**: `backend-specialist` | **Skill**: `api-patterns`

#### Task 1.2: Implement Celery Task

Create the task that actually hits n8n.

- **File**: `server/services/tasks.py`
- **Action**: Add `send_to_n8n` task.
- **Logic**:
  - Read `N8N_WEBHOOK_URL` from env.
  - Send POST request with payload: `{ "query": query, "plan": plan, "user_id": user_id }`
  - Return JSON response.
- **Verify**: Call task manually in shell `send_to_n8n.delay(...)` and check return value.
- **Agent**: `backend-specialist` | **Skill**: `nodejs-best-practices` (Using Python requests actually)

### Phase 2: API & Integration

#### Task 2.1: Create Chat Route

Implement the blocking endpoint.

- **File**: `server/routes/chat.py`
- **Action**: Create `POST /sync`
- **Logic**:
  - Enqueue task: `task = send_to_n8n.delay(data)`
  - Wait: `result = task.get(timeout=30)`
  - Error Handling: Catch `TimeoutError` -> 504.
- **Verify**: Curl the endpoint returns 200 OK with n8n response.
- **Agent**: `backend-specialist` | **Skill**: `api-patterns`

#### Task 2.2: Register Router

Wire the new route into the main app.

- **File**: `server/app.py`
- **Action**: `app.include_router(chat.router, ...)`
- **Verify**: `/docs` shows the new endpoints.
- **Agent**: `backend-specialist`

---

## ✅ Phase X: Verification Checklist

### 1. Manual Verification

- [ ] **Env Check**: Ensure `N8N_WEBHOOK_URL` is set in `.env` (Checked: It is present).
- [ ] **Celery Worker**: Must be running (`celery -A celery_app worker ...`).
- [ ] **Flow Test**:
  - Send: `{ "query": "Hello n8n", "plan": "test", "user_id": "123" }`
  - Expect: JSON response from n8n.
  - Latency: Should be < 5s (typical n8n).

### 2. Automated Checks

- [ ] Linting: `flake8 server/routes/chat.py`
- [ ] Type Check: `mypy server/dtos`

---

## 🔮 Future Improvements

- Add `session_id` to persist context in Redis.
- Add "Typing..." indicators via WebSocket (Option C).
- Retry logic for failed n8n calls.
