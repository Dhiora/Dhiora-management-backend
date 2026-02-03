"""Unit tests for teacher referral code generation."""

import re
from datetime import datetime

import pytest

from app.auth.referral_code import generate_teacher_referral_code


def test_referral_code_format() -> None:
    """Code must be 3 uppercase letters + 2 digit year + 2 alphanumeric."""
    code = generate_teacher_referral_code("Ramesh Kumar")
    assert len(code) == 7
    assert code[:3].isalpha() and code[:3].isupper()
    assert code[3:5].isdigit()
    year_suffix = str(datetime.now().year)[-2:]
    assert code[3:5] == year_suffix
    assert re.match(r"^[A-Z0-9]{2}$", code[5:7])


def test_first_name_three_letters() -> None:
    """First 3 letters of first name (uppercase)."""
    code = generate_teacher_referral_code("Ramesh Kumar")
    assert code.startswith("RAM")
    code2 = generate_teacher_referral_code("Suresh Rao")
    assert code2.startswith("SUR")


def test_short_first_name_padded() -> None:
    """Short first name is padded with X to get 3 chars."""
    code = generate_teacher_referral_code("Jo Lee")
    assert code[:3] == "JOX"  # "Jo" -> ("JO" + "XXX")[:3] = "JOX"


def test_empty_name_uses_xxx() -> None:
    """Empty or whitespace name yields XXX prefix."""
    code = generate_teacher_referral_code("")
    assert code.startswith("XXX")
    code2 = generate_teacher_referral_code("   ")
    assert code2.startswith("XXX")


def test_referral_code_uniqueness_random_part() -> None:
    """Multiple calls produce different codes (random suffix)."""
    codes = {generate_teacher_referral_code("Ramesh Kumar") for _ in range(10)}
    # With 36^2 = 1296 possibilities, 10 calls should almost always have at least 2 distinct
    assert len(codes) >= 2
