"""Base provider interface for git sources."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class CommitInfo:
    """Information about a commit."""

    hash: str
    short_hash: str
    author_name: str
    author_email: str
    timestamp: datetime
    message: str
    subject: str  # First line of message


@dataclass
class FunctionSnapshot:
    """A snapshot of a function/entity at a specific commit."""

    commit: CommitInfo
    source: str  # The entity source code at this commit
    start_line: int
    end_line: int
    change_type: str  # 'created', 'modified', 'deleted'


class Provider(ABC):
    """Abstract base class for git providers."""

    @abstractmethod
    def get_function_evolution(
        self,
        file_path: str,
        func_name: str,
        language: str,
        entity_type: str = "function",
    ) -> tuple[str, list[FunctionSnapshot]]:
        """
        Get the entity source at each commit that touched it.

        Args:
            file_path: Path to the source file
            func_name: Name of the entity to track
            language: Programming language
            entity_type: Type of entity ("function", "class", "struct", "enum", "impl", "auto")

        Returns:
            Tuple of (detected_entity_type, snapshots) where snapshots are in
            chronological order (oldest first).
        """
        pass

    @abstractmethod
    def get_file_content(self, file_path: str, ref: str = "HEAD") -> str | None:
        """Get file content at a specific ref (commit/branch)."""
        pass
