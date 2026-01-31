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

### school.teacher_class_assignments

Links teachers to class-sections for an academic year. Teachers can only mark attendance for students in assigned classes.

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
- `POST /api/v1/attendance/teacher-assignments` – Assign teacher to class-section (required for teachers to mark student attendance)

---

## 4. Rules

- Academic year must be ACTIVE (no attendance for CLOSED years)
- Date must be within academic year range (students)
- No future dates
- One attendance per student/employee per day
- Transaction-safe inserts
