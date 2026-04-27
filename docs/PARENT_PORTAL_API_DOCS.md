# Parent Portal API Docs (Frontend)

This document lists the implemented Parent Portal APIs for:
- Parent-facing app
- Admin parent-management app

All endpoints are JSON unless stated otherwise.

## Base URL

- Local: `http://localhost:8000`
- API prefix is already included in each endpoint path.

## Authentication

- Parent auth endpoints:
  - `POST /api/v1/auth/parent/login`
  - `POST /api/v1/auth/parent/refresh`
  - `POST /api/v1/auth/parent/forgot-password`
  - `POST /api/v1/auth/parent/reset-password`
- Protected parent and admin endpoints require:
  - Header: `Authorization: Bearer <access_token>`

---

## Parent Auth APIs

### 1) Parent Login

`POST /api/v1/auth/parent/login`

Request:
```json
{
  "email": "parent@example.com",
  "password": "your_password"
}
```

Response:
```json
{
  "access_token": "jwt_token",
  "refresh_token": "refresh_token",
  "token_type": "bearer",
  "parent_id": "uuid",
  "linked_children": [
    {
      "student_id": "uuid",
      "full_name": "Child Name",
      "class_name": "5",
      "section_name": "A",
      "roll_number": "12",
      "relation": "father",
      "is_primary": true
    }
  ]
}
```

Notes:
- Login rate limit: 10 attempts per 15 minutes per IP.

### 2) Parent Refresh Token

`POST /api/v1/auth/parent/refresh`

Request:
```json
{
  "refresh_token": "refresh_token"
}
```

Response:
```json
{
  "access_token": "new_jwt_token",
  "token_type": "bearer"
}
```

### 3) Parent Forgot Password

`POST /api/v1/auth/parent/forgot-password`

Request:
```json
{
  "email": "parent@example.com"
}
```

Response:
```json
{
  "message": "Password reset token generated",
  "reset_token": "token_string"
}
```

### 4) Parent Reset Password

`POST /api/v1/auth/parent/reset-password`

Request:
```json
{
  "token": "reset_token",
  "new_password": "NewStrongPassword123"
}
```

Response:
```json
{
  "message": "Password reset successful"
}
```

---

## Parent App APIs

Base: `/api/v1/parent`

### Profile

#### Get parent profile + children
`GET /api/v1/parent/me`

Response:
```json
{
  "parent": {
    "id": "uuid",
    "full_name": "Parent Name",
    "phone": "9999999999",
    "email": "parent@example.com"
  },
  "children": [
    {
      "student_id": "uuid",
      "full_name": "Child Name",
      "class_name": "5",
      "section_name": "A",
      "roll_number": "12",
      "relation": "mother",
      "is_primary": true
    }
  ]
}
```

#### Update parent profile
`PUT /api/v1/parent/me`

Request:
```json
{
  "phone": "8888888888",
  "email": "new_parent@example.com"
}
```

Response:
```json
{
  "id": "uuid",
  "full_name": "Parent Name",
  "phone": "8888888888",
  "email": "new_parent@example.com"
}
```

### Children

#### List children
`GET /api/v1/parent/children`

Response is same as `GET /api/v1/parent/me`.

#### Child profile
`GET /api/v1/parent/children/{student_id}`

Response:
```json
{
  "id": "uuid",
  "full_name": "Child Name",
  "email": "student@example.com",
  "mobile": "9999999999",
  "roll_number": "12",
  "class_id": "uuid",
  "class_name": "5",
  "section_id": "uuid",
  "section_name": "A",
  "academic_year_name": "2025-26"
}
```

#### Child dashboard summary
`GET /api/v1/parent/children/{student_id}/summary`

Response:
```json
{
  "student_id": "uuid",
  "full_name": "Child Name",
  "class_name": "5",
  "section_name": "A",
  "attendance_this_month": {
    "total_days": 20,
    "present": 18,
    "absent": 1,
    "late": 1,
    "percentage": 90.0
  },
  "fees_pending": {
    "count": 1,
    "total_amount": 2500
  },
  "homework_pending": 3,
  "next_exam": null
}
```

### Attendance

#### Monthly attendance
`GET /api/v1/parent/children/{student_id}/attendance?month=4&year=2026`

