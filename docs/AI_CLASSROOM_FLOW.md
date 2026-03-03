# AI Classroom – Detailed Flow

This document explains how the AI Classroom feature works end-to-end: **lecture creation** (upload or live recording), **transcription & embeddings**, and **RAG-based doubt answering**.

---

## 1. Overview

AI Classroom does three things:

1. **Ingest lectures** – Either upload an audio file (one-shot) or record live via WebSocket and then process.
2. **Make lectures searchable** – Transcribe audio with **Whisper**, split transcript into chunks, and store **embeddings** (OpenAI `text-embedding-3-small`) in **pgvector** for similarity search.
3. **Answer doubts** – Student (or admin) asks a question; system finds **relevant chunks** by vector similarity, then **GPT-4o** answers using only that context (RAG).

**Actors:**

- **Teacher / Admin** – Creates lectures (upload or start recording), can edit transcript.
- **Student / Admin** – Asks doubts; sees own (or all) doubt chats.
- **Backend** – OpenAI (Whisper, embeddings, chat), PostgreSQL + pgvector, in-memory audio buffer for live recording.

---

## 2. Data Model (high level)

| Table | Purpose |
|-------|--------|
| `school.ai_lecture_sessions` | One row per lecture: metadata (class, subject, teacher, title), full `transcript`, status (IDLE, RECORDING, PAUSED, PROCESSING, COMPLETED), recording timestamps. |
| `school.ai_lecture_chunks` | Chunks of that transcript + 1536-dim **embedding** vector for similarity search. |
| `school.ai_doubt_chats` | One chat per (student, lecture): links student + lecture. |
| `school.ai_doubt_messages` | Messages in a doubt chat: role STUDENT or AI, message text. |

**Flow:** Lecture → many Chunks. Lecture → many DoubtChats. DoubtChat → many DoubtMessages.

---

## 3. Flow A – Create Lecture from Uploaded Audio

**Use case:** Teacher has a pre-recorded audio file and wants to create a lecture in one step.

**Endpoint:** `POST /api/v1/ai-classroom/lectures`  
**Permission:** `ai_classroom.create_lecture`  
**Request:** Query params: `academic_year_id`, `class_id`, `section_id?`, `subject_id`, `title`. Body: multipart with `audio_file`.

**Step-by-step:**

1. **Auth & validation**
   - Resolve current user; require teacher or admin.
   - Load and validate (tenant-scoped): AcademicYear, SchoolClass, optional Section, SchoolSubject.

2. **Transcription**
   - Read uploaded file into memory → `io.BytesIO`, set `.name` from filename or content-type (so Whisper knows format).
   - Call **OpenAI Whisper** (`client.audio.transcriptions.create`, model `whisper-1`, `response_format="text"`).
   - Result is the full **transcript** string.

3. **Save lecture**
   - Insert `AILectureSession`: tenant, academic_year_id, class_id, section_id, subject_id, teacher_id, title, **transcript**. Status is effectively “completed” (no recording fields used).

4. **Chunking**
   - `chunk_text(transcript, chunk_size=500, overlap=50)`:
     - Splits transcript into ~500-character segments with 50-char overlap.
     - Prefers breaking at `.` or `\n` near 70% of chunk size so sentences stay intact.

5. **Embeddings & chunks**
   - For each chunk:
     - Call **OpenAI embeddings** (`text-embedding-3-small`) → 1536-dim vector.
     - Insert `AILectureChunk`: tenant_id, lecture_id, **content**, **embedding**.

6. **Response**
   - Commit; return lecture with class/subject/section names attached for the API response.

**Outcome:** One lecture with full transcript and N chunks (with vectors) in DB. Ready for “Ask doubt” (RAG).

---

## 4. Flow B – Live Recording (Start → Stream → Pause/Resume → Stop)

**Use case:** Teacher records a live lecture in the browser; audio is streamed over WebSocket, then processed when they stop.

### 4.1 Start recording

**Endpoint:** `POST /api/v1/ai-classroom/recording/start`  
**Permission:** `ai_classroom.create_lecture`  
**Request body:** `academic_year_id`, `class_id`, `section_id?`, `subject_id`, `title`.

**Steps:**

1. Validate teacher/admin and tenant; validate academic year, class, optional section, subject.
2. Insert `AILectureSession` with:
   - `transcript = ""`
   - `status = "RECORDING"`
   - `recording_started_at = now`, `is_active_recording = True`, `audio_buffer_size_bytes = 0`.
