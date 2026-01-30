from fastapi import status


class ServiceError(Exception):
    """Base exception for service layer errors."""

    def __init__(self, message: str, status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
