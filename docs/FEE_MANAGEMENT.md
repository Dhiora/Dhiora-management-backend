# Fee Management Module

Production-ready Fee Management for multi-tenant School ERP. Financial audit safety, academic year scoping, and role-based access.

## Architecture

- **Multi-tenant**: All tables include `tenant_id`
- **Academic year scoped**: Fee structures, assignments, discounts, and payments are per academic year
- **Decimal precision**: All monetary values use `Numeric(12, 2)`
- **Audit trail**: `fee_audit_logs` records CREATE/UPDATE/DEACTIVATE for discounts, payments, and assignments

## Tables

| Table | Schema | Description |
|-------|--------|-------------|
| fee_components | school | Master: Tuition, Bus, Exam, Hostel |
| class_fee_structures | school | Fee per class per academic year |
| student_fee_assignments | school | Frozen snapshot per student; `original_amount` immutable |
| student_fee_discounts | school | Multiple discounts per assignment |
| payment_transactions | school | Payments; updates assignment status |
| fee_audit_logs | school | Financial audit trail |

## API Endpoints

### Fee Components
- `POST /api/v1/fee-components` – Create component
- `GET /api/v1/fee-components?active_only=` – List (`active_only` optional, default `true`)
- `PATCH /api/v1/fee-components/{fee_component_id}` – Update

Request body for create:

```json
{
  "name": "Tuition",
  "code": "TUITION",
  "description": "Annual tuition fee",
  "component_category": "ACADEMIC",
  "allow_discount": true,
  "is_mandatory_default": true
}
```

`component_category`: `ACADEMIC` \| `TRANSPORT` \| `HOSTEL` \| `OTHER`. Update supports optional fields: `name`, `description`, `component_category`, `allow_discount`, `is_mandatory_default`, `is_active`.

### Class Fee Structure
- `POST /api/v1/fees/class` – Create structure
- `GET /api/v1/fees/class?academic_year_id=&class_id=` – List (`class_id` optional; filter by class)
- `GET /api/v1/fees/class/all?academic_year_id=&active_only=` – Read all fees for all classes (grouped). `active_only` optional, default `true`.

Request body for create:

```json
{
  "academic_year_id": "uuid",
  "class_id": "uuid",
  "fee_component_id": "uuid",
  "amount": 15000,
  "frequency": "one_time",
  "due_date": "2025-04-01",
  "is_mandatory": true
}
```

`frequency`: `one_time` \| `monthly` \| `term_wise`. `due_date` optional.

### Student Fee Assignment
- `POST /api/v1/fees/assign/{student_id}` – Assign TEMPLATE fees (mandatory auto + optional selection + custom amount override)
- `GET /api/v1/fees/student/{student_id}?academic_year_id=` – List assignments (`academic_year_id` optional; omit to get all years)

Request body for assign:

```json
{
  "academic_year_id": "uuid",
  "optional_components": [
    { "class_fee_structure_id": "uuid", "custom_amount": 2500 }
  ]
}
```

### Custom Student Fees
- `POST /api/v1/fees/custom/{student_id}` – Add a CUSTOM student-level fee row

Request body:

```json
{
  "academic_year_id": "uuid",
  "custom_name": "Attendance Condonation",
  "amount": 1500,
  "reason": "Low attendance"
}
```

### Discounts
- `POST /api/v1/fees/discount/{student_fee_assignment_id}` – Add discount
- `PATCH /api/v1/fees/discount/{discount_id}/deactivate` – Deactivate discount (no body)

Request body for add discount:

```json
{
  "discount_name": "Sibling Concession",
  "discount_category": "MASTER",
  "discount_type": "percentage",
  "discount_value": 10,
  "reason": "Second child"
}
```

`discount_category`: `MASTER` \| `CUSTOM` \| `SYSTEM`. `discount_type`: `fixed` \| `percentage`. Discounts are not allowed when the fee component has `allow_discount: false`.

### Payments
- `POST /api/v1/fees/pay/{student_fee_assignment_id}` – Record payment
- `GET /api/v1/fees/payment-history/{student_id}?academic_year_id=` – Payment history (`academic_year_id` optional)

Request body for record payment:

```json
{
  "amount_paid": 5000,
  "payment_mode": "UPI",
  "transaction_reference": "TXN123",
  "paid_at": "2025-02-17T10:00:00Z"
}
```

`payment_mode`: `UPI` \| `CARD` \| `CASH` \| `BANK`. `transaction_reference` and `paid_at` optional; `paid_at` defaults to server time.

### Report
- `GET /api/v1/fees/report?academic_year_id=&class_id=&fee_status=` – Fee report by class/status. `class_id` and `fee_status` optional. `fee_status`: `unpaid` \| `partial` \| `paid`.

## RBAC

Requires `fees` module permissions: `create`, `read`, `update` (and `delete` if added). Admin/Accountant roles should be granted these.

## Business Rules

- `original_amount` on student_fee_assignment is **never** updated
- Total discount cannot exceed `original_amount`
- Payment cannot exceed `final_amount` (remaining balance)
- Discount > 20% requires Admin role (`SUPER_ADMIN`, `PLATFORM_ADMIN`, or `ADMIN`)
- Discounts are not allowed on assignments whose fee component has `allow_discount: false`
- All financial updates run inside DB transactions
- Fee operations (create/update/assign/discount/payment) require writable (ACTIVE, non-CLOSED) academic year

## Migration

Run schema check to create tables:

```bash
python -m app.db.schema_check
```
