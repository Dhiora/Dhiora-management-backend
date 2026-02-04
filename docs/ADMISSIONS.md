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
| GET    | `/requests?status=` | admissions.read | All requests (filter by status) |
| POST   | `/requests/{id}/approve` | admissions.update | Approve (body: section_id, remarks?) |
| POST   | `/requests/{id}/reject` | admissions.update | Reject (body: remarks?) |
| GET    | `/students?status=` | students.read | List admission students |
| POST   | `/students/{id}/activate` | students.update | Activate (body: password, joined_date?) |

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
