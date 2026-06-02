"""Error classes for pytronikon."""

from typing import Any


class ElektronikonError(Exception):
    """Base error class for all pytronikon exceptions."""

    def __init__(
        self,
        message: str,
        code: str = "ELEKTRONIKON_ERROR",
        context: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        """Initialize ElektronikonError.

        Args:
            message: The error message.
            code: A string code identifying the error type.
            context: A dictionary of contextual information.
            cause: The underlying exception that caused this error.
        """
        super().__init__(message)
        self.code = code
        self.context = context or {}
        self.cause = cause

    def to_dict(self) -> dict[str, Any]:
        """Convert the error to a dictionary suitable for JSON serialization."""
        result: dict[str, Any] = {
            "name": self.__class__.__name__,
            "code": self.code,
            "message": str(self),
            "context": self.context,
        }
        if self.cause:
            result["cause"] = {
                "name": self.cause.__class__.__name__,
                "message": str(self.cause),
            }
        else:
            result["cause"] = None
        return result


class InvalidSelectorError(ElektronikonError):
    """Raised when a selector is invalid or malformed."""

    def __init__(self, selector: Any, reason: str) -> None:
        """Initialize InvalidSelectorError."""
        message = f"Invalid selector {selector!r}: {reason}"
        super().__init__(
            message,
            code="INVALID_SELECTOR",
            context={"selector": selector, "reason": reason},
        )


class ElektronikonHttpError(ElektronikonError):
    """Raised when an HTTP request fails."""

    def __init__(
        self,
        message: str,
        context: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        """Initialize ElektronikonHttpError."""
        super().__init__(
            message,
            code="HTTP_ERROR",
            context=context or {},
            cause=cause,
        )


class ResponseAlignmentError(ElektronikonError):
    """Raised when a response cannot be parsed correctly."""

    def __init__(self, message: str, context: dict[str, Any] | None = None) -> None:
        """Initialize ResponseAlignmentError."""
        super().__init__(
            message,
            code="RESPONSE_ALIGNMENT_ERROR",
            context=context or {},
        )


class UsageError(ElektronikonError):
    """Raised when the API is used incorrectly."""

    def __init__(self, message: str, context: dict[str, Any] | None = None) -> None:
        """Initialize UsageError."""
        super().__init__(
            message,
            code="USAGE_ERROR",
            context=context or {},
        )


class UnknownPointError(ElektronikonError):
    """Raised when a point ID is not found in the catalog."""

    def __init__(self, point_id: str) -> None:
        """Initialize UnknownPointError."""
        message = f"Unknown discovered point: {point_id}"
        super().__init__(
            message,
            code="UNKNOWN_POINT",
            context={"point_id": point_id},
        )


class UnknownFamilyError(ElektronikonError):
    """Raised when a family name is not found in the catalog."""

    def __init__(self, family: str) -> None:
        """Initialize UnknownFamilyError."""
        message = f"Unknown family: {family}"
        super().__init__(
            message,
            code="UNKNOWN_FAMILY",
            context={"family": family},
        )
