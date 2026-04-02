# AI Classroom – Detailed Flow

This document describes how the AI Classroom feature works end-to-end in **this codebase**: **lecture creation** (upload or live recording), **transcription & embeddings**, **RAG-based doubt answering**, and **related APIs** (streaming doubts, management chat, delete).

---

## 1. Overview

AI Classroom does three core things:

1. **Ingest lectures** – Upload an audio file (`POST /lectures`) or record live (`POST /recording/start` → WebSocket stream → `POST /recording/stop`).
2. **Make lectures searchable** – Transcribe with **Whisper**, split into chunks (`chunk_text`), store **embeddings** (OpenAI `text-embedding-3-small`, 1536-dim) in **pgvector** (`school.ai_lecture_chunks`).
3. **Answer doubts** – Embed the question, retrieve top similar chunks, then call a **chat model** with context-only instructions (RAG). The simple JSON endpoint uses **`gpt-4o-mini`** (see `MODEL_BASIC` in `service.py`), not `gpt-4o`.

**Actors:**

- **Teacher / Admin** – Create lectures, pause/resume/stop recording, edit transcript (when allowed), delete own lecture (admin can delete more broadly per service rules).
- **Student / Admin** – Ask doubts; list/get chats (students scoped to self).
- **Backend** – OpenAI (Whisper, embeddings, chat), PostgreSQL + pgvector, `AudioBufferManager` + optional **realtime pipeline** for live recording.

---

## 2. Data model (high level)

| Table | Purpose |
|-------|--------|
| `school.ai_lecture_sessions` | One row per lecture/session: metadata (tenant, academic year, class, optional section, subject, teacher, title), `transcript`, optional `structured_notes` (JSONB), **status** and recording/upload fields (see below). |
| `school.ai_lecture_chunks` | Text chunks + **embedding** vector for similarity search. |
| `school.ai_doubt_chats` | One row per (tenant, student, lecture) conversation. |
| `school.ai_doubt_messages` | Messages: roles such as `STUDENT` and `AI`. |

### `AILectureSession` – fields the API often exposes

Besides ids and metadata, responses can include:

- `transcript`, `structured_notes`, `status`
- Recording: `recording_started_at`, `recording_paused_at`, `total_recording_seconds`, `is_active_recording`, `audio_buffer_size_bytes`
- Upload/processing: `upload_completed`, `audio_file_path`, `processing_stage`, `last_chunk_received_at`, `upload_progress_percent`

### Status values (as used in code)

The ORM default is `IDLE`. The app also uses (non-exhaustive, see `ai_lecture_session` model + service):

- **`IDLE`** – Default; upload path after create does not always set status explicitly (see Flow A).
- **`RECORDING`**, **`PAUSED`** – Live recording.
- **`STOPPING`** – Set by `POST /recording/stop`; WebSocket finalizes audio and processing.
- **`UPLOADING`** – Used in some flows when aligning with upload/processing UX.
- **`PROCESSING`** – Transcription / chunking / embedding in progress.
- **`COMPLETED`** – Ready for RAG and transcript edit rules.
- **`FAILED`** – Processing error (e.g. missing audio file in fallback path).

**Flow:** Lecture → many Chunks. Lecture → many DoubtChats. DoubtChat → many DoubtMessages.

---

## 3. Flow A – Create lecture from uploaded audio

**Use case:** Teacher uploads a pre-recorded audio file in one request.

| Item | Value |
|------|--------|
| **Endpoint** | `POST /api/v1/ai-classroom/lectures` |
| **Permission** | `ai_classroom.create_lecture` |
| **Request** | Query: `academic_year_id`, `class_id`, `section_id?`, `subject_id`, `title`. Body: multipart `audio_file`. |

**Steps:**

1. **Auth & validation** – Tenant-scoped `AcademicYear`, `SchoolClass`, optional `Section`, `SchoolSubject`; teacher/employee or elevated admin role.
2. **Transcription** – `transcribe_audio` → Whisper (`whisper-1`, text response).
3. **Save lecture** – Insert `AILectureSession` with transcript populated. **Status is not set in code**; it remains the model default (**`IDLE`**) unless changed elsewhere. RAG still works because transcript + chunks exist.
4. **Chunking** – `chunk_text(text, chunk_size=500, overlap=50)` (sentence-aware breaks near ~70% of chunk size).
5. **Embeddings** – `generate_embeddings_batch(chunks)` then insert one `AILectureChunk` per chunk (batch API, not necessarily one HTTP per chunk).
6. **Response** – Lecture with `class_name`, `subject_name`, `section_name` attached for display.

