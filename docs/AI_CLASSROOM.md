# AI Classroom - AI Assistant Teacher

AI-powered lecture recording, transcription, and student doubt answering using OpenAI Whisper and GPT-4o with RAG (Retrieval Augmented Generation).

---

## 1. Data Model

### school.ai_lecture_sessions
- **id** (UUID, PK)
- **tenant_id** (UUID, FK, indexed) - Multi-tenant isolation
- **academic_year_id** (UUID, FK)
- **class_id** (UUID, FK)
- **section_id** (UUID, FK, nullable)
- **subject_id** (UUID, FK)
- **teacher_id** (UUID, FK, indexed) - Teacher ownership
- **title** (String 255)
- **transcript** (Text) - Full transcribed text
- **structured_notes** (JSONB, nullable) - Optional structured data
- **status** (String 20) - `IDLE` | `RECORDING` | `PAUSED` | `PROCESSING` | `COMPLETED`
- **recording_started_at** (DateTime timezone, nullable)
- **recording_paused_at** (DateTime timezone, nullable)
- **total_recording_seconds** (Integer, default 0)
- **is_active_recording** (Boolean, default False)
- **created_at** (DateTime timezone)

### school.ai_lecture_chunks
- **id** (UUID, PK)
- **tenant_id** (UUID, FK, indexed) - Multi-tenant isolation
- **lecture_id** (UUID, FK, indexed)
- **content** (Text) - Chunk of transcript
- **embedding** (Vector(1536)) - pgvector embedding for semantic search
- **created_at** (DateTime timezone)

### school.ai_doubt_chats
- **id** (UUID, PK)
- **tenant_id** (UUID, FK, indexed) - Multi-tenant isolation
- **student_id** (UUID, FK, indexed)
- **lecture_id** (UUID, FK, indexed)
- **created_at** (DateTime timezone)

### school.ai_doubt_messages
- **id** (UUID, PK)
- **chat_id** (UUID, FK, indexed)
- **role** (Text) - `STUDENT` | `AI`
- **message** (Text)
- **created_at** (DateTime timezone)

---

## 2. Permissions

Roles need `ai_classroom` permissions:

| Permission Key | Meaning |
|---------------|---------|
| `ai_classroom.create_lecture` | Start recording, upload audio files |
| `ai_classroom.update_lecture` | Pause, resume, stop recording |
| `ai_classroom.read` | View lectures, transcripts, chats |
| `ai_classroom.ask_doubt` | Ask questions about lectures (students) |

| Role | Capabilities |
|------|--------------|
| **Teacher** | Create lectures (upload or live record), pause/resume/stop, view all their lectures |
| **Student** | View available lectures, ask doubts, view chat history |
| **Admin** | Full access to all lectures |

---

## 3. API Endpoints

### Lecture Management (Upload-based)

#### Create Lecture from Audio File
```
POST /api/v1/ai-classroom/lectures
```
**Permission:** `ai_classroom.create_lecture`

**Query Parameters:**
- `academic_year_id` (UUID, required)
- `class_id` (UUID, required)
- `section_id` (UUID, optional)
- `subject_id` (UUID, required)
- `title` (String, required, 1-255 chars)

**Body:** Multipart form data
- `audio_file` (File, required) - Audio file (mp3, wav, etc.)

**Response:** `LectureResponse`
```json
{
  "id": "uuid",
  "tenant_id": "uuid",
  "academic_year_id": "uuid",
  "class_id": "uuid",
  "section_id": "uuid|null",
  "subject_id": "uuid",
  "teacher_id": "uuid",
  "title": "string",
  "transcript": "string",
  "structured_notes": {}|null,
  "created_at": "datetime"
}
```

**Flow:**
1. Validates teacher role and tenant
2. Transcribes audio using OpenAI Whisper
3. Chunks transcript into semantic pieces
4. Generates embeddings for each chunk
5. Stores chunks with embeddings in `ai_lecture_chunks`

