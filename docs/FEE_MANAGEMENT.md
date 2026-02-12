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
- `GET /api/v1/fee-components` – List (optional `active_only`)
- `PATCH /api/v1/fee-components/{id}` – Update

### Class Fee Structure
- `POST /api/v1/fees/class` – Create structure
- `GET /api/v1/fees/class?academic_year_id=&class_id=` – List
- `GET /api/v1/fees/class/all?academic_year_id=` – Read all fees for all classes (grouped)

### Student Fee Assignment
- `POST /api/v1/fees/assign/{student_id}` – Assign TEMPLATE fees (mandatory auto + optional selection + custom amount override)
- `GET /api/v1/fees/student/{student_id}?academic_year_id=` – List assignments

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
- `PATCH /api/v1/fees/discount/{discount_id}/deactivate` – Deactivate discount

### Payments
- `POST /api/v1/fees/pay/{student_fee_assignment_id}` – Record payment
- `GET /api/v1/fees/payment-history/{student_id}?academic_year_id=` – Payment history

### Report
- `GET /api/v1/fees/report?academic_year_id=&class_id=&fee_status=` – Fee report by class/status

## RBAC

Requires `fees` module permissions: `create`, `read`, `update` (and `delete` if added). Admin/Accountant roles should be granted these.

## Business Rules

- `original_amount` on student_fee_assignment is **never** updated
- Total discount cannot exceed `original_amount`
- Payment cannot exceed `final_amount` (remaining balance)
- Discount > 20% requires Admin role
- All financial updates run inside DB transactions
- Fee operations require writable (ACTIVE, non-CLOSED) academic year

## Migration

Run schema check to create tables:

```bash
python -m app.db.schema_check
```
