# Public Chat Frontend Requirements

## Goal

Integrate the public chatbot with free-token limits and a contact capture fallback flow.

- Each chat session has a free limit of `3000` tokens.
- Once the limit is reached, chat should stop calling AI and collect `name`, `phone`, and `email`.
- Super admin can track token usage from platform leads endpoints.

## Public Endpoints

### 1) Chat

- **Endpoint**: `POST /api/v1/public/chat`
- **Auth**: none
- **Request**:
```json
{
  "session_id": "optional-uuid-string",
  "message": "User message"
}
```

- **Response**:
```json
{
  "session_id": "uuid-string",
  "lead_id": "uuid-string",
  "reply": "assistant reply",
  "lead_captured": false,
  "limit_reached": false,
  "tokens_used": 420,
  "tokens_remaining": 2580
}
```

### 2) Contact Submit (after limit reached)

- **Endpoint**: `POST /api/v1/public/contact`
- **Auth**: none
- **Request**:
```json
{
  "session_id": "same-session-id-from-chat",
  "name": "optional string",
  "phone": "optional string",
  "email": "optional@email.com"
}
```

- **Response**:
```json
{
  "session_id": "uuid-string",
  "lead_id": "uuid-string",
  "message": "status message",
  "all_collected": false,
  "missing_fields": ["phone", "email"]
}
```

## Frontend Flow

1. On first message, call `/chat` without `session_id`.
2. Store returned `session_id` and reuse it for every next chat message.
3. After each response:
   - Show `reply`.
   - Update usage UI from `tokens_used` and `tokens_remaining`.
4. If `limit_reached` becomes `true`:
   - Disable normal chat input.
   - Show a form with `name`, `phone`, and `email`.
   - Submit the form to `/contact`.
5. If `/contact` returns `all_collected: false`, keep the form open and highlight `missing_fields`.
6. When `all_collected: true`, show success message and keep chat locked (no further AI calls).

## UI Requirements

- **Token indicator**: show remaining tokens, for example `2580 / 3000`.
- **Limit state**:
  - Show backend `reply` as the limit message.
  - Persist this state in local storage/session storage using `session_id`.
- **Contact form validation**:
  - `name`: non-empty
  - `phone`: non-empty
  - `email`: valid email format

## Error Handling

- If `/chat` fails: show "Unable to process your request. Please try again."
- If `/contact` fails: keep the form state and allow retry.
- If session is lost on frontend reload, start a new chat session.

## Super Admin APIs (for dashboard)

Use existing platform leads endpoints:

- `GET /api/v1/platform/leads`:
  - Includes each lead's `total_tokens_used`, `token_limit`, and `limit_reached`.
  - Includes aggregate `total_tokens_consumed` and `leads_at_limit`.
- `GET /api/v1/platform/leads/token-stats`:
  - Returns:
    - `total_leads`
    - `total_tokens_consumed`
    - `leads_at_limit`
    - `leads_with_contact`
    - `avg_tokens_per_session`

## Suggested Dashboard Cards

- Total leads
- Total free tokens consumed
- Leads at token limit
- Leads with full contact details
- Average tokens per session
