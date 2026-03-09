# Payroll and Payslip API Documentation

Reference for **Payroll Management** and **Payslip** APIs in the multi-tenant HRMS backend.

**Base URL:** `http://localhost:8000` (or your deployed host)  
**Prefix:** `/api/v1/payroll`  
**Auth:** All endpoints require a valid JWT in the `Authorization` header (e.g. `Bearer <token>`).  
**Permissions:** Use the `payroll` module: `create`, `read`, `update`, `delete` as noted per endpoint.

---

## Table of contents

| Section | Description |
|--------|-------------|
| [1. Payroll run](#1-payroll-run) | Create run, list runs, get run, issue payslips, list run records |
| [2. Salary calculation](#2-salary-calculation) | Calculate employee salary (gross, deductions, net) |
| [3. Payroll components (master)](#3-payroll-components-master) | Create, list, update components (Basic, HRA, PF, etc.) |
| [4. Employee salary components (assignments)](#4-employee-salary-components-assignments) | Assign, **list all employees with assignments**, **edit amount**, **delete assignment** |
| [5. Payslip templates](#5-payslip-templates) | Create, list, update, delete templates |
| [6. Payslip template variables](#6-payslip-template-variables) | Placeholders for rendering |
| [7. Enums reference](#7-enums-reference) | Component type, payment mode, run status |
| [8. Typical flow](#8-typical-flow) | Step-by-step usage |

**Quick links – employee assignments (list / edit / delete):**

- **[4.3 List all employees with assigned salary components](#43-list-all-employees-with-assigned-salary-components)** — `GET /api/v1/payroll/employee-assignments`
- **[4.4 Update employee salary component](#44-update-employee-salary-component-assignment)** — `PUT /api/v1/payroll/employee-components/{assignment_id}`
- **[4.5 Delete employee salary component](#45-delete-employee-salary-component-assignment)** — `DELETE /api/v1/payroll/employee-components/{assignment_id}`

---

## Response format

All payroll endpoints return a **consistent wrapper**:

```json
{
  "success": true,
  "message": "Human-readable message",
  "data": { ... }
}
```

- **Single resource:** `data` is the resource object.
- **List:** `data` is `{ "items": [ ... ] }`.
- **Delete:** `data` is `null`.

Errors return standard HTTP status codes (400, 403, 404, 409) with a `detail` string (not wrapped).

---

## 1. Payroll run

### 1.1 Create payroll run

**POST** `/api/v1/payroll/run`

Creates a payroll run for the given month/year: loads all active employees, calculates salary from assigned components, and bulk-creates payroll employee records. Run status is `draft`.

**Permission:** `payroll.create`

**Request body:**

| Field  | Type   | Required | Description                    |
|--------|--------|----------|--------------------------------|
| month  | string | Yes      | Month, e.g. `"01"`, `"03"`, `"January"` |
| year   | string | Yes      | Year, e.g. `"2025"`            |

**Example payload:**

```json
{
  "month": "03",
  "year": "2025"
}
```

**Response (201):**

```json
{
  "success": true,
  "message": "Payroll run created",
  "data": {
    "id": "uuid",
    "tenant_id": "uuid",
    "month": "03",
    "year": "2025",
    "start_date": "2025-03-01",
    "end_date": "2025-03-31",
    "status": "draft",
    "created_at": "2025-03-05T10:00:00Z",
    "updated_at": "2025-03-05T10:00:00Z"
  }
}
```

**Errors:**  
- **409** – A payroll run already exists for this tenant + month + year.

---

### 1.2 List payroll runs

**GET** `/api/v1/payroll/run`

Returns all payroll runs for the tenant, newest first.

**Permission:** `payroll.read`

**Query parameters:** None.

**Response (200):**

```json
{
  "success": true,
  "message": "Payroll runs retrieved",
  "data": {
    "items": [
      {
        "id": "uuid",
        "tenant_id": "uuid",
        "month": "03",
        "year": "2025",
        "start_date": "2025-03-01",
        "end_date": "2025-03-31",
        "status": "draft",
        "created_at": "2025-03-05T10:00:00Z",
        "updated_at": "2025-03-05T10:00:00Z"
      }
    ]
  }
}
```

---

### 1.3 Get payroll run by ID

**GET** `/api/v1/payroll/run/{run_id}`

**Permission:** `payroll.read`

**Path parameters:**

| Name   | Type | Description   |
|--------|------|---------------|
| run_id | UUID | Payroll run ID |

**Response (200):** Same single-run object as in **1.1** (inside `data`).

**Errors:** **404** – Run not found.

---

### 1.4 Issue payslips

**POST** `/api/v1/payroll/run/{run_id}/issue`

Generates a payslip record per employee in the run (using the tenant’s default template if set), sets run status to `issued`.

**Permission:** `payroll.create`

**Path parameters:**

| Name   | Type | Description   |
|--------|------|---------------|
| run_id | UUID | Payroll run ID |

**Request body:** None.

**Response (200):**

```json
{
  "success": true,
  "message": "Payslips issued",
  "data": {
    "id": "uuid",
    "tenant_id": "uuid",
    "month": "03",
    "year": "2025",
    "start_date": "2025-03-01",
    "end_date": "2025-03-31",
    "status": "issued",
    "created_at": "2025-03-05T10:00:00Z",
    "updated_at": "2025-03-05T10:00:00Z"
  }
}
```

**Errors:**  
- **400** – Run is already issued.  
- **404** – Run not found.

---

### 1.5 List payroll run records (employee records)

**GET** `/api/v1/payroll/run/{run_id}/records`

Returns per-employee payroll records for the run (gross, deductions, net, payment mode).

**Permission:** `payroll.read`

**Path parameters:**

| Name   | Type | Description   |
|--------|------|---------------|
| run_id | UUID | Payroll run ID |

**Response (200):**

```json
{
  "success": true,
  "message": "Payroll records retrieved",
  "data": {
    "items": [
      {
        "id": "uuid",
        "tenant_id": "uuid",
        "payroll_run_id": "uuid",
        "employee_id": "uuid",
        "gross_salary": "50000.00",
        "total_deductions": "5000.00",
        "net_salary": "45000.00",
        "payment_mode": "bank",
        "status": "draft",
        "created_at": "2025-03-05T10:00:00Z",
        "updated_at": "2025-03-05T10:00:00Z"
      }
    ]
  }
}
```

---

## 2. Salary calculation

### 2.1 Calculate employee salary

**GET** `/api/v1/payroll/salary/calculate/{employee_id}`

Computes gross, total deductions, and net from the employee’s assigned salary components (earnings vs deductions).

**Permission:** `payroll.read`

**Path parameters:**

| Name       | Type | Description    |
|------------|------|----------------|
| employee_id| UUID | Employee (user) ID |

**Response (200):**

```json
{
  "success": true,
  "message": "Salary calculated",
  "data": {
    "gross_salary": "50000.00",
    "total_deductions": "5000.00",
    "net_salary": "45000.00"
  }
}
```

---

## 3. Payroll components (master)

### 3.1 Create component

**POST** `/api/v1/payroll/components`

Defines a salary component (e.g. Basic Salary, HRA, PF). `code` is stored uppercase and must be unique per tenant.

**Permission:** `payroll.create`

**Request body:**

| Field            | Type    | Required | Description                          |
|------------------|---------|----------|--------------------------------------|
| name             | string  | Yes      | Display name (1–100 chars)           |
| code             | string  | Yes      | Code (1–50 chars), unique per tenant |
| type             | string  | Yes      | `"earning"` or `"deduction"`        |
| calculation_type | string  | Yes      | `"fixed"` or `"percentage"`          |
| default_value    | decimal | No       | Default amount or %                  |
| is_active        | boolean | No       | Default `true`                      |

**Example payload:**

```json
{
  "name": "Basic Salary",
  "code": "BASIC",
  "type": "earning",
  "calculation_type": "fixed",
  "default_value": 40000,
  "is_active": true
}
```

**Response (201):**

```json
{
  "success": true,
  "message": "Payroll component created",
  "data": {
    "id": "uuid",
    "tenant_id": "uuid",
    "name": "Basic Salary",
    "code": "BASIC",
    "type": "earning",
    "calculation_type": "fixed",
    "default_value": 40000,
    "is_active": true,
    "created_at": "2025-03-05T10:00:00Z",
    "updated_at": "2025-03-05T10:00:00Z"
  }
}
```

---

### 3.2 List components

**GET** `/api/v1/payroll/components`

**Permission:** `payroll.read`

**Query parameters:**

| Name       | Type    | Default | Description                    |
|------------|---------|---------|--------------------------------|
| active_only| boolean | true    | When true, only active components |

**Response (200):**

```json
{
  "success": true,
  "message": "Payroll components retrieved",
  "data": {
    "items": [
      {
        "id": "uuid",
        "tenant_id": "uuid",
        "name": "Basic Salary",
        "code": "BASIC",
        "type": "earning",
        "calculation_type": "fixed",
        "default_value": 40000,
        "is_active": true,
        "created_at": "2025-03-05T10:00:00Z",
        "updated_at": "2025-03-05T10:00:00Z"
      }
    ]
  }
}
```

---

### 3.3 Update component

**PUT** `/api/v1/payroll/components/{component_id}`

**Permission:** `payroll.update`

**Path parameters:**

| Name         | Type | Description      |
|--------------|------|------------------|
| component_id | UUID | Component ID     |

**Request body:** All fields optional; only sent fields are updated.

| Field            | Type    | Description                          |
|------------------|---------|--------------------------------------|
| name             | string  | Display name (1–100 chars)           |
| code             | string  | Code (1–50 chars)                    |
| type             | string  | `"earning"` or `"deduction"`        |
| calculation_type | string  | `"fixed"` or `"percentage"`         |
| default_value    | decimal | Default amount or %                  |
| is_active        | boolean | Active flag                          |

**Response (200):** Same component object as in **3.1** (inside `data`).

**Errors:** **404** – Component not found.

---

## 4. Employee salary components (assignments)

### 4.1 Assign component to employee

**POST** `/api/v1/payroll/employee-components`

Assigns a payroll component to an employee with a specific amount. One assignment per (employee, component) per tenant.

**Permission:** `payroll.create`

**Request body:**

| Field        | Type    | Required | Description          |
|-------------|---------|----------|----------------------|
| employee_id | UUID    | Yes      | Employee (user) ID   |
| component_id| UUID    | Yes      | Payroll component ID|
| amount      | decimal | Yes      | Amount (≥ 0)         |

**Example payload:**

```json
{
  "employee_id": "uuid-of-employee",
  "component_id": "uuid-of-basic-component",
  "amount": 40000
}
```

**Response (201):**

```json
{
  "success": true,
  "message": "Employee salary component assigned",
  "data": {
    "id": "uuid",
    "tenant_id": "uuid",
    "employee_id": "uuid",
    "component_id": "uuid",
    "amount": "40000.00",
    "created_at": "2025-03-05T10:00:00Z",
    "updated_at": "2025-03-05T10:00:00Z"
  }
}
```

**Errors:** **409** – Employee already has this component assigned.

---

### 4.2 List employee salary components

**GET** `/api/v1/payroll/employees/{employee_id}/salary-components`

**Permission:** `payroll.read`

**Path parameters:**

| Name        | Type | Description     |
|-------------|------|-----------------|
| employee_id | UUID | Employee (user) ID |

**Response (200):**

```json
{
  "success": true,
  "message": "Employee salary components retrieved",
  "data": {
    "items": [
      {
        "id": "uuid",
        "tenant_id": "uuid",
        "employee_id": "uuid",
        "component_id": "uuid",
        "amount": "40000.00",
        "created_at": "2025-03-05T10:00:00Z",
        "updated_at": "2025-03-05T10:00:00Z"
      }
    ]
  }
}
```

---

### 4.3 List all employees with assigned salary components

**GET** `/api/v1/payroll/employee-assignments`

Returns all active employees with their assigned salary components (component name, code, type, amount), plus calculated gross, total deductions, and net salary. Use each assignment’s **id** for edit (PUT) or delete (DELETE).

**Permission:** `payroll.read`

**Query parameters:** None.

**Response (200):**

```json
{
  "success": true,
  "message": "Employee assignments retrieved",
  "data": {
    "items": [
      {
        "employee_id": "uuid",
        "employee_name": "John Doe",
        "salary_components": [
          {
            "id": "uuid",
            "component_id": "uuid",
            "component_name": "Basic Salary",
            "component_code": "BASIC",
            "component_type": "earning",
            "amount": "40000.00"
          },
          {
            "id": "uuid",
            "component_id": "uuid",
            "component_name": "PF",
            "component_code": "PF",
            "component_type": "deduction",
            "amount": "4800.00"
          }
        ],
        "gross_salary": "50000.00",
        "total_deductions": "5000.00",
        "net_salary": "45000.00"
      }
    ]
  }
}
```

Each item in **salary_components** has an **id** — use this as `assignment_id` for **4.4** (update) and **4.5** (delete).

---

### 4.4 Update employee salary component (assignment)

**PUT** `/api/v1/payroll/employee-components/{assignment_id}`

Updates the amount for an existing employee salary component assignment. `assignment_id` is the **id** of the assignment (from **4.3** or **4.2**).

**Permission:** `payroll.update`

**Path parameters:**

| Name           | Type | Description                        |
|----------------|------|------------------------------------|
| assignment_id  | UUID | Assignment ID (EmployeeSalaryComponent id) |

**Request body:**

| Field  | Type    | Required | Description     |
|--------|---------|----------|-----------------|
| amount | decimal | Yes      | New amount (≥ 0) |

**Example payload:**

```json
{
  "amount": 42000
}
```

**Response (200):**

```json
{
  "success": true,
  "message": "Employee salary component updated",
  "data": {
    "id": "uuid",
    "tenant_id": "uuid",
    "employee_id": "uuid",
    "component_id": "uuid",
    "amount": "42000.00",
    "created_at": "2025-03-05T10:00:00Z",
    "updated_at": "2025-03-05T10:00:00Z"
  }
}
```

**Errors:** **400** – amount not provided. **404** – Assignment not found.

---

### 4.5 Delete employee salary component (assignment)

**DELETE** `/api/v1/payroll/employee-components/{assignment_id}`

Removes an employee salary component assignment. `assignment_id` is the **id** of the assignment (from **4.3** or **4.2**).

**Permission:** `payroll.delete`

**Path parameters:**

| Name           | Type | Description                        |
|----------------|------|------------------------------------|
| assignment_id  | UUID | Assignment ID (EmployeeSalaryComponent id) |

**Request body:** None.

**Response (200):**

```json
{
  "success": true,
  "message": "Employee salary component removed",
  "data": null
}
```

**Errors:** **404** – Assignment not found.

---

## 5. Payslip templates

Maximum **5 templates per tenant**. Creating when already at 5 returns **400** with message: `"Maximum 5 templates allowed per tenant"`.

A **template** defines the **layout** of the payslip: where the title goes, where text and variables appear, and where tables (e.g. salary components) are placed. Users design the template by adding **blocks** and setting their **order** (position). Each block can be:

- **Heading** – Static title (e.g. top heading, bottom “Thank you”)
- **Text + variable** – A label and a value (the value can be a variable like `{{employee_name}}`)
- **Table** – A section with a title and rows (label + value per row; values can be variables like `{{basic_salary}}`)

The frontend can let users **move blocks** (change `order`) to change the position of each part of the payslip.

---

### 5.1 Template design: `template_json` structure

`template_json` is a single object with a **`blocks`** array. Each block has an **`order`** (number) so you can position and reorder blocks (e.g. top = lower number, bottom = higher number). Block types:

| Block type        | Description |
|-------------------|-------------|
| `heading`         | Single line of text (e.g. "Salary Slip", "Thank You"). |
| `text_with_variable` | A **label** (static text) and a **value** (static or variable like `{{employee_name}}`). |
| `table`           | A **title** (e.g. "Earnings", "Deductions") and **rows**: each row has `label` and `value`; `value` can be a variable (e.g. `{{basic_salary}}`). |

**Block shape (common):**

| Field     | Type   | Required | Description |
|-----------|--------|----------|-------------|
| id        | string | Yes      | Unique id for the block (e.g. `"block-1"`). |
| type      | string | Yes      | `heading` \| `text_with_variable` \| `table` |
| order     | number | Yes      | Position in the document (lower = higher on page). Users move blocks by changing order. |

**For `type: "heading"`:**

| Field     | Type   | Description |
|-----------|--------|-------------|
| content   | string | The heading text. |

**For `type: "text_with_variable"`:**

| Field     | Type   | Description |
|-----------|--------|-------------|
| label     | string | Static label (e.g. "Employee:", "Period:"). |
| value     | string | Static text or variable, e.g. `"{{employee_name}}"`, `"{{period_start}} to {{period_end}}"`. |

**For `type: "table"`:**

| Field     | Type   | Description |
|-----------|--------|-------------|
| title     | string | Section title (e.g. "Earnings", "Deductions"). |
| rows      | array  | Each item: `{ "label": "Basic Salary", "value": "{{basic_salary}}" }`. `value` can be a variable. |

**Example: template with top heading, table for salary components, bottom title**

```json
{
  "blocks": [
    {
      "id": "block-1",
      "type": "heading",
      "order": 1,
      "content": "Salary Slip"
    },
    {
      "id": "block-2",
      "type": "text_with_variable",
      "order": 2,
      "label": "Organization:",
      "value": "{{organization_name}}"
    },
    {
      "id": "block-3",
      "type": "text_with_variable",
      "order": 3,
      "label": "Employee:",
      "value": "{{employee_name}}"
    },
    {
      "id": "block-4",
      "type": "text_with_variable",
      "order": 4,
      "label": "Designation:",
      "value": "{{designation}}"
    },
    {
      "id": "block-5",
      "type": "text_with_variable",
      "order": 5,
      "label": "Period:",
      "value": "{{period_start}} to {{period_end}}"
    },
    {
      "id": "block-6",
      "type": "table",
      "order": 6,
      "title": "Earnings",
      "rows": [
        { "label": "Basic Salary", "value": "{{basic_salary}}" },
        { "label": "HRA", "value": "{{hra}}" },
        { "label": "Transport Allowance", "value": "{{transport_allowance}}" }
      ]
    },
    {
      "id": "block-7",
      "type": "table",
      "order": 7,
      "title": "Deductions",
      "rows": [
        { "label": "PF", "value": "{{pf}}" },
        { "label": "Professional Tax", "value": "{{professional_tax}}" }
      ]
    },
    {
      "id": "block-8",
      "type": "text_with_variable",
      "order": 8,
      "label": "Net Salary:",
      "value": "{{net_salary}}"
    },
    {
      "id": "block-9",
      "type": "heading",
      "order": 9,
      "content": "Thank You"
    }
  ]
}
```

To **move** a block (e.g. put "Thank You" above Net Salary), change `order`: set "Thank You" to `8` and "Net Salary" to `9`. The frontend template builder can allow drag-and-drop and then persist the new `order` values in `template_json`.

---

### 5.2 Create template

**POST** `/api/v1/payroll/payslip-templates`

**Permission:** `payroll.create`

**Request body:**

| Field         | Type    | Required | Description                                      |
|---------------|---------|----------|--------------------------------------------------|
| name          | string  | Yes      | Template name (1–100 chars)                      |
| template_json | object  | No       | Layout and content (see 5.1). Use `blocks` array for position/order. Default `{}`. |
| is_default    | boolean | No       | Set as default template (default `false`)       |

**Example payload (top heading, table for salary components, bottom title):**

```json
{
  "name": "Standard Payslip",
  "template_json": {
    "blocks": [
      {
        "id": "block-1",
        "type": "heading",
        "order": 1,
        "content": "Salary Slip"
      },
      {
        "id": "block-2",
        "type": "text_with_variable",
        "order": 2,
        "label": "Organization:",
        "value": "{{organization_name}}"
      },
      {
        "id": "block-3",
        "type": "text_with_variable",
        "order": 3,
        "label": "Employee:",
        "value": "{{employee_name}}"
      },
      {
        "id": "block-4",
        "type": "table",
        "order": 4,
        "title": "Earnings",
        "rows": [
          { "label": "Basic Salary", "value": "{{basic_salary}}" },
          { "label": "HRA", "value": "{{hra}}" }
        ]
      },
      {
        "id": "block-5",
        "type": "table",
        "order": 5,
        "title": "Deductions",
        "rows": [
          { "label": "PF", "value": "{{pf}}" }
        ]
      },
      {
        "id": "block-6",
        "type": "text_with_variable",
        "order": 6,
        "label": "Net Salary:",
        "value": "{{net_salary}}"
      },
      {
        "id": "block-7",
        "type": "heading",
        "order": 7,
        "content": "Thank You"
      }
    ]
  },
  "is_default": true
}
```

**Response (201):**

```json
{
  "success": true,
  "message": "Payslip template created",
  "data": {
    "id": "uuid",
    "tenant_id": "uuid",
    "name": "Standard Template",
    "is_default": true,
    "template_json": { ... },
    "is_active": true,
    "created_at": "2025-03-05T10:00:00Z",
    "updated_at": "2025-03-05T10:00:00Z"
  }
}
```

**Errors:** **400** – Maximum 5 templates allowed per tenant.

---

### 5.3 List templates

**GET** `/api/v1/payroll/payslip-templates`

**Permission:** `payroll.read`

**Query parameters:**

| Name       | Type    | Default | Description                 |
|------------|---------|---------|-----------------------------|
| active_only| boolean | true    | When true, only active templates |

**Response (200):**

```json
{
  "success": true,
  "message": "Payslip templates retrieved",
  "data": {
    "items": [
      {
        "id": "uuid",
        "tenant_id": "uuid",
        "name": "Standard Template",
        "is_default": true,
        "template_json": { ... },
        "is_active": true,
        "created_at": "2025-03-05T10:00:00Z",
        "updated_at": "2025-03-05T10:00:00Z"
      }
    ]
  }
}
```

---

### 5.4 Update template

**PUT** `/api/v1/payroll/payslip-templates/{template_id}`

**Permission:** `payroll.update`

**Path parameters:**

| Name        | Type | Description   |
|-------------|------|---------------|
| template_id | UUID | Template ID   |

**Request body:** All fields optional.

| Field        | Type    | Description                    |
|-------------|---------|--------------------------------|
| name        | string  | Template name (1–100 chars)    |
| template_json | object | JSON structure                 |
| is_default  | boolean | Set as default                |
| is_active   | boolean | Active flag                   |

**Response (200):** Same template object as in **5.1** (inside `data`).

**Errors:** **404** – Template not found.

---

### 5.5 Delete template

**DELETE** `/api/v1/payroll/payslip-templates/{template_id}`

**Permission:** `payroll.delete`

**Path parameters:**

| Name        | Type | Description   |
|-------------|------|---------------|
| template_id | UUID | Template ID   |

**Response (200):**

```json
{
  "success": true,
  "message": "Payslip template deleted",
  "data": null
}
```

**Errors:** **404** – Template not found.

---

## 6. Payslip template variables

When rendering a payslip from `template_json`, these placeholders are supported:

| Variable               | Description                    |
|------------------------|--------------------------------|
| `{{organization_name}}`| Tenant/organization name       |
| `{{employee_name}}`    | Employee full name             |
| `{{employee_code}}`    | Employee code (e.g. from staff profile) |
| `{{designation}}`      | Employee designation          |
| `{{period_start}}`     | Payroll period start date     |
| `{{period_end}}`       | Payroll period end date       |
| `{{gross_salary}}`     | Gross salary                  |
| `{{net_salary}}`       | Net salary                    |

Component-specific placeholders (e.g. `{{basic_salary}}`, `{{hra}}`, `{{pf}}`) can be used as defined in your template structure.

---

## 7. Enums reference

| Concept            | Values                                      |
|--------------------|---------------------------------------------|
| Component type     | `earning`, `deduction`                      |
| Calculation type   | `fixed`, `percentage`                      |
| Payment mode       | `bank`, `cash`, `upi`, `cheque`            |
| Payroll run status | `draft`, `processed`, `issued`             |

---

## 8. Typical flow

1. **Setup:** Create payroll components (Basic, HRA, PF, etc.) via **POST /components**.
2. **Assign:** For each employee, assign components and amounts via **POST /employee-components**.
3. **List / edit / delete:** Use **GET /employee-assignments** to list all employees with their assigned components and salary; use each assignment’s **id** with **PUT /employee-components/{assignment_id}** to change amount or **DELETE /employee-components/{assignment_id}** to remove.
4. **Optional:** Create one or more payslip templates via **POST /payslip-templates** (max 5).
5. **Run payroll:** **POST /run** with `month` and `year` → creates run and employee records (draft).
6. **Review:** **GET /run/{run_id}/records** to review gross/deductions/net per employee.
7. **Issue:** **POST /run/{run_id}/issue** → creates payslip rows and sets run to `issued`.
8. **PDF/email:** Use stored payslips and template variables to generate PDFs or emails (implementation-specific).
