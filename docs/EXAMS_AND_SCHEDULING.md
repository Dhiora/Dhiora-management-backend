# Exams and Scheduling API Documentation

Complete reference for **Class Schedule** (from timetable) and **Exam Management** APIs in the Dhiora backend.

**Base URL:** `http://localhost:8000` (or your deployed host)  
**Auth:** All endpoints require a valid JWT in the `Authorization` header (e.g. `Bearer <token>`).  
**Permissions:** Use the `attendance` module permissions: `read`, `create`, `update` as noted per endpoint.

---

## 1. Class Schedule (from Timetable)

The class schedule is **derived from the timetable**. You can either fetch **all** schedules for the academic year (and filter client-side or with query params) or fetch a single class/section schedule by path.

### GET All Schedules (recommended: return all, then filter)

**URL:**  
`GET /api/v1/classes/schedule`

**Path parameters:** None.

**Query parameters:**

| Parameter           | Type   | Required | Description |
|--------------------|--------|----------|-------------|
| `academic_year_id` | UUID   | **Yes**  | Academic year for which the timetable is defined |
| `class_id`         | UUID   | No       | Filter to this class only (omit to return all classes) |
| `section_id`       | UUID   | No       | Filter to this section only (omit to return all sections) |
| `teacher_name`     | string | No       | Filter slots by teacher name (ilike) |
| `class_name`       | string | No       | Filter by class name (ilike) |
| `section_name`     | string | No       | Filter by section name (ilike) |

**Example request (all data):**

```
GET /api/v1/classes/schedule?academic_year_id=a36e8d38-d052-4107-a3cb-b34f3e098cb1
```

**Example request (filtered by class/section):**

```
GET /api/v1/classes/schedule?academic_year_id=a36e8d38-d052-4107-a3cb-b34f3e098cb1&class_id=a1b2c3d4-...&section_id=b2c3d4e5-...
```

**Permission:** `attendance.read`

**Response (200 OK):** Array of schedule items, one per class/section combination (respecting filters). Each item includes `class_id`, `section_id`, `class_name`, `section_name`, and the weekly slots per day.

```json
[
  {
    "class_id": "uuid",
    "section_id": "uuid",
    "class_name": "Class 10",
    "section_name": "A",
    "monday": [
      {
        "subject_id": "uuid",
        "teacher_id": "uuid",
        "start_time": "09:00",
        "end_time": "09:45",
        "subject_name": "Mathematics",
        "teacher_name": "John Doe"
      }
    ],
    "tuesday": [],
    "wednesday": [],
    "thursday": [],
    "friday": [],
    "saturday": [],
    "sunday": []
  }
]
```

Return all data first, then filter by `class_id` / `section_id` (or by name) as needed.

---

### GET Class Section Schedule (by path)

**URL:**  
`GET /api/v1/classes/{class_id}/sections/{section_id}/schedule`

**Path parameters:**

| Parameter     | Type | Description                    |
|--------------|------|--------------------------------|
| `class_id`   | UUID | Class ID (from core.classes)   |
| `section_id` | UUID | Section ID (from core.sections) |

**Query parameters:**

| Parameter           | Type   | Required | Description |
|--------------------|--------|----------|-------------|
| `academic_year_id` | UUID   | **Yes**  | Academic year for which the timetable is defined |
| `teacher_name`     | string | No       | Filter slots by teacher name (ilike) |
| `class_name`       | string | No       | Filter by class name (ilike) |
| `section_name`     | string | No       | Filter by section name (ilike) |

**Example request:**

```
GET /api/v1/classes/a1b2c3d4-e5f6-7890-abcd-ef1234567890/sections/b2c3d4e5-f6a7-8901-bcde-f12345678901/schedule?academic_year_id=a36e8d38-d052-4107-a3cb-b34f3e098cb1
```

**Permission:** `attendance.read`

**Response (200 OK):** Single weekly schedule (no `class_id`/`section_id` in body; path identifies the class/section).

```json
{
  "monday": [
    {
      "subject_id": "uuid",
      "teacher_id": "uuid",
      "start_time": "09:00",
      "end_time": "09:45",
      "subject_name": "Mathematics",
      "teacher_name": "John Doe"
    }
  ],
  "tuesday": [],
  "wednesday": [],
  "thursday": [],
  "friday": [],
  "saturday": [],
  "sunday": []
}
```

Each day key (`monday` … `sunday`) has an array of slots ordered by `start_time`. Each slot includes `subject_id`, `teacher_id`, `start_time`, `end_time`, and optionally `subject_name` and `teacher_name`.

---

## 2. Exam Types

### GET List Exam Types

**URL:**  
`GET /api/v1/exam-types`

**Request body:** None

**Permission:** `attendance.read`

**Response (200 OK):**

