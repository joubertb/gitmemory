"""Git operations for extracting file and commit history."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from git import Repo


@dataclass
class DiffHunk:
    """Represents a single hunk in a diff."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int
    content: str


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


def get_repo(repo_path: str) -> Repo:
    """Open a git repository."""
    path = Path(repo_path).resolve()
    if not path.exists():
        raise ValueError(f"Repository path does not exist: {path}")
    return Repo(path)


def get_file_commits(repo: Repo, file_path: str) -> list[CommitInfo]:
    """
    Get all commits that touched a specific file.

    Returns commits in reverse chronological order (newest first).
    Note: Does not track renames in this version.
    """
    commits = []

    # Use GitPython's iter_commits with paths filter
    for commit in repo.iter_commits(paths=file_path):
        commits.append(
            CommitInfo(
                hash=commit.hexsha,
                short_hash=commit.hexsha[:7],
                author_name=commit.author.name or "Unknown",
                author_email=commit.author.email or "",
                timestamp=datetime.fromtimestamp(commit.committed_date),
                message=commit.message,
                subject=commit.message.split("\n")[0].strip(),
            )
        )

    return commits


def get_file_at_commit(repo: Repo, commit_hash: str, file_path: str) -> str | None:
    """
    Get file contents at a specific commit.

    Returns None if the file doesn't exist at that commit.
    """
    try:
        commit = repo.commit(commit_hash)
        blob = commit.tree / file_path
        return blob.data_stream.read().decode("utf-8")
    except KeyError:
        # File doesn't exist at this commit
        return None
    except UnicodeDecodeError:
        # Binary file
        return None


def get_diff_hunks(repo: Repo, commit_hash: str, file_path: str) -> list[DiffHunk]:
    """
    Get diff hunks for a file in a specific commit.

    Returns the hunks showing what changed in this commit for this file.
    """
    commit = repo.commit(commit_hash)

    # Get parent commit (for initial commit, diff against empty tree)
    if commit.parents:
        parent = commit.parents[0]
        diffs = parent.diff(commit, paths=file_path, create_patch=True)
    else:
        # Initial commit - diff against empty tree
        diffs = commit.diff(None, paths=file_path, create_patch=True, R=True)

    hunks = []
    for diff in diffs:
        if diff.diff:
            hunks.extend(_parse_diff_hunks(diff.diff.decode("utf-8")))

    return hunks


def _parse_diff_hunks(diff_text: str) -> list[DiffHunk]:
    """Parse unified diff text into DiffHunk objects."""
    hunks = []
    current_hunk = None
    hunk_lines = []

    for line in diff_text.split("\n"):
        if line.startswith("@@"):
            # Save previous hunk
            if current_hunk is not None:
                current_hunk.content = "\n".join(hunk_lines)
                hunks.append(current_hunk)
                hunk_lines = []

            # Parse hunk header: @@ -old_start,old_count +new_start,new_count @@
            try:
                parts = line.split("@@")[1].strip()
                old_part, new_part = parts.split(" ")

                old_start, old_count = _parse_hunk_range(old_part[1:])  # Remove -
                new_start, new_count = _parse_hunk_range(new_part[1:])  # Remove +

                current_hunk = DiffHunk(
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                    content="",
                )
            except (ValueError, IndexError):
                continue
        elif current_hunk is not None:
            hunk_lines.append(line)

    # Save last hunk
    if current_hunk is not None:
        current_hunk.content = "\n".join(hunk_lines)
        hunks.append(current_hunk)

    return hunks


def _parse_hunk_range(range_str: str) -> tuple[int, int]:
    """Parse a hunk range like '10,5' or '10' into (start, count)."""
    if "," in range_str:
        start, count = range_str.split(",")
        return int(start), int(count)
    else:
        return int(range_str), 1


@dataclass
class LineChange:
    """A single change to a line, with content."""

    commit: CommitInfo
    content: str  # The line content after this commit


@dataclass
class BlameLine:
    """Blame information for a single line."""

    line_number: int  # 1-indexed
    content: str
    commit: CommitInfo


