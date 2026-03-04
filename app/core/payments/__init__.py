"""Payment integrations (Razorpay, etc.)."""

from .razorpay_client import get_razorpay_client

__all__ = ["get_razorpay_client"]
