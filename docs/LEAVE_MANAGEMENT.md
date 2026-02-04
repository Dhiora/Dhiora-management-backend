# Global Leave Management

One reusable leave module; behavior depends on **tenant_type** (SCHOOL / COLLEGE / SOFTWARE) and **applicant_type** (EMPLOYEE / STUDENT). Approval routing is dynamic; all actions are permission-based and audited.

---

## 1. Permissions (role JSON)

| Key | Meaning |
|-----|--------|
| `leave.manage_types` | Create and update leave types for the tenant (Super Admin has this by default) |
| `leave.create` | Apply for leave (e.g. teachers, employees) |
| `leave.update` | Approve or reject leave (when assigned or Super Admin) |
| `leave.read` | View my leaves and pending (assigned to me); also needed to list leave types when applying |
| `leave.view_all` | View all leave requests in the tenant |

Example (teacher: can apply and see own/pending; cannot create leave types):

```json
{
  "leave": { "create": true, "update": true, "read": true }
}
```

Super Admin (and optionally roles with `leave.manage_types`) can create/update leave types per tenant.

---

## 2. Tenant types

Derived from `core.tenants.organization_type` (normalized to):

- **SCHOOL** – School
- **COLLEGE** – College
- **SOFTWARE** – Software / IT / Tech

---

## 3. Applicant types

- **EMPLOYEE** – `user_type = "employee"` (leave_requests.employee_id = user_id)
- **STUDENT** – `user_type = "student"` (leave_requests.student_id = user_id)

---

## 4. Approver resolution

`resolve_leave_approver(tenant_type, applicant_type, …)` sets **assigned_to_user_id**:

| Tenant   | Applicant | Approver |
|----------|-----------|----------|
| SCHOOL   | STUDENT   | Class teacher (from teacher_class_assignments for student’s current class/section) |
| SCHOOL   | EMPLOYEE  | First user with role ADMIN / SUPER_ADMIN |
| COLLEGE  | STUDENT   | First user with role Mentor / Advisor |
| COLLEGE  | EMPLOYEE  | First user with role HOD / ADMIN / SUPER_ADMIN |
| SOFTWARE | EMPLOYEE  | `staff_profiles.reporting_manager_id` or first ADMIN |

Super Admin / Platform Admin can always approve or reject (override).

---

## 5. Leave status

- **PENDING** → **APPROVED** or **REJECTED** (only by assigned approver or Super Admin)

---

## 6. Leave types (per tenant)

Leave types are **per tenant**: each tenant has its own set (e.g. Sick, Casual, Earned). They are stored in `leave.leave_types` with `tenant_id`.

- **Who creates leave types:** Super Admin (or any role with `leave.manage_types`). Create/update via API only.
- **Who uses leave types:** Users with `leave.create` (e.g. teachers, employees) list types with `GET /types` and pass `leave_type_id` when applying.

---

## 7. API endpoints

Base: `/api/v1/leaves`. All require auth.

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET    | `/types` | leave.read | List leave types for tenant (for apply dropdown) |
| POST   | `/types` | leave.manage_types | Create leave type (Super Admin); body: name, code, is_active |
| PUT    | `/types/{type_id}` | leave.manage_types | Update leave type (name, code, is_active) |
| POST   | `/apply` | leave.create | Apply for leave (body: leave_type_id or custom_reason, from_date, to_date, total_days) |
| GET    | `/my` | leave.read | My leave requests |
| GET    | `/pending` | leave.update | Pending requests assigned to current user |
| GET    | `` | leave.read + leave.view_all | All leaves in tenant (if view_all); else same as pending |
| POST   | `/{id}/approve` | leave.update | Approve (body: remarks?) |
| POST   | `/{id}/reject` | leave.update | Reject (body: remarks?) |

---

## 8. Database (schema_check)

- **leave.leave_types** – tenant_id, name, code, is_active
- **leave.leave_requests** – tenant_id, tenant_type, applicant_type, employee_id/student_id, leave_type_id, custom_reason, from_date, to_date, total_days, status, assigned_to_user_id, approved_by_user_id, approved_at, created_by
- **leave.leave_audit_logs** – leave_request_id, action (APPLIED/APPROVED/REJECTED), performed_by, performed_by_role, remarks, created_at

**auth.staff_profiles**: optional **reporting_manager_id** (FK auth.users) for SOFTWARE employee approver.

Run:

```bash
python -m app.db.schema_check
```

---

## 9. Validation and security

- Only **assigned_to_user_id** or **Super Admin** can approve/reject.
- Only **PENDING** requests can be approved or rejected.
- **from_date** / **to_date** validated; **total_days** ≥ 1.
- Either **leave_type_id** or **custom_reason** required.
- Overlapping leave (same applicant, overlapping dates, PENDING) is rejected.

---

## 10. Notifications (logic only)

- On **apply** → notify assigned approver (tenant-aware content).
- On **approve** / **reject** → notify applicant (tenant-aware content).

(Implementation is out of scope; integrate with your notification service.)
