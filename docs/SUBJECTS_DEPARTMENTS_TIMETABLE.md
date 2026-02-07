# Subjects, Departments, Class–Subject, Timetable & Teacher Assignments

Multi-tenant school schema: **global departments** (core.departments), year-agnostic subjects, year-specific class–subject mapping, timetables, and teacher–subject assignments. Attendance consumes timetable data and teacher assignments for override validation.

---

## Principles

- **Departments** are **global** (core.departments): used for school, college, and software; one place for employees and subjects.
- **Subjects** are **not** academic-year specific; they belong to a core department and are reusable across years.
- **Employees (teachers)** belong to departments (core).
- Teachers teach **subjects** via **school.teacher_subject_assignments** (academic-year specific).
- **Academic year** applies only to: class_subjects, teacher_subject_assignments, timetables, attendance.
- **Attendance** consumes timetable data; it does not own subject logic. Subject overrides are validated against timetable slots and teacher assignments.

---

## 1. core.departments (global)

Used for both employees and subjects. Same table and API for school, college, and other org types.

**APIs:** `/api/v1/departments` – CRUD + dropdown. Use for subject create/update (department_id) and employee assignment.

---

## 2. school.subjects (year-agnostic)

| Column          | Type        | Description              |
|-----------------|-------------|--------------------------|
| id              | UUID        | Primary key              |
| tenant_id       | UUID        | FK → core.tenants        |
| department_id   | UUID        | FK → core.departments    |
| name            | VARCHAR     | Display name             |
| code            | VARCHAR     | Unique per tenant        |
| is_active       | BOOLEAN     | Default true             |
| display_order   | INTEGER     | Optional                 |
| created_at      | TIMESTAMPTZ |                          |

**Rules:** No `academic_year_id`. Subjects are reused across academic years.

**APIs:** `/api/v1/subjects` – CRUD + dropdown. Create/update require `department_id`.

---

## 3. school.class_subjects (year-specific)

Maps which subjects are taught in which class for an academic year.

| Column            | Type        | Description              |
|-------------------|-------------|--------------------------|
| id                | UUID        | Primary key              |
| tenant_id         | UUID        | FK → core.tenants        |
| academic_year_id  | UUID        | FK → core.academic_years |
| class_id          | UUID        | FK → core.classes        |
| subject_id        | UUID        | FK → school.subjects     |
| created_at        | TIMESTAMPTZ |                          |

**Constraint:** UNIQUE (academic_year_id, class_id, subject_id).

**APIs:** `/api/v1/class-subjects` – Create (single + bulk), list by academic_year_id (optional class_id), delete. Validates academic year ACTIVE and subject in tenant.

---

## 4. school.teacher_subject_assignments

Which teacher teaches which subject for which class-section in an academic year.

| Column            | Type        | Description              |
|-------------------|-------------|--------------------------|
| id                | UUID        | Primary key              |
| tenant_id         | UUID        | FK → core.tenants        |
| academic_year_id  | UUID        | FK → core.academic_years |
| teacher_id        | UUID        | FK → auth.users (employee) |
| class_id          | UUID        | FK → core.classes        |
| section_id        | UUID        | FK → core.sections       |
| subject_id        | UUID        | FK → school.subjects     |

**Rules:** Teacher must be an employee. Subject must exist in **class_subjects** for that academic year and class. Used for daily-attendance scope and for **subject override** permission (teacher can override only for assigned subject; override also requires a timetable slot).

**APIs:** `/api/v1/teacher-subject-assignments` – Create, list (by academic_year_id, optional teacher_id/class_id), delete.

---

## 5. school.timetables (source of truth)

One slot per (class, section, subject, teacher, day, time range).

| Column            | Type        | Description              |
|-------------------|-------------|--------------------------|
| id                | UUID        | Primary key              |
| tenant_id         | UUID        | FK → core.tenants        |
| academic_year_id  | UUID        | FK → core.academic_years |
| class_id          | UUID        | FK → core.classes        |
| section_id        | UUID        | FK → core.sections       |
| subject_id        | UUID        | FK → school.subjects     |
| teacher_id        | UUID        | FK → auth.users          |
| day_of_week       | INT         | 0=Monday .. 6=Sunday     |
| start_time        | TIME        | Slot start               |
| end_time          | TIME        | Slot end                 |

**Rules:** Subject must exist in **class_subjects** for that academic year and class. **Attendance** uses this to validate subject overrides: override is allowed only when a timetable slot exists for that class/section/subject.

**APIs:** `/api/v1/timetables` – CRUD for slots. Create validates subject in class_subjects for that year and class.

---

## 6. Attendance integration

- **Daily attendance:** Teacher can mark daily attendance if they have a **teacher_class_assignment** or a **teacher_subject_assignment** for that class-section.
- **Subject override:** Allowed only when:
  1. Subject is in **school.subjects**.
  2. A **timetable slot** exists for that class/section/subject (`school.timetables`).
  3. Teacher has a **teacher_subject_assignment** for that class/section/subject.
- Override and subject-wise/monthly APIs use **school.subjects** for subject names and resolution.
- See **ATTENDANCE.md** for daily/override tables and resolution rules.

---

## 7. RBAC summary

| Role     | Departments (core) / Subjects / Class–Subjects / Timetables / Assignments | Daily attendance     | Subject override                    |
|----------|--------------------------------------------------------------------------|----------------------|-------------------------------------|
| ADMIN    | Full access                                                              | Mark any             | Any (when slot + assignment exist)  |
| TEACHER  | Read as needed by UI                                                     | Assigned class/section only | Assigned subject + timetable slot only |
| STUDENT  | —                                                                        | —                    | —                                   |
| PARENT   | —                                                                        | —                    | —                                   |

Student/Parent: read-only access to attendance after status is SUBMITTED.
