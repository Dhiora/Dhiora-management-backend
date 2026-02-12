"""Fees service: class structure, assignments, discounts, payments, reports. Financial logic with audit."""

from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import status
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ServiceError
from app.core.models import (
    AcademicYear,
    ClassFeeStructure,
    FeeComponent,
    FeeAuditLog,
    PaymentTransaction,
    SchoolClass,
    StudentAcademicRecord,
    StudentFeeAssignment,
    StudentFeeDiscount,
)
from app.auth.models import User

from .schemas import (
    AddCustomStudentFeeRequest,
    AssignTemplateFeesRequest,
    ClassFeeStructureCreate,
    ClassFeeStructureResponse,
    ClassFeeStructureByClassResponse,
    ClassFeeStructureItem,
    FeeReportItem,
    PaymentCreate,
    PaymentResponse,
    StudentFeeAssignmentResponse,
    StudentFeeAssignmentWithDetails,
    StudentFeeDiscountCreate,
    StudentFeeDiscountResponse,
)


def _to_uuid(val):
    if val is None:
        return None
    return val if isinstance(val, UUID) else UUID(str(val))


def _to_decimal(val) -> Decimal:
    if val is None:
        return Decimal("0")
    return val if isinstance(val, Decimal) else Decimal(str(val))


# --- Audit helper ---
async def _log_fee_audit(
    db: AsyncSession,
    tenant_id: UUID,
    reference_table: str,
    reference_id: UUID,
    action_type: str,
    old_value: Optional[dict],
    new_value: Optional[dict],
    changed_by: Optional[UUID],
) -> None:
    log = FeeAuditLog(
        tenant_id=tenant_id,
        reference_table=reference_table,
        reference_id=reference_id,
        action_type=action_type,
        old_value=old_value,
        new_value=new_value,
        changed_by=changed_by,
    )
    db.add(log)


# --- Class Fee Structure ---
def _cfs_to_response(cfs: ClassFeeStructure) -> ClassFeeStructureResponse:
    return ClassFeeStructureResponse(
        id=_to_uuid(cfs.id),
        tenant_id=_to_uuid(cfs.tenant_id),
        academic_year_id=_to_uuid(cfs.academic_year_id),
        class_id=_to_uuid(cfs.class_id),
        fee_component_id=_to_uuid(cfs.fee_component_id),
        amount=_to_decimal(cfs.amount),
        frequency=cfs.frequency,
        due_date=cfs.due_date,
        is_mandatory=cfs.is_mandatory,
        is_active=cfs.is_active,
        created_at=cfs.created_at,
        updated_at=cfs.updated_at,
    )


async def create_class_fee_structure(
    db: AsyncSession,
    tenant_id: UUID,
    payload: ClassFeeStructureCreate,
) -> ClassFeeStructureResponse:
    ay = await db.get(AcademicYear, payload.academic_year_id)
    if not ay or ay.tenant_id != tenant_id:
        raise ServiceError("Invalid academic year", status.HTTP_400_BAD_REQUEST)
    if ay.status != "ACTIVE":
        raise ServiceError("Cannot modify fee structure for a CLOSED academic year", status.HTTP_400_BAD_REQUEST)
    cl = await db.get(SchoolClass, payload.class_id)
    if not cl or cl.tenant_id != tenant_id:
        raise ServiceError("Invalid class", status.HTTP_400_BAD_REQUEST)
    fc = await db.get(FeeComponent, payload.fee_component_id)
    if not fc or fc.tenant_id != tenant_id or not fc.is_active:
        raise ServiceError("Invalid fee component", status.HTTP_400_BAD_REQUEST)
    try:
        cfs = ClassFeeStructure(
            tenant_id=tenant_id,
            academic_year_id=payload.academic_year_id,
            class_id=payload.class_id,
            fee_component_id=payload.fee_component_id,
            amount=payload.amount,
            frequency=payload.frequency.strip().lower(),
            due_date=payload.due_date,
            is_mandatory=payload.is_mandatory,
            is_active=True,
        )
        db.add(cfs)
        await db.flush()
        await _log_fee_audit(
            db, tenant_id, "class_fee_structures", cfs.id,
            "CREATE", None,
            {"amount": str(payload.amount), "frequency": cfs.frequency, "class_id": str(payload.class_id), "fee_component_id": str(payload.fee_component_id)},
            None,
        )
        await db.commit()
        await db.refresh(cfs)
        return _cfs_to_response(cfs)
    except IntegrityError:
        await db.rollback()
        raise ServiceError(
            "This class already has this fee component for this academic year",
            status.HTTP_409_CONFLICT,
        )