**Outcome:** Transcript + vectorized chunks in DB; ready for doubt RAG.

---

## 4. Flow B – Live recording (start → stream → pause/resume → stop)

**Use case:** Teacher records in the browser; audio streams over WebSocket; processing is coordinated with **`POST /recording/stop`** and the WebSocket lifecycle.

### 4.1 Start recording

| Item | Value |
|------|--------|
| **Endpoint** | `POST /api/v1/ai-classroom/recording/start` |
| **Permission** | `ai_classroom.create_lecture` |
| **Body** | `RecordingStartRequest`: `academic_year_id`, `class_id`, `section_id?`, `subject_id`, `title` |

Creates `AILectureSession` with `status="RECORDING"`, empty transcript, recording timestamps, `buffer_manager.initialize(session_id, …)` (defaults overridden by WebSocket handler).

Returns `{ session_id, status }`.

### 4.2 Stream audio (WebSocket)

| Item | Value |
|------|--------|
| **Endpoint** | `WebSocket /api/v1/ai-classroom/recording/stream/{session_id}?token=<JWT>` |

**Auth:** JWT in query (`token`); user must own the session.

**Session states allowed for streaming:** `RECORDING`, `PAUSED`, or `STOPPING` (see handler checks).

**On connect:** JSON greeting including `real_time_enabled` from settings (`ai_realtime_enabled`).

**Two modes:**

1. **Realtime enabled (`settings.ai_realtime_enabled`)**  
   - `RealtimeConfig` + `realtime_pipeline`: chunked Whisper, embeddings, and queue workers while streaming.  
   - Binary frames appended via `buffer_manager`; adaptive chunk sizing; periodic `buffer_health` and `processing_status` events.  
   - Oversized frames may be dropped (`max_frame_bytes`).

2. **Fallback (realtime off)**  
   - Audio buffered and/or written to a temp file under `/tmp` (e.g. `lecture_{session_id}.webm`) in ~5 MB flushes.  
   - On close, session moves toward `PROCESSING` and `asyncio.create_task(service.process_lecture_background(session_id))` runs chunked transcription + batch embeddings.

**Control messages:**

- Optional **text** JSON: `{ "type": "end_of_stream" }` or `{ "type": "stop_stream" }` to signal end of upload before socket close.
- Receive loop uses a **timeout** so if the client stops sending after `POST /recording/stop` (status `STOPPING`), the server can finalize without hanging forever.

**Note:** The doc no longer lists legacy “ignore &lt; 1 KB” or “200 MB hard cap” rules; current behavior is frame limits, buffer health, and configured max buffer sizes (`RealtimeConfig` / `buffer_manager`).

### 4.3 Pause / Resume

| Endpoint | Permission |
|----------|------------|
| `POST /api/v1/ai-classroom/recording/pause/{session_id}` | `ai_classroom.update_lecture` |
| `POST /api/v1/ai-classroom/recording/resume/{session_id}` | `ai_classroom.update_lecture` |

Behavior matches service: pause only from `RECORDING`, resume only from `PAUSED`, ownership checks, timer updates for `total_recording_seconds`, buffer size persisted where applicable.

### 4.4 Stop recording

| Item | Value |
|------|--------|
| **Endpoint** | `POST /api/v1/ai-classroom/recording/stop/{session_id}` |
| **Permission** | `ai_classroom.update_lecture` |

**Important:** This does **not** immediately run Whisper on the full buffer in the request handler. It:

1. Validates tenant + ownership.
2. Is **idempotent** if status is already `STOPPING`, `PROCESSING`, `COMPLETED`, or `FAILED`.
3. Otherwise requires `RECORDING` or `PAUSED`, updates `total_recording_seconds`, sets `is_active_recording = False`, **`status = "STOPPING"`**, commits.

The **WebSocket** handler then finalizes: realtime pipeline drain or fallback file + `process_lecture_background`, transitions to **`PROCESSING`** → **`COMPLETED`** (or **`FAILED`**), updates `processing_stage`, `upload_progress_percent`, etc.

**Response:** `StopRecordingResponse` – message indicates processing is continuing (e.g. background / WebSocket finalize); exact strings may differ from older docs.

**Outcome:** Same end state as Flow A when successful: transcript + `AILectureChunk` rows for RAG.

