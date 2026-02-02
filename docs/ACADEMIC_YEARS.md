# Academic Year & Student Academic Records

Master configuration for academic data. One academic year per tenant can be "current"; CLOSED years are read-only. Admissions allowed only when `is_current=true`, `status=ACTIVE`, `admissions_allowed=true`.

---

## 0. Login Default Academic Year

On user login:

- The system fetches the ACTIVE academic year for the tenant: `WHERE tenant_id = user.tenant_id AND is_current = true`.
- If an academic year is found and `status = ACTIVE`, its `id` and `status` are embedded in the access token.
- If **no** active academic year is found:
  - **Non-admin** users: login is blocked with `"No active academic year found. Please contact administrator."`
  - **Admin** (ADMIN, PLATFORM_ADMIN, SUPER_ADMIN): login is allowed; token has no `academic_year_id` (frontend can prompt to create/set one).

**Token payload** includes:

- `sub`, `user_id`, `tenant_id`, `role`, `modules`, `iat`, `exp`
- `academic_year_id` (UUID string) – ACTIVE year at login
- `academic_year_status` – `"ACTIVE"` or `"CLOSED"`

**Request context** (from token):

- `CurrentUser.academic_year_id`, `CurrentUser.academic_year_status` are available on every authenticated request.
- APIs should apply `tenant_id` and `academic_year_id` filters from context; academic year must **not** be accepted from query/body/headers (except controlled admin override).

**CLOSED academic year:**

- When `academic_year_status = CLOSED`, all CREATE/UPDATE/DELETE operations are blocked with: `"This academic year is closed and cannot be modified."`
- Use the `require_writable_academic_year` dependency on write endpoints (attendance mark, homework assignment/submit, etc.).

**Academic year switch:**

- Switching academic year must re-issue a **new** token (new `academic_year_id`/`academic_year_status`); the old token is not mutated in place.

---

## 1. Database Schema

### Table: `core.academic_years`

| Column             | Type         | Nullable | Default   | Description                                      |
|--------------------|--------------|----------|-----------|--------------------------------------------------|
| id                 | UUID         | NO       | gen       | Primary key                                      |
| tenant_id          | UUID         | NO       | -         | FK → core.tenants(id) ON DELETE CASCADE          |
| name               | VARCHAR(50)  | NO       | -         | e.g. "2025-2026"                                 |
| start_date         | DATE         | NO       | -         | Academic year start                              |
| end_date           | DATE         | NO       | -         | Academic year end (must be > start_date)         |
| is_current         | BOOLEAN      | NO       | false     | Only one per tenant can be true                  |
| status             | VARCHAR(20)  | NO       | 'ACTIVE'  | ACTIVE \| CLOSED                                 |
| admissions_allowed | BOOLEAN      | NO       | true      | Whether student admissions are allowed           |
| created_at         | TIMESTAMPTZ  | NO       | NOW()     |                                                  |
| updated_at         | TIMESTAMPTZ  | NO       | NOW()     |                                                  |
| closed_at          | TIMESTAMPTZ  | YES      | -         | When the year was closed                         |
| closed_by          | UUID         | YES      | -         | FK → auth.users(id) ON DELETE SET NULL           |

**Constraints:**

- `UNIQUE (tenant_id, name)` – name unique per tenant
- `CHECK (end_date > start_date)` – dates validation
- `UNIQUE (tenant_id) WHERE (is_current = true)` – partial unique index: at most one current year per tenant

---

### Table: `school.student_academic_records`

| Column            | Type         | Nullable | Default   | Description                                      |
|-------------------|--------------|----------|-----------|--------------------------------------------------|
| id                | UUID         | NO       | gen       | Primary key                                      |
| student_id        | UUID         | NO       | -         | FK → auth.users(id) ON DELETE CASCADE            |
| academic_year_id  | UUID         | NO       | -         | FK → core.academic_years(id) ON DELETE RESTRICT  |
| class_id          | UUID         | NO       | -         | FK → core.classes(id)                            |
| section_id        | UUID         | NO       | -         | FK → core.sections(id)                           |
| roll_number       | VARCHAR(50)  | YES      | -         | Optional roll number                             |
| status            | VARCHAR(20)  | NO       | 'ACTIVE'  | ACTIVE \| PROMOTED \| LEFT                        |
| created_at        | TIMESTAMPTZ  | NO       | NOW()     |                                                  |

