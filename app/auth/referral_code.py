"""
Teacher referral code generation.
Unique per tenant; only teachers get a code. Format: first 3 of first name + last 2 of year + 2 random alphanumeric.
"""

import secrets
import string
from datetime import datetime


def generate_teacher_referral_code(name: str) -> str:
    """
    Generate a unique-style referral code from teacher's name.

    Rules:
    - First 3 letters of first name (uppercase); pad with 'X' if shorter.
    - Last 2 digits of current year.
    - 2 random uppercase alphanumeric (A-Z, 0-9).

    Examples:
        Ramesh Kumar -> RAM26A7
        Suresh Rao   -> SUR26Q9
        Jo Lee       -> JOL26K2

    Production-safe: uses secrets for random part.
    """
    if not name or not str(name).strip():
        first_part = "XXX"
    else:
        first_name = str(name).strip().split()[0]
        first_part = (first_name[:3].upper() + "XXX")[:3]

    year_suffix = str(datetime.now().year)[-2:]
    alphabet = string.ascii_uppercase + string.digits
    random_part = "".join(secrets.choice(alphabet) for _ in range(2))

    return first_part + year_suffix + random_part
