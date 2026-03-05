# Global Asset Management

Reusable asset module; behavior depends on **tenant_type** (SCHOOL / COLLEGE / SOFTWARE) and **asset_user_type** (EMPLOYEE / STUDENT). All actions are permission-based and audited.

---

## 1. Permissions (role JSON)

| Key | Meaning |
|-----|--------|
| `asset.manage_types` | Create and update asset types for the tenant |
| `asset.manage_assets` | Add, update, and delete assets |
| `asset.assign` | Assign assets to users (employees or students) |
| `asset.return` | Accept returned assets |
| `asset.read` | View my assets and asset catalog |
| `asset.view_all` | View all asset assignments in the tenant |
| `asset.audit` | View asset history and audit logs |

Example (employee can see and return their assets):

```json
{
  "asset": {
    "read": true,
    "return": true
  }
}
```

Admin / Asset Manager role:

```json
{
  "asset": {
    "manage_types": true,
    "manage_assets": true,
    "assign": true,
    "return": true,
    "view_all": true,
    "audit": true
  }
}
```

---

## 2. Tenant types

Derived from `core.tenants.organization_type` (normalized to):

- **SCHOOL**
- **COLLEGE**
- **SOFTWARE**

The asset catalog and assignment patterns can differ by tenant type (for example: SCHOOL → books, projectors; SOFTWARE → laptops, monitors, access cards). The module remains tenant-scoped and does not mix assets across tenants.

---

## 3. Asset user types

Assets can be assigned to:

- **EMPLOYEE** – `user_type = "employee"` (`asset_assignments.employee_id = user_id`)
- **STUDENT** – `user_type = "student"` (`asset_assignments.student_id = user_id`)

The `asset_user_type` column ensures that only one of `employee_id` or `student_id` is populated per assignment.

---

## 4. Asset status

Each asset has a lifecycle status:

- **AVAILABLE**
- **ASSIGNED**
- **UNDER_MAINTENANCE**
- **DAMAGED**
- **LOST**
- **RETIRED**

Only **AVAILABLE** assets can be assigned. Assets that are **LOST** or **RETIRED** cannot be assigned or sent to maintenance.

---

## 5. Asset types (per tenant)

Asset types are **per tenant**: each tenant maintains its own list (Laptop, Monitor, Library Book, Lab Equipment, Mobile Device, ID Card, etc.). They are stored in `asset.asset_types` with `tenant_id`.

- **Who manages asset types:** Users with `asset.manage_types`. Create/update via API only.
- **Who uses asset types:** Users with `asset.manage_assets` and `asset.assign` use these types when creating assets and assignments.

Fields:

- `id`
- `tenant_id`
- `name`
- `code`
- `description`
- `is_active`
- `created_at`

---

## 6. Assets

Assets represent physical or digital items owned by the tenant, such as laptops, monitors, library books, projectors, lab equipment, access cards, or mobile devices.

Fields:

- `id`
- `tenant_id`
- `asset_type_id`
- `asset_name`
- `asset_code`
- `serial_number`
- `purchase_date`
- `purchase_cost`
- `warranty_expiry`
- `status` (see section 4)
- `location`
- `created_by`
- `created_at`

Example:

- Type: **Laptop**
- Asset name: "Dell Latitude 7420 – John Doe"
- Asset code: "LAP-001"
- Serial: "DELL-AXY12345"
- Status: **ASSIGNED**

---

## 7. Asset assignment

Assets can be assigned to employees or students via `asset.asset_assignments`.

Fields:

- `id`
- `tenant_id`
- `asset_id`
- `asset_user_type` (**EMPLOYEE** / **STUDENT**)
- `employee_id` (when `asset_user_type = EMPLOYEE`)
- `student_id` (when `asset_user_type = STUDENT`)
- `assigned_by`
- `assigned_at`
- `expected_return_date`
- `returned_at`
- `return_condition`
- `status` (**ASSIGNED**, **RETURNED**, **OVERDUE**)

Rules:

- Only **AVAILABLE** assets can be assigned.
- On assignment, the asset status becomes **ASSIGNED**.
- On return, the assignment status becomes **RETURNED** and the asset status becomes **AVAILABLE** (unless separately marked damaged, lost, or retired).
- An assignment is marked **OVERDUE** when `expected_return_date` is in the past and status is still **ASSIGNED**.

---

## 8. Asset maintenance

Maintenance records (repairs and servicing) are stored in `asset.asset_maintenance`.

Fields:

- `id`
- `tenant_id`
- `asset_id`
- `reported_issue`
- `maintenance_type` (**REPAIR** / **SERVICE**)
- `reported_by`
- `assigned_technician`
- `maintenance_status` (**OPEN**, **IN_PROGRESS**, **COMPLETED**)
- `cost`
- `started_at`
- `completed_at`
- `created_at`

Rules:

- Maintenance cannot be created for **LOST** or **RETIRED** assets.
- When maintenance is reported for an **AVAILABLE** asset, its status becomes **UNDER_MAINTENANCE**.
- On maintenance completion, assets in **UNDER_MAINTENANCE** move back to **AVAILABLE**.

---