**Constraints:**

- `UNIQUE (student_id, academic_year_id)` – one record per student per academic year
- Student deletion CASCADE; academic year deletion RESTRICT (blocked if records exist)

**Note:** `student_profile` does NOT store class/section; current class/section come from `student_academic_records` (current academic year).

---

## 2. Admissions Control

Student admissions are allowed ONLY when:

- `is_current = true`
- `status = ACTIVE`
- `admissions_allowed = true`

If no such academic year exists, student creation MUST FAIL with:

> "No academic year is open for admissions. Create an academic year with is_current=true, status=ACTIVE, and admissions_allowed=true."

---

## 3. Student Creation Rules (CRITICAL)

When a student is created (via Admission or Direct Add):

1. Fetch current academic year where `is_current=true`, `status=ACTIVE`, `admissions_allowed=true`
2. If none found → BLOCK student creation
3. If found → create:
   - `auth.users`
   - `auth.student_profile` (roll_number only; no class_id/section_id)
   - Exactly ONE `school.student_academic_records` row for that academic year

Student creation is INVALID without an academic year assignment.

---

## 4. Promotion Rules (NON-NEGOTIABLE)

Student promotion MUST NOT update existing records in place. Old record `status` → `PROMOTED`; NEW row created for target year.

### Bulk Promotion API

**`POST /api/v1/students/promote-bulk?preview=true`**

| Field | Description |
|-------|-------------|
| source_academic_year_id | Year to promote from |
| target_academic_year_id | Year to promote to (must be ACTIVE, admissions_allowed=true) |
| default_class_promotion | [{from_class_id, to_class_id}] - class mapping |
| default_section_behavior | AUTO \| SAME \| MANUAL |
| student_overrides | [{student_id, action: RETAIN\|PROMOTE, to_class_id?, to_section_id?}] |

**Actions:**
- **RETAIN:** Same class/section (repeat year)
- **PROMOTE:** New class/section (from override or default_class_promotion)

**Section behavior:**
- **AUTO:** Assign first section of target class
- **SAME:** Keep same section name (e.g. 6A → 7A)
- **MANUAL:** Fail unless section provided in overrides

**Preview:** `?preview=true` returns actions without committing.

### Single Student Promotion

**`POST /api/v1/students/{user_id}/promote`** – promote one student with explicit class/section.

---

## 5. Query & Usage Rules

- **Current students:** Query `student_academic_records` filtered by `academic_year_id` where `is_current=true`
- **student_profile** MUST NOT store current class or section
- Class/section come from current `student_academic_record`

---

## 6. Academic Year APIs

| Method | Path                        | Description                          |
|--------|-----------------------------|--------------------------------------|
| POST   | `/api/v1/academic-years`    | Create academic year                 |
| GET    | `/api/v1/academic-years`    | List (per tenant)                    |
| GET    | `/api/v1/academic-years/current` | Get current year               |
| GET    | `/api/v1/academic-years/{id}`    | Get one by id                   |
| PUT    | `/api/v1/academic-years/{id}`    | Update (ACTIVE only)             |
| POST   | `/api/v1/academic-years/{id}/set-current` | Set as current          |
| POST   | `/api/v1/academic-years/{id}/close` | Close year (sets closed_at, closed_by) |

**Create body:** `name`, `start_date`, `end_date`, `is_current`, `admissions_allowed` (default true)

---

## 7. Backfill / Migration

If students existed before this design:

1. Create `school.student_academic_records` for all existing students
2. Use current academic year (`is_current=true`, `status=ACTIVE`)
3. Use existing `class_id`, `section_id`, `roll_number` from `student_profile`
4. Drop `class_id`, `section_id` from `auth.student_profiles`

Migration is idempotent (safe to re-run).
