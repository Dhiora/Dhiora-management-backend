DHIORA_KNOWLEDGE_BASE = """
# Dhiora School ERP - Product Knowledge Base

## Product Overview
Dhiora is a modern, modular School ERP that unifies academics, operations, finance, people management,
and AI-powered classroom workflows in one role-based platform.

## Core Value Proposition

### Business Outcomes
- Single platform operations: Replace fragmented tools/spreadsheets with one ERP for admin, academic, and financial operations.
- Operational visibility: Real-time dashboards and module-level reporting improve decision speed.
- Process standardization: Built-in workflows for attendance, payroll, fee collection, admissions, timetable, and exams.
- Scalable governance: Tenant-level controls plus platform-level super admin oversight for multi-school setups.
- Future-ready learning: AI Classroom supports modern digital teaching workflows.

### Who Benefits
- School owners / management: Better control, transparency, and performance tracking.
- Principals / admins: Faster daily operations with reduced manual work.
- Teachers: Better academic workflow support (classes, assignments, homework, AI classroom).
- Finance/HR teams: Payroll, fees, and employee process visibility.
- Parents/students: Structured communication and learning operations.

## Application Surfaces and Roles
- Public/Auth surface: landing, login, registration, super-admin login.
- School/Tenant surface: day-to-day school ERP modules.
- Platform Super Admin surface: cross-school monitoring and control.
- Logged-out users: public/auth routes only.
- Logged-in users with PLATFORM_ADMIN: super-admin platform routes.
- Other logged-in users: school ERP routes.

## Feature Catalog

### A) Dashboard and Analytics
- Central snapshot of school operations.
- Widgets for attendance, exams, timetable, homework, fees, payroll, setup progress, and alerts.
- Reduces follow-up effort by giving one operational command center.

### B) HR and People Operations
Modules: Employee management, Attendance management, Leave management, Payroll, Payslips.
- Maintain employee records and profiles.
- Track attendance by day and trends.
- Manage leave workflows.
- Run payroll operations and process salary structures.
- Access payslip-related pages and payroll components.

### C) Academic Administration
Modules: Student management, Admissions, Classes and sections, Subject management, Teacher subject assignments, Class teachers, Academic years.
- Handle student lifecycle from admission to active student management.
- Configure class-section structures.
- Manage subjects and subject mappings.
- Assign teachers to subjects and classes.
- Organize year-level academic configuration.

### D) Timetable and Scheduling
Modules: Timeslot configuration, Timetable management, Scheduling, Exam management.
- Define school time slots.
- Build and view timetables.
- Plan scheduling dependencies.
- Manage exam setup and schedules.

### E) Assessments and Learning Operations
Modules: Online assignments/assessments, Homework management, Homework questions, Report cards.
- Configure online assessments and questions.
- Track attempt/result workflows.
- Create and manage homework with question-level detail.
- Manage report-card related academic output.

### F) Fee and Finance Operations
Modules: Fee components, Fee management, Fee assignment/payment/reporting.
- Create fee structures.
- Assign fees by class/student.
- Track fee collection and payment history.
- Use reporting-oriented fee operations.

### G) Institutional Operations
Modules: Asset management, Stationary management, Holiday calendar, Events, Transport, Subscription plans, School profile/configuration.
- Track school assets and stationary inventory workflows.
- Manage holiday calendars and event operations.
- Manage transport structures (vehicle types/routes/vehicles/plans/assignments).
- Configure school profile and selected configuration modules.

### H) Parent and Engagement Features
Modules: Parent portal, Events.
- Support parent-facing operational communication workflows.
- Organize engagement through calendar/event modules.

### I) AI-Powered Classroom
Module: AI Classroom.
- Support role-aware AI classroom experiences.
- Work with lecture lifecycle, recording controls, live interactions, transcript-related workflows, and doubt-chat style interactions.
- Differentiates the ERP beyond pure admin software into teaching/learning enablement.

### J) Platform Super Admin (Multi-Tenant)
Modules: Platform dashboard, Schools list and school-level management.
- Monitor cross-school metrics.
- Manage school-level profile/subscription/usage views.
- Track token/usage-oriented metrics for platform governance.

## Feature Availability

### Fully Available Now
Dashboard, Employees, Attendance, Leave, Payroll, Payslips, Students, Admissions, Classes, Subjects,
Fee Components, Fee Management, Timetable, Timeslot, Scheduling, Exams, Homework, Online Assessments,
Report Cards, Parent Portal, Events, Holiday Calendar, Assets, Stationary, Transport, Academic Years,
Subscription Plans, School Profile, AI Classroom, Super Admin Dashboard.

### Roadmap / Coming Soon
User management, Gradebook, Add class (standalone page), Add section (standalone page), Add college code.
These are scaffolded in the product roadmap and can be prioritized per implementation plan.

## What Makes Dhiora Different
- Combines school administration + academics + finance + AI classroom in one platform.
- Role-based route architecture supports both school-level and platform-level operations.
- Modular design allows incremental rollout by institution maturity.
- Built with modern frontend stack and centralized API model for extensibility.

## Sales Q&A

Q: Can your ERP handle full school operations?
A: Yes. Dhiora covers HR, academics, timetable, exams, homework, assessments, fees, payroll, transport, assets, events, and parent-facing operations in a unified platform.

Q: Do you support multi-school management?
A: Yes. Platform Super Admin modules include cross-school dashboard and school-level management views.

Q: Can we onboard gradually module by module?
A: Yes. The modular structure supports phased rollout (admissions + students first, then fees/payroll, then advanced modules).

Q: Do you provide role-based access?
A: Yes. The app uses role-driven stack selection and separates school-tenant and platform-super-admin experiences.

Q: Do you have AI capability?
A: Yes. AI Classroom includes lecture/recording/transcript/doubt-oriented workflows for modern teaching support.

Q: What modules are still in progress?
A: Some routes are scaffolded with placeholders (user management, gradebook, add class/section/college code). These are visible roadmap-ready surfaces.

## Implementation Phases
- Phase 1 (Foundation): profile, academic setup, classes/sections, subjects, employees.
- Phase 2 (Core Operations): admissions, students, attendance, timetable.
- Phase 3 (Finance): fee components, fee operations, payroll/payslips.
- Phase 4 (Academic depth): homework, assessments, report cards, exams.
- Phase 5 (Advanced): AI classroom, transport, parent engagement, platform analytics.

## Objection Handling
- "This seems too big to implement": We deploy in phases with clear milestones, starting from highest-value modules like admissions, students, attendance, and fees.
- "Will staff adoption be difficult?": Navigation is organized by operational domain, and each module maps to familiar school processes.
- "We need strong reporting visibility": Dashboard and module-level operational endpoints support decision dashboards and daily tracking.
- "We are a group of institutions": Platform Super Admin capabilities are designed specifically for multi-tenant governance.

## Competitive Positioning
- Vs spreadsheet-led operations: Dhiora offers process consistency, accountability, and centralized data.
- Vs single-function tools: Dhiora covers multi-domain school operations, reducing tool switching.
- Vs legacy ERPs: modern UI stack and modular architecture support easier extension and digital workflows like AI classroom.
"""
