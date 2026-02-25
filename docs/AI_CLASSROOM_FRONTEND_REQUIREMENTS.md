# AI Classroom Frontend Requirements

## Overview

The backend has been updated to use a **buffered transcription architecture**. Audio chunks are accumulated in memory during recording and transcribed **only when the recording is stopped**.

## Key Changes

1. **No Real-Time Transcription**: The WebSocket no longer transcribes chunks in real-time.
2. **Buffered Architecture**: All audio chunks are buffered in memory until recording stops.
3. **Single Transcription**: Transcription happens once when `POST /recording/stop/{session_id}` is called.

---

## Frontend Workflow

### 1. Start Recording

**Endpoint**: `POST /api/v1/ai-classroom/recording/start`

**Request Body**:
```json
{
  "academic_year_id": "uuid",
  "class_id": "uuid",
  "section_id": "uuid (optional)",
  "subject_id": "uuid",
  "title": "Lecture Title"
}
```

**Response**:
```json
{
  "session_id": "uuid",
  "status": "RECORDING",
  "message": "Recording session started successfully"
}
```

**Action**: Store `session_id` for subsequent operations.

---

### 2. Connect WebSocket

**Endpoint**: `ws://your-domain/api/v1/ai-classroom/recording/stream/{session_id}?token={jwt_token}`

**Connection Flow**:
1. Connect to WebSocket with JWT token in query parameter.
2. Wait for initial message:
   ```json
   {
     "status": "connected",
     "session_id": "uuid",
     "message": "Send audio chunks as binary data. Audio will be transcribed when recording stops."
   }
   ```

**Important**: 
- Authentication is required via JWT token.
- Only the teacher who created the session can connect.
- Session must be in `RECORDING` status.

---

### 3. Stream Audio Chunks

**Audio Format Requirements**:
- **Format**: WebM (recommended), MP3, WAV, M4A, MP4
- **Browser MediaRecorder**: Use `audio/webm` mimeType
- **Chunk Size**: Send chunks as they are produced by MediaRecorder (typically 1-10KB per chunk)
- **Minimum Chunk**: Backend ignores chunks < 1KB

**JavaScript Example**:
```javascript
// Get user media
const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

// Create MediaRecorder with WebM format
const mediaRecorder = new MediaRecorder(stream, {
  mimeType: 'audio/webm;codecs=opus'
});

// Connect WebSocket
const ws = new WebSocket(
  `ws://your-domain/api/v1/ai-classroom/recording/stream/${sessionId}?token=${jwtToken}`
);

ws.onopen = () => {
  console.log('WebSocket connected');
  
  // Start recording
  mediaRecorder.start(1000); // Record in 1-second chunks
};

// Send audio chunks as binary data
mediaRecorder.ondataavailable = (event) => {
  if (event.data.size > 0 && ws.readyState === WebSocket.OPEN) {
    ws.send(event.data); // Send as binary
  }
};

// Handle server responses
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.status === 'chunk_received') {
    console.log(`Buffer size: ${data.size} bytes`);
    // Update UI with buffer size if needed
  } else if (data.error) {
    console.error('Error:', data.error);
  }
};
```

**Server Responses**:
- **Chunk Received**:
  ```json
  {
    "status": "chunk_received",
    "size": 12345
  }
  ```
  - `size`: Current total buffer size in bytes

- **Error**:
  ```json
  {
    "error": "Error message"
  }
  ```

**Important Notes**:
- **No transcription responses**: The server will NOT send transcription text during streaming.
- **Buffer size updates**: Monitor `chunk_received` responses to track buffer size.
- **Memory limit**: If buffer exceeds 200MB, recording stops automatically.

---

### 4. Pause Recording (Optional)

**Endpoint**: `POST /api/v1/ai-classroom/recording/pause/{session_id}`

**Response**:
```json
{
  "session_id": "uuid",
  "status": "PAUSED",
  "message": "Recording paused successfully"
}
```

**Frontend Action**:
- Stop MediaRecorder: `mediaRecorder.stop()`
- Close WebSocket connection (optional, but recommended)
- Update UI to show paused state

---

### 5. Resume Recording (Optional)

**Endpoint**: `POST /api/v1/ai-classroom/recording/resume/{session_id}`

**Response**:
```json
{
  "session_id": "uuid",
  "status": "RECORDING",
  "message": "Recording resumed successfully"
}
```

**Frontend Action**:
- Reconnect WebSocket (if closed)
- Restart MediaRecorder: `mediaRecorder.start(1000)`
- Update UI to show recording state

---

### 6. Stop Recording

**Endpoint**: `POST /api/v1/ai-classroom/recording/stop/{session_id}`

**Response**:
```json
{
  "session_id": "uuid",
  "status": "PROCESSING",
  "message": "Recording session stopped and processing started",
  "lecture_id": "uuid"
}
```

**Frontend Actions**:
1. **Stop MediaRecorder**:
   ```javascript
   mediaRecorder.stop();
   mediaRecorder.stream.getTracks().forEach(track => track.stop());
   ```

2. **Close WebSocket**:
   ```javascript
   ws.close();
   ```

3. **Show Processing State**: 
   - Update UI to show "Processing..." or "Transcribing..."
   - The backend will:
     - Transcribe the full audio buffer
     - Generate embeddings
     - Store chunks
     - Set status to `COMPLETED`

4. **Poll for Completion** (Optional):
   - Poll `GET /api/v1/ai-classroom/lectures/{lecture_id}` to check when `status === "COMPLETED"`
   - Or wait for a webhook/notification (if implemented)

---

## Error Handling

### WebSocket Errors

1. **Authentication Failed**:
   - WebSocket closes with code 1008
   - Reason: "Authentication failed"
   - **Fix**: Ensure JWT token is valid and not expired

2. **Session Not Found**:
   - WebSocket closes with code 1008
   - Reason: "Session not found or access denied"
   - **Fix**: Verify session_id and teacher ownership

3. **Session Not Recording**:
   - WebSocket closes with code 1008
   - Reason: "Session not recording (status: {status})"
   - **Fix**: Ensure session status is `RECORDING`

4. **Buffer Limit Exceeded**:
   - Server sends error message
   - Recording stops automatically
   - **Fix**: Limit recording duration or optimize audio quality

### API Errors

All REST endpoints return standard HTTP error responses:
- `400`: Bad Request (invalid parameters)
- `401`: Unauthorized (missing/invalid token)
- `403`: Forbidden (insufficient permissions)
- `404`: Not Found (session/lecture not found)
- `409`: Conflict (e.g., active recording already exists)
- `500`: Internal Server Error (transcription/processing failed)

---

## Best Practices

### 1. Audio Quality
- Use **WebM with Opus codec** for best browser compatibility
- Recommended bitrate: 64-128 kbps
- Sample rate: 16-48 kHz

### 2. Chunk Size
- MediaRecorder chunks are typically 1-10KB
- Backend ignores chunks < 1KB
- No need to manually buffer on frontend

### 3. Connection Management
- **Always close WebSocket** when pausing or stopping
- **Reconnect WebSocket** when resuming
- Handle WebSocket disconnections gracefully

### 4. UI/UX
- Show buffer size during recording (from `chunk_received` responses)
- Show "Processing..." state after stopping
- Poll lecture status or use WebSocket for completion notification
- Handle errors gracefully with user-friendly messages

### 5. Memory Management
- Stop MediaRecorder tracks when done: `stream.getTracks().forEach(track => track.stop())`
- Close WebSocket connections properly
- Clean up event listeners

---

## Example Complete Flow

```javascript
class LectureRecorder {
  constructor(sessionId, jwtToken) {
    this.sessionId = sessionId;
    this.jwtToken = jwtToken;
    this.ws = null;
    this.mediaRecorder = null;
    this.stream = null;
  }

