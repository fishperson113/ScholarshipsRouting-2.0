# Plan: Add `use_profile` Field to ChatRequest

## Overview

Add a `use_profile` boolean field to `ChatRequest` DTO to enable the chatbot to use user profile information when the frontend sends `use_profile: selectedPlan === 'pro' ? useProfile : false`. This field will be propagated through the entire chat pipeline to n8n.

## Project Type

**BACKEND** (API + DTOs)

## Success Criteria

1. `ChatRequest` accepts `use_profile` as an optional boolean field (defaults to `False`)
2. The field is backward compatible (existing requests without it still work)
3. `use_profile` is included in the payload sent to n8n via Celery
4. n8n receives the `use_profile` flag in the webhook payload
5. No breaking changes to existing functionality

## Tech Stack

- **Server**: FastAPI (Python)
- **Validation**: Pydantic
- **Async**: Celery + Redis
- **Integration**: N8n Webhooks

## File Structure

No new files. Modifying existing:

- `server/dtos/chat_dtos.py`
- `server/services/tasks.py` (docstring update only)

## Task Breakdown

### Task 1: Update ChatRequest DTO

**Agent**: `backend-specialist`
**Skill**: `api-patterns`

- **Input**: `server/dtos/chat_dtos.py`
- **Action**:
  - Add `use_profile: bool = False` field to `ChatRequest` class
  - Place it after `user_id` and before `sessionId` for logical grouping
  - Add docstring comment explaining the field's purpose
- **Output**: Updated `ChatRequest` with `use_profile` field
- **Verify**:
  - Pydantic model validates correctly
  - Requests without `use_profile` default to `False`
  - Requests with `use_profile=True` are accepted

### Task 2: Update Task Documentation

**Agent**: `backend-specialist`
**Skill**: `api-patterns`

- **Input**: `server/services/tasks.py`
- **Action**:
  - Update `send_to_n8n` docstring to include `use_profile` in the payload description
- **Output**: Updated docstring
- **Verify**: Documentation is accurate

### Task 3: Verify Route Compatibility (No Code Change Needed)

**Agent**: `backend-specialist`
**Skill**: `api-patterns`

- **Input**: `server/routes/chat.py`
- **Action**:
  - **VERIFY ONLY** - No code changes needed
  - Confirm that existing `payload = request.dict()` already includes `use_profile`
  - Confirm that `payload['sessionId'] = str(request.sessionId)` doesn't interfere
- **Output**: Confirmation that route handles the new field automatically
- **Verify**: Manual inspection confirms compatibility

## Implementation Notes

### Why No Route Changes?

The existing route code already handles this automatically:

```python
payload = request.dict()  # ← This includes ALL fields, including use_profile
payload['sessionId'] = str(request.sessionId)  # ← Only converts sessionId
```

Since we're using `request.dict()`, any new fields in `ChatRequest` are automatically included in the payload sent to Celery/n8n.

### Backward Compatibility

- Old requests: `{"query": "...", "plan": "...", "user_id": "..."}` → `use_profile` defaults to `False`
- New requests: `{"query": "...", "plan": "...", "user_id": "...", "use_profile": true}` → Works as expected

## Phase X: Verification

### Manual Verification

- [ ] **Test 1: Default Value**
  - Send request WITHOUT `use_profile`
  - Verify n8n receives `"use_profile": false`

- [ ] **Test 2: Explicit True**
  - Send request with `"use_profile": true`
  - Verify n8n receives `"use_profile": true`

- [ ] **Test 3: Explicit False**
  - Send request with `"use_profile": false`
  - Verify n8n receives `"use_profile": false`

### Test Payload Examples

**Minimal Request (Backward Compatible):**

```json
{
  "query": "Hello",
  "plan": "basic",
  "user_id": "test_user"
}
```

Expected in n8n: `use_profile: false`

**Pro Plan Request:**

```json
{
  "query": "Hello",
  "plan": "pro",
  "user_id": "test_user",
  "use_profile": true
}
```

Expected in n8n: `use_profile: true`

## Risk Assessment

| Risk                          | Mitigation                                           |
| ----------------------------- | ---------------------------------------------------- |
| Breaking existing requests    | Use default value `False` for backward compatibility |
| n8n doesn't handle boolean    | n8n natively supports JSON booleans                  |
| Frontend sends invalid values | Pydantic validates boolean type automatically        |

## Timeline

- Task 1: 2 minutes
- Task 2: 1 minute
- Task 3: 1 minute (verification only)
- Testing: 5 minutes

**Total: ~10 minutes**
