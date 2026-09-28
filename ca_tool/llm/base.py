"""AI abstraction layer: the only interface business logic uses to talk to a model."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class LLM(ABC):
    name: str = "base"

    @abstractmethod
    def generate_json(self, prompt: str, schema: type[T], system: str = "") -> T:
        """Return an instance of `schema` produced by the model."""

    @abstractmethod
    def generate_text(self, prompt: str, system: str = "") -> str:
        ...