async def list_class_fee_structures(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: UUID,
    class_id: Optional[UUID] = None,
) -> List[ClassFeeStructureResponse]:
    stmt = select(ClassFeeStructure).where(
        ClassFeeStructure.tenant_id == tenant_id,
        ClassFeeStructure.academic_year_id == academic_year_id,
        ClassFeeStructure.is_active.is_(True),
    )
    if class_id is not None:
        stmt = stmt.where(ClassFeeStructure.class_id == class_id)
    stmt = stmt.order_by(ClassFeeStructure.class_id, ClassFeeStructure.fee_component_id)
    result = await db.execute(stmt)
    return [_cfs_to_response(c) for c in result.scalars().all()]


async def list_all_class_fees(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: UUID,
    active_only: bool = True,
) -> List[ClassFeeStructureByClassResponse]:
    """
    Read all class fee structures for an academic year, grouped by class with component details.
    """
    stmt = (
        select(
            ClassFeeStructure,
            SchoolClass.name.label("class_name"),
            FeeComponent.name.label("fee_component_name"),
            FeeComponent.code.label("fee_component_code"),
        )
        .join(SchoolClass, ClassFeeStructure.class_id == SchoolClass.id)
        .join(FeeComponent, ClassFeeStructure.fee_component_id == FeeComponent.id)
        .where(
            ClassFeeStructure.tenant_id == tenant_id,
            ClassFeeStructure.academic_year_id == academic_year_id,
        )
    )
    if active_only:
        stmt = stmt.where(ClassFeeStructure.is_active.is_(True), FeeComponent.is_active.is_(True))
    stmt = stmt.order_by(SchoolClass.display_order.nullslast(), SchoolClass.name, FeeComponent.name)

    result = await db.execute(stmt)
    rows = result.all()

    grouped: dict[UUID, ClassFeeStructureByClassResponse] = {}
    for cfs, class_name, fc_name, fc_code in rows:
        class_id = _to_uuid(cfs.class_id)
        if class_id not in grouped:
            grouped[class_id] = ClassFeeStructureByClassResponse(
                academic_year_id=_to_uuid(cfs.academic_year_id),
                class_id=class_id,
                class_name=class_name,
                items=[],
            )
        grouped[class_id].items.append(
            ClassFeeStructureItem(
                id=_to_uuid(cfs.id),
                fee_component_id=_to_uuid(cfs.fee_component_id),
                fee_component_name=fc_name,
                fee_component_code=fc_code,
                amount=_to_decimal(cfs.amount),
                frequency=cfs.frequency,
                due_date=cfs.due_date,
                is_mandatory=cfs.is_mandatory,
                is_active=cfs.is_active,
                created_at=cfs.created_at,
                updated_at=cfs.updated_at,
            )
        )

    return list(grouped.values())


# --- Student Fee Assignment ---
def _sfa_to_response(sfa: StudentFeeAssignment) -> StudentFeeAssignmentResponse:
    return StudentFeeAssignmentResponse(
        id=_to_uuid(sfa.id),
        tenant_id=_to_uuid(sfa.tenant_id),
        academic_year_id=_to_uuid(sfa.academic_year_id),
        student_id=_to_uuid(sfa.student_id),
        source_type=sfa.source_type,
        class_fee_structure_id=_to_uuid(sfa.class_fee_structure_id),
        custom_name=sfa.custom_name,
        base_amount=_to_decimal(sfa.base_amount),
        total_discount=_to_decimal(sfa.total_discount),
        final_amount=_to_decimal(sfa.final_amount),
        status=sfa.status,
        is_active=sfa.is_active,
        created_at=sfa.created_at,
        updated_at=sfa.updated_at,
    )