---

## 5. Flow C – Ask doubt (RAG – JSON)

**Use case:** Simple request/response doubt for one lecture.

| Item | Value |
|------|--------|
| **Endpoint** | `POST /api/v1/ai-classroom/doubts` |
| **Permission** | `ai_classroom.ask_doubt` |
| **Body** | `{ "lecture_id": "uuid", "question": "..." }` |

**Steps:**

1. User must be **student** or **SUPER_ADMIN / PLATFORM_ADMIN / ADMIN** (see `ask_doubt` checks).
2. `generate_embedding(question)` with `text-embedding-3-small`.
3. SQL on `school.ai_lecture_chunks`: `ORDER BY embedding <-> (:question_embedding)::vector LIMIT 5`.
4. Chat completion with **`MODEL_BASIC` (`gpt-4o-mini`)**, system prompt restricting answers to provided context.
5. Find or create `AIDoubtChat`; insert `STUDENT` and `AI` messages.
6. Return `DoubtAskResponse`: `chat_id`, `answer`, `message`.

---

## 6. Streaming doubt APIs (SSE)

These return **Server-Sent Events** (`text/event-stream`), not JSON bodies. Typical events: `chunk` (content deltas), `done` (with ids), or `error`.

| Endpoint | Purpose |
|----------|--------|
| `POST /api/v1/ai-classroom/doubt/student` | Student streaming doubt; body `StudentDoubtRequest` (lecture_id, subject_name, topic_name, message, optional `chat_id`, tier-related fields). **Depends:** `get_current_user` only (no `check_permission` in router). |
| `POST /api/v1/ai-classroom/doubt/admin` | Admin streaming doubt; body `AdminDoubtRequest` includes `tier`: `BASIC` \| `PRO` \| `ULTRA`. Uses different model tiers (`MODEL_BASIC`, `MODEL_PRO`, `MODEL_ULTRA`) in service. |

Implementation details (prompts, Ultra session stages, etc.) live in `service.py` (`ask_doubt_student_stream`, `ask_doubt_admin_stream`).

---

## 7. Management chat (SSE)

| Item | Value |
|------|--------|
| **Endpoint** | `POST /api/v1/ai-classroom/management/chat` |
| **Body** | `{ "message": "..." }` – tenant scope comes **only** from JWT (`CurrentUser`), not from body. |
| **Behavior** | Streams answer chunks; uses **`management_knowledge_chunks`** (vector store) and role-based access checks in `management_chat_stream`. Model: `MODEL_MGMT` (`gpt-4o-mini`). |

This is **not** lecture RAG; it is organization/management Q&A.

---

## 8. Other REST endpoints

| Method | Path | Notes |
|--------|------|--------|
| `GET` | `/api/v1/ai-classroom/lectures` | Optional filters: `teacher_id`, `class_id`, `subject_id`. Permission: `ai_classroom.read`. |
| `GET` | `/api/v1/ai-classroom/lectures/{lecture_id}` | Single lecture. |
| `DELETE` | `/api/v1/ai-classroom/lectures/{lecture_id}` | Permanent delete; permission `ai_classroom.delete_lecture`. Teacher owns lecture; admins (`SUPER_ADMIN` / `PLATFORM_ADMIN` / `ADMIN`) per `delete_lecture` logic. |
| `PATCH` | `/api/v1/ai-classroom/lectures/{lecture_id}/transcript` | Permission: `ai_classroom.update_lecture`. **Requires `status == COMPLETED`**. Deletes all chunks, replaces transcript, re-chunks + batch re-embeds. |
| `GET` | `/api/v1/ai-classroom/doubts` | Optional `lecture_id`. Students: only their chats; admins: all in tenant. |
| `GET` | `/api/v1/ai-classroom/doubts/{chat_id}` | Same scoping as list. |

---

## 9. Flow diagrams (summary)

**Upload lecture:**

```
POST /lectures (multipart audio + query metadata)
  → transcribe (Whisper)
  → insert AILectureSession (transcript set; status default IDLE)
  → chunk_text → generate_embeddings_batch → insert AILectureChunk rows
  → return lecture (+ names)
```

**Live recording (simplified):**

```
POST /recording/start → RECORDING + buffer init
WebSocket /recording/stream/{session_id}?token=...
  → realtime path OR fallback file + background task
POST /recording/stop/{session_id} → STOPPING (+ idempotent rules)
WebSocket finalize → PROCESSING → COMPLETED (or FAILED)
```

