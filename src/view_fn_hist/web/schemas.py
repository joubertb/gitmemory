"""Pydantic schemas for the web API."""

from datetime import datetime
from pydantic import BaseModel


class AnalyzeRequest(BaseModel):
    """Request to analyze an entity's evolution."""

    github_url: str
    function_name: str  # Entity name (kept for backward compatibility)
    entity_type: str = "function"  # function, class, struct, enum, impl, interface


class CommitSchema(BaseModel):
    """Commit information."""

    hash: str
    short_hash: str
    date: datetime
    subject: str
    message: str
    author: str


class SnapshotSchema(BaseModel):
    """A snapshot of a function at a specific commit."""

    index: int
    commit: CommitSchema
    source: str
    start_line: int
    end_line: int
    change_type: str
    changed_lines: list[int]


class AnalyzeResponse(BaseModel):
    """Response containing function evolution data."""

    function_name: str
    file_path: str
    repo: str
    entity_type: str  # Detected entity type
    snapshots: list[SnapshotSchema]


class SummaryRequest(BaseModel):
    """Request to generate a summary."""

    github_url: str
    function_name: str  # Entity name (kept for backward compatibility)
    entity_type: str = "function"  # function, class, struct, enum, impl, interface


class SummaryResponse(BaseModel):
    """Response containing the LLM summary."""

    summary: str | None
    cached: bool


class ErrorResponse(BaseModel):
    """Error response."""

    error: str
    detail: str | None = None
