import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.v1.parent_portal import auth_router, service
from app.core.exceptions import ServiceError


class _FakeResult:
    def __init__(self, scalar=None, all_rows=None):
        self._scalar = scalar
        self._all_rows = all_rows or []

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return self

    def all(self):
        return self._all_rows

    def first(self):
        return self._scalar


class _FakeDB:
    def __init__(self, results):
        self._results = list(results)

    async def execute(self, _stmt):
        if not self._results:
            return _FakeResult(None)
        return self._results.pop(0)

    async def get(self, *_args, **_kwargs):
        return None

    def add(self, _obj):
        return None

    async def commit(self):
        return None

    async def refresh(self, _obj):
        return None

    async def flush(self):
        return None

    async def delete(self, _obj):
        return None


def test_child_access_forbidden_when_unlinked():
    db = _FakeDB([_FakeResult(None)])
    with pytest.raises(ServiceError) as exc:
        asyncio.run(service.assert_child_access(db, uuid4(), uuid4()))
    assert exc.value.status_code == 403
    assert "not linked" in exc.value.message.lower()


def test_child_access_allowed_when_linked():
    db = _FakeDB([_FakeResult(SimpleNamespace(id=uuid4()))])
    asyncio.run(service.assert_child_access(db, uuid4(), uuid4()))


def test_invalid_signature_verify_returns_400():
    db = _FakeDB([])
    with pytest.raises(ServiceError) as exc:
        asyncio.run(
            service.verify_razorpay_payment(
                db=db,
                tenant_id=uuid4(),
                student_id=uuid4(),
                fee_assignment_id=uuid4(),
                razorpay_order_id="order_1",
                razorpay_payment_id="pay_1",
                razorpay_signature="bad_sig",
            )
        )
    assert exc.value.status_code == 400
    assert "signature" in exc.value.message.lower()


def test_already_paid_fee_cannot_create_new_payment_order():
    paid_assignment = SimpleNamespace(
        id=uuid4(),
        tenant_id=uuid4(),
        student_id=uuid4(),
        is_active=True,
        status="paid",
        final_amount=100,
    )
    db = _FakeDB([_FakeResult(paid_assignment)])
    with pytest.raises(ServiceError) as exc:
        asyncio.run(
            service.create_razorpay_order(
                db=db,
                tenant_id=paid_assignment.tenant_id,
                student_id=paid_assignment.student_id,
                fee_assignment_id=paid_assignment.id,
            )
        )
    assert exc.value.status_code == 409
    assert "already been paid" in exc.value.message.lower()


def test_parent_login_rate_limit_blocks_after_ten_attempts():
    ip = "127.0.0.1"
    auth_router._LOGIN_ATTEMPTS[ip] = []
    for _ in range(10):
        auth_router._enforce_login_rate_limit(ip)
    with pytest.raises(Exception):
        auth_router._enforce_login_rate_limit(ip)


def test_parent_login_rate_limit_window_expires():
    ip = "127.0.0.2"
    old = datetime.now(timezone.utc) - timedelta(minutes=16)
    auth_router._LOGIN_ATTEMPTS[ip] = [old] * 10
    # Should not raise because attempts are outside 15-minute window
    auth_router._enforce_login_rate_limit(ip)