---

### Live Recording Management

#### Start Recording
```
POST /api/v1/ai-classroom/recording/start
```
**Permission:** `ai_classroom.create_lecture`

**Request Body:**
```json
{
  "academic_year_id": "uuid",
  "class_id": "uuid",
  "section_id": "uuid|null",
  "subject_id": "uuid",
  "title": "string"
}
```

**Response:**
```json
{
  "session_id": "uuid",
  "status": "RECORDING"
}
```

**Flow:**
1. Validates teacher role and tenant
2. Validates class/section/subject belong to tenant
3. Creates `AILectureSession` with:
   - `status = RECORDING`
   - `is_active_recording = True`
   - `recording_started_at = now()`
   - `transcript = ""`

---

#### Pause Recording
```
POST /api/v1/ai-classroom/recording/pause/{session_id}
```
**Permission:** `ai_classroom.update_lecture`

**Response:**
```json
{
  "session_id": "uuid",
  "status": "PAUSED",
  "message": "Recording paused successfully"
}
```

**Flow:**
1. Validates teacher owns session
2. Ensures `status == RECORDING`
3. Updates:
   - `status = PAUSED`
   - `recording_paused_at = now()`
   - `is_active_recording = False`
   - Calculates and adds elapsed time to `total_recording_seconds`

---

#### Resume Recording
```
POST /api/v1/ai-classroom/recording/resume/{session_id}
```
**Permission:** `ai_classroom.update_lecture`

**Response:**
```json
{
  "session_id": "uuid",
  "status": "RECORDING",
  "message": "Recording resumed successfully"
}
```

**Flow:**
1. Validates teacher owns session
2. Ensures `status == PAUSED`
3. Updates:
   - `status = RECORDING`
   - `is_active_recording = True`
   - `recording_started_at = now()` (resets timer)
   - `recording_paused_at = null`

---

#### Stop Recording
```
POST /api/v1/ai-classroom/recording/stop/{session_id}
```
**Permission:** `ai_classroom.update_lecture`

**Response:** `LectureResponse` (same as create lecture)

**Flow:**
1. Validates teacher owns session
2. Ensures `status in (RECORDING, PAUSED)`
3. Updates `status = PROCESSING`
4. Calculates final `total_recording_seconds`
5. Takes full `transcript`
6. Chunks transcript into semantic pieces
7. Generates embeddings for each chunk
8. Stores chunks in `ai_lecture_chunks`
9. Updates `status = COMPLETED`
10. Sets `is_active_recording = False`

---

### WebSocket Audio Streaming

#### Stream Audio Chunks
```
WS /api/v1/ai-classroom/recording/stream/{session_id}?token={jwt_token}
```
**Authentication:** JWT token as query parameter

**Connection Flow:**
1. Client connects with JWT token
2. Server validates token and extracts user
3. Validates teacher owns session
4. Ensures `status == RECORDING`
5. Sends `{"status": "connected", "session_id": "uuid"}`

**Audio Streaming:**
- Client sends binary audio chunks via WebSocket
- **Audio Format:** Chunks must be in a format Whisper supports:
  - `webm` (recommended for browser MediaRecorder)
  - `mp3`
  - `wav`
  - `m4a`
  - `mp4`
  - `mpeg`
  - `mpga`
- Server receives bytes, transcribes using Whisper
- Server appends transcript to session
- Server sends confirmation: `{"status": "transcribed", "text": "..."}`

**Format Configuration:**
- Client can set format by sending: `{"type": "format", "format": "webm"}`
- Default format is `webm`
- Format must match the actual audio data format

**Browser Example:**
```javascript
const mediaRecorder = new MediaRecorder(stream, {
  mimeType: 'audio/webm'  // or 'audio/webm;codecs=opus'
});

mediaRecorder.ondataavailable = (event) => {
  if (event.data.size > 0) {
    websocket.send(event.data);  // Send as binary
  }
};
```

