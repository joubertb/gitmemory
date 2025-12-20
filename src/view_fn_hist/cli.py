"""CLI entry point for view-fn-hist."""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env file before other imports that may need env vars
load_dotenv()

from .parser import detect_language
from .providers import GitProvider, GitHubProvider
from .providers.github_provider import parse_github_url
from .summarizer import DEFAULT_MODEL, build_prompt, is_cached
from .tui import run_tui


def is_github_url(source: str) -> bool:
    """Check if the source is a GitHub URL."""
    return source.startswith("https://github.com") or source.startswith("github.com")


def print_llm_status():
    """Print LLM configuration status before TUI starts."""
    import litellm

    model = os.environ.get("VIEW_FN_HIST_MODEL", DEFAULT_MODEL)
    print(f"LLM Model: {model}")

    # Check for API key based on model prefix
    key_status = []
    warnings = []

    if model.startswith("openrouter/"):
        key = os.environ.get("OPENROUTER_API_KEY")
        if key:
            key_status.append("OPENROUTER_API_KEY: configured")
        else:
            warnings.append("OPENROUTER_API_KEY not set - summary will be skipped")
    elif model.startswith("gemini/"):
        key = os.environ.get("GEMINI_API_KEY")
        if key:
            key_status.append("GEMINI_API_KEY: configured")
        else:
            warnings.append("GEMINI_API_KEY not set - summary will be skipped")
    elif model.startswith("gpt-") or model.startswith("openai/"):
        key = os.environ.get("OPENAI_API_KEY")
        if key:
            key_status.append("OPENAI_API_KEY: configured")
        else:
            warnings.append("OPENAI_API_KEY not set - summary will be skipped")
    elif model.startswith("claude-") or model.startswith("anthropic/"):
        key = os.environ.get("ANTHROPIC_API_KEY")
        if key:
            key_status.append("ANTHROPIC_API_KEY: configured")
        else:
            warnings.append("ANTHROPIC_API_KEY not set - summary will be skipped")
    else:
        # Generic check - litellm might figure it out
        key_status.append("API key: unknown provider, litellm will attempt connection")

    for status in key_status:
        print(f"  {status}")

    for warning in warnings:
        print(f"  Warning: {warning}")

    # Test LLM connection
    if not warnings:
        print("  Testing LLM connection...", end=" ", flush=True)
        try:
            litellm.completion(
                model=model,
                messages=[{"role": "user", "content": "Say 'ok'"}],
                max_tokens=10,
            )
            print("OK")
        except Exception:
            print("FAILED")
            print(
                "  Warning: LLM connection test failed - summary may not be available"
            )

    print()


