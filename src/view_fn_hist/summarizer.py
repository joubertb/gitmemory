"""LLM-based summarization of function evolution."""

import hashlib
import json
import os
from pathlib import Path

import litellm

# Suppress litellm's verbose output
litellm.suppress_debug_info = True

from .providers import FunctionSnapshot

DEFAULT_MODEL = "openrouter/google/gemini-flash-1.5"
CACHE_DIR = Path.home() / ".cache" / "view-fn-hist"


def _get_cache_key(
    entity_name: str,
    file_path: str,
    snapshots: list[FunctionSnapshot],
    entity_type: str = "function",
) -> str:
    """Generate a cache key based on entity identity and history."""
    # Include commit hashes to invalidate cache when history changes
    commit_hashes = "-".join(s.commit.short_hash for s in snapshots)
    key_str = f"{file_path}:{entity_type}:{entity_name}:{commit_hashes}"
    return hashlib.md5(key_str.encode()).hexdigest()


def _get_cached_summary(cache_key: str) -> str | None:
    """Try to get a cached summary."""
    cache_file = CACHE_DIR / f"{cache_key}.json"
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            return data.get("summary")
        except (json.JSONDecodeError, IOError):
            return None
    return None


def _save_cached_summary(cache_key: str, summary: str, model: str):
    """Save a summary to cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{cache_key}.json"
    try:
        cache_file.write_text(
            json.dumps(
                {
                    "summary": summary,
                    "model": model,
                }
            )
        )
    except IOError:
        pass  # Ignore cache write failures


def build_prompt(
    entity_name: str,
    file_path: str,
    snapshots: list[FunctionSnapshot],
    entity_type: str = "function",
) -> str:
    """Build the LLM prompt for debugging/display."""
    snapshot = snapshots[-1]
    commit = snapshot.commit

    # Single version - just describe what it does
    if len(snapshots) == 1:
        return f"""Describe the {entity_type} `{entity_name}` in `{file_path}`.

Commit that created it: {commit.message.strip()}

{entity_type.capitalize()} code:
```
{snapshot.source}
```

Write 1-2 sentences describing what this {entity_type} does and its purpose. Be concise and focus on the functionality."""

    # Multiple versions - describe evolution
    changes_description = []
    for i, snap in enumerate(snapshots):
        c = snap.commit
        date_str = c.timestamp.strftime("%Y-%m-%d")
        change_type = "CREATED" if i == 0 else "MODIFIED"
        full_message = c.message.strip()
        changes_description.append(
            f"[{date_str}] {change_type} ({c.short_hash}):\n{full_message}"
        )

    return f"""Analyze the evolution of the {entity_type} `{entity_name}` in `{file_path}`.

Here are the commits that modified this {entity_type}, from oldest to newest:

{chr(10).join(changes_description)}

Current {entity_type} code:
```
{snapshot.source}
```

Write a short paragraph explaining this {entity_type}. Start with one sentence describing what the {entity_type} does. Then describe how it evolved over time - what was added or changed and why. Write it as a natural narrative without referencing commit hashes or dates. Focus on the functional changes and their purpose."""


def is_cached(
    entity_name: str,
    file_path: str,
    snapshots: list[FunctionSnapshot],
    entity_type: str = "function",
) -> bool:
    """Check if a summary is cached."""
    if not snapshots:
        return True  # No LLM call needed for empty snapshots
    cache_key = _get_cache_key(entity_name, file_path, snapshots, entity_type)
    return _get_cached_summary(cache_key) is not None


def generate_evolution_summary(
    entity_name: str,
    file_path: str,
    snapshots: list[FunctionSnapshot],
    model: str | None = None,
    debug: bool = False,
    entity_type: str = "function",
) -> str:
    """
    Generate a summary of how the entity has evolved over time.

    Uses an LLM to analyze the commit messages and code changes.
    Caches results to avoid repeated API calls.

    Model can be configured via VIEW_FN_HIST_MODEL env var.
    """
    # Get model from env var, parameter, or default
    model = model or os.environ.get("VIEW_FN_HIST_MODEL", DEFAULT_MODEL)

    if not snapshots:
        return "No history available."

    # Check cache first
    cache_key = _get_cache_key(entity_name, file_path, snapshots, entity_type)
    cached = _get_cached_summary(cache_key)
    if cached:
        if debug:
            print("(using cached summary)")
        return f"(cached) {cached}"

    # Build the prompt
    prompt = build_prompt(entity_name, file_path, snapshots, entity_type)

    try:
        response = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
        )
        summary = response.choices[0].message.content.strip()

        # Cache the result
        _save_cached_summary(cache_key, summary, model)

        return summary
    except Exception as e:
        # Print error to stderr for debugging, then skip summary
        import sys

        print(f"LLM Error: {e}", file=sys.stderr)
        return ""
