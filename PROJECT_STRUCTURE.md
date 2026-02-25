# Dhiora Management Backend - Project Structure & Analysis

## 📁 Complete Folder Structure

```
Dhiora-management-backend/
│
├── app/                          # Main application package
│   ├── main.py                   # FastAPI application entry point
│   │
│   ├── api/                      # API endpoints (RESTful routes)
│   │   └── v1/                   # API version 1
│   │       ├── academic_years/   # Academic year management
│   │       ├── admissions/       # Student admission requests & processing
│   │       ├── attendance/       # Student & employee attendance tracking
│   │       ├── auth/             # Authentication & authorization
│   │       ├── classes/          # Class/grade management
│   │       ├── class_subjects/   # Subject assignments to classes
│   │       ├── class_teachers/   # Teacher assignments to classes
│   │       ├── departments/      # Department management
│   │       ├── dropdown/         # Dropdown data endpoints
│   │       ├── fee_components/   # Fee component definitions
│   │       ├── fees/             # Student fee management & payments
│   │       ├── homework/         # Homework/assignment management
│   │       ├── leaves/           # Leave request management
│   │       ├── modules/          # Module management & user modules
│   │       │   └── users/       # Employee & student user management
│   │       ├── query/            # Generic query endpoints
│   │       ├── sections/         # Section management (within classes)
│   │       ├── subjects/         # Subject management
│   │       ├── subscription_plans/ # Subscription plan management
│   │       ├── teacher_subject_assignments/ # Teacher-subject mappings
│   │       ├── timetables/       # Class timetable management
│   │       └── transport/        # Transport route & vehicle management
│   │
│   ├── auth/                     # Authentication & authorization core
│   │   ├── dependencies.py       # FastAPI dependencies (get_current_user, etc.)
│   │   ├── models.py             # User, Role, RefreshToken, StaffProfile, StudentProfile models
│   │   ├── rbac.py               # Role-Based Access Control utilities
│   │   ├── referral_code.py      # Teacher referral code logic
│   │   ├── schemas.py            # Pydantic schemas for auth
│   │   ├── security.py            # Password hashing, JWT token generation
│   │   └── services.py           # Auth business logic (login, register)
│   │
│   ├── core/                     # Core application components
│   │   ├── config.py             # Application settings (from environment)
│   │   ├── enums.py              # Application-wide enums
│   │   ├── exceptions.py         # Custom exception classes
│   │   ├── models/               # SQLAlchemy database models
│   │   │   ├── academic_year.py
│   │   │   ├── admission_request.py
│   │   │   ├── admission_student.py
│   │   │   ├── audit_log.py
│   │   │   ├── class_fee_structure.py
│   │   │   ├── class_model.py
│   │   │   ├── class_subject.py
│   │   │   ├── class_teacher_assignment.py
│   │   │   ├── department.py
│   │   │   ├── employee_attendance.py
│   │   │   ├── fee_audit_log.py
│   │   │   ├── fee_component.py
│   │   │   ├── homework.py
│   │   │   ├── leave_audit_log.py
│   │   │   ├── leave_request.py
│   │   │   ├── leave_type.py
│   │   │   ├── module.py
│   │   │   ├── payment_transaction.py
│   │   │   ├── referral_usage.py
│   │   │   ├── school_subject.py
│   │   │   ├── section_model.py
│   │   │   ├── student_academic_record.py
│   │   │   ├── student_attendance.py
│   │   │   ├── student_daily_attendance.py
│   │   │   ├── student_fee_assignment.py
│   │   │   ├── student_fee_discount.py
│   │   │   ├── student_subject_attendance_override.py
│   │   │   ├── subject.py
│   │   │   ├── subscription_plan.py
│   │   │   ├── teacher_class_assignment.py
│   │   │   ├── teacher_subject_assignment.py
│   │   │   ├── tenant.py          # Multi-tenant core model
│   │   │   ├── timetable.py
│   │   │   ├── transport_assignment.py
│   │   │   ├── transport_route.py
│   │   │   ├── transport_subscription_plan.py
│   │   │   ├── transport_vehicle_type.py
│   │   │   └── transport_vehicle.py
│   │   ├── models.py             # Model imports/exports
│   │   ├── schemas.py            # Core Pydantic schemas
│   │   ├── services.py            # Core business logic services
│   │   └── tenant_service.py     # Tenant-specific services
│   │
│   ├── db/                        # Database configuration & utilities
│   │   ├── session.py             # SQLAlchemy async session setup
│   │   ├── migrations/           # Database migration scripts
│   │   │   └── 001_add_organization_code_to_tenants.py
│   │   ├── schema_check.py        # Schema validation utilities
│   │   ├── seed_modules.py        # Seed data for modules
│   │   ├── seed_platform_admin.py # Seed platform admin user
│   │   └── seed_transport.py      # Seed transport data
│   │
│   └── scripts/                   # Utility scripts
│       ├── backfill_teacher_referrals.py
│       └── check_subjects_table.py
│
├── docs/                          # API documentation
│   ├── ACADEMIC_YEARS.md
│   ├── ADMISSIONS.md
│   ├── ATTENDANCE.md
│   ├── FEE_MANAGEMENT.md
│   ├── HOMEWORK.md
│   ├── LEAVE_MANAGEMENT.md
│   └── SUBJECTS_DEPARTMENTS_TIMETABLE.md
│
├── tests/                         # Test suite
│   ├── conftest.py                # Pytest configuration
│   ├── test_auth.py
│   └── test_referral_code.py
│
├── venv/                          # Python virtual environment
├── requirements.txt               # Python dependencies
└── README.md                      # Project documentation

```

