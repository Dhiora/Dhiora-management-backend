"""Razorpay client helper."""

import razorpay
from fastapi import status

from app.core.config import settings
from app.core.exceptions import ServiceError


def get_razorpay_client() -> razorpay.Client:
    """Return configured Razorpay client. Raises ServiceError if keys not set."""
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise ServiceError("Razorpay keys not configured", status.HTTP_500_INTERNAL_SERVER_ERROR)
    return razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
