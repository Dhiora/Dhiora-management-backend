"""Grades service layer: marks entry, grade scales, report cards."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.schemas import CurrentUser
from app.core.exceptions import ServiceError
from app.core.models.academic_year import AcademicYear
from app.core.models.class_model import SchoolClass
from app.core.models.exam import Exam
from app.core.models.exam_schedule import ExamSchedule
from app.core.models.exam_type import ExamType
from app.core.models.school_subject import SchoolSubject
from app.core.models.section_model import Section
from app.core.models.student_academic_record import StudentAcademicRecord
from app.core.models.teacher_subject_assignment import TeacherSubjectAssignment

from .models import ExamMark, GradeScale
from .schemas import (
    BulkMarksRequest,
    BulkMarksResult,
    ExamGradeSummary,
    ExamMarksResponse,
    GradeScaleCreate,
    GradeScaleItem,
    GradeScaleUpdate,
    MarkEntry,
    MarkUpdateRequest,
    ReportCard,
    ReportCardSubject,
    StudentMarksRow,
    SubjectMarkItem,
)

_ADMIN_ROLES = {"SUPER_ADMIN", "ADMIN", "SCHOOL_ADMIN"}
_WRITE_ROLES = {"SUPER_ADMIN", "ADMIN", "SCHOOL_ADMIN", "TEACHER"}

_DEFAULT_SCALES = [
    {"label": "A+", "min_percentage": Decimal("90"), "max_percentage": Decimal("100"), "gpa_points": Decimal("4.0"), "display_order": 1},
    {"label": "A",  "min_percentage": Decimal("80"), "max_percentage": Decimal("89.99"), "gpa_points": Decimal("3.7"), "display_order": 2},
    {"label": "B+", "min_percentage": Decimal("70"), "max_percentage": Decimal("79.99"), "gpa_points": Decimal("3.3"), "display_order": 3},
    {"label": "B",  "min_percentage": Decimal("60"), "max_percentage": Decimal("69.99"), "gpa_points": Decimal("3.0"), "display_order": 4},
    {"label": "C",  "min_percentage": Decimal("50"), "max_percentage": Decimal("59.99"), "gpa_points": Decimal("2.0"), "display_order": 5},
    {"label": "D",  "min_percentage": Decimal("40"), "max_percentage": Decimal("49.99"), "gpa_points": Decimal("1.0"), "display_order": 6},
    {"label": "F",  "min_percentage": Decimal("0"),  "max_percentage": Decimal("39.99"), "gpa_points": Decimal("0.0"), "display_order": 7},
]


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _apply_grade(percentage: Optional[float], scales: List[GradeScale]) -> Optional[str]:
    if percentage is None:
        return None
    for scale in sorted(scales, key=lambda s: s.min_percentage, reverse=True):
        if float(scale.min_percentage) <= percentage <= float(scale.max_percentage):
            return scale.label
    return None


def _calc_percentage(marks_obtained: Optional[Decimal], max_marks: Decimal) -> Optional[float]:
    if marks_obtained is None or max_marks == 0:
        return None
    return round(float(marks_obtained) / float(max_marks) * 100, 2)


async def _get_exam(db: AsyncSession, exam_id: UUID, tenant_id: UUID) -> Exam:
    exam = await db.get(Exam, exam_id)
    if not exam or exam.tenant_id != tenant_id:
        raise ServiceError("Exam not found", status.HTTP_404_NOT_FOUND)
    return exam


async def _get_scales(db: AsyncSession, tenant_id: UUID) -> List[GradeScale]:
    result = await db.execute(
        select(GradeScale)
        .where(GradeScale.tenant_id == tenant_id)
        .order_by(GradeScale.min_percentage.desc())
    )
    scales = result.scalars().all()
    if not scales:
        # Return built-in defaults as transient objects (not persisted)
        defaults = []
        for d in _DEFAULT_SCALES:
            g = GradeScale()
            g.label = d["label"]
            g.min_percentage = d["min_percentage"]
            g.max_percentage = d["max_percentage"]
            g.gpa_points = d["gpa_points"]
            g.display_order = d["display_order"]
            defaults.append(g)
        return defaults
    return list(scales)


async def _get_active_academic_year(db: AsyncSession, tenant_id: UUID) -> Optional[AcademicYear]:
    result = await db.execute(
        select(AcademicYear).where(
            AcademicYear.tenant_id == tenant_id,
            AcademicYear.is_current.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def _get_student_record(db: AsyncSession, student_id: UUID, academic_year_id: UUID) -> Optional[StudentAcademicRecord]:
    result = await db.execute(
        select(StudentAcademicRecord).where(
            StudentAcademicRecord.student_id == student_id,
            StudentAcademicRecord.academic_year_id == academic_year_id,
            StudentAcademicRecord.status == "ACTIVE",
        )
    )
    return result.scalar_one_or_none()


async def _assert_teacher_subject_access(
    db: AsyncSession,
    teacher_id: UUID,
    academic_year_id: UUID,
    class_id: UUID,
    section_id: Optional[UUID],
    subject_id: UUID,
) -> None:
    stmt = select(TeacherSubjectAssignment).where(
        TeacherSubjectAssignment.teacher_id == teacher_id,
        TeacherSubjectAssignment.academic_year_id == academic_year_id,
        TeacherSubjectAssignment.class_id == class_id,
        TeacherSubjectAssignment.subject_id == subject_id,
    )
    if section_id:
        stmt = stmt.where(TeacherSubjectAssignment.section_id == section_id)
    result = await db.execute(stmt)
    if not result.scalar_one_or_none():
        raise ServiceError(
            "Teacher not assigned to this subject for the given class/section",
            status.HTTP_403_FORBIDDEN,
        )


async def _teacher_has_class_access(
    db: AsyncSession,
    teacher_id: UUID,
    academic_year_id: UUID,
    class_id: UUID,
    section_id: Optional[UUID],
) -> bool:
    stmt = select(TeacherSubjectAssignment).where(
        TeacherSubjectAssignment.teacher_id == teacher_id,
        TeacherSubjectAssignment.academic_year_id == academic_year_id,
        TeacherSubjectAssignment.class_id == class_id,
    )
    if section_id:
        stmt = stmt.where(TeacherSubjectAssignment.section_id == section_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


def _assert_student_self_access(current_user: CurrentUser, student_id: UUID) -> None:
    if current_user.role == "STUDENT" and current_user.id != student_id:
        raise ServiceError("Students can only access their own data", status.HTTP_403_FORBIDDEN)


def _assert_write_permission(current_user: CurrentUser) -> None:
    if current_user.role not in _WRITE_ROLES:
        raise ServiceError("Insufficient permissions to enter marks", status.HTTP_403_FORBIDDEN)


async def _build_subject_mark_item(
    mark: ExamMark,
    subject_name: str,
    scales: List[GradeScale],
    db: AsyncSession,
) -> SubjectMarkItem:
    pct = None if mark.is_absent else _calc_percentage(mark.marks_obtained, mark.max_marks)
    entered_by_name = None
    if mark.entered_by:
        u = await db.get(User, mark.entered_by)
        entered_by_name = u.full_name if u else None
    return SubjectMarkItem(
        mark_id=mark.id,
        subject_id=mark.subject_id,
        subject_name=subject_name,
        marks_obtained=mark.marks_obtained,
        max_marks=mark.max_marks,
        percentage=pct,
        grade_label=_apply_grade(pct, scales),
        is_absent=mark.is_absent,
        remarks=mark.remarks,
        entered_by_name=entered_by_name,
        updated_at=mark.updated_at,
    )


def _aggregate_marks(subject_items: List[SubjectMarkItem]) -> tuple:
    """Returns (total_obtained, total_max, overall_pct) from a list of subject marks."""
    total_max = sum(float(s.max_marks) for s in subject_items)
    scored_items = [s for s in subject_items if s.marks_obtained is not None and not s.is_absent]
    if not scored_items or total_max == 0:
        return None, Decimal(str(total_max)), None
    total_obtained = sum(float(s.marks_obtained) for s in scored_items)
    pct = round(total_obtained / total_max * 100, 2)
    return Decimal(str(total_obtained)), Decimal(str(total_max)), pct


# ─── Grade Scales ─────────────────────────────────────────────────────────────

async def list_grade_scales(db: AsyncSession, tenant_id: UUID) -> List[GradeScaleItem]:
    scales = await _get_scales(db, tenant_id)
    result = []
    for s in sorted(scales, key=lambda x: x.display_order):
        result.append(GradeScaleItem(
            id=s.id if s.id else UUID(int=0),
            label=s.label,
            min_percentage=s.min_percentage,
            max_percentage=s.max_percentage,
            gpa_points=s.gpa_points,
            remarks=s.remarks,
            display_order=s.display_order,
        ))
    return result


async def create_grade_scale(db: AsyncSession, tenant_id: UUID, payload: GradeScaleCreate) -> GradeScaleItem:
    scale = GradeScale(
        tenant_id=tenant_id,
        label=payload.label,
        min_percentage=payload.min_percentage,
        max_percentage=payload.max_percentage,
        gpa_points=payload.gpa_points,
        remarks=payload.remarks,
        display_order=payload.display_order,
    )
    db.add(scale)
    await db.commit()
    await db.refresh(scale)
    return GradeScaleItem(
        id=scale.id,
        label=scale.label,
        min_percentage=scale.min_percentage,
        max_percentage=scale.max_percentage,
        gpa_points=scale.gpa_points,
        remarks=scale.remarks,
        display_order=scale.display_order,
    )


async def update_grade_scale(db: AsyncSession, tenant_id: UUID, scale_id: UUID, payload: GradeScaleUpdate) -> GradeScaleItem:
    scale = await db.get(GradeScale, scale_id)
    if not scale or scale.tenant_id != tenant_id:
        raise ServiceError("Grade scale not found", status.HTTP_404_NOT_FOUND)
    if payload.label is not None:
        scale.label = payload.label
    if payload.min_percentage is not None:
        scale.min_percentage = payload.min_percentage
    if payload.max_percentage is not None:
        scale.max_percentage = payload.max_percentage
    if payload.gpa_points is not None:
        scale.gpa_points = payload.gpa_points
    if payload.remarks is not None:
        scale.remarks = payload.remarks
    if payload.display_order is not None:
        scale.display_order = payload.display_order
    await db.commit()
    await db.refresh(scale)
    return GradeScaleItem(
        id=scale.id,
        label=scale.label,
        min_percentage=scale.min_percentage,
        max_percentage=scale.max_percentage,
        gpa_points=scale.gpa_points,
        remarks=scale.remarks,
        display_order=scale.display_order,
    )


async def delete_grade_scale(db: AsyncSession, tenant_id: UUID, scale_id: UUID) -> None:
    scale = await db.get(GradeScale, scale_id)
    if not scale or scale.tenant_id != tenant_id:
        raise ServiceError("Grade scale not found", status.HTTP_404_NOT_FOUND)
    await db.delete(scale)
    await db.commit()


# ─── Marks Entry ─────────────────────────────────────────────────────────────

async def bulk_enter_marks(
    db: AsyncSession,
    tenant_id: UUID,
    exam_id: UUID,
    payload: BulkMarksRequest,
    current_user: CurrentUser,
) -> BulkMarksResult:
    _assert_write_permission(current_user)

    exam = await _get_exam(db, exam_id, tenant_id)

    ay = await _get_active_academic_year(db, tenant_id)
    if not ay:
        raise ServiceError("No active academic year found", status.HTTP_400_BAD_REQUEST)

    scales = await _get_scales(db, tenant_id)
    saved = 0
    errors: List[Dict[str, Any]] = []

    for entry in payload.marks:
        try:
            # Teacher permission check per subject
            if current_user.role == "TEACHER":
                await _assert_teacher_subject_access(
                    db, current_user.id, ay.id, exam.class_id, exam.section_id, entry.subject_id
                )

            # Validate student belongs to exam's class/section
            sar = await _get_student_record(db, entry.student_id, ay.id)
            if not sar or sar.class_id != exam.class_id:
                errors.append({"student_id": str(entry.student_id), "reason": "Student not enrolled in this class"})
                continue

            # Validate subject is scheduled in this exam
            sched_result = await db.execute(
                select(ExamSchedule).where(
                    ExamSchedule.exam_id == exam_id,
                    ExamSchedule.subject_id == entry.subject_id,
                )
            )
            if not sched_result.scalar_one_or_none():
                errors.append({"student_id": str(entry.student_id), "subject_id": str(entry.subject_id), "reason": "Subject not scheduled in this exam"})
                continue

            marks_val = None if entry.is_absent else entry.marks_obtained
            if marks_val is not None and marks_val > entry.max_marks:
                errors.append({"student_id": str(entry.student_id), "subject_id": str(entry.subject_id), "reason": "marks_obtained exceeds max_marks"})
                continue

            # Upsert
            existing_result = await db.execute(
                select(ExamMark).where(
                    ExamMark.exam_id == exam_id,
                    ExamMark.student_id == entry.student_id,
                    ExamMark.subject_id == entry.subject_id,
                )
            )
            mark = existing_result.scalar_one_or_none()
            if mark:
                mark.marks_obtained = marks_val
                mark.max_marks = entry.max_marks
                mark.is_absent = entry.is_absent
                mark.remarks = entry.remarks
                mark.entered_by = current_user.id
                mark.updated_at = datetime.utcnow()
            else:
                mark = ExamMark(
                    tenant_id=tenant_id,
                    academic_year_id=ay.id,
                    exam_id=exam_id,
                    student_id=entry.student_id,
                    subject_id=entry.subject_id,
                    class_id=exam.class_id,
                    section_id=exam.section_id,
                    marks_obtained=marks_val,
                    max_marks=entry.max_marks,
                    is_absent=entry.is_absent,
                    remarks=entry.remarks,
                    entered_by=current_user.id,
                )
                db.add(mark)
            saved += 1

        except ServiceError as e:
            errors.append({"student_id": str(entry.student_id), "reason": e.message})
        except Exception as e:
            errors.append({"student_id": str(entry.student_id), "reason": str(e)})

    await db.commit()
    return BulkMarksResult(saved=saved, errors=errors)


async def update_mark(
    db: AsyncSession,
    tenant_id: UUID,
    mark_id: UUID,
    payload: MarkUpdateRequest,
    current_user: CurrentUser,
) -> SubjectMarkItem:
    _assert_write_permission(current_user)

    mark = await db.get(ExamMark, mark_id)
    if not mark or mark.tenant_id != tenant_id:
        raise ServiceError("Mark record not found", status.HTTP_404_NOT_FOUND)

    # Teacher can only update marks for their assigned subject
    if current_user.role == "TEACHER":
        ay = await _get_active_academic_year(db, tenant_id)
        if ay:
            await _assert_teacher_subject_access(
                db, current_user.id, ay.id, mark.class_id, mark.section_id, mark.subject_id
            )

    if payload.is_absent is not None:
        mark.is_absent = payload.is_absent
    if payload.marks_obtained is not None:
        mark.marks_obtained = None if mark.is_absent else payload.marks_obtained
    if payload.max_marks is not None:
        mark.max_marks = payload.max_marks
    if payload.remarks is not None:
        mark.remarks = payload.remarks

    mark.marks_obtained = None if mark.is_absent else mark.marks_obtained
    mark.entered_by = current_user.id
    mark.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(mark)

    scales = await _get_scales(db, tenant_id)
    subj = await db.get(SchoolSubject, mark.subject_id)
    return await _build_subject_mark_item(mark, subj.name if subj else "", scales, db)


async def delete_mark(db: AsyncSession, tenant_id: UUID, mark_id: UUID, current_user: CurrentUser) -> None:
    if current_user.role not in _ADMIN_ROLES:
        raise ServiceError("Only admins can delete mark records", status.HTTP_403_FORBIDDEN)
    mark = await db.get(ExamMark, mark_id)
    if not mark or mark.tenant_id != tenant_id:
        raise ServiceError("Mark record not found", status.HTTP_404_NOT_FOUND)
    await db.delete(mark)
    await db.commit()


# ─── Read Marks ──────────────────────────────────────────────────────────────

async def get_exam_marks(
    db: AsyncSession,
    tenant_id: UUID,
    exam_id: UUID,
    current_user: CurrentUser,
    subject_id: Optional[UUID] = None,
) -> ExamMarksResponse:
    exam = await _get_exam(db, exam_id, tenant_id)
    scales = await _get_scales(db, tenant_id)

    school_class = await db.get(SchoolClass, exam.class_id)
    section = await db.get(Section, exam.section_id)
    exam_type_obj = await db.get(ExamType, exam.exam_type_id)

    ay = await _get_active_academic_year(db, tenant_id)

    # Teacher: must have at least one subject assignment in this class/section
    if current_user.role == "TEACHER" and ay:
        has_access = await _teacher_has_class_access(db, current_user.id, ay.id, exam.class_id, exam.section_id)
        if not has_access:
            raise ServiceError("Teacher not assigned to this class/section", status.HTTP_403_FORBIDDEN)

    # Student: only their own marks
    if current_user.role == "STUDENT":
        return await _get_single_student_marks_response(
            db, tenant_id, exam, current_user.id, scales, school_class, section
        )

    # Get all students in exam's class/section
    if not ay:
        return ExamMarksResponse(
            exam_id=exam.id,
            exam_name=exam.name,
            class_name=school_class.name if school_class else "",
            section_name=section.name if section else "",
            students=[],
        )

    sar_result = await db.execute(
        select(StudentAcademicRecord).where(
            StudentAcademicRecord.academic_year_id == ay.id,
            StudentAcademicRecord.class_id == exam.class_id,
            StudentAcademicRecord.section_id == exam.section_id,
            StudentAcademicRecord.status == "ACTIVE",
        )
    )
    records = sar_result.scalars().all()

    student_rows = []
    for sar in records:
        row = await _build_student_marks_row(
            db, tenant_id, exam_id, sar.student_id, sar.roll_number, scales, subject_id
        )
        student_rows.append(row)

    return ExamMarksResponse(
        exam_id=exam.id,
        exam_name=exam.name,
        class_name=school_class.name if school_class else "",
        section_name=section.name if section else "",
        students=student_rows,
    )


async def _get_single_student_marks_response(
    db: AsyncSession,
    tenant_id: UUID,
    exam: Exam,
    student_id: UUID,
    scales: List[GradeScale],
    school_class: Optional[SchoolClass],
    section: Optional[Section],
) -> ExamMarksResponse:
    student = await db.get(User, student_id)
    row = await _build_student_marks_row(db, tenant_id, exam.id, student_id, None, scales, None)
    if student:
        ay = await _get_active_academic_year(db, tenant_id)
        if ay:
            sar = await _get_student_record(db, student_id, ay.id)
            if sar:
                row.roll_number = sar.roll_number
    return ExamMarksResponse(
        exam_id=exam.id,
        exam_name=exam.name,
        class_name=school_class.name if school_class else "",
        section_name=section.name if section else "",
        students=[row],
    )


async def _build_student_marks_row(
    db: AsyncSession,
    tenant_id: UUID,
    exam_id: UUID,
    student_id: UUID,
    roll_number: Optional[str],
    scales: List[GradeScale],
    subject_id_filter: Optional[UUID] = None,
) -> StudentMarksRow:
    student = await db.get(User, student_id)
    full_name = student.full_name if student else str(student_id)

    # Get scheduled subjects for this exam
    sched_stmt = select(ExamSchedule).where(ExamSchedule.exam_id == exam_id)
    if subject_id_filter:
        sched_stmt = sched_stmt.where(ExamSchedule.subject_id == subject_id_filter)
    sched_result = await db.execute(sched_stmt)
    schedules = sched_result.scalars().all()

    subject_items: List[SubjectMarkItem] = []
    for sched in schedules:
        subj = await db.get(SchoolSubject, sched.subject_id)
        subj_name = subj.name if subj else str(sched.subject_id)

        mark_result = await db.execute(
            select(ExamMark).where(
                ExamMark.exam_id == exam_id,
                ExamMark.student_id == student_id,
                ExamMark.subject_id == sched.subject_id,
            )
        )
        mark = mark_result.scalar_one_or_none()

        if mark:
            subject_items.append(await _build_subject_mark_item(mark, subj_name, scales, db))
        else:
            subject_items.append(SubjectMarkItem(
                mark_id=UUID(int=0),
                subject_id=sched.subject_id,
                subject_name=subj_name,
                marks_obtained=None,
                max_marks=Decimal("100"),
                percentage=None,
                grade_label=None,
                is_absent=False,
                remarks=None,
                entered_by_name=None,
                updated_at=datetime.utcnow(),
            ))

    total_obtained, total_max, overall_pct = _aggregate_marks(subject_items)
    overall_grade = _apply_grade(overall_pct, scales) if overall_pct is not None else None

    return StudentMarksRow(
        student_id=student_id,
        full_name=full_name,
        roll_number=roll_number,
        subjects=subject_items,
        total_marks_obtained=total_obtained,
        total_max_marks=total_max,
        overall_percentage=overall_pct,
        overall_grade=overall_grade,
    )


# ─── Report Card ─────────────────────────────────────────────────────────────

async def get_report_card(
    db: AsyncSession,
    tenant_id: UUID,
    student_id: UUID,
    exam_id: UUID,
    current_user: CurrentUser,
) -> ReportCard:
    _assert_student_self_access(current_user, student_id)

    # Teacher access check
    exam = await _get_exam(db, exam_id, tenant_id)
    if current_user.role == "TEACHER":
        ay_check = await _get_active_academic_year(db, tenant_id)
        if ay_check:
            has_access = await _teacher_has_class_access(db, current_user.id, ay_check.id, exam.class_id, exam.section_id)
            if not has_access:
                raise ServiceError("Teacher not assigned to this class/section", status.HTTP_403_FORBIDDEN)

    return await _build_report_card(db, tenant_id, student_id, exam_id)


async def _build_report_card(
    db: AsyncSession,
    tenant_id: UUID,
    student_id: UUID,
    exam_id: UUID,
) -> ReportCard:
    exam = await _get_exam(db, exam_id, tenant_id)
    exam_type_obj = await db.get(ExamType, exam.exam_type_id)
    school_class = await db.get(SchoolClass, exam.class_id)
    section = await db.get(Section, exam.section_id)
    student = await db.get(User, student_id)
    scales = await _get_scales(db, tenant_id)

    # Get academic year from student record or active year
    ay = await _get_active_academic_year(db, tenant_id)
    roll_number = None
    ay_name = ay.name if ay else "N/A"
    if ay:
        sar = await _get_student_record(db, student_id, ay.id)
        if sar:
            roll_number = sar.roll_number

    # Get scheduled subjects
    sched_result = await db.execute(
        select(ExamSchedule).where(ExamSchedule.exam_id == exam_id).order_by(ExamSchedule.exam_date)
    )
    schedules = sched_result.scalars().all()

    subjects: List[ReportCardSubject] = []
    total_max = Decimal("0")
    total_obtained = Decimal("0")
    has_any_marks = False

    for sched in schedules:
        subj = await db.get(SchoolSubject, sched.subject_id)
        subj_name = subj.name if subj else str(sched.subject_id)

        mark_result = await db.execute(
            select(ExamMark).where(
                ExamMark.exam_id == exam_id,
                ExamMark.student_id == student_id,
                ExamMark.subject_id == sched.subject_id,
            )
        )
        mark = mark_result.scalar_one_or_none()

        if mark:
            has_any_marks = True
            pct = None if mark.is_absent else _calc_percentage(mark.marks_obtained, mark.max_marks)
            total_max += mark.max_marks
            if mark.marks_obtained is not None and not mark.is_absent:
                total_obtained += mark.marks_obtained
            subjects.append(ReportCardSubject(
                subject_id=sched.subject_id,
                subject_name=subj_name,
                marks_obtained=mark.marks_obtained,
                max_marks=mark.max_marks,
                percentage=pct,
                grade_label=_apply_grade(pct, scales),
                is_absent=mark.is_absent,
            ))
        else:
            total_max += Decimal("100")
            subjects.append(ReportCardSubject(
                subject_id=sched.subject_id,
                subject_name=subj_name,
                marks_obtained=None,
                max_marks=Decimal("100"),
                percentage=None,
                grade_label=None,
                is_absent=False,
            ))

    overall_pct = None
    overall_grade = None
    if has_any_marks and total_max > 0:
        overall_pct = round(float(total_obtained) / float(total_max) * 100, 2)
        overall_grade = _apply_grade(overall_pct, scales)

    return ReportCard(
        student_id=student_id,
        student_name=student.full_name if student else str(student_id),
        roll_number=roll_number,
        class_name=school_class.name if school_class else "",
        section_name=section.name if section else "",
        academic_year_name=ay_name,
        exam_id=exam.id,
        exam_name=exam.name,
        exam_type=exam_type_obj.name if exam_type_obj else "",
        start_date=exam.start_date,
        end_date=exam.end_date,
        subjects=subjects,
        total_marks_obtained=total_obtained if has_any_marks else None,
        total_max_marks=total_max,
        overall_percentage=overall_pct,
        overall_grade=overall_grade,
    )


async def get_class_report(
    db: AsyncSession,
    tenant_id: UUID,
    exam_id: UUID,
    current_user: CurrentUser,
) -> ExamMarksResponse:
    if current_user.role == "STUDENT":
        raise ServiceError("Students cannot access class-wide reports", status.HTTP_403_FORBIDDEN)
    return await get_exam_marks(db, tenant_id, exam_id, current_user)


# ─── Student exam list ────────────────────────────────────────────────────────

async def get_student_exam_list(
    db: AsyncSession,
    tenant_id: UUID,
    student_id: UUID,
    current_user: CurrentUser,
) -> List[ExamGradeSummary]:
    _assert_student_self_access(current_user, student_id)

    ay = await _get_active_academic_year(db, tenant_id)
    if not ay:
        return []

    sar = await _get_student_record(db, student_id, ay.id)
    if not sar:
        return []

    # Teacher: only for their class/section
    if current_user.role == "TEACHER":
        has_access = await _teacher_has_class_access(db, current_user.id, ay.id, sar.class_id, sar.section_id)
        if not has_access:
            raise ServiceError("Teacher not assigned to this student's class/section", status.HTTP_403_FORBIDDEN)

    exam_result = await db.execute(
        select(Exam).where(
            Exam.tenant_id == tenant_id,
            Exam.class_id == sar.class_id,
            Exam.section_id == sar.section_id,
        ).order_by(Exam.start_date.desc())
    )
    exams = exam_result.scalars().all()

    scales = await _get_scales(db, tenant_id)
    summaries = []
    for exam in exams:
        school_class = await db.get(SchoolClass, exam.class_id)
        section = await db.get(Section, exam.section_id)
        exam_type_obj = await db.get(ExamType, exam.exam_type_id)

        # Check if any marks exist for this student in this exam
        marks_result = await db.execute(
            select(ExamMark).where(
                ExamMark.exam_id == exam.id,
                ExamMark.student_id == student_id,
            ).limit(1)
        )
        marks_entered = marks_result.scalar_one_or_none() is not None

        overall_pct = None
        overall_grade = None
        if marks_entered:
            rc = await _build_report_card(db, tenant_id, student_id, exam.id)
            overall_pct = rc.overall_percentage
            overall_grade = rc.overall_grade

        summaries.append(ExamGradeSummary(
            exam_id=exam.id,
            exam_name=exam.name,
            exam_type=exam_type_obj.name if exam_type_obj else "",
            start_date=exam.start_date,
            end_date=exam.end_date,
            status=exam.status,
            class_name=school_class.name if school_class else "",
            section_name=section.name if section else "",
            overall_percentage=overall_pct,
            overall_grade=overall_grade,
            marks_entered=marks_entered,
        ))

    return summaries


# ─── Parent-facing helpers (called from parent portal) ────────────────────────

async def get_parent_student_exam_list(
    db: AsyncSession,
    tenant_id: UUID,
    student_id: UUID,
) -> List[ExamGradeSummary]:
    ay = await _get_active_academic_year(db, tenant_id)
    if not ay:
        return []
    sar = await _get_student_record(db, student_id, ay.id)
    if not sar:
        return []

    exam_result = await db.execute(
        select(Exam).where(
            Exam.tenant_id == tenant_id,
            Exam.class_id == sar.class_id,
            Exam.section_id == sar.section_id,
        ).order_by(Exam.start_date.desc())
    )
    exams = exam_result.scalars().all()
    scales = await _get_scales(db, tenant_id)
    summaries = []
    for exam in exams:
        school_class = await db.get(SchoolClass, exam.class_id)
        section = await db.get(Section, exam.section_id)
        exam_type_obj = await db.get(ExamType, exam.exam_type_id)
        marks_result = await db.execute(
            select(ExamMark).where(
                ExamMark.exam_id == exam.id,
                ExamMark.student_id == student_id,
            ).limit(1)
        )
        marks_entered = marks_result.scalar_one_or_none() is not None
        overall_pct = None
        overall_grade = None
        if marks_entered:
            rc = await _build_report_card(db, tenant_id, student_id, exam.id)
            overall_pct = rc.overall_percentage
            overall_grade = rc.overall_grade
        summaries.append(ExamGradeSummary(
            exam_id=exam.id,
            exam_name=exam.name,
            exam_type=exam_type_obj.name if exam_type_obj else "",
            start_date=exam.start_date,
            end_date=exam.end_date,
            status=exam.status,
            class_name=school_class.name if school_class else "",
            section_name=section.name if section else "",
            overall_percentage=overall_pct,
            overall_grade=overall_grade,
            marks_entered=marks_entered,
        ))
    return summaries


async def get_parent_student_report_card(
    db: AsyncSession,
    tenant_id: UUID,
    student_id: UUID,
    exam_id: UUID,
) -> ReportCard:
    return await _build_report_card(db, tenant_id, student_id, exam_id)
