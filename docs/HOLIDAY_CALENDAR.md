## Holiday Calendar API Documentation

Complete reference for the **Holiday Calendar** module used by attendance, payroll, and academic calendar.

**Base URL**: `/api/v1/holiday-calendar`  
**Auth**: All endpoints require a valid JWT (`Authorization: Bearer <token>`).  
**Scope**: All data is tenant-specific via `tenant_id` from the token.

---

### 1. Data Model

**Table**: `school.holiday_calendar`

**Columns**:
- `id` (UUID, PK)
- `tenant_id` (UUID, FK → `core.tenants.id`, required)
- `academic_year_id` (UUID, FK → `core.academic_years.id`, required)
- `holiday_name` (string, required, max 255)
- `holiday_date` (date, required)
- `month` (integer, required, 1–12, derived from `holiday_date`)
- `year` (integer, required, derived from `holiday_date`)
- `description` (text, optional)
- `created_at` (timestamp with timezone)
- `updated_at` (timestamp with timezone)
- `created_by` (UUID, FK → `auth.users.id`, optional)
- `updated_by` (UUID, FK → `auth.users.id`, optional)

**Constraints**:
- `UNIQUE (tenant_id, academic_year_id, holiday_date)`  
  Ensures no duplicate holiday dates within the same tenant + academic year.
- `CHECK (month >= 1 AND month <= 12)`  
  Ensures `month` stays in the valid range.

---

### 2. Permissions and Roles

Permissions are enforced via the `holiday_calendar` module key:

- `holiday_calendar.create`
- `holiday_calendar.read`
- `holiday_calendar.update`
- `holiday_calendar.delete`

**Recommended mapping**:
- **SUPER_ADMIN / ADMIN**: `create`, `read`, `update`, `delete`
- **TEACHER / STUDENT / STAFF**: `read` only

`SUPER_ADMIN` and `PLATFORM_ADMIN` automatically bypass individual permission checks.

---

### 3. Schemas

#### 3.1 HolidayCreate (request)

