from enum import Enum


class OrganizationType(str, Enum):
    SCHOOL = "School"
    COLLEGE = "College"
    SOFTWARE_COMPANY = "Software Company"
    SALES_ORGANIZATION = "Sales Organization"
    HOSPITAL = "Hospital"
    SHOPPING_MALL = "Shopping Mall"
    OTHER = "Other"


class FeeComponentCategory(str, Enum):
    ACADEMIC = "ACADEMIC"
    TRANSPORT = "TRANSPORT"
    HOSTEL = "HOSTEL"
    OTHER = "OTHER"


class StudentFeeSourceType(str, Enum):
    TEMPLATE = "TEMPLATE"
    CUSTOM = "CUSTOM"


class StudentFeeStatus(str, Enum):
    unpaid = "unpaid"
    partial = "partial"
    paid = "paid"

