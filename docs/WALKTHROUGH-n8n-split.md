# Walkthrough - Split n8n Celery Tasks

I have successfully split the `send_to_n8n` task into two distinct Celery tasks to decouple the HTTP request from the response processing, and chained them together.

## Changes

### 1. Server Data Transfer Objects

#### [chat_dtos.py](file:///f:/THUC%20HANH/SR%202.0/ScholarshipsRouting-2.0/server/dtos/chat_dtos.py)

- Added `celery: bool = True` to `ChatResponse`.

### 2. Celery Tasks

#### [tasks.py](file:///f:/THUC%20HANH/SR%202.0/ScholarshipsRouting-2.0/server/services/tasks.py)

- **`send_to_n8n`**: Modified to only perform the HTTP request and return the raw JSON (or error dict).
- **`receive_from_n8n`**: New task that takes the output of `send_to_n8n`, extracts the reply text, and formats it into the `ChatResponse` structure with `celery=True`.

### 3. API Route

#### [chat.py](file:///f:/THUC%20HANH/SR%202.0/ScholarshipsRouting-2.0/server/routes/chat.py)

- Updated `chat_sync` to use `celery.chain`:
  ```python
  task_chain = chain(send_to_n8n.s(request.dict()) | receive_from_n8n.s())
  task = task_chain.apply_async()
  ```

## Verification Results

### Automated Logic Verification

I ran a standalone script to verify the logic of `receive_from_n8n`:

- **Success Case**: Correctly extracts `output`/`text`/`reply` and sets `celery=True`.
- **Error Case**: Correctly propagates error status and message.

All logic tests passed.