Response:
```json
{
  "month": 4,
  "year": 2026,
  "records": [
    {
      "date": "2026-04-01",
      "status": "PRESENT",
      "marked_by_name": null,
      "marked_at": "2026-04-01T09:00:00Z"
    }
  ],
  "stats": {
    "total_days": 20,
    "present": 18,
    "absent": 1,
    "late": 1,
    "percentage": 90.0
  }
}
```

#### Attendance stats
`GET /api/v1/parent/children/{student_id}/attendance/stats?month=4&year=2026`

Response:
```json
{
  "total_days": 20,
  "present": 18,
  "absent": 1,
  "late": 1,
  "percentage": 90.0
}
```

#### Attendance by date
`GET /api/v1/parent/children/{student_id}/attendance/{yyyy-mm-dd}`

Response:
```json
{
  "date": "2026-04-01",
  "status": "PRESENT",
  "marked_by_name": null,
  "marked_at": "2026-04-01T09:00:00Z"
}
```

### Fees

#### All fees
`GET /api/v1/parent/children/{student_id}/fees`

Response item:
```json
{
  "id": "uuid",
  "fee_name": "Tuition Fee",
  "base_amount": 5000,
  "total_discount": 500,
  "final_amount": 4500,
  "amount_paid": 2000,
  "balance": 2500,
  "status": "partial",
  "due_date": "2026-04-10"
}
```

#### Pending fees
`GET /api/v1/parent/children/{student_id}/fees/pending`

Response shape same as all fees list.

#### Payment history
`GET /api/v1/parent/children/{student_id}/fees/history`

Response item:
```json
{
  "id": "uuid",
  "fee_name": "Tuition Fee",
  "amount_paid": 2000,
  "payment_mode": "UPI",
  "transaction_reference": "pay_abc",
  "paid_at": "2026-04-12T10:30:00Z"
}
```

#### Create Razorpay order
`POST /api/v1/parent/children/{student_id}/fees/pay?fee_assignment_id={fee_assignment_id}`

Response:
```json
{
  "razorpay_order_id": "order_xxx",
  "amount": 250000,
  "currency": "INR",
  "key_id": "rzp_key",
  "fee_assignment_id": "uuid"
}
```

#### Verify Razorpay payment
`POST /api/v1/parent/children/{student_id}/fees/pay/verify`

Request:
```json
{
  "razorpay_order_id": "order_xxx",
  "razorpay_payment_id": "pay_xxx",
  "razorpay_signature": "signature",
  "fee_assignment_id": "uuid"
}
```

Response:
```json
{
  "success": true,
  "payment_id": "uuid"
}
```

#### Fee receipt payload
`GET /api/v1/parent/children/{student_id}/fees/receipt/{payment_id}`

Response:
```json
{
  "payment_id": "uuid",
  "student_fee_assignment_id": "uuid",
  "amount_paid": 2500,
  "payment_mode": "UPI",
  "transaction_reference": "pay_xxx",
  "paid_at": "2026-04-12T10:30:00Z"
}
```

### Homework

#### Homework list
`GET /api/v1/parent/children/{student_id}/homework?status=submitted`

Response item:
```json
{
  "homework_id": "uuid",
  "assignment_id": "uuid",
  "title": "Math Practice",
  "description": "Complete chapter 2",
  "subject_name": "Mathematics",
  "due_date": "2026-04-18T23:59:59Z",
  "submission_status": "submitted",
  "score": null,
  "teacher_remarks": null
}
```

#### Homework detail
`GET /api/v1/parent/children/{student_id}/homework/{assignment_id}`

Response:
```json
{
  "homework_id": "uuid",
  "assignment_id": "uuid",
  "title": "Math Practice",
  "description": "Complete chapter 2",
  "subject_name": "Mathematics",
  "due_date": "2026-04-18T23:59:59Z",
  "submission_status": "submitted",
  "score": null,
  "teacher_remarks": null,
  "total_questions": 10
}
```

### Assessments

#### Assessments list
`GET /api/v1/parent/children/{student_id}/assessments`

Response item:
```json
{
  "assessment_id": "uuid",
  "title": "Unit Test 1",
  "subject_name": "Science",
  "due_date": "2026-04-20",
  "status": "COMPLETED",
  "attempt_status": "SUBMITTED",
  "score": 18,
  "total_marks": 20,
  "percentage": 90.0
}
```

