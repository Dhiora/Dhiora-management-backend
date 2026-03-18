# Online Assessment API

Base URL: `https://schoolapi.dhiora.com/api/v1/assessments`

All endpoints require a **Bearer token** in the `Authorization` header.

---

## Data Model

### Assessment statuses

| Status | Meaning |
|--------|---------|
| `DRAFT` | Created by teacher but not published; invisible to students |
| `UPCOMING` | Scheduled but start time not yet reached |
| `ACTIVE` | Students can start now |
| `COMPLETED` | Past due date; no new attempts allowed |

### Question types (current & future)

| Type | Description | `options` | `correct_answer` |
|------|-------------|-----------|-----------------|
| `MCQ` | Single-choice (multiple choice) | `["A","B","C","D"]` | `"C"` (single string) |
| `MULTI_SELECT` | Multiple correct options | `["A","B","C","D"]` | `["A","C"]` (list) |
| `FILL_IN_BLANK` | Type the answer | `null` | `"Paris"` (string) |
| `SHORT_ANSWER` | Short typed response | `null` | `"Newton"` (string) |
| `LONG_ANSWER` | Essay / manual grading | `null` | `null` or rubric |

> Currently only **MCQ** is implemented in the UI. The backend stores and grades all types.

---

## Permissions

Role permissions key: `assessments`

| Action | Required permission |
|--------|-------------------|
| Create / add questions | `assessments.create` |
| Read / list / start | `assessments.read` |
| Update | `assessments.update` |
| Delete | `assessments.delete` |

---

## Endpoints

---

### 1. List assessments

`GET /api/v1/assessments`

Returns assessments visible to the current user.

- **Students** – automatically filtered to their enrolled class/section; DRAFT assessments are hidden.
- **Teachers / Admin** – all assessments for the current academic year.

#### Query parameters

| Param | Type | Description |
|-------|------|-------------|
| `status` | string | Filter: `ACTIVE` \| `UPCOMING` \| `COMPLETED` \| `DRAFT` |
| `search` | string | Case-insensitive title search |
| `class_id` | UUID | Filter by class |
| `subject_id` | UUID | Filter by subject |

#### Response `200`

```json
[
  {
    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "title": "Mathematics – Unit Test 2",
    "subject": "Mathematics",
    "class_label": "Class 9 – Section A",
    "total_questions": 15,
    "total_marks": 30,
    "duration_minutes": 30,
    "status": "ACTIVE",
    "due_date": "2026-03-25",
    "attempts_allowed": 2,
    "attempts_taken": 0,
    "description": "Covers algebra, linear equations and coordinate geometry.",
    "score": null
  }
]
```

> For a completed attempt `score` will be the student's best score, e.g. `16`.

---

### 2. Create assessment (teacher)

`POST /api/v1/assessments`

#### Request body

