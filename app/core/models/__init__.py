from app.core.models.academic_year import AcademicYear
from app.core.models.class_model import SchoolClass
from app.core.models.student_academic_record import StudentAcademicRecord
from app.core.models.student_attendance import StudentAttendance
from app.core.models.teacher_class_assignment import TeacherClassAssignment
from app.core.models.employee_attendance import EmployeeAttendance
from app.core.models.homework import (
    Homework,
    HomeworkAssignment,
    HomeworkAttempt,
    HomeworkHintUsage,
    HomeworkQuestion,
    HomeworkSubmission,
)
from app.core.models.department import Department
from app.core.models.module import Module, OrganizationTypeModule
from app.core.models.section_model import Section
from app.core.models.subscription_plan import SubscriptionPlan
from app.core.models.referral_usage import ReferralUsage
from app.core.models.tenant import Tenant, TenantModule
from app.core.models.admission_request import AdmissionRequest
from app.core.models.admission_student import AdmissionStudent
from app.core.models.audit_log import AuditLog
from app.core.models.leave_type import LeaveType
from app.core.models.leave_request import LeaveRequest
from app.core.models.leave_audit_log import LeaveAuditLog

__all__ = [
    "AcademicYear",
    "Department",
    "EmployeeAttendance",
    "Homework",
    "HomeworkAssignment",
    "HomeworkAttempt",
    "HomeworkHintUsage",
    "HomeworkQuestion",
    "HomeworkSubmission",
    "StudentAcademicRecord",
    "Module",
    "OrganizationTypeModule",
    "SchoolClass",
    "Section",
    "StudentAttendance",
    "ReferralUsage",
    "SubscriptionPlan",
    "TeacherClassAssignment",
    "Tenant",
    "TenantModule",
    "AdmissionRequest",
    "AdmissionStudent",
    "AuditLog",
    "LeaveType",
    "LeaveRequest",
    "LeaveAuditLog",
]