```json
[
  {
    "id": "uuid",
    "tenant_id": "uuid",
    "name": "Unit Test",
    "description": "Monthly unit tests",
    "created_at": "2026-01-15T10:00:00Z"
  },
  {
    "id": "uuid",
    "tenant_id": "uuid",
    "name": "Half Yearly",
    "description": "Mid-term examination",
    "created_at": "2026-01-15T10:00:00Z"
  },
  {
    "id": "uuid",
    "tenant_id": "uuid",
    "name": "Annual Exam",
    "description": "Year-end examination",
    "created_at": "2026-01-15T10:00:00Z"
  }
]
```

---

### POST Create Exam Type

**URL:**  
`POST /api/v1/exam-types`

**Payload (JSON body):**

| Field         | Type   | Required | Description      |
|---------------|--------|----------|------------------|
| `name`        | string | Yes      | Max 100 chars    |
| `description` | string | No       | Optional text    |

**Example:**

```json
{
  "name": "Unit Test",
  "description": "Monthly unit tests"
}
```

**Permission:** `attendance.create`

**Response (201 Created):**

```json
{
  "id": "uuid",
  "tenant_id": "uuid",
  "name": "Unit Test",
  "description": "Monthly unit tests",
  "created_at": "2026-01-15T10:00:00Z"
}
```

---

## 3. Exams

### GET List Exams

**URL:**  
`GET /api/v1/exams`

**Query parameters (all optional):**

| Parameter        | Type | Description |
|------------------|------|-------------|
| `class_id`       | UUID | Filter by class |
| `section_id`     | UUID | Filter by section |
| `status_filter`  | string | Filter by status: `draft`, `scheduled`, or `completed` |

**Example:**

```
GET /api/v1/exams
GET /api/v1/exams?class_id=uuid&status_filter=draft
```

**Permission:** `attendance.read`

**Response (200 OK):**

```json
[
  {
    "id": "uuid",
    "tenant_id": "uuid",
    "exam_type_id": "uuid",
    "name": "Unit Test 1 - March 2026",
    "class_id": "uuid",
    "section_id": "uuid",
    "start_date": "2026-03-01",
    "end_date": "2026-03-10",
    "status": "draft",
    "created_at": "2026-01-15T10:00:00Z"
  }
]
```

Exams are ordered by `start_date` descending, then `created_at` descending.

---

### POST Create Exam

**URL:**  
`POST /api/v1/exams`

**Payload (JSON body):**

| Field          | Type   | Required | Description |
|----------------|--------|----------|-------------|
| `exam_type_id` | UUID   | Yes      | From exam-types |
| `name`         | string | Yes      | Max 255 chars (e.g. "Unit Test 1 - March 2026") |
| `class_id`     | UUID   | Yes      | Class (core.classes) |
| `section_id`   | UUID   | Yes      | Section (core.sections); must belong to class |
| `start_date`   | date   | Yes      | Exam period start (YYYY-MM-DD) |
| `end_date`     | date   | Yes      | Exam period end (≥ start_date) |
| `status`      | string | No       | `draft` (default), `scheduled`, or `completed` |

**Example:**

```json
{
  "exam_type_id": "e1a2b3c4-d5e6-7890-abcd-ef1234567890",
  "name": "Unit Test 1 - March 2026",
  "class_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "section_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "start_date": "2026-03-01",
  "end_date": "2026-03-10",
  "status": "draft"
}
```

**Permission:** `attendance.create`

**Response (201 Created):**

```json
{
  "id": "uuid",
  "tenant_id": "uuid",
  "exam_type_id": "uuid",
  "name": "Unit Test 1 - March 2026",
  "class_id": "uuid",
  "section_id": "uuid",
  "start_date": "2026-03-01",
  "end_date": "2026-03-10",
  "status": "draft",
  "created_at": "2026-01-15T10:00:00Z"
}
```

**Validation:**  
- `end_date` must be on or after `start_date`.  
- `section_id` must belong to `class_id`.  
- `exam_type_id` must exist for the tenant.

---

## 4. Exam Schedule (per subject)

### GET Exam Schedule

**URL:**  
`GET /api/v1/exams/{exam_id}/schedule`

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `exam_id` | UUID | Exam ID |

**Request body:** None

**Permission:** `attendance.read`

**Response (200 OK):**

```json
[
  {
    "id": "uuid",
    "tenant_id": "uuid",
    "exam_id": "uuid",
    "subject_id": "uuid",
    "class_id": "uuid",
    "section_id": "uuid",
    "exam_date": "2026-03-05",
    "start_time": "09:00",
    "end_time": "12:00",
    "room_number": "101",
    "invigilator_teacher_id": "uuid",
    "created_at": "2026-01-15T10:00:00Z",
    "subject_name": "Mathematics",
    "invigilator_name": "John Doe"
  }
]
```

Returns all scheduled slots for that exam, ordered by `exam_date` and `start_time`.  
404 if `exam_id` is not found for the tenant.

---

### POST Schedule Exam Subject

**URL:**  
`POST /api/v1/exams/{exam_id}/schedule`

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `exam_id` | UUID | Exam ID |

**Payload (JSON body):**

