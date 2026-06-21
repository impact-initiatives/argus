from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum, auto
from typing import Any

from locales.il8n import _


class SeverityLevel(StrEnum):
    INFO = auto()
    WARNING = auto()
    ERROR = auto()
    ADMIN_ERROR = auto()
    PASSED = auto()
    ADMIN_INFO = auto()


@dataclass
class ValidationResult:
    rule: str
    message: str
    severity: SeverityLevel
    sheet_name: str | None = None
    column_name: str | None = None
    details: dict[str, Any] | None = None


class BaseValidator(ABC):
    """Abstract base class for all validators."""

    @abstractmethod
    def validate(self, data: Any) -> list[ValidationResult]:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    def _(self, key: str, **kwargs: str | int | float):
        return _(key, **kwargs)