3. **Initialize in-memory buffer** for this session: `buffer_manager.initialize(session.id)` (creates empty bytearray keyed by session ID).
4. Return session (e.g. `session_id`) to the client.

**Outcome:** Session exists in DB and a buffer exists in memory for that `session_id`. Client can open the WebSocket and send audio.

---

### 4.2 Stream audio (WebSocket)

**Endpoint:** `WebSocket /api/v1/ai-classroom/recording/stream/{session_id}?token=...`

**Steps:**

1. Client connects with JWT in query (`token`). Server accepts connection.
2. **Auth:** Decode JWT, load user; ensure session exists and is owned by this teacher and `status == "RECORDING"`. If not, send error JSON and close.
3. Ensure buffer for this `session_id` is initialized (idempotent).
4. Send JSON: `{ "status": "connected", "session_id": "...", "message": "Send audio chunks as binary data..." }`.
5. **Loop:** Receive WebSocket messages.
   - If the message contains **binary data** (`bytes`):
     - Ignore chunks smaller than 1 KB.
     - Re-validate session (still RECORDING, same teacher).
     - **Append bytes to buffer:** `buffer_manager.append_chunk(session_id, audio_bytes)`.
     - If total buffer size &gt; 200 MB: set session to PROCESSING, clear buffer, send error, break.
     - Update `session.audio_buffer_size_bytes` in DB and commit.
     - Send JSON: `{ "status": "chunk_received", "size": current_size }`.
   - On disconnect or error, break and close.

**Outcome:** All streamed audio for this session lives in the in-memory buffer (and DB only stores the current size). No transcription yet.

---

### 4.3 Pause / Resume (optional)

- **Pause** – `POST /api/v1/ai-classroom/recording/pause/{session_id}`  
  - Session must be RECORDING, owned by teacher.  
  - Add elapsed time to `total_recording_seconds`; read `buffer_manager.get_size(session_id)` into `audio_buffer_size_bytes`; set `status = "PAUSED"`, `is_active_recording = False`, `recording_paused_at = now`.  
  - Buffer is **not** cleared; recording can resume later.

- **Resume** – `POST /api/v1/ai-classroom/recording/resume/{session_id}`  
  - Session must be PAUSED, owned by teacher.  
  - Set `status = "RECORDING"`, `recording_started_at = now`, clear `recording_paused_at`, `is_active_recording = True`.  
  - Client can send more audio on the same WebSocket (or reconnect) and chunks keep appending.

---

### 4.4 Stop recording and process

**Endpoint:** `POST /api/v1/ai-classroom/recording/stop/{session_id}`  
**Permission:** `ai_classroom.update_lecture`

**Steps:**

1. Validate session (tenant, owner, status RECORDING or PAUSED). Set `status = "PROCESSING"`, `is_active_recording = False`; update `total_recording_seconds` from last segment.
2. **Read full buffer:** `audio_bytes = buffer_manager.get_buffer(session_id)`.
3. **If no audio:** Set status COMPLETED, clear buffer, return (no transcript/chunks).
4. **Transcribe:**
   - Wrap `audio_bytes` in `io.BytesIO`, set `.name = "lecture.webm"`.
   - Call **Whisper** (same as Flow A). Set `session.transcript = transcript`.
5. **Clear buffer:** `buffer_manager.clear(session_id)` (free memory, remove session from buffer map).
6. **Chunk + embed:**
   - `chunk_text(transcript)` → list of text chunks.
   - For each chunk: OpenAI embedding → insert `AILectureChunk` (lecture_id, content, embedding).
7. Set `status = "COMPLETED"`, commit, return lecture (with class/subject/section names).

**Outcome:** Same as Flow A: lecture has transcript and vectorized chunks; students can ask doubts.

---

## 5. Flow C – Ask Doubt (RAG)

**Use case:** Student (or admin) asks a question about a lecture; system answers using only that lecture’s content.

**Endpoint:** `POST /api/v1/ai-classroom/doubts`  
**Permission:** `ai_classroom.ask_doubt`  
**Request body:** `{ "lecture_id": "uuid", "question": "..." }`.

**Step-by-step:**

1. **Auth & validation**
   - Resolve user; must be student **or** SUPER_ADMIN / PLATFORM_ADMIN / ADMIN.
   - Load lecture; must exist and belong to tenant.

