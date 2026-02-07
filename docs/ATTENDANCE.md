# Attendance Management

Student and employee attendance with role-based access control.

---

## 1. Data Model

### school.student_attendance

| Column            | Type    | Description                    |
|-------------------|---------|--------------------------------|
| id                | UUID    | Primary key                    |
| student_id        | UUID    | FK → auth.users                |
| academic_year_id  | UUID    | FK → core.academic_years       |
| date              | DATE    | Attendance date                |
| status            | VARCHAR | PRESENT, ABSENT, LATE, HALF_DAY|
| marked_by         | UUID    | FK → auth.users                |
| created_at        | TIMESTAMPTZ |                      |

**Constraints:** UNIQUE (student_id, academic_year_id, date)

### hrms.employee_attendance

| Column     | Type    | Description                         |
|------------|---------|-------------------------------------|
| id         | UUID    | Primary key                         |
| employee_id| UUID    | FK → auth.users                     |
| date       | DATE    | Attendance date                     |
| status     | VARCHAR | PRESENT, ABSENT, LATE, HALF_DAY, LEAVE |
| marked_by  | UUID    | FK → auth.users                     |
| created_at | TIMESTAMPTZ |                         |

**Constraints:** UNIQUE (employee_id, date)

### school.teacher_class_assignments (legacy)

Links teachers to class-sections (optional subject). Still used for daily-attendance scope; for **subject overrides** the system uses **school.teacher_subject_assignments** and **school.timetables** (see below).

### school.teacher_subject_assignments

Defines which teacher teaches which subject for a class-section in an academic year. Used for:
- **Daily attendance:** Teacher can mark daily attendance if they have *either* a teacher_class_assignment *or* a teacher_subject_assignment for that class-section.
- **Subject override:** Teacher can add/update overrides **only** for subjects they are assigned via this table **and** for which a **timetable slot** exists (school.timetables).

**Constraint:** UNIQUE (academic_year_id, teacher_id, class_id, section_id, subject_id).

### school.timetables (source of truth)

One row per slot: class, section, subject, teacher, day_of_week, start_time, end_time. **Subject override is allowed only when a timetable slot exists** for that class/section/subject (validated on override create/update).

### school.subjects (year-agnostic)

Tenant-scoped subjects (e.g. Math, Science). **No academic_year_id**; reusable across years. Used for class-subject mapping, timetables, and subject-wise attendance overrides. FK: **school.student_subject_attendance_overrides.subject_id** → school.subjects.

| Column          | Type       | Description        |
|-----------------|------------|--------------------|
| id              | UUID       | Primary key        |
| tenant_id       | UUID       | FK → core.tenants  |
| department_id   | UUID       | FK → core.departments   |
| name            | VARCHAR    | Display name       |
| code            | VARCHAR(50)| Unique per tenant  |
| display_order   | INTEGER    | Optional           |
| is_active       | BOOLEAN    | Default true       |

### school.student_daily_attendance (Daily master)

One row per (academic_year_id, class_id, section_id, attendance_date).

| Column            | Type       | Description                    |
|-------------------|------------|--------------------------------|
| id                | UUID       | Primary key                    |
| tenant_id         | UUID       | FK → core.tenants              |
| academic_year_id  | UUID       | FK → core.academic_years       |
| class_id          | UUID       | FK → core.classes              |
| section_id        | UUID       | FK → core.sections             |
| attendance_date   | DATE       | Date of attendance             |
| marked_by         | UUID       | FK → auth.users                |
| status            | VARCHAR(20)| DRAFT \| SUBMITTED \| LOCKED   |
| created_at        | TIMESTAMPTZ|                                |

**Constraint:** UNIQUE (academic_year_id, class_id, section_id, attendance_date).

### school.student_daily_attendance_records

One row per student per daily master.

| Column              | Type    | Description                         |
|---------------------|---------|-------------------------------------|
| id                  | UUID    | Primary key                         |
| daily_attendance_id | UUID    | FK → student_daily_attendance       |
| student_id          | UUID    | FK → auth.users                     |
| status              | VARCHAR | PRESENT, ABSENT, LATE, HALF_DAY, LEAVE |

**Constraint:** UNIQUE (daily_attendance_id, student_id).

### school.student_subject_attendance_overrides

Subject-specific override. Resolution: **if override exists → use override_status; else → use daily record status.**

