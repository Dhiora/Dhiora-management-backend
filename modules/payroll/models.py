"""Payroll SQLAlchemy models: components, employee salary structure, runs, records, templates, payslips."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class PayrollComponent(Base):
    """Salary component master (e.g. Basic Salary, HRA, PF). Tenant-scoped."""

    __tablename__ = "payroll_components"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_payroll_component_tenant_code"),
        {"schema": "hrms"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    code = Column(String(50), nullable=False)
    type = Column(String(20), nullable=False)  # earning | deduction
    calculation_type = Column(String(20), nullable=False)  # fixed | percentage
    default_value = Column(Numeric(12, 2), nullable=True)  # amount for fixed, % for percentage
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", backref="payroll_components")
    employee_components = relationship("EmployeeSalaryComponent", back_populates="component", cascade="all, delete-orphan")


class EmployeeSalaryComponent(Base):
    """Assigns salary components to an employee with amount."""

    __tablename__ = "employee_salary_components"
    __table_args__ = (
        UniqueConstraint("tenant_id", "employee_id", "component_id", name="uq_employee_salary_component"),
        {"schema": "hrms"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False, index=True)
    component_id = Column(UUID(as_uuid=True), ForeignKey("hrms.payroll_components.id", ondelete="RESTRICT"), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    component = relationship("PayrollComponent", back_populates="employee_components")


class PayrollRun(Base):
    """One payroll run per tenant per month/year."""

    __tablename__ = "payroll_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "month", "year", name="uq_payroll_run_tenant_month_year"),
        {"schema": "hrms"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    month = Column(String(20), nullable=False)  # e.g. "01", "02" or "January"
    year = Column(String(10), nullable=False)  # e.g. "2025"
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(String(20), nullable=False, default="draft")  # draft | processed | issued
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    employee_records = relationship("PayrollEmployeeRecord", back_populates="payroll_run", cascade="all, delete-orphan")
    payslips = relationship("Payslip", back_populates="payroll_run", cascade="all, delete-orphan")


class PayrollEmployeeRecord(Base):
    """Per-employee record in a payroll run (gross, deductions, net, payment mode)."""

    __tablename__ = "payroll_employee_records"
    __table_args__ = (
        UniqueConstraint("payroll_run_id", "employee_id", name="uq_payroll_record_run_employee"),
        {"schema": "hrms"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    payroll_run_id = Column(UUID(as_uuid=True), ForeignKey("hrms.payroll_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False, index=True)
    gross_salary = Column(Numeric(14, 2), nullable=False)
    total_deductions = Column(Numeric(14, 2), nullable=False, default=0)
    net_salary = Column(Numeric(14, 2), nullable=False)
    payment_mode = Column(String(20), nullable=False)  # bank | cash | upi | cheque
    status = Column(String(20), nullable=False, default="draft")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    payroll_run = relationship("PayrollRun", back_populates="employee_records")


class PayslipTemplate(Base):
    """Payslip template per tenant (max 5 per tenant)."""

    __tablename__ = "payslip_templates"
    __table_args__ = {"schema": "hrms"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    is_default = Column(Boolean, nullable=False, default=False)
    template_json = Column(JSONB, nullable=False, default=dict)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    payslips = relationship("Payslip", back_populates="template")


class Payslip(Base):
    """Generated payslip per employee per payroll run."""

    __tablename__ = "payslips"
    __table_args__ = (
        UniqueConstraint("employee_id", "payroll_run_id", name="uq_payslip_employee_run"),
        {"schema": "hrms"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("core.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False, index=True)
    payroll_run_id = Column(UUID(as_uuid=True), ForeignKey("hrms.payroll_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    template_id = Column(UUID(as_uuid=True), ForeignKey("hrms.payslip_templates.id", ondelete="SET NULL"), nullable=True)
    month = Column(String(20), nullable=False)
    year = Column(String(10), nullable=False)
    gross_salary = Column(Numeric(14, 2), nullable=False)
    deductions = Column(Numeric(14, 2), nullable=False, default=0)
    net_salary = Column(Numeric(14, 2), nullable=False)
    payment_mode = Column(String(20), nullable=False)
    issued_at = Column(DateTime(timezone=True), nullable=True)
    pdf_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant")
    payroll_run = relationship("PayrollRun", back_populates="payslips")
    template = relationship("PayslipTemplate", back_populates="payslips")
