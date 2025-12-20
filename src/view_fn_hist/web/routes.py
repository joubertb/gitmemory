"""API routes for the web application."""

from fastapi import APIRouter, HTTPException

from ..parser import detect_language
from ..providers import GitHubProvider, FunctionSnapshot
from ..providers.github_provider import parse_github_url
from ..summarizer import generate_evolution_summary
from ..tui import compute_changed_lines
from .schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    CommitSchema,
    SnapshotSchema,
    SummaryRequest,
    SummaryResponse,
)

router = APIRouter(prefix="/api")

# Simple in-memory cache for snapshots (avoids re-fetching from GitHub for summary)
_snapshot_cache: dict[str, list[FunctionSnapshot]] = {}


def _cache_key(url: str, func: str, entity_type: str = "function") -> str:
    return f"{url}:{entity_type}:{func}"


def _get_cached_snapshots(
    url: str, func: str, entity_type: str = "function"
) -> list[FunctionSnapshot] | None:
    return _snapshot_cache.get(_cache_key(url, func, entity_type))


def _cache_snapshots(
    url: str,
    func: str,
    snapshots: list[FunctionSnapshot],
    entity_type: str = "function",
):
    # Keep cache small - only store last 20 queries
    if len(_snapshot_cache) > 20:
        # Remove oldest entry
        oldest_key = next(iter(_snapshot_cache))
        del _snapshot_cache[oldest_key]
    _snapshot_cache[_cache_key(url, func, entity_type)] = snapshots


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_function(request: AnalyzeRequest):
    """Analyze an entity's evolution from a GitHub URL."""
    # Parse the GitHub URL
    try:
        owner, repo_name, branch, file_path = parse_github_url(request.github_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not file_path:
        raise HTTPException(
            status_code=400,
            detail="GitHub URL must include file path (e.g., /blob/main/src/file.rs)",
        )

    # Detect language first
    language = detect_language(file_path)
    if not language:
        raise HTTPException(
            status_code=400, detail=f"Unsupported file type: {file_path}"
        )

    # Check cache first (only if not auto-detecting)
    entity_type = request.entity_type
    snapshots = None
    if entity_type != "auto":
        snapshots = _get_cached_snapshots(
            request.github_url, request.function_name, entity_type
        )

    if not snapshots:
        # Get entity evolution from GitHub
        try:
            provider = GitHubProvider(request.github_url)
            entity_type, snapshots = provider.get_function_evolution(
                file_path, request.function_name, language, request.entity_type
            )
        except Exception:
            raise HTTPException(
                status_code=500,
                detail="Failed to analyze repository. Check the URL and try again.",
            )

        if not snapshots:
            raise HTTPException(
                status_code=404,
                detail=f"'{request.function_name}' not found in {file_path}",
            )

        # Cache snapshots for future requests
        _cache_snapshots(
            request.github_url, request.function_name, snapshots, entity_type
        )

    # Build response with computed diffs
    response_snapshots = []
    for i, snapshot in enumerate(snapshots):
        # Compute changed lines
        prev_source = snapshots[i - 1].source if i > 0 else None
        changed_lines = list(compute_changed_lines(prev_source, snapshot.source))

        response_snapshots.append(
            SnapshotSchema(
                index=i,
                commit=CommitSchema(
                    hash=snapshot.commit.hash,
                    short_hash=snapshot.commit.short_hash,
                    date=snapshot.commit.timestamp,
                    subject=snapshot.commit.subject,
                    message=snapshot.commit.message,
                    author=snapshot.commit.author_name,
                ),
                source=snapshot.source,
                start_line=snapshot.start_line,
                end_line=snapshot.end_line,
                change_type=snapshot.change_type,
                changed_lines=changed_lines,
            )
        )

    return AnalyzeResponse(
        function_name=request.function_name,
        file_path=file_path,
        repo=f"{owner}/{repo_name}",
        entity_type=entity_type,
        snapshots=response_snapshots,
    )


@router.post("/summary", response_model=SummaryResponse)
async def get_summary(request: SummaryRequest):
    """Generate an LLM summary of the entity's evolution."""
    # Parse the GitHub URL
    try:
        owner, repo_name, branch, file_path = parse_github_url(request.github_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not file_path:
        raise HTTPException(status_code=400, detail="GitHub URL must include file path")

    # Detect language
    language = detect_language(file_path)
    if not language:
        raise HTTPException(
            status_code=400, detail=f"Unsupported file type: {file_path}"
        )

    # Try to get cached snapshots first (from recent /analyze call)
    entity_type = request.entity_type
    snapshots = None
    if entity_type != "auto":
        snapshots = _get_cached_snapshots(
            request.github_url, request.function_name, entity_type
        )

    if not snapshots:
        # Fetch from GitHub if not cached
        try:
            provider = GitHubProvider(request.github_url)
            entity_type, snapshots = provider.get_function_evolution(
                file_path, request.function_name, language, request.entity_type
            )
        except Exception:
            raise HTTPException(
                status_code=500,
                detail="Failed to analyze repository. Check the URL and try again.",
            )

    if not snapshots:
        raise HTTPException(
            status_code=404, detail=f"'{request.function_name}' not found"
        )

    # Generate summary
    try:
        summary = generate_evolution_summary(
            request.function_name, file_path, snapshots, entity_type=entity_type
        )
        # Check if it was cached (summary starts with "(cached)")
        cached = summary.startswith("(cached)")
        if cached:
            summary = summary[9:]  # Remove "(cached) " prefix
        return SummaryResponse(summary=summary, cached=cached)
    except Exception:
        # Return empty summary on LLM errors
        return SummaryResponse(summary=None, cached=False)