**Status Checks:**
- If `status != RECORDING`, rejects chunk and closes connection
- If paused, closes connection gracefully
- Chunks smaller than 100 bytes are skipped with a warning

**Ping/Pong:**
- Client can send `{"type": "ping"}` for keepalive
- Server responds `{"type": "pong"}`

**Close:**
- Client sends `{"type": "close"}` to disconnect gracefully
- Server closes on WebSocketDisconnect

**Error Handling:**
- Sends `{"error": "message"}` on errors
- Closes with code 1008 on authentication/authorization failures

---

### Lecture Retrieval

#### List Lectures
```
GET /api/v1/ai-classroom/lectures
```
**Permission:** `ai_classroom.read`

**Query Parameters:**
- `teacher_id` (UUID, optional) - Filter by teacher
- `class_id` (UUID, optional) - Filter by class
- `subject_id` (UUID, optional) - Filter by subject

**Response:** `List[LectureResponse]`

---

#### Get Lecture
```
GET /api/v1/ai-classroom/lectures/{lecture_id}
```
**Permission:** `ai_classroom.read`

**Response:** `LectureResponse`

---

### Student Doubts (RAG-based Q&A)

#### Ask Doubt
```
POST /api/v1/ai-classroom/doubts
```
**Permission:** `ai_classroom.ask_doubt`

**Request Body:**
```json
{
  "lecture_id": "uuid",
  "question": "string"
}
```

**Response:**
```json
{
  "chat_id": "uuid",
  "answer": "string",
  "message": {
    "id": "uuid",
    "chat_id": "uuid",
    "role": "AI",
    "message": "string",
    "created_at": "datetime"
  }
}
```

**Flow (RAG):**
1. Validates student role and tenant
2. Validates lecture exists and belongs to tenant
3. Generates embedding for question using `text-embedding-3-small`
4. Queries `ai_lecture_chunks` using pgvector:
   ```sql
   SELECT content
   FROM school.ai_lecture_chunks
   WHERE tenant_id = :tenant_id
   AND lecture_id = :lecture_id
   ORDER BY embedding <-> :question_embedding::vector
   LIMIT 5
   ```
5. Constructs prompt with:
   - System: "You are an assistant teacher. Answer only from provided context. If not found, say politely that it was not discussed."
   - User: Context chunks + student question
6. Sends to GPT-4o
7. Saves chat history (student message + AI response)
8. Returns AI answer

---

#### Get Doubt Chat
```
GET /api/v1/ai-classroom/doubts/{chat_id}
```
**Permission:** `ai_classroom.read`

**Response:**
```json
{
  "id": "uuid",
  "tenant_id": "uuid",
  "student_id": "uuid",
  "lecture_id": "uuid",
  "created_at": "datetime",
  "messages": [
    {
      "id": "uuid",
      "chat_id": "uuid",
      "role": "STUDENT|AI",
      "message": "string",
      "created_at": "datetime"
    }
  ]
}
```

**Note:** Students can only view their own chats.

---

#### List Doubt Chats
```
GET /api/v1/ai-classroom/doubts
```
**Permission:** `ai_classroom.read`

**Query Parameters:**
- `lecture_id` (UUID, optional) - Filter by lecture

**Response:** `List[DoubtChatResponse]`

**Note:** Students only see their own chats. Admins/teachers see all.

---

## 4. Rules & Constraints

### Recording Rules
- Only teachers (or admins) can start/pause/resume/stop recordings
- Teacher must own the session to control it
- Can only pause when `status == RECORDING`
- Can only resume when `status == PAUSED`
- Can only stop when `status in (RECORDING, PAUSED)`
- WebSocket streaming only works when `status == RECORDING`
- Transcript is accumulated in real-time during recording
- Embeddings are generated only after stopping (during PROCESSING phase)