2. **Embed the question**
   - `generate_embedding(payload.question)` → same model `text-embedding-3-small`, 1536-dim vector.

3. **Vector search**
   - Raw SQL on `school.ai_lecture_chunks`:
     - `WHERE tenant_id = :tenant_id AND lecture_id = :lecture_id`
     - `ORDER BY embedding <-> :question_embedding::vector` (pgvector L2 distance)
     - `LIMIT 5`
   - Collect **content** of these 5 chunks → `context` (concatenated text).

4. **Generate answer**
   - **GPT-4o** with:
     - **System:** “Answer only from the provided context. If not in context, say it wasn’t discussed.”
     - **User:** “Context from lecture: … Student question: &lt;question&gt;”
   - Response → `ai_answer` (string).

5. **Persist chat**
   - Find or create `AIDoubtChat` for (tenant, student_id, lecture_id).
   - Insert two `AIDoubtMessage` rows: role STUDENT (question), role AI (ai_answer).
   - Commit.

6. **Response**
   - Return `chat_id`, `answer` (ai_answer), and the AI message object.

**Outcome:** Doubt is answered from lecture content only; conversation is stored for GET doubt chat / list doubt chats.

---

## 6. Supporting Flows

- **List lectures** – `GET /api/v1/ai-classroom/lectures` (optional filters: teacher_id, class_id, subject_id). Returns lectures with class/subject/section names.
- **Get lecture** – `GET /api/v1/ai-classroom/lectures/{lecture_id}`. Single lecture, same shape.
- **Update transcript** – `PATCH /api/v1/ai-classroom/lectures/{lecture_id}/transcript`. Teacher only; lecture must be COMPLETED. Deletes all chunks for that lecture, updates transcript, re-chunks and re-embeds (same chunk_text + embedding flow).
- **List doubt chats** – `GET /api/v1/ai-classroom/doubts?lecture_id=...`. Students see only their chats; admins see all (student_id not passed).
- **Get doubt chat** – `GET /api/v1/ai-classroom/doubts/{chat_id}`. Students only their own; admins any chat in tenant.

---

## 7. Flow Diagrams (summary)

**Create lecture (upload):**

```
Client → POST /lectures (audio file + metadata)
  → Validate teacher, academic year, class, section, subject
  → Whisper (transcript)
  → Insert AILectureSession
  → chunk_text(transcript)
  → For each chunk: embedding → Insert AILectureChunk
  → Return lecture
```

**Live recording:**

```
Client → POST /recording/start (metadata)
  → Insert AILectureSession (RECORDING), buffer_manager.initialize(session_id)
  → Client opens WebSocket /recording/stream/{session_id}?token=...
  → Client sends binary audio → buffer_manager.append_chunk(session_id, bytes)
  → [Optional] POST /recording/pause, POST /recording/resume
  → POST /recording/stop/{session_id}
  → buffer_manager.get_buffer(session_id) → Whisper → transcript
  → buffer_manager.clear(session_id)
  → chunk_text + embeddings → AILectureChunk rows, status COMPLETED
```

**Ask doubt (RAG):**

```
Client → POST /doubts { lecture_id, question }
  → Validate user (student or admin), lecture
  → embedding(question)
  → SQL: chunks ORDER BY embedding <-> question_embedding LIMIT 5 → context
  → GPT-4o(system + context + question) → ai_answer
  → Upsert AIDoubtChat, insert STUDENT + AI messages
  → Return chat_id, answer, message
```

---

## 8. Important details

- **Audio buffer** – In-memory only (singleton `AudioBufferManager`). Not persisted; if the process restarts during recording, buffer is lost. Stop recording before restarting.
- **Whisper** – Expects a file-like object with a name hint (e.g. `.webm`, `.mp3`). Upload flow uses client filename or content-type; stop flow uses `lecture.webm`.
- **Chunking** – 500 chars, 50 overlap, break near sentence boundaries. Same for upload and stop-recording.
- **Embeddings** – Always `text-embedding-3-small` (1536 dimensions). Stored in pgvector; search uses `<->` (L2 distance).
- **RAG** – Only the top 5 closest chunks are sent to GPT-4o; answer is restricted to that context.
- **Permissions** – Create/update lecture and recording require teacher or admin; ask_doubt requires student or admin; read can be broader (e.g. admin sees all doubt chats).

This is the full AI Classroom flow as implemented in the codebase.