## 9. Asset audit logs

Every important action is recorded in `asset.asset_audit_logs`.

Fields:

- `id`
- `tenant_id`
- `asset_id`
- `action`
- `performed_by`
- `performed_by_role`
- `remarks`
- `created_at`

Actions include:

- **CREATED**
- **UPDATED**
- **ASSIGNED**
- **RETURNED**
- **MAINTENANCE_STARTED**
- **MAINTENANCE_COMPLETED**
- **STATUS_CHANGED** (reserved for future explicit status change actions)

---

## 10. API endpoints

Base: `/api/v1/assets`. All endpoints require auth.

### Asset types

| Method | Path          | Permission          | Description |
|--------|---------------|---------------------|-------------|
| GET    | `/types`      | `asset.read`        | List asset types for tenant (for dropdowns) |
| POST   | `/types`      | `asset.manage_types`| Create asset type (per tenant) |
| PUT    | `/types/{id}` | `asset.manage_types`| Update asset type |
| DELETE | `/types/{id}` | `asset.manage_types`| Delete asset type (if no assets exist) |

### Assets

| Method | Path           | Permission          | Description |
|--------|----------------|---------------------|-------------|
| GET    | ``             | `asset.read`        | List assets for tenant |
| POST   | ``             | `asset.manage_assets` | Create asset |
| GET    | `/{asset_id}`  | `asset.read`        | Get single asset |
| PUT    | `/{asset_id}`  | `asset.manage_assets` | Update asset |
| DELETE | `/{asset_id}`  | `asset.manage_assets` | Delete asset (if no assignments) |

### Assignments

| Method | Path                     | Permission       | Description |
|--------|--------------------------|------------------|-------------|
| POST   | `/assign`               | `asset.assign`   | Assign asset to EMPLOYEE/STUDENT |
| POST   | `/return/{assignment_id}` | `asset.return` | Mark assignment as returned |
| GET    | `/my`                   | `asset.read`     | Assets assigned to current user |
| GET    | `/assigned`             | `asset.view_all` | All active (ASSIGNED/OVERDUE) assignments |
| GET    | `/history/{asset_id}`   | `asset.audit`    | Full history (asset + assignments + maintenance + audit logs) |

### Maintenance

| Method | Path                          | Permission          | Description |
|--------|-------------------------------|---------------------|-------------|
| POST   | `/maintenance/report`        | `asset.manage_assets` | Report maintenance issue for an asset |
| PUT    | `/maintenance/{id}/start`    | `asset.manage_assets` | Mark maintenance as IN_PROGRESS |
| PUT    | `/maintenance/{id}/complete` | `asset.manage_assets` | Complete maintenance and update cost/status |
| GET    | `/maintenance`               | `asset.read`        | List maintenance records for tenant |

### Audit

| Method | Path               | Permission    | Description |
|--------|--------------------|---------------|-------------|
| GET    | `/audit/{asset_id}`| `asset.audit` | Audit logs for one asset |

---

## 11. Validation rules

- Only **AVAILABLE** assets can be assigned.
- Assets in **UNDER_MAINTENANCE**, **LOST**, or **RETIRED** cannot be assigned.
- Returned assets set assignment status to **RETURNED** and, if appropriate, asset status back to **AVAILABLE**.
- Assignments with `expected_return_date` earlier than today and status **ASSIGNED** are marked **OVERDUE**.
- For assignments:
  - When `asset_user_type = EMPLOYEE` → `employee_id` required, `student_id` must be null.
  - When `asset_user_type = STUDENT` → `student_id` required, `employee_id` must be null.

---

## 12. Notifications (logic only)

Hook into your notification service as needed:

- On **ASSIGNED** → notify assignee (employee or student).
- When return due date is near (e.g. 1–3 days before `expected_return_date`) → remind assignee.
- On **RETURNED** → notify asset manager / admin.
- On **MAINTENANCE_COMPLETED** → notify asset manager / requester.

Implementation is out of scope for this module; integrate using your existing notification infrastructure.

---

## 13. Database (schema_check)

- **asset.asset_types** – tenant-scoped asset types (name, code, description, is_active).
- **asset.assets** – assets owned by tenant (type, code, serial, purchase details, status, location, created_by).
- **asset.asset_assignments** – assignment records to employees or students with expected/actual return.
- **asset.asset_maintenance** – maintenance records (repairs/services) for assets.
- **asset.asset_audit_logs** – audit trail for asset lifecycle actions.

Run:

```bash
python -m app.db.schema_check
```

---

## 14. Security

- All queries are scoped by `tenant_id`.
- Users can only see and act on assets within their own tenant.
- Management actions require:
  - `asset.manage_assets` for asset CRUD and maintenance operations.
  - `asset.assign` for assigning assets.
  - `asset.return` for accepting returns.
- Read and audit views follow `asset.read`, `asset.view_all`, and `asset.audit` permissions.

---

## 15. Future extensions

- QR code / barcode scanning for fast lookup.
- Asset depreciation and amortization tracking.
- Bulk asset import from CSV/Excel.
- Periodic inventory audit workflows.
- Integration with procurement / purchasing systems.