```json
{
  "title": "Mathematics – Unit Test 2",
  "description": "Covers algebra, linear equations and coordinate geometry.",
  "academic_year_id": "uuid",
  "class_id": "uuid",
  "section_id": "uuid",
  "subject_id": "uuid",
  "duration_minutes": 30,
  "attempts_allowed": 2,
  "status": "DRAFT",
  "due_date": "2026-03-25"
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `title` | string | Yes | Max 255 chars |
| `academic_year_id` | UUID | Yes | |
| `class_id` | UUID | Yes | |
| `section_id` | UUID | No | Null = all sections |
| `subject_id` | UUID | No | |
| `duration_minutes` | int | No | Default 30, min 5 |
| `attempts_allowed` | int | No | Default 1, max 10 |
| `status` | string | No | Default `DRAFT` |
| `due_date` | date | No | ISO `YYYY-MM-DD` |
| `description` | string | No | |

#### Response `201`

```json
{
  "id": "uuid",
  "tenant_id": "uuid",
  "created_by": "uuid",
  "academic_year_id": "uuid",
  "class_id": "uuid",
  "section_id": "uuid",
  "subject_id": "uuid",
  "title": "Mathematics – Unit Test 2",
  "description": "...",
  "duration_minutes": 30,
  "attempts_allowed": 2,
  "status": "DRAFT",
  "due_date": "2026-03-25",
  "total_questions": 0,
  "total_marks": 0,
  "created_at": "2026-03-18T10:00:00Z",
  "updated_at": "2026-03-18T10:00:00Z"
}
```

---

### 3. Update assessment (teacher)

`PUT /api/v1/assessments/{assessment_id}`

#### Request body (all fields optional)

```json
{
  "title": "New Title",
  "status": "ACTIVE",
  "due_date": "2026-04-01",
  "duration_minutes": 45,
  "attempts_allowed": 1
}
```

#### Response `200` — same as create response.

---

### 4. Delete assessment (teacher)

`DELETE /api/v1/assessments/{assessment_id}`

Only **DRAFT** assessments can be deleted.

#### Response `204 No Content`

---

### 5. Add a question (teacher)

`POST /api/v1/assessments/{assessment_id}/questions`

#### Request body

```json
{
  "question_text": "If 2x + 3 = 11, what is the value of x?",
  "question_type": "MCQ",
  "options": ["2", "3", "4", "5"],
  "correct_answer": "4",
  "marks": 2,
  "difficulty": "easy",
  "order_index": 0
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `question_text` | string | Yes | |
| `question_type` | string | Yes | `MCQ` \| `FILL_IN_BLANK` \| `MULTI_SELECT` \| `SHORT_ANSWER` \| `LONG_ANSWER` |
| `options` | string[] | Required for MCQ / MULTI_SELECT | |
| `correct_answer` | any | No | String for MCQ/FILL; list for MULTI_SELECT; null for LONG_ANSWER |
| `marks` | int | No | Default 1, min 1 |
| `difficulty` | string | No | `easy` \| `medium` \| `hard` |
| `order_index` | int | No | Default 0 |

#### Response `201`

```json
{
  "id": "uuid",
  "assessment_id": "uuid",
  "question_text": "If 2x + 3 = 11, what is the value of x?",
  "question_type": "MCQ",
  "options": ["2", "3", "4", "5"],
  "correct_answer": "4",
  "marks": 2,
  "difficulty": "easy",
  "order_index": 0,
  "created_at": "2026-03-18T10:00:00Z"
}
```

> `total_questions` and `total_marks` on the assessment are automatically updated.

---

### 6. Bulk-add questions (teacher)

`POST /api/v1/assessments/{assessment_id}/questions/bulk`

#### Request body

```json
{
  "questions": [
    {
      "question_text": "...",
      "question_type": "MCQ",
      "options": ["A","B","C","D"],
      "correct_answer": "B",
      "marks": 2,
      "difficulty": "medium",
      "order_index": 0
    }
  ]
}
```

#### Response `201` — array of question objects (same shape as single add).

---

### 7. List questions (teacher preview)

`GET /api/v1/assessments/{assessment_id}/questions?include_correct=true`

| Query param | Default | Notes |
|-------------|---------|-------|
| `include_correct` | `true` | Set `false` for student-safe preview |

#### Response `200` — array of question objects.

---

### 8. Update a question (teacher)

`PUT /api/v1/assessments/questions/{question_id}`

All fields optional. Same shape as add-question body.

#### Response `200` — updated question object.

---

### 9. Delete a question (teacher)

`DELETE /api/v1/assessments/questions/{question_id}`

#### Response `204 No Content`

> `total_questions` and `total_marks` on the assessment are automatically recalculated.

---

### 10. Start attempt (student)

`POST /api/v1/assessments/{assessment_id}/start`

- Creates an `IN_PROGRESS` attempt and returns the questions **without** `correct_answer`.
- Only allowed when `status === 'ACTIVE'` and `attempts_taken < attempts_allowed`.
- If student already has an `IN_PROGRESS` attempt, returns `400` (frontend should resume with same `attempt_id`).

#### Response `201`

```json
{
  "attempt_id": "uuid",
  "questions": [
    {
      "id": "uuid",
      "assessment_id": "uuid",
      "question_text": "If 2x + 3 = 11, what is the value of x?",
      "question_type": "MCQ",
      "options": ["2", "3", "4", "5"],
      "correct_answer": null,
      "marks": 2,
      "difficulty": "easy",
      "order_index": 0,
      "created_at": "2026-03-18T10:00:00Z"
    }
  ]
}
```

---

### 11. Submit answers (student)

`POST /api/v1/assessments/{assessment_id}/submit`

Call this when the student finishes OR when the timer runs out (auto-submit).

#### Request body

```json
{
  "attempt_id": "uuid",
  "answers": {
    "question-uuid-1": "4",
    "question-uuid-2": "x = 2",
    "question-uuid-3": "2"
  },
  "time_taken_seconds": 847
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `attempt_id` | UUID | Yes | From start response |
| `answers` | object | Yes | `{ "question_id": selected_answer }` — omit skipped questions |
| `time_taken_seconds` | int | Yes | Total seconds elapsed |

**Answer formats per question type:**

| Type | Format |
|------|--------|
| MCQ | `"4"` (exact option string) |
| MULTI_SELECT | `["A", "C"]` (array of selected options) |
| FILL_IN_BLANK | `"Paris"` (string) |
| SHORT_ANSWER | `"Newton"` (string) |
| LONG_ANSWER | any string (not auto-graded) |

#### Response `200`

```json
{
  "attempt_id": "uuid",
  "score": 24,
  "total_marks": 30,
  "correct": 12,
  "wrong": 2,
  "skipped": 1,
  "time_taken_seconds": 847
}
```

---

### 12. Get attempt detail / review

`GET /api/v1/assessments/attempts/{attempt_id}`

Returns result + per-question breakdown with correct answers (shown after submit).

- Students can only view their own attempts.
- Teachers/Admin can view any attempt.

#### Response `200`

```json
{
  "attempt_id": "uuid",
  "assessment_id": "uuid",
  "student_id": "uuid",
  "attempt_number": 1,
  "status": "SUBMITTED",
  "score": 24,
  "total_marks": 30,
  "correct_count": 12,
  "wrong_count": 2,
  "skipped_count": 1,
  "time_taken_seconds": 847,
  "started_at": "2026-03-18T10:00:00Z",
  "submitted_at": "2026-03-18T10:14:07Z",
  "answers": [
    {
      "question_id": "uuid",
      "question_text": "If 2x + 3 = 11, what is the value of x?",
      "question_type": "MCQ",
      "options": ["2", "3", "4", "5"],
      "correct_answer": "4",
      "selected_answer": "4",
      "is_correct": true,
      "marks_awarded": 2,
      "marks": 2
    }
  ]
}
```

---

### 13. Abort attempt (student)

`POST /api/v1/assessments/attempts/{attempt_id}/abort`

Called when student clicks "Exit" (before submitting). The attempt is marked `ABORTED` and counts toward `attempts_taken`.

#### Response `204 No Content`

---

### 14. Get all results (teacher)

`GET /api/v1/assessments/{assessment_id}/results`

Returns a summary of all student submissions for an assessment.

#### Response `200`

```json
{
  "assessment_id": "uuid",
  "title": "Mathematics – Unit Test 2",
  "total_marks": 30,
  "results": [
    {
      "student_id": "uuid",
      "student_name": "John Doe",
      "attempt_number": 1,
      "attempt_id": "uuid",
      "status": "SUBMITTED",
      "score": 24,
      "total_marks": 30,
      "correct_count": 12,
      "wrong_count": 2,
      "skipped_count": 1,
      "time_taken_seconds": 847,
      "submitted_at": "2026-03-18T10:14:07Z"
    }
  ]
}
```

---

## Error responses

All errors follow the standard FastAPI format:

```json
{ "detail": "Human-readable error message" }
```

| HTTP status | Meaning |
|-------------|---------|
| `400` | Bad request (validation, business rule) |
| `401` | Missing or invalid token |
| `403` | Insufficient permissions |
| `404` | Resource not found |
| `422` | Request body validation error (Pydantic) |

---

## Frontend integration flow

```
Teacher flow
────────────
1. POST /assessments              → create assessment (DRAFT)
2. POST /assessments/:id/questions/bulk → add questions
3. PUT  /assessments/:id          → set status = ACTIVE

Student flow
────────────
1. GET  /assessments              → list (auto-filtered by class/section)
2. POST /assessments/:id/start    → get attempt_id + questions
   (timer starts in UI)
3. POST /assessments/:id/submit   → send answers → get score
   OR
   POST /assessments/attempts/:attempt_id/abort  → user exited

Review (after submit)
─────────────────────
GET /assessments/attempts/:attempt_id  → question-by-question review
```

---

## Summary table

| # | Purpose | Method | Path |
|---|---------|--------|------|
| 1 | List assessments | GET | `/api/v1/assessments` |
| 2 | Create assessment | POST | `/api/v1/assessments` |
| 3 | Update assessment | PUT | `/api/v1/assessments/{id}` |
| 4 | Delete assessment (DRAFT only) | DELETE | `/api/v1/assessments/{id}` |
| 5 | Add question | POST | `/api/v1/assessments/{id}/questions` |
| 6 | Bulk-add questions | POST | `/api/v1/assessments/{id}/questions/bulk` |
| 7 | List questions | GET | `/api/v1/assessments/{id}/questions` |
| 8 | Update question | PUT | `/api/v1/assessments/questions/{question_id}` |
| 9 | Delete question | DELETE | `/api/v1/assessments/questions/{question_id}` |
| 10 | Start attempt | POST | `/api/v1/assessments/{id}/start` |
| 11 | Submit answers | POST | `/api/v1/assessments/{id}/submit` |
| 12 | Get attempt detail/review | GET | `/api/v1/assessments/attempts/{attempt_id}` |
| 13 | Abort attempt | POST | `/api/v1/assessments/attempts/{attempt_id}/abort` |
| 14 | Get all results (teacher) | GET | `/api/v1/assessments/{id}/results` |