### Lecture Access
- All queries filter by `tenant_id` - strict tenant isolation
- Teachers can only see their own lectures (unless admin)
- Students can see all lectures in their tenant (for asking doubts)
- Cross-tenant access is blocked

### Doubt/Chat Rules
- Only students can ask doubts (or admins for testing)
- Each lecture can have multiple doubt chats per student
- Chat history is preserved
- RAG search is scoped to the specific lecture only
- AI answers are based solely on lecture content (no external knowledge)
- If question not found in lecture, AI politely says it wasn't discussed

### Embedding & Vector Search
- Embeddings use `text-embedding-3-small` (1536 dimensions)
- Chunks are ~500 characters with 50 character overlap
- Vector search uses pgvector `<->` operator (L2 distance)
- Top 5 most relevant chunks are used for context
- All vector queries include `tenant_id` filter

### Audio Processing
- **File Upload:** Supports common audio formats (mp3, wav, webm, m4a, mp4, mpeg, mpga)
- **WebSocket Streaming:** Client must send audio in a supported format
  - Browser: Use `MediaRecorder` with `mimeType: 'audio/webm'`
  - Native apps: Send audio in mp3, wav, or webm format
- **Format Requirements:** Raw PCM or unsupported formats will fail
- Whisper API handles format conversion for supported formats
- Real-time transcription via WebSocket chunks (minimum 100 bytes per chunk)
- File-based transcription for uploaded audio

---

## 5. Workflow Examples

### Workflow 1: Upload Audio File
1. Teacher uploads audio file via `POST /lectures`
2. System transcribes entire file
3. System chunks transcript
4. System generates embeddings
5. System stores everything
6. Lecture is immediately available for student doubts

### Workflow 2: Live Recording
1. Teacher calls `POST /recording/start`
2. Teacher connects WebSocket to `/recording/stream/{session_id}`
3. Teacher streams audio chunks
4. System transcribes each chunk in real-time
5. Transcript is appended to session
6. Teacher can pause/resume as needed
7. Teacher calls `POST /recording/stop/{session_id}`
8. System processes transcript (chunk + embed)
9. Lecture is available for student doubts

### Workflow 3: Student Asking Doubt
1. Student views available lectures
2. Student asks question via `POST /doubts`
3. System finds relevant lecture chunks
4. System generates answer using GPT-4o with RAG
5. System saves chat history
6. Student can continue conversation in same chat

---

## 6. Technical Details

### Dependencies
- **OpenAI SDK** - Whisper transcription, embeddings, GPT-4o
- **pgvector** - Vector similarity search
- **FastAPI WebSocket** - Real-time audio streaming
- **SQLAlchemy 2.0 async** - Database operations

### Database Extensions
- `vector` extension must be enabled in PostgreSQL
- Run migration: `python -m app.db.migrations.002_enable_pgvector`

### Environment Variables
- `OPENAI_API_KEY` - Required for all AI operations

### Performance Considerations
- WebSocket connections are per-session (one teacher per session)
- Embedding generation is async and non-blocking
- Vector search is optimized with indexes on `tenant_id` and `lecture_id`
- Transcript chunking happens in-memory (fast)

### Error Handling
- All OpenAI API errors are caught and returned as HTTP 500
- Invalid session states return HTTP 400
- Unauthorized access returns HTTP 403
- Missing resources return HTTP 404
- WebSocket errors are sent as JSON messages before closing

---

## 7. Security

### Tenant Isolation
- Every query includes `tenant_id` filter
- No cross-tenant data access possible
- Vector search is scoped by tenant

### Authentication
- REST APIs use JWT Bearer tokens
- WebSocket uses JWT token as query parameter
- All endpoints require valid authentication

### Authorization
- Teacher ownership validation on all recording operations
- Student-only validation on doubt operations
- RBAC permissions enforced via dependencies

### Data Privacy
- Transcripts are stored per-tenant
- Embeddings are tenant-scoped
- Chat history is isolated by tenant
- No data leakage between tenants

