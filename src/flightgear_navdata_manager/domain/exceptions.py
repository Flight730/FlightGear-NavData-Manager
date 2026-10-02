"""Application-specific exceptions."""

from __future__ import annotations


class NavDataError(Exception):
    """Base class for all application-specific errors."""


class ValidationError(NavDataError):
    """Raised when user-supplied field values fail validation."""