**JSON doubt (RAG):**

```
POST /doubts { lecture_id, question }
  → embed question → top-5 chunks (<->) → gpt-4o-mini + context
  → persist chat + messages → JSON response
```

---

## 10. Important details

- **Chunking** – `chunk_text`: 500 chars, 50 overlap; sentence-friendly breaks.
- **Embeddings** – `text-embedding-3-small`, 1536 dimensions; pgvector distance operator `<->`.
- **RAG JSON endpoint** – Top **5** chunks; chat model **`gpt-4o-mini`** for `POST /doubts` (not `gpt-4o`).
- **Transcript edit** – Only when lecture **`status == COMPLETED`**.
- **Audio / buffer** – Buffers are process-local; restart loses in-flight recording. Realtime and fallback paths differ; see `audio_buffer_manager.py`, `realtime_pipeline.py`, WebSocket handler in `router.py`.
- **Permissions** – Most routes use `check_permission("ai_classroom", "<action>")`; streaming student/admin doubt routes currently depend on `get_current_user` only—align frontend with your security expectations.

This document matches the implementation in `app/api/v1/ai_classroom/` at the time of writing.

---

## 11. Board Image Annotation — Frontend Integration Guide

This section covers every frontend change required to support the **board image upload + visual doubt answering** feature added to the backend.

---

### 11.1 New API types

Add these TypeScript types wherever you keep your API response models.

```ts
// A single bounding-box region on a board image
export interface ImageRegion {
  id: string;           // UUID
  label: string;        // e.g. "shaft", "bearing", "gear"
  x: number;            // 0.0–1.0, left edge as fraction of image width
  y: number;            // 0.0–1.0, top edge as fraction of image height
  w: number;            // 0.0–1.0, width fraction
  h: number;            // 0.0–1.0, height fraction
  color_hex: string;    // e.g. "#EF9F27"
  description: string | null;
}

// A board image with its regions
export interface LectureImage {
  id: string;
  lecture_id: string;
  chunk_id: string | null;
  image_url: string;
  sequence_order: number;
  topic_label: string | null;
  regions: ImageRegion[];
  created_at: string;   // ISO datetime
}

// Extend the existing DoubtAskResponse type — add these three optional fields
export interface DoubtAskResponse {
  chat_id: string;
  answer: string;
  message: DoubtMessage;
  // NEW — all three are null when no board image is linked to this lecture
  image_url: string | null;
  highlight_region: ImageRegion | null;
  all_regions: ImageRegion[] | null;
}

// Streaming SSE event type — add alongside existing "chunk" and "done"
export interface ImageAnnotationEvent {
  type: "image_annotation";
  image_url: string;
  highlight_region: ImageRegion | null;
  all_regions: ImageRegion[];
}
```

---

### 11.2 New API calls

Add these functions in your API layer (next to existing ai-classroom calls).

#### Upload a board image
```ts
// POST /api/v1/ai-classroom/lectures/{lectureId}/images
// Content-Type: multipart/form-data
// Auth: requires ai_classroom.update_lecture permission (teacher role)

async function uploadLectureImage(
  lectureId: string,
  imageFile: File,
  options?: {
    topicLabel?: string;    // query param: topic_label
    chunkId?: string;       // query param: chunk_id
    sequenceOrder?: number; // query param: sequence_order (default 0)
  }
): Promise<LectureImage>

// Example:
const formData = new FormData();
formData.append("image_file", file);

const url = new URL(`/api/v1/ai-classroom/lectures/${lectureId}/images`, BASE_URL);
if (options?.topicLabel) url.searchParams.set("topic_label", options.topicLabel);
if (options?.chunkId)    url.searchParams.set("chunk_id", options.chunkId);
url.searchParams.set("sequence_order", String(options?.sequenceOrder ?? 0));

const res = await fetch(url.toString(), {
  method: "POST",
  headers: { Authorization: `Bearer ${token}` },
  body: formData,
});
// Returns LectureImage with regions already populated by GPT-4o.
// This call may take 3–8 seconds — show a loading state.
```

#### List board images for a lecture
```ts
// GET /api/v1/ai-classroom/lectures/{lectureId}/images
// Auth: ai_classroom.read (teachers + students)

async function listLectureImages(lectureId: string): Promise<LectureImage[]>
```

