"""Core analysis logic for function history tracking."""

from dataclasses import dataclass

from .git_ops import (
    CommitInfo,
    DiffHunk,
    get_diff_hunks,
    get_file_at_commit,
    get_file_commits,
    get_repo,
)
from .parser import FunctionInfo, detect_language, find_function


@dataclass
class FunctionChange:
    """A single change to a function."""

    commit: CommitInfo
    function_info: FunctionInfo | None  # None if function was deleted
    change_type: str  # 'modified', 'created', 'deleted'


@dataclass
class FunctionHistory:
    """Complete history of a function."""

    function_name: str
    file_path: str
    repo_path: str
    language: str | None
    changes: list[FunctionChange]
    first_appeared: CommitInfo | None
    last_modified: CommitInfo | None
    total_changes: int
    current_info: FunctionInfo | None  # Current state, None if deleted


def analyze_function_history(
    repo_path: str, file_path: str, func_name: str
) -> FunctionHistory:
    """
    Analyze the git history of a specific function.

    Args:
        repo_path: Path to the git repository
        file_path: Path to the source file (relative to repo root)
        func_name: Name of the function to track

    Returns:
        FunctionHistory with all changes to the function
    """
    repo = get_repo(repo_path)

    # Detect language from file extension
    language = detect_language(file_path)
    if not language:
        raise ValueError(f"Could not detect language for file: {file_path}")

    # Get current state of the function
    current_source = get_file_at_commit(repo, "HEAD", file_path)
    current_info = None
    if current_source:
        current_info = find_function(current_source, func_name, language)

    # Get all commits that touched this file
    commits = get_file_commits(repo, file_path)

    if not commits:
        return FunctionHistory(
            function_name=func_name,
            file_path=file_path,
            repo_path=repo_path,
            language=language,
            changes=[],
            first_appeared=None,
            last_modified=None,
            total_changes=0,
            current_info=current_info,
        )

    # Analyze each commit to see if it affected the function
    changes: list[FunctionChange] = []
    prev_func_info: FunctionInfo | None = None

    # Process commits from oldest to newest for accurate tracking
    for commit in reversed(commits):
        # Get file at this commit
        source = get_file_at_commit(repo, commit.hash, file_path)
        if source is None:
            # File was deleted in this commit
            if prev_func_info is not None:
                changes.append(
                    FunctionChange(
                        commit=commit,
                        function_info=None,
                        change_type="deleted",
                    )
                )
                prev_func_info = None
            continue

        # Find function in this version
        func_info = find_function(source, func_name, language)

        if func_info is None:
            # Function doesn't exist at this commit
            if prev_func_info is not None:
                # Function was deleted
                changes.append(
                    FunctionChange(
                        commit=commit,
                        function_info=None,
                        change_type="deleted",
                    )
                )
                prev_func_info = None
            continue

        if prev_func_info is None:
            # Function was created
            changes.append(
                FunctionChange(
                    commit=commit,
                    function_info=func_info,
                    change_type="created",
                )
            )
            prev_func_info = func_info
        else:
            # Function exists - check if this commit modified it
            diff_hunks = get_diff_hunks(repo, commit.hash, file_path)
            if _diff_touches_function(diff_hunks, func_info):
                changes.append(
                    FunctionChange(
                        commit=commit,
                        function_info=func_info,
                        change_type="modified",
                    )
                )
            prev_func_info = func_info

    # Reverse to get newest first
    changes.reverse()

    return FunctionHistory(
        function_name=func_name,
        file_path=file_path,
        repo_path=repo_path,
        language=language,
        changes=changes,
        first_appeared=changes[-1].commit if changes else None,
        last_modified=changes[0].commit if changes else None,
        total_changes=len(changes),
        current_info=current_info,
    )


def _diff_touches_function(hunks: list[DiffHunk], func_info: FunctionInfo) -> bool:
    """Check if any diff hunk overlaps with the function's line range."""
    for hunk in hunks:
        # Check if hunk overlaps with function
        # Hunk affects lines from new_start to new_start + new_count
        hunk_start = hunk.new_start
        hunk_end = hunk.new_start + hunk.new_count

        func_start = func_info.start_line
        func_end = func_info.end_line

        if _ranges_overlap(hunk_start, hunk_end, func_start, func_end):
            return True

    return False


def _ranges_overlap(start1: int, end1: int, start2: int, end2: int) -> bool:
    """Check if two line ranges overlap."""
    return start1 <= end2 and start2 <= end1
