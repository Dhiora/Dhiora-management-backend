import uuid
from datetime import datetime, date

from sqlalchemy import Column, Date, DateTime, ForeignKey, String, Text, UniqueConstraint, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class User(Base):
    """User within a tenant, with role-based access to tenant modules."""

    __tablename__ = "users"
    __table_args__ = (
        # Email must be unique per tenant
        UniqueConstraint("tenant_id", "email", name="uq_user_tenant_email"),
        {"schema": "auth"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Owning tenant
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id"), nullable=False)
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    mobile = Column(String(50), nullable=True)
    password_hash = Column(Text, nullable=False)
    # High-level role within the tenant: SUPER_ADMIN, ADMIN, HR, EMPLOYEE, STUDENT, etc.
    role = Column(String(50), nullable=False)
    # FK to auth.roles for employees/students; null for legacy admin users
    role_id = Column(UUID(as_uuid=True), ForeignKey("auth.roles.id"), nullable=True)
    status = Column(String(20), nullable=False, default="ACTIVE")
    # Origin: SYSTEM, EMPLOYEE, STUDENT, PARENT
    source = Column(String(50), nullable=False, default="SYSTEM")
    # employee | student | null (for admin users)
    user_type = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    # Tenant relationship (lazy-loaded)
    tenant = relationship("Tenant", back_populates="users")
    role_obj = relationship("Role", foreign_keys=[role_id])
    refresh_tokens = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )
    staff_profile = relationship(
        "StaffProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    student_profile = relationship(
        "StudentProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class RefreshToken(Base):
    """Stored refresh tokens for users."""

    __tablename__ = "refresh_tokens"
    __table_args__ = {"schema": "auth"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id"), nullable=False)
    token = Column(String(512), nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    user = relationship("User", back_populates="refresh_tokens")


class Role(Base):
    """Tenant-scoped role with JSON permissions."""

    __tablename__ = "roles"
    __table_args__ = (
        # Role name must be unique within a tenant
        UniqueConstraint("tenant_id", "name", name="uq_role_tenant_name"),
        {"schema": "auth"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id"), nullable=False)
    name = Column(String(100), nullable=False)
    # Example shape:
    # {
    #   "roles": {"create": true, "read": true, "update": false, "delete": false},
    #   "students": {"read": true}
    # }
    permissions = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class StaffProfile(Base):
    """Profile for employee users. employee_code is auto-generated (e.g. KTS-EMP-001); identification only, never for joins/permissions."""

    __tablename__ = "staff_profiles"
    __table_args__ = ({"schema": "auth"},)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False)
    employee_code = Column(String(50), nullable=True)  # Auto-generated: <ORG_CODE>-EMP-<SEQ>; not editable after creation
    department_id = Column(UUID(as_uuid=True), ForeignKey("core.departments.id"), nullable=True)
    designation = Column(String(100), nullable=True)
    join_date = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="staff_profile")
    department_rel = relationship("Department", foreign_keys=[department_id])


class StudentProfile(Base):
    """
    Profile for student users. Does NOT store class/section.
    Current class/section come from student_academic_records (current academic year).
    """

    __tablename__ = "student_profiles"
    __table_args__ = ({"schema": "auth"},)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False)
    roll_number = Column(String(50), nullable=True)  # Legacy/display; per-year roll in student_academic_records
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="student_profile")


class TeacherReferral(Base):
    """Unique referral code per teacher, scoped by tenant. Only teachers get a row."""

    __tablename__ = "teacher_referrals"
    __table_args__ = (
        UniqueConstraint("tenant_id", "referral_code", name="uq_teacher_referral_tenant_code"),
        {"schema": "auth"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False)
    referral_code = Column(String(20), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    user = relationship("User", foreign_keys=[teacher_id])