#### Assessment result
`GET /api/v1/parent/children/{student_id}/assessments/{assessment_id}/result`

Response:
```json
{
  "assessment_id": "uuid",
  "title": "Unit Test 1",
  "total_marks": 20,
  "score": 18,
  "percentage": 90.0,
  "correct_count": 18,
  "wrong_count": 2,
  "skipped_count": 0,
  "time_taken_seconds": 900,
  "submitted_at": "2026-04-20T10:00:00Z"
}
```

### Exams and Gradebook (stubs)

- `GET /api/v1/parent/children/{student_id}/exams`
  - 503: `"Exam schedule coming soon"` (when gradebook disabled)
- `GET /api/v1/parent/children/{student_id}/grades`
  - 503: `"Gradebook coming soon"`
- `GET /api/v1/parent/children/{student_id}/grades/{term_id}`
  - 503: `"Gradebook coming soon"`
- `GET /api/v1/parent/children/{student_id}/report-card/{term_id}`
  - 503: `"Report cards coming soon"`

### Timetable

#### Weekly timetable
`GET /api/v1/parent/children/{student_id}/timetable`

Response:
```json
{
  "monday": [
    {
      "period": 1,
      "subject_name": "Mathematics",
      "teacher_name": "Teacher A",
      "start_time": "09:00:00",
      "end_time": "09:45:00",
      "slot_type": "CLASS"
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

#### Day timetable
`GET /api/v1/parent/children/{student_id}/timetable/{day}`

Response: list of timetable slot items for that day.

### Notifications

#### List notifications
`GET /api/v1/parent/notifications?is_read=false`

Response item:
```json
{
  "id": "uuid",
  "type": "attendance_absent",
  "title": "Attendance Alert",
  "body": "Your child was absent today",
  "is_read": false,
  "sent_at": "2026-04-27T09:30:00Z",
  "student_id": "uuid"
}
```

#### Mark one read
`PUT /api/v1/parent/notifications/{notification_id}/read`

Response:
```json
{
  "success": true
}
```

#### Mark all read
`PUT /api/v1/parent/notifications/read-all`

Response:
```json
{
  "success": true
}
```

#### Get notification preferences
`GET /api/v1/parent/notifications/preferences`

Response:
```json
{
  "sms_enabled": true,
  "email_enabled": true,
  "push_enabled": true,
  "types_muted": []
}
```

#### Update notification preferences
`PUT /api/v1/parent/notifications/preferences`

Request:
```json
{
  "sms_enabled": true,
  "email_enabled": false,
  "push_enabled": true,
  "types_muted": ["homework_due"]
}
```

Response shape same as get preferences.

### Circulars (stubs)

- `GET /api/v1/parent/circulars` -> 503
- `GET /api/v1/parent/circulars/{circular_id}` -> 503

### Parent-Teacher Messaging

#### List threads
`GET /api/v1/parent/messages`

Response item:
```json
{
  "id": "uuid",
  "teacher_id": "uuid",
  "teacher_name": "Teacher A",
  "student_id": "uuid",
  "student_name": "Child Name",
  "subject": "Regarding homework",
  "last_message_at": "2026-04-27T10:00:00Z",
  "unread_count": 1,
  "last_message_preview": "Please help with chapter 3..."
}
```

#### Thread detail
`GET /api/v1/parent/messages/{thread_id}`

Response:
```json
{
  "id": "uuid",
  "teacher_id": "uuid",
  "teacher_name": "Teacher A",
  "student_id": "uuid",
  "student_name": "Child Name",
  "subject": "Regarding homework",
  "created_at": "2026-04-27T09:00:00Z",
  "messages": [
    {
      "id": "uuid",
      "sender_role": "parent",
      "sender_id": "uuid",
      "body": "Hello teacher",
      "sent_at": "2026-04-27T09:01:00Z",
      "is_read": true
    }
  ]
}
```

#### Create thread
`POST /api/v1/parent/messages`

Request:
```json
{
  "teacher_id": "uuid",
  "student_id": "uuid",
  "subject": "About exam prep",
  "first_message": "Can you guide us on revision?"
}
```

Response: `ThreadDetail` object (same shape as above).

#### Reply in thread
`POST /api/v1/parent/messages/{thread_id}/reply`

Request:
```json
{
  "body": "Thanks for the update."
}
```

Response:
```json
{
  "id": "uuid",
  "sender_role": "parent",
  "sender_id": "uuid",
  "body": "Thanks for the update.",
  "sent_at": "2026-04-27T10:10:00Z",
  "is_read": false
}
```

---

## Admin Parent Management APIs

Base: `/api/v1/admin/parents`

Auth requirement:
- Role must be one of: `SUPER_ADMIN`, `ADMIN`, `SCHOOL_ADMIN`

### 1) Create parent

`POST /api/v1/admin/parents`

Request:
```json
{
  "full_name": "Parent Name",
  "email": "parent@example.com",
  "phone": "9999999999",
  "password": "Parent@123",
  "confirm_password": "Parent@123",
  "children": [
    {
      "student_id": "uuid",
      "relation": "father",
      "is_primary": true
    }
  ]
}
```

Response:
```json
{
  "parent_id": "uuid",
  "invite_sent": false,
  "invite_token": "setup_token"
}
```

### 2) List parents

`GET /api/v1/admin/parents?search=parent&page=1&limit=20`

Response item:
```json
{
  "id": "uuid",
  "full_name": "Parent Name",
  "email": "parent@example.com",
  "phone": "9999999999",
  "is_active": true,
  "children": [
    {
      "student_id": "uuid",
      "full_name": "Child Name",
      "class_name": null,
      "section_name": null,
      "roll_number": null,
      "relation": "father",
      "is_primary": true
    }
  ],
  "created_at": "2026-04-27T08:00:00Z"
}
```

### 3) Get parent details

`GET /api/v1/admin/parents/{parent_id}`

Response:
```json
{
  "id": "uuid",
  "full_name": "Parent Name",
  "email": "parent@example.com",
  "phone": "9999999999",
  "is_active": true,
  "children": [
    {
      "student_id": "uuid",
      "full_name": "Child Name",
      "class_name": null,
      "section_name": null,
      "roll_number": null,
      "relation": "father",
      "is_primary": true
    }
  ],
  "created_at": "2026-04-27T08:00:00Z",
  "last_login": "2026-04-27T09:00:00Z"
}
```

### 4) Update parent

`PUT /api/v1/admin/parents/{parent_id}`

Request:
```json
{
  "full_name": "Updated Parent Name",
  "phone": "8888888888",
  "email": "new_parent@example.com",
  "password": "NewParent@123",
  "confirm_password": "NewParent@123",
  "children": [
    {
      "student_id": "uuid",
      "relation": "mother",
      "is_primary": true
    }
  ]
}
```

Response: same shape as `GET /api/v1/admin/parents/{parent_id}`.

### 5) Admin reset parent password (separate endpoint)

`POST /api/v1/admin/parents/{parent_id}/reset-password`

Request:
```json
{
  "password": "NewParent@123",
  "confirm_password": "NewParent@123"
}
```

Response:
```json
{
  "success": true,
  "message": "Parent password updated successfully"
}
```

### 6) Resend invite

`POST /api/v1/admin/parents/{parent_id}/resend-invite`

Response:
```json
{
  "parent_id": "uuid",
  "invite_sent": false,
  "invite_token": "new_setup_token"
}
```

### 7) Deactivate parent

`DELETE /api/v1/admin/parents/{parent_id}`

Response:
- HTTP 204 (No Content)

### 8) Bulk import

`POST /api/v1/admin/parents/bulk-import`

Content-Type:
- `multipart/form-data`
- file field name: `file`

CSV columns expected:
- `full_name`
- `email`
- `phone`
- `student_admission_number`
- `relation`
- `is_primary`

Response:
```json
{
  "created": 10,
  "failed": [
    {
      "email": "bad@example.com",
      "reason": "Student with admission number XYZ not found"
    }
  ]
}
```

---

## Common Error Responses

Typical error body:
```json
{
  "detail": "Error message"
}
```

Common status codes:
- `400` bad request or validation
- `401` invalid credentials/token
- `403` forbidden (role mismatch, parent-child link mismatch)
- `404` not found
- `409` conflict (duplicate email, already paid, etc.)
- `429` parent login rate limit
- `503` stub endpoint / feature not available