#### Get a single board image
```ts
// GET /api/v1/ai-classroom/lectures/{lectureId}/images/{imageId}
// Auth: ai_classroom.read

async function getLectureImage(lectureId: string, imageId: string): Promise<LectureImage>
```

#### Delete a board image
```ts
// DELETE /api/v1/ai-classroom/lectures/{lectureId}/images/{imageId}
// Auth: ai_classroom.delete_lecture (teacher who owns lecture, or admin)
// Returns 204 No Content

async function deleteLectureImage(lectureId: string, imageId: string): Promise<void>
```

---

### 11.3 Updated: POST /doubts response

The `POST /api/v1/ai-classroom/doubts` endpoint now returns three additional optional fields.

**Before:**
```json
{
  "chat_id": "...",
  "answer": "The shaft connects...",
  "message": { ... }
}
```

**After:**
```json
{
  "chat_id": "...",
  "answer": "The shaft connects...",
  "message": { ... },
  "image_url": "/tmp/board_xyz.jpg",
  "highlight_region": {
    "id": "...",
    "label": "shaft",
    "x": 0.1, "y": 0.1, "w": 0.3, "h": 0.2,
    "color_hex": "#EF9F27",
    "description": "Rotating shaft component"
  },
  "all_regions": [ ... ]
}
```

All three new fields are `null` when no board image is linked to the lecture. **Your existing doubt UI will not break** — just add a conditional block after the answer text.

---

### 11.4 Updated: SSE streaming doubt events

Both `POST /doubt/student` and `POST /doubt/admin` now emit an extra SSE event **before** the text chunks, when a board image is found.

**New event type: `image_annotation`**

```
event: data
data: {"type":"image_annotation","image_url":"...","highlight_region":{...},"all_regions":[...]}

event: data
data: {"type":"chunk","content":"The shaft is..."}

event: data
data: {"type":"chunk","content":" the rotating rod..."}

event: data
data: {"type":"done","chat_id":"...","message":{...}}
```

**How to handle it in your EventSource / fetch-stream parser:**

```ts
// Existing parser probably looks like:
switch (event.type) {
  case "chunk": appendText(event.content); break;
  case "done":  finalize(event); break;
  case "error": showError(event.message); break;
}

// ADD this case:
case "image_annotation":
  setImageAnnotation({
    imageUrl: event.image_url,
    highlightRegion: event.highlight_region,
    allRegions: event.all_regions,
  });
  break;
```

The `image_annotation` event arrives **before any text chunks**, so you can render the image immediately while the answer streams in.

When no board image exists for the lecture, this event is simply not emitted — the stream proceeds with `chunk` → `done` as before.

---

### 11.5 AnnotatedImage component

Build (or place in your components folder) a canvas-overlay component that draws bounding boxes on a board image.

**Props:**
```ts
interface AnnotatedImageProps {
  imageUrl: string;
  regions: ImageRegion[];
  highlightRegion: ImageRegion | null;
  onRegionClick?: (region: ImageRegion) => void;
}
```

**Rendering rules:**

| Element | Normal region | Highlighted region |
|---------|--------------|-------------------|
| Rectangle stroke | 1.5 px, `color_hex`, 30 % fill opacity | 2.5 px, `color_hex`, 40 % fill opacity |
| Center dot | none | Filled circle, radius 6 px |
| Pulsing ring | none | CSS keyframe: opacity 0→1→0, radius 8→20 px |
| Label pill | none | Small pill at top-right of region |
| Dashed line | none | From center dot to label pill |

The canvas must be **absolutely positioned on top of** the `<img>` element and kept the same size using `ResizeObserver`. Multiply the fractional `x, y, w, h` values by canvas `width / height` to get pixel coordinates.

---

### 11.6 Teacher: board image upload UI

Add a "Board images" section to the **teacher's lecture detail page** (where they view/edit the transcript).

**Section layout:**
1. Section title: **"Board images"**
2. File picker: `accept="image/*"` + "Upload board image" button
3. Optional fields below the picker:
   - **Topic label** — text input, placeholder: `"e.g. quadratic formula, shaft diagram"`
   - **Link to transcript section** — optional; either a free-text chunk sequence number or a dropdown of topics parsed from the transcript
4. On submit: call `uploadLectureImage()` with `multipart/form-data`
5. Show **"Analysing image with AI..."** spinner (this takes 3–8 s while GPT-4o vision runs)
6. On success: render the image using `<AnnotatedImage>` with all regions shown; list region labels as small colored pills below the image
7. Each uploaded image should have a **trash icon on hover** that calls `deleteLectureImage()`
8. Load existing images on page mount by calling `listLectureImages(lectureId)`