| Field                    | Type   | Required | Description |
|--------------------------|--------|----------|-------------|
| `subject_id`             | UUID   | Yes      | Subject (school.subjects) |
| `class_id`               | UUID   | Yes      | Must match the exam’s class_id |
| `section_id`             | UUID   | Yes      | Must match the exam’s section_id |
| `exam_date`              | date   | Yes      | YYYY-MM-DD; must be within exam start_date–end_date |
| `start_time`             | string | Yes      | "HH:MM" (e.g. "09:00") |
| `end_time`               | string | Yes      | "HH:MM"; must be after start_time |
| `room_number`            | string | No       | Max 50 chars |
| `invigilator_teacher_id`  | UUID   | No       | Teacher user ID; optional |

**Example (without invigilator):**

```json
{
  "subject_id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "class_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "section_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "exam_date": "2026-09-10",
  "start_time": "09:00",
  "end_time": "12:00",
  "room_number": "101"
}
```

**Example (with invigilator):**

```json
{
  "subject_id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "class_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "section_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "exam_date": "2026-09-10",
  "start_time": "09:00",
  "end_time": "12:00",
  "room_number": "101",
  "invigilator_teacher_id": "d4e5f6a7-b8c9-0123-def0-234567890123"
}
```

**Permission:** `attendance.create`

**Response (201 Created):**

Same shape as one item in the GET schedule response (see above), including `subject_name` and `invigilator_name` when available.

**Business rules (400 on violation):**

- Same **class+section** cannot have two exams at the **same date and overlapping time**.
- Same **room** cannot have two exams at the **same date and overlapping time** (when room_number is set).
- Same **invigilator** cannot be assigned to two exams at the **same date and overlapping time** (when invigilator_teacher_id is set).
- `exam_date` must be between the exam’s `start_date` and `end_date`.
- `class_id` and `section_id` must match the exam.

---

## 5. Update Invigilator

**URL:**  
`PATCH /api/v1/exam-schedule/{schedule_id}/invigilator`

**Path parameters:**

| Parameter    | Type | Description |
|-------------|------|-------------|
| `schedule_id` | UUID | Exam schedule row ID (from POST schedule or GET schedule) |

**Payload (JSON body):**

| Field                    | Type | Required | Description |
|--------------------------|------|----------|-------------|
| `invigilator_teacher_id` | UUID | No       | Set to a user UUID to assign; omit or `null` to clear |

**Example (assign):**

```json
{
  "invigilator_teacher_id": "d4e5f6a7-b8c9-0123-def0-234567890123"
}
```

**Example (clear):**

```json
{
  "invigilator_teacher_id": null
}
```

**Permission:** `attendance.update`

**Response (200 OK):**

Same shape as one exam schedule response (id, exam_id, subject_id, exam_date, start_time, end_time, room_number, invigilator_teacher_id, subject_name, invigilator_name, etc.).

**Business rule:**  
If assigning a teacher, they cannot already be invigilating another exam at the same date and overlapping time (400 with message about double-booking).

---

## 6. Summary Table

| Method | API URL | Payload | Permission |
|--------|---------|---------|------------|
| GET | `/api/v1/classes/{class_id}/sections/{section_id}/schedule` | Query: `academic_year_id` (required), `teacher_name`, `class_name`, `section_name` | attendance.read |
| GET | `/api/v1/exam-types` | — | attendance.read |
| POST | `/api/v1/exam-types` | `name`, `description?` | attendance.create |
| GET | `/api/v1/exams` | Query: `class_id?`, `section_id?`, `status_filter?` | attendance.read |
| POST | `/api/v1/exams` | `exam_type_id`, `name`, `class_id`, `section_id`, `start_date`, `end_date`, `status?` | attendance.create |
| GET | `/api/v1/exams/{exam_id}/schedule` | — | attendance.read |
| POST | `/api/v1/exams/{exam_id}/schedule` | `subject_id`, `class_id`, `section_id`, `exam_date`, `start_time`, `end_time`, `room_number?`, `invigilator_teacher_id?` | attendance.create |
| PATCH | `/api/v1/exam-schedule/{schedule_id}/invigilator` | `invigilator_teacher_id?` (or null to clear) | attendance.update |

---

## 7. Database Tables (reference)

- **school.exam_types** – id, tenant_id, name, description, created_at  
- **school.exams** – id, tenant_id, exam_type_id, name, class_id, section_id, start_date, end_date, status (draft/scheduled/completed), created_at  
- **school.exam_schedule** – id, tenant_id, exam_id, subject_id, class_id, section_id, exam_date, start_time, end_time, room_number, invigilator_teacher_id (nullable), created_at  

Class schedule reads from **school.timetables** joined with **school.time_slots** (and class, section, subject, user for names and filters).

---

## 8. Error Responses

- **400 Bad Request** – Validation or business rule failure (e.g. duplicate slot, invalid dates). Body: `{ "detail": "message" }`.
- **403 Forbidden** – Missing permission for the resource.
- **404 Not Found** – Exam or exam schedule not found for the tenant.
- **422 Unprocessable Entity** – Invalid payload (e.g. wrong types, missing required fields).
