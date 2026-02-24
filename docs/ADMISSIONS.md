# Admission Management

TRACK (immutable) and STATUS (mutable) are handled separately. Teachers raise requests; any user with **admissions.update** can approve/reject; approved records create an admission student with **INACTIVE** status; only users with **students.update** can activate (create auth user + physical join).

---

## 1. Permissions (role-based JSON)

Configure in `auth.roles.permissions` (use standard create/read/update keys):

| Permission key        | Meaning |
|-----------------------|--------|
| `admissions.create`   | Raise an admission request (teachers/admins) |
| `admissions.update`   | Approve or reject requests (any role with this permission) |
| `admissions.read`     | List requests (my + all with status filter) |
| `students.update`     | Activate an admission student (create user + join) |
| `students.read`      | List admission students (e.g. INACTIVE queue) |

Example role permissions:

```json
{
  "admissions": { "create": true, "update": true, "read": true },
  "students": { "read": true, "update": true }
}
```

---

## 2. TRACK (immutable)

Set only at creation; never updated.

| Value             | When |
|-------------------|------|
| TEACHER_RAISED    | Logged-in user is a Teacher |
| CAMPAIGN_REFERRAL | Valid `referral_code` present |
| WEBSITE_FORM      | Raised via public website form (no teacher/referral) |
| ADMIN_RAISED      | Raised by Admin/Super Admin from panel |
| PARENT_DIRECT     | Fallback |

---

## 3. STATUS

**Admission request:** `PENDING_APPROVAL` → `APPROVED` or `REJECTED`.  
**Admission student:** `INACTIVE` (on approval) → `ACTIVE` (after activate).

Valid transitions:

- `PENDING_APPROVAL` → `APPROVED` (creates admission_student INACTIVE)
- `PENDING_APPROVAL` → `REJECTED`
- `INACTIVE` → `ACTIVE` (create User + StudentProfile + StudentAcademicRecord)

---

## 4. API Endpoints

Base: `/api/v1/admissions`. All require authentication.

| Method | Path | Permission | Description |
|--------|------|-------------|-------------|
| POST   | `/requests` | admissions.create | Raise request (track set by backend) |
| GET    | `/requests/my` | admissions.read | My requests |
| GET    | `/requests` | admissions.read | All requests (optional filter by status) |
| POST   | `/requests/{request_id}/approve` | admissions.update | Approve (creates admission_student INACTIVE) |
| POST   | `/requests/{request_id}/reject` | admissions.update | Reject |
| GET    | `/students` | students.read | List admission students (optional filter by status) |
| POST   | `/students/{student_id}/activate` | students.update | Activate (create User + profile + academic record) |

### 4.1 POST `/requests` – Raise admission request

**Request body:**

```json
{
  "student_name": "string (required, 1–255)",
  "parent_name": "string (optional, max 255)",
  "mobile": "string (optional, max 50)",
  "email": "email (optional)",
  "class_applied_for": "uuid (required) – Class ID applying for",
  "section_applied_for": "uuid (optional) – Section; can be set at approval instead",
  "referral_code": "string (optional, max 20) – If valid, track=CAMPAIGN_REFERRAL",
  "raised_via_website_form": false
}
```

- `raised_via_website_form`: if `true` and no teacher/referral, track becomes `WEBSITE_FORM`.
- **Track** is set by backend (see §2). Response includes `track`, `status` (e.g. `PENDING_APPROVAL`), `academic_year_id`, `raised_by_user_id`, `raised_by_role`, etc.

**Response:** `AdmissionRequestResponse` (id, tenant_id, student_name, parent_name, mobile, email, class_applied_for, section_applied_for, academic_year_id, track, status, raised_by_user_id, raised_by_role, referral_teacher_id, approved_by_user_id, approved_by_role, approved_at, remarks, created_at, updated_at).

---

### 4.2 GET `/requests/my` – My requests

No query params. Returns `List[AdmissionRequestResponse]` for the current user.

---

### 4.3 GET `/requests` – All requests

**Query:**

| Param   | Type   | Description |
|---------|--------|-------------|
| `status` | string | Optional. One of: `PENDING_APPROVAL`, `APPROVED`, `REJECTED` |

Returns `List[AdmissionRequestResponse]`.

---

### 4.4 POST `/requests/{request_id}/approve` – Approve request

**Request body:**

```json
{
  "section_id": "uuid (required) – Section for the approved student (must belong to request’s class)",
  "remarks": "string (optional, max 2000)"
}
```

Creates an **admission_student** with status `INACTIVE`. Response is updated `AdmissionRequestResponse` (status=APPROVED, approved_by_*, approved_at, etc.).

---

### 4.5 POST `/requests/{request_id}/reject` – Reject request

**Request body:**

```json
{
  "remarks": "string (optional, max 2000)"
}
```

Response is updated `AdmissionRequestResponse` (status=REJECTED).

---

### 4.6 GET `/students` – List admission students

**Query:**

| Param   | Type   | Description |
|---------|--------|-------------|
| `status` | string | Optional. One of: `INACTIVE`, `ACTIVE` |

Use `status=INACTIVE` for the activation queue. Returns `List[AdmissionStudentResponse]`.

**Response fields (per item):** id, tenant_id, admission_request_id, user_id (null until activated), student_name, parent_name, mobile, email, class_id, section_id, academic_year_id, track, status, joined_date (null until activated), created_at, updated_at.

---

### 4.7 POST `/students/{student_id}/activate` – Activate student

**Request body:**

```json
{
  "password": "string (required, min 8) – Initial password for the new user account",
  "joined_date": "date (optional) – Physical join date; default today"
}
```

Creates auth **User**, **StudentProfile**, and **StudentAcademicRecord**; sets admission_student `user_id`, status=ACTIVE, joined_date. Response is updated `AdmissionStudentResponse`.

---

## 5. Database

- **school.admission_requests** – request rows (track, status, raised_by, approved_by, etc.).
- **school.admission_students** – one per approved request (INACTIVE until activated); after activate: `user_id` set, status=ACTIVE, joined_date.
- **school.audit_logs** – every state change (entity_type, entity_id, action, from_status, to_status, performed_by, timestamp).

These tables are created by **schema_check** (no separate migration). Run:

```bash
python -m app.db.schema_check
```

---

## 6. Rules

1. Teacher cannot directly create a student; must raise request.
2. Approval is permission-based (admissions.update), not role-based.
3. Approved admission always creates admission_student with INACTIVE.
4. Only users with students.update can activate; teachers can never activate.
5. Track is set once at creation and never changed.
6. Status transitions are enforced in service layer.
7. All actions are audited.