| Column              | Type    | Description        |
|---------------------|---------|--------------------|
| id                  | UUID    | Primary key        |
| tenant_id           | UUID    | FK → core.tenants  |
| daily_attendance_id | UUID    | FK → student_daily_attendance |
| subject_id          | UUID    | FK → school.subjects |
| student_id          | UUID    | FK → auth.users    |
| override_status     | VARCHAR | PRESENT, ABSENT, LATE, HALF_DAY, LEAVE |
| reason              | TEXT    | Optional           |
| marked_by           | UUID    | FK → auth.users    |
| created_at          | TIMESTAMPTZ |                  |

**Constraint:** UNIQUE (daily_attendance_id, subject_id, student_id).

---

## 2. Permissions

Ensure roles have `attendance` permissions:
```json
{
  "attendance": {
    "create": true,
    "read": true
  }
}
```

| Role    | Student Attendance           | Employee Attendance    |
|---------|------------------------------|------------------------|
| ADMIN   | Mark any, view all           | Mark any, view all     |
| TEACHER | Mark assigned classes only   | Mark self only         |
| STAFF   | —                            | Mark self only         |
| STUDENT | View own (if permission)     | —                      |

---

## 3. API Endpoints

### Student Attendance
- `POST /api/v1/attendance/students/mark` – Bulk mark student attendance
- `GET /api/v1/attendance/students/day?academic_year_id=&date=` – Day-wise summary + list
- `GET /api/v1/attendance/students/monthly/{student_id}?academic_year_id=&year=&month=` – Monthly summary

### Employee Attendance
- `POST /api/v1/attendance/employees/mark` – Bulk mark employee attendance
- `GET /api/v1/attendance/employees/day?date=` – Day-wise summary + list
- `GET /api/v1/attendance/employees/monthly/{employee_id}?year=&month=` – Monthly summary

### Teacher Assignments
- `POST /api/v1/attendance/teacher-assignments` – Assign teacher to class-section (and optional subject_id for override scope)

### Daily + Subject Override (Student attendance)
- `POST /api/v1/attendance/students/daily/mark` – Bulk mark daily attendance for a class-section (creates master + records in one transaction)
- `POST /api/v1/attendance/students/daily/submit` – Change status DRAFT → SUBMITTED
- `POST /api/v1/attendance/students/subject-override` – Create or update subject override for one student
- `GET /api/v1/attendance/students/daily?academic_year_id=&class_id=&section_id=&date=` – Get daily attendance for class-section-date (ignores overrides)
- `GET /api/v1/attendance/students/subject-wise?academic_year_id=&class_id=&section_id=&date=&subject_id=` – Get resolved attendance (COALESCE(override, daily)); optional subject_id
- `GET /api/v1/attendance/students/monthly/{student_id}/extended?academic_year_id=&year=&month=` – Monthly with daily percentage and subject-wise percentages

### Subjects (for overrides and teacher assignments)
- `GET /api/v1/subjects` – List subjects for tenant
- `GET /api/v1/subjects/dropdown` – Dropdown for subject picker
- `POST /api/v1/subjects` – Create subject (attendance.create)
- `PUT /api/v1/subjects/{id}` – Update subject (attendance.update)

---

## 4. Rules

- Academic year must be ACTIVE (no attendance for CLOSED years)
- Date must be within academic year range (students)
- No future dates
- One attendance per student/employee per day
- Transaction-safe inserts

---

## 5. Daily + Subject Override rules

- **Daily attendance** is taken once per day per class-section; applies to all subjects by default.
- **Subject override** does not modify the daily record; it affects only the given subject for resolution.
- **Resolution:** When checking subject attendance: if an override exists for (daily, subject, student) → use `override_status`; else → use daily record `status`.
- Daily master **status:** DRAFT (editable) → SUBMITTED (students/parents can view) → LOCKED (only ADMIN can unlock).
- Daily can be edited only when status = DRAFT. After SUBMITTED, no edit; overrides can still be added/updated until LOCKED.
- **RBAC:** ADMIN full access. TEACHER: daily for assigned class-section (via teacher_class_assignment or teacher_subject_assignment); subject override **only** for a subject they are assigned in **school.teacher_subject_assignments** **and** for which a **timetable slot** exists (school.timetables). STUDENT/PARENT: read-only after SUBMITTED.
- Subject override is rejected with a clear error if no timetable slot exists for that class/section/subject.
