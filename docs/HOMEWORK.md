# Homework Management

Homework creation (teacher), assignment to class/section, student attempts, submissions, and hint tracking.

---

## 1. Data Model

### school.homeworks
- id, teacher_id, title, description
- status: DRAFT | PUBLISHED | ARCHIVED
- time_mode: NO_TIME | TOTAL_TIME | PER_QUESTION
- total_time_minutes, per_question_time_seconds (required per time_mode)

### school.homework_questions
- id, homework_id, question_text, question_type (MCQ | FILL_IN_BLANK | SHORT_ANSWER | LONG_ANSWER | MULTI_CHECK)
- options (JSON, required for MCQ/MULTI_CHECK), correct_answer (JSON), hints (JSON array)
- Hints: `[{type: "TEXT"|"VIDEO_LINK", content, title?}]`

### school.homework_assignments
- id, homework_id, academic_year_id, class_id, section_id (nullable)
- due_date, assigned_by
- section_id NULL = entire class

### school.homework_attempts
- id, homework_assignment_id, student_id
- attempt_number, restart_reason (required if > 1)
- started_at, completed_at

### school.homework_submissions
- id, homework_assignment_id, student_id, attempt_id
- answers (JSON: question_id → answer), submitted_at

### school.homework_hint_usage
- id, homework_question_id, homework_attempt_id, student_id
- hint_index, viewed_at

---

## 2. Permissions

Roles need `homework` permissions: `create`, `read`, `update`, `delete`

| Role   | Capabilities |
|--------|--------------|
| Teacher| Create/manage homework, add questions, assign, view submissions & hint usage |
| Student| View assigned, start/restart, view hints, submit |
| Admin  | View all, full access |

---

## 3. API Endpoints

### Homework
- `POST /api/v1/homework/` – Create
- `GET /api/v1/homework/` – List (filter: status)
- `GET /api/v1/homework/{id}` – Get one
- `PUT /api/v1/homework/{id}` – Update (DRAFT only)

### Questions
- `GET /api/v1/homework/{id}/questions` – List (include_correct for teacher)
- `POST /api/v1/homework/{id}/questions` – Add single
- `POST /api/v1/homework/{id}/questions/bulk` – Add multiple (reduces API calls)
- `PUT /api/v1/homework/questions/{id}` – Update
- `DELETE /api/v1/homework/questions/{id}` – Delete

### Assignments
- `POST /api/v1/homework/assignments` – Assign homework to class/section
- `GET /api/v1/homework/assignments` – List (filter: homework_id)
- `GET /api/v1/homework/assignments/{id}` – Get one

### Student
- `GET /api/v1/homework/my-assignments` – List assigned to current student
- `POST /api/v1/homework/assignments/{id}/start` – Start attempt (body: {restart_reason} for restart)
- `POST /api/v1/homework/attempts/{id}/submit` – Submit answers
- `POST /api/v1/homework/attempts/{id}/hint-view?question_id=&hint_index=` – Record hint view

### Analytics
- `GET /api/v1/homework/assignments/{id}/hint-usage` – Hint usage summary (teacher/admin)

---

## 4. Rules

- Homework editable only when DRAFT
- Questions/hints locked after assignment
- Assignment: academic year ACTIVE, due_date in future
- Restart: requires restart_reason
- One submission per attempt
- Videos: external links only (no upload)