  async start() {
    // 1. Get audio stream
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    
    // 2. Create MediaRecorder
    this.mediaRecorder = new MediaRecorder(this.stream, {
      mimeType: 'audio/webm;codecs=opus'
    });

    // 3. Connect WebSocket
    this.ws = new WebSocket(
      `ws://your-domain/api/v1/ai-classroom/recording/stream/${this.sessionId}?token=${this.jwtToken}`
    );

    this.ws.onopen = () => {
      console.log('WebSocket connected');
      this.mediaRecorder.start(1000);
    };

    this.mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0 && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(event.data);
      }
    };

    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.status === 'chunk_received') {
        this.onBufferUpdate?.(data.size);
      }
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      this.onError?.(error);
    };
  }

  async pause() {
    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
      this.mediaRecorder.stop();
    }
    if (this.ws) {
      this.ws.close();
    }
    // Call pause API
    await fetch(`/api/v1/ai-classroom/recording/pause/${this.sessionId}`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${this.jwtToken}` }
    });
  }

  async resume() {
    // Call resume API
    await fetch(`/api/v1/ai-classroom/recording/resume/${this.sessionId}`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${this.jwtToken}` }
    });
    // Reconnect WebSocket and restart MediaRecorder
    await this.start();
  }

  async stop() {
    // Stop MediaRecorder
    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
      this.mediaRecorder.stop();
    }
    
    // Stop all tracks
    if (this.stream) {
      this.stream.getTracks().forEach(track => track.stop());
    }

    // Close WebSocket
    if (this.ws) {
      this.ws.close();
    }

    // Call stop API
    const response = await fetch(`/api/v1/ai-classroom/recording/stop/${this.sessionId}`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${this.jwtToken}` }
    });

    const data = await response.json();
    this.onProcessingStarted?.(data);
    
    // Poll for completion
    this.pollForCompletion(data.lecture_id);
  }

  async pollForCompletion(lectureId) {
    const interval = setInterval(async () => {
      const response = await fetch(`/api/v1/ai-classroom/lectures/${lectureId}`, {
        headers: { 'Authorization': `Bearer ${this.jwtToken}` }
      });
      const lecture = await response.json();
      
      if (lecture.status === 'COMPLETED') {
        clearInterval(interval);
        this.onCompleted?.(lecture);
      }
    }, 2000); // Poll every 2 seconds
  }
}
```

---

## Summary

**What Changed**:
- ❌ No real-time transcription during streaming
- ✅ Audio buffered in memory
- ✅ Transcription happens on stop
- ✅ Simpler, more reliable architecture

**Frontend Must**:
1. Send audio chunks as binary via WebSocket
2. Handle `chunk_received` responses (buffer size updates)
3. Close WebSocket and stop MediaRecorder when stopping
4. Poll or wait for completion after stopping
5. Use WebM format for best compatibility

**Frontend Should NOT**:
- ❌ Expect transcription text during streaming
- ❌ Try to transcribe on frontend
- ❌ Buffer audio chunks manually (backend handles this)
- ❌ Send text messages about format (not needed)

