"""Annotator module for creating annotated function views with full line history."""

from dataclasses import dataclass

from .git_ops import (
    CommitInfo,
    LineChange,
    get_blame_for_range,
    get_line_history_from_commits,
    get_repo,
)
from .parser import detect_language, find_function
from .analyzer import analyze_function_history


@dataclass
class AnnotatedLine:
    """A line with its full history of changes."""

    line_number: int
    content: str
    history: list[LineChange]  # All changes to this line, oldest first (chronological)
    blame_commit: CommitInfo  # The commit that last touched this line (from git blame)


@dataclass
class AnnotatedFunction:
    """A function with per-line history annotations."""

    function_name: str
    file_path: str
    repo_path: str
    language: str | None
    start_line: int
    end_line: int
    lines: list[AnnotatedLine]
    total_commits: int  # Total unique commits that touched this function
    created_at: CommitInfo | None  # First commit that introduced the function


def annotate_function(
    repo_path: str, file_path: str, func_name: str
) -> AnnotatedFunction:
    """
    Create an annotated view of a function with full per-line history.

    Args:
        repo_path: Path to the git repository
        file_path: Path to the source file (relative to repo root)
        func_name: Name of the function to annotate

    Returns:
        AnnotatedFunction with per-line history
    """
    repo = get_repo(repo_path)

    # Detect language
    language = detect_language(file_path)
    if not language:
        raise ValueError(f"Could not detect language for file: {file_path}")

    # Get current function info
    from .git_ops import get_file_at_commit

    current_source = get_file_at_commit(repo, "HEAD", file_path)
    if not current_source:
        raise ValueError(f"File not found: {file_path}")

    func_info = find_function(current_source, func_name, language)
    if not func_info:
        raise ValueError(f"Function not found: {func_name}")

    # Get function history to find all commits that touched it
    history = analyze_function_history(repo_path, file_path, func_name)

    # Get blame info for the function's line range
    blame_lines = get_blame_for_range(
        repo, file_path, func_info.start_line, func_info.end_line
    )

    # Get commits that touched this function
    func_commits = [change.commit for change in history.changes]

    # Get per-line history from diff analysis
    line_history = get_line_history_from_commits(
        repo, file_path, func_commits, func_info.start_line, func_info.end_line
    )

    # Build annotated lines
    annotated_lines = []
    source_lines = current_source.split("\n")

    for blame_line in blame_lines:
        ln = blame_line.line_number
        content = source_lines[ln - 1] if ln <= len(source_lines) else ""

        # Get the full history for this line (already in chronological order)
        changes_for_line = line_history.get(ln, [])

        # If no changes found from diff analysis, use blame commit
        if not changes_for_line:
            changes_for_line = [LineChange(commit=blame_line.commit, content=content)]

        annotated_lines.append(
            AnnotatedLine(
                line_number=ln,
                content=content,
                history=changes_for_line,
                blame_commit=blame_line.commit,
            )
        )

    # Collect unique commits
    all_commits = set()
    for line in annotated_lines:
        for change in line.history:
            all_commits.add(change.commit.hash)

    return AnnotatedFunction(
        function_name=func_name,
        file_path=file_path,
        repo_path=repo_path,
        language=language,
        start_line=func_info.start_line,
        end_line=func_info.end_line,
        lines=annotated_lines,
        total_commits=len(all_commits),
        created_at=history.first_appeared,
    )