## 🎯 Project Understanding

### **Project Type**
**Multi-tenant School/Educational Institution Management System (SaaS Backend)**

This is a comprehensive **School Management System (SMS)** backend built as a **Software-as-a-Service (SaaS)** platform that supports multiple educational institutions (tenants) on a single codebase.

---

### **Core Architecture**

#### **1. Technology Stack**
- **Framework**: FastAPI (async Python web framework)
- **Database**: PostgreSQL with asyncpg (async PostgreSQL driver)
- **ORM**: SQLAlchemy 2.0 (async)
- **Authentication**: JWT (JSON Web Tokens) with refresh tokens
- **Validation**: Pydantic v2
- **Testing**: Pytest
- **API Documentation**: FastAPI auto-generated OpenAPI/Swagger docs

#### **2. Multi-Tenancy Architecture**
- **Tenant Model**: Each organization (school/college) is a separate tenant
- **Tenant Isolation**: All data is scoped by `tenant_id` - every table includes tenant_id
- **Organization Code**: Human-readable identifier (e.g., "SCH-A3K9") for login/routing
- **Schema-based Separation**: Uses PostgreSQL schemas (`auth`, `core`) for logical separation

#### **3. Authentication & Authorization**
- **JWT-based Auth**: Access tokens (15 min expiry) + Refresh tokens (7 days)
- **Role-Based Access Control (RBAC)**:
  - System roles: `SUPER_ADMIN`, `PLATFORM_ADMIN`
  - Tenant roles: Custom roles per tenant with JSON permissions
  - Module-based permissions: Granular permissions per module (create/read/update/delete)
- **User Types**: 
  - `EMPLOYEE` (teachers, staff)
  - `STUDENT`
  - `ADMIN` (tenant admins)
- **Referral System**: Teachers can have referral codes for admission campaigns

---

### **4. Key Features & Modules**

#### **Academic Management**
- **Academic Years**: Manage academic year cycles
- **Classes**: Grade/class management (e.g., Class 1, Class 2, etc.)
- **Sections**: Sections within classes (e.g., Class 1-A, Class 1-B)
- **Subjects**: Subject catalog management
- **Class-Subject Mapping**: Assign subjects to classes
- **Timetables**: Class schedule/timetable management

#### **Student Management**
- **Admissions**: 
  - Admission request workflow (PENDING → APPROVED/REJECTED)
  - Track admission source (TEACHER_RAISED, CAMPAIGN_REFERRAL, WEBSITE_FORM, etc.)
  - Admission student records (INACTIVE → ACTIVE)
- **Student Profiles**: Student user accounts with academic records
- **Student Academic Records**: Track student's class/section per academic year
- **Roll Numbers**: Per-academic-year roll number assignment

#### **Employee/Staff Management**
- **Employee Profiles**: Staff user accounts
- **Employee Codes**: Auto-generated codes (e.g., ORG-EMP-001)
- **Departments**: Department/organizational structure
- **Reporting Managers**: Hierarchical staff structure
- **Designations**: Job titles/positions

#### **Attendance Management**
- **Student Attendance**: Daily attendance tracking per subject
- **Employee Attendance**: Staff attendance tracking
- **Attendance Overrides**: Manual attendance corrections

#### **Fee Management**
- **Fee Components**: Define fee types (ACADEMIC, TRANSPORT, HOSTEL, OTHER)
- **Class Fee Structures**: Fee templates per class
- **Student Fee Assignments**: Individual student fee assignments
- **Fee Discounts**: Discount management
- **Payment Transactions**: Payment tracking
- **Fee Audit Logs**: Audit trail for fee changes
- **Fee Status**: unpaid/partial/paid tracking

#### **Homework/Assignments**
- **Homework Management**: Create and manage homework assignments
- **Class/Subject-based**: Assignments linked to classes and subjects

#### **Leave Management**
- **Leave Requests**: Employee leave request workflow
- **Leave Types**: Configurable leave types
- **Leave Audit Logs**: Audit trail for leave management

#### **Transport Management**
- **Transport Routes**: Bus/vehicle route management
- **Transport Vehicles**: Vehicle fleet management
- **Vehicle Types**: Different vehicle categories
- **Transport Assignments**: Assign students to routes
- **Transport Subscription Plans**: Transport fee plans