def get_blame_for_range(
    repo: Repo, file_path: str, start_line: int, end_line: int
) -> list[BlameLine]:
    """
    Get blame information for a range of lines.

    Returns list of BlameLine with commit info for each line.
    """
    blame_lines = []

    # GitPython's blame returns [(commit, [lines]), ...]
    try:
        blame_data = repo.blame("HEAD", file_path)
    except Exception:
        return blame_lines

    current_line = 1
    for commit, lines in blame_data:
        for line_content in lines:
            if start_line <= current_line <= end_line:
                blame_lines.append(
                    BlameLine(
                        line_number=current_line,
                        content=line_content,
                        commit=CommitInfo(
                            hash=commit.hexsha,
                            short_hash=commit.hexsha[:7],
                            author_name=commit.author.name or "Unknown",
                            author_email=commit.author.email or "",
                            timestamp=datetime.fromtimestamp(commit.committed_date),
                            message=commit.message,
                            subject=commit.message.split("\n")[0].strip(),
                        ),
                    )
                )
            current_line += 1
            if current_line > end_line:
                break
        if current_line > end_line:
            break

    return blame_lines


def get_line_history_from_commits(
    repo: Repo,
    file_path: str,
    func_commits: list[CommitInfo],
    start_line: int,
    end_line: int,
) -> dict[int, list[LineChange]]:
    """
    Get the history of changes for each line in a range, with content.

    For each line, returns the list of changes (oldest first / chronological).
    Each change includes the commit and the line content at that point.
    """
    # Map: line_number -> list of changes
    line_history: dict[int, list[LineChange]] = {
        ln: [] for ln in range(start_line, end_line + 1)
    }

    # Process commits from oldest to newest (chronological order)
    for commit_info in reversed(func_commits):
        hunks = get_diff_hunks(repo, commit_info.hash, file_path)

        for hunk in hunks:
            # Extract the new lines from this hunk (lines that were added/modified)
            new_lines = _extract_new_lines_from_hunk(hunk)

            # Map hunk positions to actual line numbers
            for offset, line_content in enumerate(new_lines):
                line_num = hunk.new_start + offset
                if start_line <= line_num <= end_line:
                    # Record this change with its content
                    line_history[line_num].append(
                        LineChange(commit=commit_info, content=line_content)
                    )

    return line_history


def _extract_new_lines_from_hunk(hunk: DiffHunk) -> list[str]:
    """
    Extract the new/added lines from a diff hunk.

    Returns lines in order, representing the new state after the commit.
    Context lines (no prefix or space prefix) and added lines (+) are included.
    Removed lines (-) are excluded.
    """
    new_lines = []
    for line in hunk.content.split("\n"):
        if line.startswith("-"):
            # Removed line - skip it
            continue
        elif line.startswith("+"):
            # Added line - include without the + prefix
            new_lines.append(line[1:])
        elif line.startswith(" ") or line == "":
            # Context line - include without the space prefix
            if line.startswith(" "):
                new_lines.append(line[1:])
            # Empty lines at end of hunk are ignored
    return new_lines


@dataclass
class FunctionSnapshot:
    """A snapshot of a function at a specific commit."""

    commit: CommitInfo
    source: str  # The function source code at this commit
    start_line: int
    end_line: int
    change_type: str  # 'created', 'modified', 'deleted'


def get_function_evolution(
    repo: Repo,
    file_path: str,
    func_name: str,
    language: str,
) -> list[FunctionSnapshot]:
    """
    Get the function source at each commit that touched it.

    Returns snapshots in chronological order (oldest first).
    """
    from .parser import find_function

    snapshots: list[FunctionSnapshot] = []
    commits = get_file_commits(repo, file_path)

    prev_source: str | None = None

    # Process from oldest to newest
    for commit_info in reversed(commits):
        source = get_file_at_commit(repo, commit_info.hash, file_path)
        if source is None:
            continue

        func_info = find_function(source, func_name, language)
        if func_info is None:
            # Function doesn't exist at this commit
            if prev_source is not None:
                # Function was deleted
                snapshots.append(
                    FunctionSnapshot(
                        commit=commit_info,
                        source="(deleted)",
                        start_line=0,
                        end_line=0,
                        change_type="deleted",
                    )
                )
                prev_source = None
            continue

        # Extract function source
        lines = source.split("\n")
        func_source = "\n".join(lines[func_info.start_line - 1 : func_info.end_line])

        if prev_source is None:
            # Function was created
            snapshots.append(
                FunctionSnapshot(
                    commit=commit_info,
                    source=func_source,
                    start_line=func_info.start_line,
                    end_line=func_info.end_line,
                    change_type="created",
                )
            )
            prev_source = func_source
        elif func_source != prev_source:
            # Function was modified
            snapshots.append(
                FunctionSnapshot(
                    commit=commit_info,
                    source=func_source,
                    start_line=func_info.start_line,
                    end_line=func_info.end_line,
                    change_type="modified",
                )
            )
            prev_source = func_source

    return snapshots