Used in **POST /**:

```json
{
  "academic_year_id": "uuid",
  "holiday_name": "Republic Day",
  "holiday_date": "2026-01-26",
  "description": "Indian National Holiday"
}
```

- `academic_year_id`: UUID, required.
- `holiday_name`: string, max 255, required.
- `holiday_date`: date (YYYY-MM-DD), required.
- `description`: string, optional.
- `month` and `year` are automatically derived from `holiday_date` on the server.

#### 3.2 HolidayUpdate (request)

Used in **PUT /{holiday_id}**. All fields are optional:

```json
{
  "holiday_name": "Republic Day",
  "holiday_date": "2026-01-26",
  "description": "Updated description"
}
```

- Allows partial updates (name/date/description).
- `academic_year_id` cannot be changed through this API.

#### 3.3 HolidayResponse (response)

Returned by create, list, and update endpoints:

```json
{
  "id": "uuid",
  "academic_year_id": "uuid",
  "holiday_name": "Republic Day",
  "holiday_date": "2026-01-26",
  "month": 1,
  "year": 2026,
  "description": "Indian National Holiday",
  "created_at": "2025-12-15T10:00:00Z",
  "updated_at": "2025-12-15T10:00:00Z"
}
```

---

### 4. Endpoints

#### 4.1 Create Holiday

**Method**: `POST`  
**URL**: `/api/v1/holiday-calendar`  
**Permission**: `holiday_calendar.create`

**Request body**: `HolidayCreate`

Example:

```json
{
  "academic_year_id": "a36e8d38-d052-4107-a3cb-b34f3e098cb1",
  "holiday_name": "Republic Day",
  "holiday_date": "2026-01-26",
  "description": "Indian National Holiday"
}
```

**Validation rules**:
- Academic year must exist for the tenant:
  - `academic_year.tenant_id == current_user.tenant_id`.
- `holiday_date` must be within the academic year range:
  - `start_date <= holiday_date <= end_date`.
- No other holiday exists for the same `tenant_id + academic_year_id + holiday_date`.

**Errors**:
- `400 "Invalid academic year"` – if academic year does not belong to tenant.
- `400 "Holiday date must be within the academic year range"`.
- `400 "Holiday already exists for this date in the academic year"`.

**Response (201 Created)**: `HolidayResponse`.

---

#### 4.2 List Holidays

**Method**: `GET`  
**URL**: `/api/v1/holiday-calendar`  
**Permission**: `holiday_calendar.read`

**Query parameters**:

- `academic_year_id` (UUID, required)
- `month` (int, optional, 1–12)

Examples:

- All holidays in the academic year:

  `/api/v1/holiday-calendar?academic_year_id=a36e8d38-d052-4107-a3cb-b34f3e098cb1`

- Holidays in January:

  `/api/v1/holiday-calendar?academic_year_id=a36e8d38-d052-4107-a3cb-b34f3e098cb1&month=1`

**Validation rules**:
- Academic year must exist for the tenant.
- If `month` provided:
  - Must be between 1 and 12, or:
  - `400 "month must be between 1 and 12"`.

**Response (200 OK)**: `List[HolidayResponse]` ordered by `holiday_date`.

---

#### 4.3 Calendar View

**Method**: `GET`  
**URL**: `/api/v1/holiday-calendar/calendar`  
**Permission**: `holiday_calendar.read`

**Query parameters**:

- `academic_year_id` (UUID, required)
- `month` (int, required, 1–12)

Example:

`/api/v1/holiday-calendar/calendar?academic_year_id=a36e8d38-d052-4107-a3cb-b34f3e098cb1&month=1`

**Response (200 OK)**:

```json
{
  "2026-01-01": "New Year",
  "2026-01-14": "Pongal",
  "2026-01-26": "Republic Day"
}
```

- Keys: ISO date strings from `holiday_date`.
- Values: `holiday_name`.

This endpoint is ideal for rendering a monthly calendar UI.

---

#### 4.4 Update Holiday

**Method**: `PUT`  
**URL**: `/api/v1/holiday-calendar/{holiday_id}`  
**Permission**: `holiday_calendar.update`

**Path parameter**:
- `holiday_id`: UUID (required).

**Request body**: `HolidayUpdate` (any subset of fields).

Example:

```json
{
  "holiday_name": "Republic Day (Observed)",
  "holiday_date": "2026-01-27",
  "description": "Shifted due to internal schedule"
}
```

**Validation rules**:
- If holiday not found for this tenant:
  - `404 "Holiday not found"`.
- If `holiday_date` changed:
  - `holiday_date` must remain within the same academic year's date range.
  - Date must remain unique in `(tenant_id, academic_year_id, holiday_date)`:
    - Otherwise `400 "Another holiday already exists for this date in the academic year"`.

**Response (200 OK)**: Updated `HolidayResponse`.

---

#### 4.5 Delete Holiday

**Method**: `DELETE`  
**URL**: `/api/v1/holiday-calendar/{holiday_id}`  
**Permission**: `holiday_calendar.delete`

**Path parameter**:
- `holiday_id`: UUID (required).

**Business rules**:

1. **Cannot delete past holidays**:
   - If `holiday_date < current_date`:
     - Return `400` with:
       - `"Past holidays cannot be deleted"`.

2. **If deletion allowed (holiday today or in the future)**:
   - Call payroll integration hook:
     - `remove_holiday_references_from_payroll(tenant_id, academic_year_id, holiday_id)`
     - Currently a **no-op placeholder**; payroll module should implement removing references from payslip attachments / cached calculations.
   - Delete the record from `school.holiday_calendar`.

**Response (204 No Content)**: Empty body on success.

---

### 5. Integration Notes

- **Attendance**:
  - Use `GET /api/v1/holiday-calendar` or `/calendar` to determine non-working days per academic year/month.
- **Payroll**:
  - Should rely on the same holiday calendar to decide paid/unpaid holidays, working days count, etc.
  - Implement `remove_holiday_references_from_payroll` to keep payslips consistent when future holidays are deleted.
- **Academic Calendar / UI**:
  - Use `/calendar` for monthly calendar widgets.
  - Use list endpoint for admin views and holiday management screens.

---

### 6. Summary of Endpoints

| Method | URL                                    | Description                                      | Permission                |
|--------|----------------------------------------|--------------------------------------------------|---------------------------|
| POST   | `/api/v1/holiday-calendar`             | Create a holiday                                 | `holiday_calendar.create` |
| GET    | `/api/v1/holiday-calendar`             | List holidays by academic year (optional month)  | `holiday_calendar.read`   |
| GET    | `/api/v1/holiday-calendar/calendar`    | Date → name mapping for a given month            | `holiday_calendar.read`   |
| PUT    | `/api/v1/holiday-calendar/{holiday_id}`| Update a holiday                                 | `holiday_calendar.update` |
| DELETE | `/api/v1/holiday-calendar/{holiday_id}`| Delete a non-past holiday                         | `holiday_calendar.delete` |