#### **Teacher Management**
- **Teacher-Subject Assignments**: Assign teachers to subjects
- **Teacher-Class Assignments**: Assign teachers to classes
- **Class Teachers**: Class teacher assignments

#### **Module System**
- **Tenant Modules**: Enable/disable features per tenant
- **Module-based Access**: Permissions tied to modules
- **Flexible Feature Set**: Tenants can subscribe to different modules

#### **Subscription Plans**
- **Plan Management**: Different subscription tiers for tenants

---

### **5. Data Model Patterns**

#### **Multi-Tenant Pattern**
Every core table includes:
- `tenant_id` (UUID, Foreign Key to `core.tenants`)
- Unique constraints scoped by `tenant_id` (e.g., unique email per tenant)

#### **Audit Trail**
- `created_at` (DateTime with timezone)
- `updated_at` (DateTime with timezone)
- Separate audit log tables for sensitive operations (fees, leaves, admissions)

#### **Soft Deletes**
- `is_active` flags on many models
- `status` fields (ACTIVE, INACTIVE, etc.)

#### **Academic Year Scoping**
- Many records are scoped by academic year
- Student academic records track class/section per year

---

### **6. API Structure**

Each feature module follows a consistent pattern:
```
module_name/
├── router.py      # FastAPI route definitions
├── service.py     # Business logic
├── schemas.py     # Pydantic request/response models
└── __init__.py
```

**API Versioning**: All routes under `/api/v1/`

**Common Endpoints Pattern**:
- `POST /api/v1/{resource}` - Create
- `GET /api/v1/{resource}` - List (with filters)
- `GET /api/v1/{resource}/{id}` - Get by ID
- `PUT /api/v1/{resource}/{id}` - Update
- `DELETE /api/v1/{resource}/{id}` - Delete

---

### **7. Security Features**

- **Password Hashing**: bcrypt
- **JWT Tokens**: Secure token-based authentication
- **Refresh Tokens**: Stored in database for revocation
- **CORS**: Configurable CORS middleware
- **Permission Checks**: Dependency injection for permission validation
- **Tenant Isolation**: Automatic tenant_id filtering in queries

---

### **8. Database Schema Organization**

- **`auth` schema**: Authentication-related tables (users, roles, refresh_tokens, etc.)
- **`core` schema**: Core business entities (tenants, modules, departments, etc.)
- **Implicit schemas**: Other tables likely in default/public schema

---

### **9. Workflow Patterns**

#### **Admission Workflow**
1. Teacher/Admin creates admission request (PENDING_APPROVAL)
2. User with `admissions.update` approves → creates AdmissionStudent (INACTIVE)
3. User with `students.update` activates → creates User account + StudentProfile

#### **Fee Workflow**
1. Define fee components
2. Create class fee structures (templates)
3. Assign fees to students (from template or custom)
4. Record payments
5. Track fee status

#### **Leave Workflow**
1. Employee creates leave request
2. Manager/Admin approves/rejects
3. Audit log maintained

---

### **10. Key Design Decisions**

1. **Multi-tenancy First**: Every feature designed with tenant isolation
2. **Role-Based Permissions**: Flexible JSON-based permission system
3. **Academic Year Awareness**: Many features scoped by academic year
4. **Audit Logging**: Critical operations have audit trails
5. **Referral System**: Teacher referral codes for marketing/admissions
6. **Module System**: Feature flags per tenant
7. **Async Architecture**: Full async/await for performance
8. **Type Safety**: Pydantic schemas for request/response validation

---

### **11. Use Cases**

This system is designed for:
- **Schools**: K-12 educational institutions
- **Colleges**: Higher education institutions
- **Multi-campus Organizations**: Organizations with multiple locations
- **SaaS Providers**: Companies offering SMS as a service

---

### **12. Development Patterns**

- **Service Layer**: Business logic separated from routes
- **Dependency Injection**: FastAPI dependencies for auth, DB sessions
- **Error Handling**: Custom exceptions with proper HTTP status codes
- **Validation**: Pydantic models for input/output validation
- **Database Migrations**: Manual migration scripts
- **Seeding**: Scripts for initial data setup

---

## 🚀 Getting Started

1. **Environment Setup**: Create `.env` with database URL, JWT secrets
2. **Database Setup**: Run migrations, seed initial data
3. **Run Server**: `uvicorn app.main:app --reload`
4. **API Docs**: Available at `/docs` (Swagger UI)

---

## 📊 Summary

This is a **production-ready, enterprise-grade School Management System backend** that:
- Supports multiple schools/organizations (multi-tenant SaaS)
- Manages complete student lifecycle (admission → graduation)
- Handles staff/employee management
- Tracks attendance, fees, homework, leaves
- Provides flexible role-based access control
- Uses modern async Python stack
- Follows RESTful API design principles
- Includes comprehensive audit trails

The codebase is well-organized, follows consistent patterns, and is designed for scalability and maintainability.


