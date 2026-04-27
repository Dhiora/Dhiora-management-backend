# Grades and Report Cards API Docs

Frontend-ready API contract for:
- `GET/POST/PUT/DELETE /api/v1/grades/*`
- Parent grade endpoints under `/api/v1/parent/children/*`

## Auth

- Send `Authorization: Bearer <access_token>` for all endpoints below.
- Role access:
  - Admin: `SUPER_ADMIN`, `ADMIN`, `SCHOOL_ADMIN`
  - Teacher: `TEACHER`
  - Student: `STUDENT`
  - Parent: via `/api/v1/parent/*` only

---

## A) Grades Module (`/api/v1/grades`)

## 1) Grade Scales

### GET `/api/v1/grades/scales`
Response:
```json
[
  {
    "id": "uuid",
    "label": "A+",
    "min_percentage": 90,
    "max_percentage": 100,
    "gpa_points": 4.0,
    "remarks": "Excellent",
    "display_order": 1
  }
]
```

### POST `/api/v1/grades/scales` (Admin)
Request:
```json
{
  "label": "A+",
  "min_percentage": 90,
  "max_percentage": 100,
  "gpa_points": 4.0,
  "remarks": "Excellent",
  "display_order": 1
}
```
Response: `GradeScaleItem` (same shape as GET item).

### PUT `/api/v1/grades/scales/{scale_id}` (Admin)
Request (all optional):
```json
{
  "label": "A",
  "min_percentage": 80,
  "max_percentage": 89.99,
  "gpa_points": 3.7,
  "remarks": "Very good",
  "display_order": 2
}
```
Response: `GradeScaleItem`.

### DELETE `/api/v1/grades/scales/{scale_id}` (Admin)
Response:
- HTTP `204 No Content`

---

## 2) Marks Entry / Read

### GET `/api/v1/grades/exams/{exam_id}/marks?subject_id={optional}`
- Admin/Teacher: full class marks
- Student: self marks only

Response:
```json
{
  "exam_id": "uuid",
  "exam_name": "Term 1",
  "class_name": "10",
  "section_name": "A",
  "students": [
    {
      "student_id": "uuid",
      "full_name": "Student One",
      "roll_number": "12",
      "subjects": [
        {
          "mark_id": "uuid",
          "subject_id": "uuid",
          "subject_name": "Mathematics",
          "marks_obtained": 89,
          "max_marks": 100,
          "percentage": 89,
          "grade_label": "A",
          "is_absent": false,
          "remarks": "Good work",
          "entered_by_name": "Teacher Name",
          "updated_at": "2026-04-27T11:00:00Z"
        }
      ],
      "total_marks_obtained": 445,
      "total_max_marks": 500,
      "overall_percentage": 89,
      "overall_grade": "A"
    }
  ]
}
```

### POST `/api/v1/grades/exams/{exam_id}/marks/bulk` (Admin/Teacher)
Request:
```json
{
  "marks": [
    {
      "student_id": "uuid",
      "subject_id": "uuid",
      "marks_obtained": 78,
      "max_marks": 100,
      "is_absent": false,
      "remarks": "Needs improvement"
    }
  ]
}
```
Response:
```json
{
  "saved": 1,
  "errors": []
}
```

### PUT `/api/v1/grades/marks/{mark_id}` (Admin/Teacher)
Request (all optional):
```json
{
  "marks_obtained": 82,
  "max_marks": 100,
  "is_absent": false,
  "remarks": "Updated"
}
```
Response: `SubjectMarkItem`
```json
{
  "mark_id": "uuid",
  "subject_id": "uuid",
  "subject_name": "Mathematics",
  "marks_obtained": 82,
  "max_marks": 100,
  "percentage": 82,
  "grade_label": "A",
  "is_absent": false,
  "remarks": "Updated",
  "entered_by_name": "Teacher Name",
  "updated_at": "2026-04-27T11:30:00Z"
}
```

### DELETE `/api/v1/grades/marks/{mark_id}` (Admin)
Response:
- HTTP `204 No Content`

---

## 3) Student Reports

### GET `/api/v1/grades/students/{student_id}/exams`
Response (`ExamGradeSummary[]`):
```json
[
  {
    "exam_id": "uuid",
    "exam_name": "Term 1",
    "exam_type": "TERM",
    "start_date": "2026-04-01",
    "end_date": "2026-04-10",
    "status": "COMPLETED",
    "class_name": "10",
    "section_name": "A",
    "overall_percentage": 88.6,
    "overall_grade": "A",
    "marks_entered": true
  }
]
```

### GET `/api/v1/grades/students/{student_id}/report-card/{exam_id}`
Response (`ReportCard`):
```json
{
  "student_id": "uuid",
  "student_name": "Student One",
  "roll_number": "12",
  "class_name": "10",
  "section_name": "A",
  "academic_year_name": "2026-27",
  "exam_id": "uuid",
  "exam_name": "Term 1",
  "exam_type": "TERM",
  "start_date": "2026-04-01",
  "end_date": "2026-04-10",
  "subjects": [
    {
      "subject_id": "uuid",
      "subject_name": "Mathematics",
      "marks_obtained": 89,
      "max_marks": 100,
      "percentage": 89,
      "grade_label": "A",
      "is_absent": false
    }
  ],
  "total_marks_obtained": 445,
  "total_max_marks": 500,
  "overall_percentage": 89,
  "overall_grade": "A"
}
```

### GET `/api/v1/grades/exams/{exam_id}/class-report`
Response shape: same as `GET /api/v1/grades/exams/{exam_id}/marks`.

---

## B) Parent Grade APIs (`/api/v1/parent`)

All routes validate that child belongs to logged-in parent.

### GET `/api/v1/parent/children/{student_id}/grades`
Response: `ExamGradeSummary[]` (same shape as student exam list above).

### GET `/api/v1/parent/children/{student_id}/grades/{exam_id}`
Response: `ReportCard` (same shape as above).

### GET `/api/v1/parent/children/{student_id}/report-card/{exam_id}`
Response: `ReportCard` (same as previous endpoint).

---

## C) Common Errors

Error body:
```json
{ "detail": "Error message" }
```

Common statuses:
- `400` bad request/validation
- `401` unauthenticated
- `403` forbidden (role/assignment/child ownership)
- `404` not found
- `409` conflict
