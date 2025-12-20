"""GitHub repository provider using PyGithub."""

import os
import re
import sys

from github import Github, Auth

from ..parser import find_entity
from .base import CommitInfo, FunctionSnapshot, Provider


def parse_github_url(url: str) -> tuple[str, str, str | None, str | None]:
    """
    Parse a GitHub URL to extract owner, repo, branch, and file path.

    Supports formats:
    - https://github.com/owner/repo
    - https://github.com/owner/repo/tree/branch
    - https://github.com/owner/repo/blob/branch/path/to/file.rs
    - github.com/owner/repo

    Returns: (owner, repo, branch or None, file_path or None)
    """
    # Remove protocol if present
    url = re.sub(r"^https?://", "", url)

    # Remove github.com prefix
    url = re.sub(r"^github\.com/", "", url)

    parts = url.split("/")
    if len(parts) < 2:
        raise ValueError(f"Invalid GitHub URL: {url}")

    owner = parts[0]
    repo = parts[1]

    # Check for branch and file path in /tree/branch or /blob/branch/path format
    branch = None
    file_path = None
    if len(parts) >= 4 and parts[2] in ("tree", "blob"):
        branch = parts[3]
        # Everything after branch is the file path
        if len(parts) > 4:
            file_path = "/".join(parts[4:])

    return owner, repo, branch, file_path


class GitHubProvider(Provider):
    """Provider for GitHub repositories via API."""

    def __init__(self, github_url: str, token: str | None = None):
        """
        Initialize GitHub provider.

        Args:
            github_url: GitHub file URL (e.g., https://github.com/owner/repo/blob/main/path/to/file.rs)
            token: GitHub personal access token (or use GITHUB_TOKEN env var)
        """
        self.owner, self.repo_name, self.branch, self.file_path = parse_github_url(
            github_url
        )

        # Get token from parameter or environment
        token = token or os.environ.get("GITHUB_TOKEN")
        if token:
            auth = Auth.Token(token)
            self.github = Github(auth=auth)
        else:
            # Unauthenticated (lower rate limits)
            self.github = Github()

        self.repo = self.github.get_repo(f"{self.owner}/{self.repo_name}")
        self.default_branch = self.branch or self.repo.default_branch

    def get_file_content(self, file_path: str, ref: str = "HEAD") -> str | None:
        """Get file content at a specific ref."""
        if ref == "HEAD":
            ref = self.default_branch
        try:
            content = self.repo.get_contents(file_path, ref=ref)
            if isinstance(content, list):
                return None  # It's a directory
            return content.decoded_content.decode("utf-8")
        except Exception:
            return None

    def _get_file_commits(self, file_path: str) -> list[CommitInfo]:
        """Get all commits that touched a specific file."""
        commits = []
        try:
            for commit in self.repo.get_commits(path=file_path):
                commits.append(
                    CommitInfo(
                        hash=commit.sha,
                        short_hash=commit.sha[:7],
                        author_name=commit.commit.author.name or "Unknown",
                        author_email=commit.commit.author.email or "",
                        timestamp=commit.commit.author.date,
                        message=commit.commit.message,
                        subject=commit.commit.message.split("\n")[0].strip(),
                    )
                )
        except Exception:
            print("Warning: Failed to fetch some commits from GitHub", file=sys.stderr)
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
            current_source = self.get_file_content(file_path)
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