**Upload flow state machine:**
```
idle → uploading (show spinner) → success (show AnnotatedImage) | error (show message)
```

---

### 11.7 Student: doubt answer UI changes

In the component that renders a doubt answer (after `POST /doubts` or after SSE `done` event):

**JSON endpoint (`POST /doubts`):**
```tsx
// After rendering the answer text:
{response.image_url && (
  <div style={{ marginTop: 16 }}>
    <p style={{ fontSize: 12, color: "#888" }}>
      Board image — tap any part to ask more
    </p>
    <AnnotatedImage
      imageUrl={response.image_url}
      regions={response.all_regions ?? []}
      highlightRegion={response.highlight_region}
      onRegionClick={(region) => {
        // Optional: pre-fill question input with region label
        setQuestion(`Tell me more about the ${region.label}`);
      }}
    />
  </div>
)}
```

**Streaming endpoint (`POST /doubt/student` or `/doubt/admin`):**
```tsx
// State:
const [imageAnnotation, setImageAnnotation] = useState<{
  imageUrl: string;
  highlightRegion: ImageRegion | null;
  allRegions: ImageRegion[];
} | null>(null);

// In your SSE event handler, add:
if (event.type === "image_annotation") {
  setImageAnnotation({
    imageUrl: event.image_url,
    highlightRegion: event.highlight_region,
    allRegions: event.all_regions,
  });
}

// Render — this shows WHILE text is still streaming:
{imageAnnotation && (
  <div style={{ marginTop: 16 }}>
    <p style={{ fontSize: 12, color: "#888" }}>
      Board image — tap any part to ask more
    </p>
    <AnnotatedImage
      imageUrl={imageAnnotation.imageUrl}
      regions={imageAnnotation.allRegions}
      highlightRegion={imageAnnotation.highlightRegion}
      onRegionClick={(region) => {
        setMessage(`Tell me more about the ${region.label}`);
      }}
    />
  </div>
)}
```

---

### 11.8 Permissions summary

| Action | Required permission | Who has it |
|--------|--------------------|----|
| Upload board image | `ai_classroom.update_lecture` | Teacher who owns lecture, ADMIN, SUPER_ADMIN |
| List / get board images | `ai_classroom.read` | Teachers, students, admins |
| Delete board image | `ai_classroom.delete_lecture` | Teacher who owns lecture, ADMIN, SUPER_ADMIN |
| Ask doubt (with annotation) | `ai_classroom.ask_doubt` | Students, admins |

No permission changes are required for the streaming doubt endpoints — they already depend on `get_current_user` only.

---

### 11.9 Error handling notes

- The image annotation fields (`image_url`, `highlight_region`, `all_regions`) are always `null` / absent when no image exists. **Never assume they are present.**
- The `image_annotation` SSE event may never arrive (lecture has no images). Your SSE parser must not break if it doesn't see this event.
- `uploadLectureImage` will return `400` if the lecture is in `RECORDING`, `PAUSED`, `PROCESSING`, or `STOPPING` state. Show a user-friendly message: *"You can't upload images while recording is in progress."*
- `uploadLectureImage` will return `404` if the `lecture_id` doesn't belong to this tenant.
- The image is currently stored **locally on the server** (`/tmp/...`). This means image URLs will be server-local paths, not public HTTP URLs. **The frontend cannot fetch these directly yet.** This is a known placeholder — wire up to S3 / your CDN before going to production. Once S3 is wired, the `image_url` field will be a full `https://` URL and the `<img>` tag will work without changes.

---

### 11.10 Checklist before shipping

- [ ] `DoubtAskResponse` type updated with optional `image_url`, `highlight_region`, `all_regions`
- [ ] SSE parser handles `image_annotation` event without crashing
- [ ] `AnnotatedImage` component renders and redraws correctly on window resize
- [ ] Teacher upload UI shows loading state during the 3–8 s vision analysis
- [ ] Deleting an image triggers a list refresh
- [ ] Student doubt UI renders image annotation only when `image_url` is non-null
- [ ] `onRegionClick` optionally pre-fills follow-up question input
- [ ] S3 / CDN storage wired before going to production (backend `TODO` comment in `upload_and_analyze_image`)
