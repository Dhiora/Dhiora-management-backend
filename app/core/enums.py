from enum import Enum


class OrganizationType(str, Enum):
    SCHOOL = "School"
    COLLEGE = "College"
    SOFTWARE_COMPANY = "Software Company"
    SALES_ORGANIZATION = "Sales Organization"
    HOSPITAL = "Hospital"
    SHOPPING_MALL = "Shopping Mall"
    OTHER = "Other"

