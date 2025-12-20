"""Local git repository provider."""

from datetime import datetime
from pathlib import Path

from git import Repo

from ..parser import find_entity
from .base import CommitInfo, FunctionSnapshot, Provider


class GitProvider(Provider):
    """Provider for local git repositories."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        if not self.repo_path.exists():
            raise ValueError(f"Repository path does not exist: {self.repo_path}")
        self.repo = Repo(self.repo_path)

    def get_file_content(self, file_path: str, ref: str = "HEAD") -> str | None:
        """Get file content at a specific ref."""
        try:
            commit = self.repo.commit(ref)
            blob = commit.tree / file_path
            return blob.data_stream.read().decode("utf-8")
        except (KeyError, UnicodeDecodeError):
            return None

    def _get_file_commits(self, file_path: str) -> list[CommitInfo]:
        """Get all commits that touched a specific file."""
        commits = []
        for commit in self.repo.iter_commits(paths=file_path):
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

    def get_function_evolution(
        self,
        file_path: str,
        func_name: str,
        language: str,
        entity_type: str = "function",
    ) -> tuple[str, list[FunctionSnapshot]]:
        """Get the entity source at each commit that touched it."""
        snapshots: list[FunctionSnapshot] = []
        commits = self._get_file_commits(file_path)

        # If auto-detecting, find the entity type from the current file
        detected_type = entity_type
        if entity_type == "auto":
            current_source = self.get_file_content(file_path, "HEAD")
            if current_source:
                func_info = find_entity(current_source, func_name, "auto", language)
                if func_info:
                    detected_type = func_info.entity_type
                else:
                    # Try to find in the most recent commit that has the file
                    for commit_info in commits:
                        source = self.get_file_content(file_path, commit_info.hash)
                        if source:
                            func_info = find_entity(source, func_name, "auto", language)
                            if func_info:
                                detected_type = func_info.entity_type
                                break

            # Fallback to "function" if auto-detection didn't find the entity
            if detected_type == "auto":
                detected_type = "function"

        prev_source: str | None = None

        # Process from oldest to newest
        for commit_info in reversed(commits):
            source = self.get_file_content(file_path, commit_info.hash)
            if source is None:
                continue

            func_info = find_entity(source, func_name, detected_type, language)
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
            func_source = "\n".join(
                lines[func_info.start_line - 1 : func_info.end_line]
            )

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

        return (detected_type, snapshots)
