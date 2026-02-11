# PLAN-n8n-celery-split

## Context

The goal is to decouple the n8n interaction logic by splitting the `send_to_n8n` Celery task into two distinct tasks:

1. `send_to_n8n`: Handles the HTTP request to the n8n webhook.
2. `receive_from_n8n`: Processes the raw response from n8n and formats it into a `ChatResponse` DTO.

This separation allows for better modularity and error handling. We will orchestrate these tasks using a Celery `chain`. Additionally, the `ChatResponse` DTO will be updated to include a `celery` flag indicating execution status.

## User Review Required

> [!IMPORTANT]
> Verify the `ChatResponse` DTO field changes (`celery: bool`) are compatible with the frontend client.

## Proposed Changes

### [Server]

#### [MODIFY] [chat_dtos.py](file:///f:/THUC%20HANH/SR%202.0/ScholarshipsRouting-2.0/server/dtos/chat_dtos.py)

- Update `ChatResponse` class to include:
  - `celery: bool` (default `True` or as appropriate)

#### [MODIFY] [tasks.py](file:///f:/THUC%20HANH/SR%202.0/ScholarshipsRouting-2.0/server/services/tasks.py)

- Refactor `send_to_n8n` to only perform the HTTP request and return the raw JSON response.
- Create new task `receive_from_n8n` that:
  - Takes the output of `send_to_n8n` as input.
  - Parses the response.
  - Returns a dict compatible with `ChatResponse` (with `reply`, `status`, `celery=True`).

#### [MODIFY] [chat.py](file:///f:/THUC%20HANH/SR%202.0/ScholarshipsRouting-2.0/server/routes/chat.py)

- Update `chat_sync` endpoint to use `celery.chain`:
  ```python
  task_chain = chain(send_to_n8n.s(request.dict()) | receive_from_n8n.s())
  result = task_chain.apply_async()
  ```
- Handle the asynchronous result retrieval appropriately.

## Verification Plan

### Automated Tests

- Create a test script (or use `tests/test_n8n_flow.py`) to:
  1. Invoke the `chat_sync` endpoint.
  2. Mock the `requests.post` in `send_to_n8n` to return a sample n8n response.
  3. Verify that `receive_from_n8n` correctly formats the output.
  4. Assert that the final response contains `celery: true`.

### Manual Verification

- Run the server and worker: `docker compose up`.
- Send a POST request to `/chat/sync` with a sample payload.
- Verify the response structure matches the new `ChatResponse` DTO.
- Check Celery logs to ensure both tasks (`send_to_n8n`, `receive_from_n8n`) were executed.