async def assign_template_fees_to_student(
    db: AsyncSession,
    tenant_id: UUID,
    student_id: UUID,
    payload: AssignTemplateFeesRequest,
    changed_by: Optional[UUID] = None,
) -> List[StudentFeeAssignmentResponse]:
    """Assign TEMPLATE fees from class_fee_structure: mandatory auto + selected optional (with custom amount override)."""
    academic_year_id = payload.academic_year_id
    ay = await db.get(AcademicYear, academic_year_id)
    if not ay or ay.tenant_id != tenant_id:
        raise ServiceError("Invalid academic year", status.HTTP_400_BAD_REQUEST)
    if ay.status != "ACTIVE":
        raise ServiceError("Cannot assign fees for a CLOSED academic year", status.HTTP_400_BAD_REQUEST)

    # Validate student exists in tenant
    student = (
        await db.execute(select(User).where(User.id == student_id, User.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if not student:
        raise ServiceError("Invalid student", status.HTTP_400_BAD_REQUEST)

    rec = (
        await db.execute(
            select(StudentAcademicRecord).where(
                StudentAcademicRecord.student_id == student_id,
                StudentAcademicRecord.academic_year_id == academic_year_id,
                StudentAcademicRecord.status == "ACTIVE",
            )
        )
    ).scalar_one_or_none()
    if not rec:
        raise ServiceError("Student not enrolled for this academic year", status.HTTP_400_BAD_REQUEST)
    class_id = rec.class_id
    cfs_list = (
        await db.execute(
            select(ClassFeeStructure).where(
                ClassFeeStructure.tenant_id == tenant_id,
                ClassFeeStructure.academic_year_id == academic_year_id,
                ClassFeeStructure.class_id == class_id,
                ClassFeeStructure.is_active.is_(True),
            )
        )
    ).scalars().all()
    if not cfs_list:
        raise ServiceError("No fee structure defined for this class", status.HTTP_400_BAD_REQUEST)

    mandatory = [c for c in cfs_list if bool(c.is_mandatory)]
    optional = [c for c in cfs_list if not bool(c.is_mandatory)]
    optional_map = {c.id: c for c in optional}

    selected_optional_ids: List[UUID] = []
    selected_optional_amounts: dict[UUID, Optional[Decimal]] = {}
    for oc in payload.optional_components or []:
        selected_optional_ids.append(oc.class_fee_structure_id)
        selected_optional_amounts[oc.class_fee_structure_id] = oc.custom_amount

    # Validate selected optional ids are actually optional & belong to this class+year
    invalid = [str(i) for i in selected_optional_ids if i not in optional_map]
    if invalid:
        raise ServiceError(
            "Invalid optional component selection (not part of this class fee structure)",
            status.HTTP_400_BAD_REQUEST,
        )

    to_assign: List[tuple[ClassFeeStructure, Optional[Decimal]]] = []
    for cfs in mandatory:
        to_assign.append((cfs, None))
    for cid in selected_optional_ids:
        to_assign.append((optional_map[cid], selected_optional_amounts.get(cid)))

    created: List[StudentFeeAssignment] = []
    async with db.begin():
        for cfs, custom_amount in to_assign:
            existing = (
                await db.execute(
                    select(StudentFeeAssignment.id).where(
                        StudentFeeAssignment.student_id == student_id,
                        StudentFeeAssignment.academic_year_id == academic_year_id,
                        StudentFeeAssignment.source_type == "TEMPLATE",
                        StudentFeeAssignment.class_fee_structure_id == cfs.id,
                        StudentFeeAssignment.is_active.is_(True),
                    )
                )
            ).scalar_one_or_none()
            if existing:
                continue

            amount = _to_decimal(custom_amount) if custom_amount is not None else _to_decimal(cfs.amount)
            if amount < 0:
                raise ServiceError("Fee amount cannot be negative", status.HTTP_400_BAD_REQUEST)

            sfa = StudentFeeAssignment(
                tenant_id=tenant_id,
                academic_year_id=academic_year_id,
                student_id=student_id,
                source_type="TEMPLATE",
                class_fee_structure_id=cfs.id,
                custom_name=None,
                base_amount=amount,
                total_discount=Decimal("0"),
                final_amount=amount,
                status="unpaid",
                is_active=True,
            )
            db.add(sfa)
            await db.flush()
            await _log_fee_audit(
                db,
                tenant_id,
                "student_fee_assignments",
                sfa.id,
                "CREATE",
                None,
                {
                    "student_id": str(student_id),
                    "source_type": "TEMPLATE",
                    "class_fee_structure_id": str(cfs.id),
                    "base_amount": str(amount),
                    "final_amount": str(amount),
                },
                changed_by,
            )
            created.append(sfa)

    for s in created:
        await db.refresh(s)
    return [_sfa_to_response(s) for s in created]


async def add_custom_student_fee(
    db: AsyncSession,
    tenant_id: UUID,
    student_id: UUID,
    payload: AddCustomStudentFeeRequest,
    changed_by: Optional[UUID],
) -> StudentFeeAssignmentResponse:
    ay = await db.get(AcademicYear, payload.academic_year_id)
    if not ay or ay.tenant_id != tenant_id:
        raise ServiceError("Invalid academic year", status.HTTP_400_BAD_REQUEST)
    if ay.status != "ACTIVE":
        raise ServiceError("Cannot add custom fee for a CLOSED academic year", status.HTTP_400_BAD_REQUEST)

    student = (
        await db.execute(select(User).where(User.id == student_id, User.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if not student:
        raise ServiceError("Invalid student", status.HTTP_400_BAD_REQUEST)

    amount = _to_decimal(payload.amount)
    if amount < 0:
        raise ServiceError("Fee amount cannot be negative", status.HTTP_400_BAD_REQUEST)

    async with db.begin():
        sfa = StudentFeeAssignment(
            tenant_id=tenant_id,
            academic_year_id=payload.academic_year_id,
            student_id=student_id,
            source_type="CUSTOM",
            class_fee_structure_id=None,
            custom_name=payload.custom_name.strip(),
            base_amount=amount,
            total_discount=Decimal("0"),
            final_amount=amount,
            status="unpaid",
            is_active=True,
        )
        db.add(sfa)
        await db.flush()
        await _log_fee_audit(
            db,
            tenant_id,
            "student_fee_assignments",
            sfa.id,
            "CREATE",
            None,
            {
                "student_id": str(student_id),
                "source_type": "CUSTOM",
                "custom_name": sfa.custom_name,
                "base_amount": str(amount),
                "final_amount": str(amount),
                "reason": (payload.reason or "").strip() or None,
            },
            changed_by,
        )
    await db.refresh(sfa)
    return _sfa_to_response(sfa)


async def get_student_fees(
    db: AsyncSession,
    tenant_id: UUID,
    student_id: UUID,
    academic_year_id: Optional[UUID] = None,
) -> List[StudentFeeAssignmentWithDetails]:
    class_id_expr = func.coalesce(ClassFeeStructure.class_id, StudentAcademicRecord.class_id)
    stmt = (
        select(
            StudentFeeAssignment,
            FeeComponent.name.label("fee_component_name"),
            FeeComponent.code.label("fee_component_code"),
            SchoolClass.name.label("class_name"),
        )
        .outerjoin(
            ClassFeeStructure,
            StudentFeeAssignment.class_fee_structure_id == ClassFeeStructure.id,
        )
        .outerjoin(FeeComponent, ClassFeeStructure.fee_component_id == FeeComponent.id)
        .outerjoin(
            StudentAcademicRecord,
            and_(
                StudentAcademicRecord.student_id == StudentFeeAssignment.student_id,
                StudentAcademicRecord.academic_year_id == StudentFeeAssignment.academic_year_id,
            ),
        )
        .outerjoin(SchoolClass, SchoolClass.id == class_id_expr)
        .where(
            StudentFeeAssignment.tenant_id == tenant_id,
            StudentFeeAssignment.student_id == student_id,
            StudentFeeAssignment.is_active.is_(True),
        )
    )
    if academic_year_id is not None:
        stmt = stmt.where(StudentFeeAssignment.academic_year_id == academic_year_id)
    stmt = stmt.order_by(StudentFeeAssignment.created_at)
    result = await db.execute(stmt)
    rows = result.all()
    out = []
    for row in rows:
        sfa, fc_name, fc_code, cl_name = row
        if (sfa.source_type or "").upper() == "CUSTOM":
            fc_name = sfa.custom_name or fc_name
            fc_code = fc_code or None
        out.append(
            StudentFeeAssignmentWithDetails(
                id=_to_uuid(sfa.id),
                tenant_id=_to_uuid(sfa.tenant_id),
                academic_year_id=_to_uuid(sfa.academic_year_id),
                student_id=_to_uuid(sfa.student_id),
                source_type=sfa.source_type,
                class_fee_structure_id=_to_uuid(sfa.class_fee_structure_id),
                custom_name=sfa.custom_name,
                base_amount=_to_decimal(sfa.base_amount),
                total_discount=_to_decimal(sfa.total_discount),
                final_amount=_to_decimal(sfa.final_amount),
                status=sfa.status,
                is_active=sfa.is_active,
                created_at=sfa.created_at,
                updated_at=sfa.updated_at,
                fee_component_name=fc_name,
                fee_component_code=fc_code,
                class_name=cl_name,
            )
        )
    return out


# --- Discount ---
def _sfd_to_response(sfd: StudentFeeDiscount) -> StudentFeeDiscountResponse:
    return StudentFeeDiscountResponse(
        id=_to_uuid(sfd.id),
        tenant_id=_to_uuid(sfd.tenant_id),
        academic_year_id=_to_uuid(sfd.academic_year_id),
        student_fee_assignment_id=_to_uuid(sfd.student_fee_assignment_id),
        discount_name=sfd.discount_name,
        discount_category=sfd.discount_category,
        discount_type=sfd.discount_type,
        discount_value=_to_decimal(sfd.discount_value),
        calculated_discount_amount=_to_decimal(sfd.calculated_discount_amount),
        reason=sfd.reason,
        approved_by=_to_uuid(sfd.approved_by),
        is_active=sfd.is_active,
        created_at=sfd.created_at,
        updated_at=sfd.updated_at,
    )


async def _recalculate_assignment(
    db: AsyncSession,
    sfa: StudentFeeAssignment,
    tenant_id: UUID,
    changed_by: Optional[UUID],
) -> None:
    total = (
        await db.execute(
            select(func.coalesce(func.sum(StudentFeeDiscount.calculated_discount_amount), 0)).where(
                StudentFeeDiscount.student_fee_assignment_id == sfa.id,
                StudentFeeDiscount.is_active.is_(True),
            )
        )
    ).scalar() or Decimal("0")
    orig = _to_decimal(sfa.base_amount)
    final = max(Decimal("0"), orig - total)
    total_paid = (
        await db.execute(
            select(func.coalesce(func.sum(PaymentTransaction.amount_paid), 0)).where(
                PaymentTransaction.student_fee_assignment_id == sfa.id,
                PaymentTransaction.payment_status == "success",
            )
        )
    ).scalar() or Decimal("0")
    if total_paid >= final:
        new_status = "paid"
    elif total_paid > 0:
        new_status = "partial"
    else:
        new_status = "unpaid"
    old_status = sfa.status
    sfa.total_discount = total
    sfa.final_amount = final
    sfa.status = new_status
    await _log_fee_audit(
        db, tenant_id, "student_fee_assignments", sfa.id,
        "UPDATE",
        {"total_discount": str(sfa.total_discount), "final_amount": str(sfa.final_amount), "status": old_status},
        {"total_discount": str(total), "final_amount": str(final), "status": new_status},
        changed_by,
    )


async def add_discount(
    db: AsyncSession,
    tenant_id: UUID,
    student_fee_assignment_id: UUID,
    payload: StudentFeeDiscountCreate,
    approved_by: Optional[UUID],
    current_user_role: str,
) -> StudentFeeDiscountResponse:
    sfa = (
        await db.execute(
            select(StudentFeeAssignment).where(
                StudentFeeAssignment.id == student_fee_assignment_id,
                StudentFeeAssignment.tenant_id == tenant_id,
                StudentFeeAssignment.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if not sfa:
        raise ServiceError("Student fee assignment not found", status.HTTP_404_NOT_FOUND)
    # TEMPLATE fees: enforce allow_discount from fee_component
    if (sfa.source_type or "").upper() == "TEMPLATE":
        cfs = await db.get(ClassFeeStructure, sfa.class_fee_structure_id)
        fc = await db.get(FeeComponent, cfs.fee_component_id) if cfs else None
        if not fc or not fc.allow_discount:
            raise ServiceError("Discounts are not allowed for this fee component", status.HTTP_400_BAD_REQUEST)
    orig = _to_decimal(sfa.base_amount)
    if payload.discount_type == "percentage":
        calc = orig * (payload.discount_value / Decimal("100"))
        if payload.discount_value > Decimal("20") and current_user_role not in ("SUPER_ADMIN", "PLATFORM_ADMIN", "ADMIN"):
            raise ServiceError("Only Admin can approve discount greater than 20%", status.HTTP_403_FORBIDDEN)
    else:
        calc = payload.discount_value
    existing_total = _to_decimal(sfa.total_discount)
    if existing_total + calc > orig:
        raise ServiceError("Total discount cannot exceed original amount", status.HTTP_400_BAD_REQUEST)
    sfd = StudentFeeDiscount(
        tenant_id=tenant_id,
        academic_year_id=sfa.academic_year_id,
        student_fee_assignment_id=student_fee_assignment_id,
        discount_name=payload.discount_name.strip(),
        discount_category=payload.discount_category.strip().upper(),
        discount_type=payload.discount_type.strip().lower(),
        discount_value=payload.discount_value,
        calculated_discount_amount=calc,
        reason=(payload.reason or "").strip() or None,
        approved_by=approved_by,
        is_active=True,
    )
    db.add(sfd)
    await db.flush()
    await _recalculate_assignment(db, sfa, tenant_id, approved_by)
    await db.commit()
    await db.refresh(sfd)
    await db.refresh(sfa)
    return _sfd_to_response(sfd)


async def deactivate_discount(
    db: AsyncSession,
    tenant_id: UUID,
    discount_id: UUID,
    changed_by: Optional[UUID],
) -> Optional[StudentFeeDiscountResponse]:
    sfd = (
        await db.execute(
            select(StudentFeeDiscount).where(
                StudentFeeDiscount.id == discount_id,
                StudentFeeDiscount.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if not sfd:
        return None
    sfa = await db.get(StudentFeeAssignment, sfd.student_fee_assignment_id)
    if not sfa:
        return None
    sfd.is_active = False
    await _recalculate_assignment(db, sfa, tenant_id, changed_by)
    await _log_fee_audit(
        db, tenant_id, "student_fee_discounts", sfd.id,
        "DEACTIVATE",
        {"is_active": True, "calculated_discount_amount": str(sfd.calculated_discount_amount)},
        {"is_active": False},
        changed_by,
    )
    await db.commit()
    await db.refresh(sfd)
    return _sfd_to_response(sfd)


# --- Payment ---
def _pt_to_response(pt: PaymentTransaction) -> PaymentResponse:
    return PaymentResponse(
        id=_to_uuid(pt.id),
        tenant_id=_to_uuid(pt.tenant_id),
        academic_year_id=_to_uuid(pt.academic_year_id),
        student_fee_assignment_id=_to_uuid(pt.student_fee_assignment_id),
        amount_paid=_to_decimal(pt.amount_paid),
        payment_mode=pt.payment_mode,
        transaction_reference=pt.transaction_reference,
        payment_status=pt.payment_status,
        paid_at=pt.paid_at,
        collected_by=_to_uuid(pt.collected_by),
        created_at=pt.created_at,
    )


async def record_payment(
    db: AsyncSession,
    tenant_id: UUID,
    student_fee_assignment_id: UUID,
    payload: PaymentCreate,
    collected_by: Optional[UUID],
    changed_by: Optional[UUID],
) -> PaymentResponse:
    from datetime import datetime, timezone

    sfa = (
        await db.execute(
            select(StudentFeeAssignment).where(
                StudentFeeAssignment.id == student_fee_assignment_id,
                StudentFeeAssignment.tenant_id == tenant_id,
                StudentFeeAssignment.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if not sfa:
        raise ServiceError("Student fee assignment not found", status.HTTP_404_NOT_FOUND)
    final = _to_decimal(sfa.final_amount)
    total_paid = (
        await db.execute(
            select(func.coalesce(func.sum(PaymentTransaction.amount_paid), 0)).where(
                PaymentTransaction.student_fee_assignment_id == student_fee_assignment_id,
                PaymentTransaction.payment_status == "success",
            )
        )
    ).scalar() or Decimal("0")
    balance = final - total_paid
    if payload.amount_paid > balance:
        raise ServiceError("Payment amount cannot exceed remaining balance", status.HTTP_400_BAD_REQUEST)
    paid_at = payload.paid_at or datetime.now(timezone.utc)
    pt = PaymentTransaction(
        tenant_id=tenant_id,
        academic_year_id=sfa.academic_year_id,
        student_fee_assignment_id=student_fee_assignment_id,
        amount_paid=payload.amount_paid,
        payment_mode=payload.payment_mode.strip().upper(),
        transaction_reference=(payload.transaction_reference or "").strip() or None,
        payment_status="success",
        paid_at=paid_at,
        collected_by=collected_by,
    )
    db.add(pt)
    await db.flush()
    new_total = total_paid + payload.amount_paid
    old_status = sfa.status
    if new_total >= final:
        sfa.status = "paid"
    else:
        sfa.status = "partial"
    await _log_fee_audit(
        db, tenant_id, "payment_transactions", pt.id,
        "CREATE",
        None,
        {"amount_paid": str(payload.amount_paid), "payment_mode": pt.payment_mode, "student_fee_assignment_id": str(student_fee_assignment_id), "assignment_old_status": old_status, "assignment_new_status": sfa.status},
        changed_by,
    )
    await _log_fee_audit(
        db, tenant_id, "student_fee_assignments", sfa.id,
        "UPDATE",
        {"status": old_status},
        {"status": sfa.status},
        changed_by,
    )
    await db.commit()
    await db.refresh(pt)
    return _pt_to_response(pt)


async def get_payment_history(
    db: AsyncSession,
    tenant_id: UUID,
    student_id: UUID,
    academic_year_id: Optional[UUID] = None,
) -> List[PaymentResponse]:
    stmt = (
        select(PaymentTransaction)
        .join(StudentFeeAssignment, PaymentTransaction.student_fee_assignment_id == StudentFeeAssignment.id)
        .where(
            PaymentTransaction.tenant_id == tenant_id,
            StudentFeeAssignment.student_id == student_id,
            PaymentTransaction.payment_status == "success",
        )
    )
    if academic_year_id is not None:
        stmt = stmt.where(PaymentTransaction.academic_year_id == academic_year_id)
    stmt = stmt.order_by(PaymentTransaction.paid_at.desc())
    result = await db.execute(stmt)
    return [_pt_to_response(pt) for pt in result.scalars().all()]


# --- Report ---
async def get_fee_report(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: UUID,
    class_id: Optional[UUID] = None,
    status_filter: Optional[str] = None,
) -> List[FeeReportItem]:
    from app.core.models import Section

    paid_subq = (
        select(
            PaymentTransaction.student_fee_assignment_id,
            func.coalesce(func.sum(PaymentTransaction.amount_paid), 0).label("total_paid"),
        )
        .where(PaymentTransaction.payment_status == "success")
        .group_by(PaymentTransaction.student_fee_assignment_id)
    ).subquery()

    class_id_expr = func.coalesce(ClassFeeStructure.class_id, StudentAcademicRecord.class_id)
    fee_name_expr = func.coalesce(FeeComponent.name, StudentFeeAssignment.custom_name)

    stmt = (
        select(
            StudentFeeAssignment,
            fee_name_expr.label("fee_component_name"),
            SchoolClass.name.label("class_name"),
            SchoolClass.id.label("class_id"),
            func.coalesce(paid_subq.c.total_paid, 0).label("amount_paid"),
        )
        .outerjoin(ClassFeeStructure, StudentFeeAssignment.class_fee_structure_id == ClassFeeStructure.id)
        .outerjoin(FeeComponent, ClassFeeStructure.fee_component_id == FeeComponent.id)
        .outerjoin(
            StudentAcademicRecord,
            and_(
                StudentAcademicRecord.student_id == StudentFeeAssignment.student_id,
                StudentAcademicRecord.academic_year_id == StudentFeeAssignment.academic_year_id,
            ),
        )
        .join(SchoolClass, SchoolClass.id == class_id_expr)
        .outerjoin(paid_subq, StudentFeeAssignment.id == paid_subq.c.student_fee_assignment_id)
        .where(
            StudentFeeAssignment.tenant_id == tenant_id,
            StudentFeeAssignment.academic_year_id == academic_year_id,
            StudentFeeAssignment.is_active.is_(True),
        )
    )
    if class_id is not None:
        stmt = stmt.where(class_id_expr == class_id)
    if status_filter:
        stmt = stmt.where(StudentFeeAssignment.status == status_filter)
    stmt = stmt.order_by(SchoolClass.name, fee_name_expr)
    result = await db.execute(stmt)
    rows = result.all()
    items = []
    for row in rows:
        sfa, fc_name, cl_name, cl_id, amount_paid_val = row
        amount_paid = _to_decimal(amount_paid_val)
        final = _to_decimal(sfa.final_amount)
        balance = final - amount_paid
        rec = (
            await db.execute(
                select(StudentAcademicRecord.section_id).where(
                    StudentAcademicRecord.student_id == sfa.student_id,
                    StudentAcademicRecord.academic_year_id == sfa.academic_year_id,
                )
            )
        ).scalar_one_or_none()
        section_id = rec[0] if rec else None
        section_name = None
        if section_id:
            sec = await db.get(Section, section_id)
            section_name = sec.name if sec else None
        items.append(
            FeeReportItem(
                student_id=_to_uuid(sfa.student_id),
                student_name=None,
                class_id=_to_uuid(cl_id),
                class_name=cl_name,
                section_id=_to_uuid(section_id),
                section_name=section_name,
                assignment_id=_to_uuid(sfa.id),
                fee_component_name=fc_name,
                base_amount=_to_decimal(sfa.base_amount),
                total_discount=_to_decimal(sfa.total_discount),
                final_amount=final,
                amount_paid=amount_paid,
                balance=balance,
                status=sfa.status,
            )
        )
    user_ids = {i.student_id for i in items}
    if user_ids:
        users = (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
        umap = {u.id: u.full_name for u in users}
        for it in items:
            it.student_name = umap.get(it.student_id)
    return items
