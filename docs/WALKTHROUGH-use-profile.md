# Walkthrough - Add use_profile Field

I have successfully added the `use_profile` boolean field to `ChatRequest` DTO to enable the chatbot to use user profile information based on the frontend's plan selection.

## Changes

### 1. Server Data Transfer Objects

#### [chat_dtos.py](file:///f:/THUC%20HANH/SR%202.0/ScholarshipsRouting-2.0/server/dtos/chat_dtos.py#L8-L10)

- Added `use_profile: bool = False` field to `ChatRequest`
- Placed after `user_id` and before `sessionId` for logical grouping
- Added comment explaining frontend usage: `use_profile: selectedPlan === 'pro' ? useProfile : false`

**Key Features:**

- **Default Value**: `False` ensures backward compatibility
- **Optional**: Frontend can omit this field entirely
- **Boolean Type**: Pydantic validates type automatically

### 2. Celery Tasks Documentation

#### [tasks.py](file:///f:/THUC%20HANH/SR%202.0/ScholarshipsRouting-2.0/server/services/tasks.py#L275)

- Updated docstring for `send_to_n8n` to include `use_profile` in payload description

### 3. Route Compatibility Verification

#### [chat.py](file:///f:/THUC%20HANH/SR%202.0/ScholarshipsRouting-2.0/server/routes/chat.py#L22-L23)

**No changes required** ✅

The existing code already handles the new field automatically:

```python
payload = request.dict()  # Includes ALL ChatRequest fields, including use_profile
payload['sessionId'] = str(request.sessionId)  # Only converts UUID
```

## Backward Compatibility

### Old Requests (Still Work)

```json
{
  "query": "Hello",
  "plan": "basic",
  "user_id": "test_user"
}
```

Result: `use_profile` defaults to `false` in n8n payload

### New Requests

```json
{
  "query": "Hello",
  "plan": "pro",
  "user_id": "test_user",
  "use_profile": true
}
```

Result: `use_profile: true` sent to n8n

## Verification

### Manual Test Checklist

1. **Test Default Value**:
   - Send request WITHOUT `use_profile`
   - Check n8n logs: Should show `"use_profile": false`

2. **Test Explicit True**:
   - Send request with `"use_profile": true`
   - Check n8n logs: Should show `"use_profile": true`

3. **Test Type Validation**:
   - Send request with `"use_profile": "invalid"`
   - Should return 422 validation error

### Example Request

```bash
curl -X POST http://localhost:8000/api/v1/chat/sync \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What scholarships are available?",
    "plan": "pro",
    "user_id": "user_123",
    "use_profile": true
  }'
```

### Expected n8n Payload

```json
{
  "query": "What scholarships are available?",
  "plan": "pro",
  "user_id": "user_123",
  "use_profile": true,
  "sessionId": "550e8400-e29b-41d4-a716-446655440000"
}
```

## Impact Analysis

| Component      | Impact                     | Action Required                            |
| -------------- | -------------------------- | ------------------------------------------ |
| Frontend       | None (backward compatible) | Can start sending `use_profile` when ready |
| Backend API    | Added field                | ✅ Completed                               |
| Celery Workers | None                       | Automatically handles new field            |
| N8n Workflow   | Can access `use_profile`   | Update workflow to use this flag           |
| Redis          | None                       | Just another payload field                 |

## Next Steps

The backend is ready. The frontend can now:

1. Send `use_profile: true` for pro plan users
2. Send `use_profile: false` or omit it for basic plan users
3. N8n workflow should check `use_profile` and conditionally query user profile data