def main():
    """Main entry point for view-fn-hist CLI."""
    parser = argparse.ArgumentParser(
        description="View the git history of a specific function, class, struct, or other code entity.",
        usage="view-fn-hist [--web] [-t TYPE] <source> [file] <entity>\n\n"
        "  GitHub:    view-fn-hist <github-file-url> <entity>\n"
        "  Local git: view-fn-hist <repo> <file> <entity>\n"
        "  Web UI:    view-fn-hist --web\n\n"
        "  Entity type is auto-detected. Use -t to override.",
    )
    parser.add_argument(
        "args",
        nargs="*",
        help="GitHub: <url> <func> | Local: <repo> <file> <func>",
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Show debug info including LLM prompt",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Start the web server instead of TUI",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for web server (default: 8000)",
    )
    parser.add_argument(
        "-t",
        "--type",
        choices=["auto", "function", "class", "struct", "enum", "impl", "interface"],
        default="auto",
        help="Entity type to track (default: auto-detect)",
    )

    parsed = parser.parse_args()

    # Web server mode
    if parsed.web:
        from .web.app import run_server

        print(f"Starting web server on http://127.0.0.1:{parsed.port}")
        print("Open this URL in your browser to use the web interface.")
        print("Press Ctrl+C to stop the server.")
        run_server(port=parsed.port)
        return

    positional = parsed.args

    if not positional:
        parser.print_help()
        sys.exit(1)

    # Determine if source is GitHub URL or local path
    if is_github_url(positional[0]):
        # GitHub URL - expect: <url> <func>
        if len(positional) < 2:
            print(
                "Error: GitHub usage: view-fn-hist <github-url> <func>", file=sys.stderr
            )
            sys.exit(1)

        github_url = positional[0]
        func_name = positional[1]

        # Parse URL to extract file path
        try:
            owner, repo_name, branch, file_path = parse_github_url(github_url)
        except ValueError:
            print("Error: Invalid GitHub URL format", file=sys.stderr)
            print(
                "Expected: https://github.com/owner/repo/blob/branch/path/to/file",
                file=sys.stderr,
            )
            sys.exit(1)

        if not file_path:
            print("Error: GitHub URL must include file path", file=sys.stderr)
            print(
                "Example: https://github.com/owner/repo/blob/main/src/file.rs",
                file=sys.stderr,
            )
            sys.exit(1)

        print(f"Source: GitHub ({owner}/{repo_name})")
        print(f"File: {file_path}")

        try:
            provider = GitHubProvider(github_url)
        except Exception:
            print("Error: Failed to connect to GitHub repository", file=sys.stderr)
            print("Check that the repository exists and is accessible", file=sys.stderr)
            sys.exit(1)
    else:
        # Local git repository - expect: <repo> <file> <func>
        if len(positional) < 3:
            print(
                "Error: Local git usage: view-fn-hist <repo> <file> <func>",
                file=sys.stderr,
            )
            sys.exit(1)

        repo_path = Path(positional[0]).resolve()
        file_path = positional[1]
        func_name = positional[2]

        if not repo_path.exists():
            print(
                f"Error: Repository path does not exist: {repo_path}", file=sys.stderr
            )
            sys.exit(1)

        git_dir = repo_path / ".git"
        if not git_dir.exists():
            print(f"Error: Not a git repository: {repo_path}", file=sys.stderr)
            sys.exit(1)

        print(f"Source: Local git ({repo_path})")

        # Normalize file path to be relative to repo root
        file_path_input = Path(file_path)

        # If it's an absolute path or starts with .., resolve it
        if file_path_input.is_absolute() or file_path.startswith(".."):
            file_path_resolved = file_path_input.resolve()
            # Check if it's inside the repo and make it relative
            try:
                file_path = str(file_path_resolved.relative_to(repo_path))
            except ValueError:
                print(
                    f"Error: File {file_path_resolved} is not inside repository {repo_path}",
                    file=sys.stderr,
                )
                sys.exit(1)

        full_file_path = repo_path / file_path
        if not full_file_path.exists():
            print(f"Error: File does not exist: {full_file_path}", file=sys.stderr)
            sys.exit(1)

        provider = GitProvider(str(repo_path))

    # Check language support
    language = detect_language(file_path)
    if not language:
        print(f"Error: Unsupported file type: {file_path}", file=sys.stderr)
        print(
            "Supported extensions: .py, .js, .ts, .go, .rs, .java, .c, .cpp, .rb, etc.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Get entity evolution
    entity_type = parsed.type
    if entity_type == "auto":
        print(f"Searching for '{func_name}' in {file_path}...")
    else:
        print(f"Analyzing {entity_type} '{func_name}' in {file_path}...")
    try:
        entity_type, snapshots = provider.get_function_evolution(
            file_path, func_name, language, entity_type
        )
    except Exception:
        print("Error: Failed to analyze git history", file=sys.stderr)
        print("Check that the file exists and has git history", file=sys.stderr)
        sys.exit(1)

    if not snapshots:
        print(f"Error: No history found for '{func_name}'", file=sys.stderr)
        sys.exit(1)

    print(f"Found {entity_type} with {len(snapshots)} versions")
    print()

    # Print LLM status before launching TUI
    print_llm_status()

    # In debug mode, show the prompt before TUI starts
    if parsed.debug:
        if is_cached(func_name, file_path, snapshots, entity_type):
            print("Summary is cached - no LLM call needed")
        else:
            print("=" * 60)
            print("LLM PROMPT:")
            print("=" * 60)
            print(build_prompt(func_name, file_path, snapshots, entity_type))
            print("=" * 60)
        print()
        input("Press Enter to start TUI...")

    # Launch TUI
    run_tui(
        func_name, file_path, snapshots, debug=parsed.debug, entity_type=entity_type
    )


if __name__ == "__main__":
    main()
