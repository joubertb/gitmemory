# GitMemory

Git-aware memory system for AI coding assistants. Transforms repository history into structured, searchable knowledge.

## Quick Start

```bash
# Create venv and install (from repo root)
uv venv
uv pip install -e .
source .venv/bin/activate

# Or install globally via pipx (for Claude Code skill)
pipx install .

# View entity history - type is auto-detected
view-fn-hist <github-file-url> <entity-name>

# Local git repository
view-fn-hist <repo> <file> <entity-name>

# Start web interface
view-fn-hist --web
```

## Commands

### view-fn-hist

View the git history of functions, classes, structs, enums, and other code entities.

**GitHub URL (recommended):**
```bash
# Entity type is auto-detected
view-fn-hist https://github.com/owner/repo/blob/main/src/lib.rs Point

# Override with explicit type
view-fn-hist https://github.com/owner/repo/blob/main/src/lib.rs Point -t struct
```

**Local git repository:**
```bash
view-fn-hist /path/to/repo src/module.py MyClass
view-fn-hist /path/to/repo src/lib.rs Config -t struct
```

**Web interface:**
```bash
view-fn-hist --web
view-fn-hist --web --port 3000  # Custom port
```

**Options:**
- `-t, --type TYPE` — Entity type: `auto` (default), `function`, `class`, `struct`, `enum`, `impl`, `interface`
- `-d, --debug` — Show LLM prompt before starting TUI
- `--web` — Start web server instead of TUI
- `--port PORT` — Port for web server (default: 8000)
- `--plain` — Output plain text instead of TUI (for scripting/Claude Code)
- `--no-summary` — Skip LLM summary (useful when Claude analyzes the output)

**Supported entity types by language:**
| Language   | Supported Types                        |
|------------|----------------------------------------|
| Rust       | function, struct, enum, impl           |
| Python     | function, class                        |
| TypeScript | function, class, interface, enum       |
| JavaScript | function, class                        |
| Go         | function, struct, interface            |
| Java       | function (method), class, interface, enum |

**TUI Navigation:**
- `↑` / `k` — Go to older version
- `↓` / `j` — Go to newer version
- `Home` — Go to first (oldest) version
- `End` — Go to last (newest) version
- `q` — Quit

**Supported languages:**
- Python (AST parsing)
- Rust, TypeScript, JavaScript, Go, Java (tree-sitter parsing)
- C, C++, Ruby (regex-based fallback)

## Web Interface

The web interface provides the same functionality as the TUI in a browser.

**Features:**
- Input GitHub URL + entity name
- Entity type selector (auto-detect, function, class, struct, enum, impl, interface)
- Navigate through entity versions
- Diff highlighting (green = changed lines)
- LLM-generated evolution summary
- Search history (persisted in browser)
- Keyboard navigation (←/→ or j/k)

**Running locally:**
```bash
# Backend only (API at http://localhost:8000)
view-fn-hist --web

# For development (with hot reload):
# Terminal 1: Backend
view-fn-hist --web

# Terminal 2: Frontend
cd src/view_fn_hist/web/frontend
npm install
npm run dev
# Frontend at http://localhost:5173
```

## Docker

```bash
# Build and run with docker-compose
docker compose up --build

# Access at http://localhost:8000
```

Docker reads environment variables from `.env` file.

## Configuration

Create a `.env` file in the project root:

```bash
# Required for GitHub API (higher rate limits)
GITHUB_TOKEN=ghp_xxxxxxxxxxxx

# Required for LLM summaries
OPENROUTER_API_KEY=sk-or-xxxxxxxxxxxx

# Optional: Change LLM model (default: openrouter/google/gemini-flash-1.5)
VIEW_FN_HIST_MODEL=openrouter/google/gemini-flash-1.5
```

**Getting tokens:**
- GitHub: https://github.com/settings/tokens (select `public_repo` scope)
- OpenRouter: https://openrouter.ai/keys

## Claude Code Skill

GitMemory includes a Claude Code skill for viewing entity history directly in Claude Code.

**Installation (from repo root):**
```bash
# Install CLI globally
pipx install .

# Symlink skill to Claude
ln -s "$(pwd)/skills/view-git-history" ~/.claude/skills/view-git-history
```

**Usage:**
```
/view-git-history <entity-name> [file-path]
```

The skill runs `view-fn-hist --plain --no-summary` and Claude analyzes the output to provide a summary.

**Output modes:**
- Default: Concise single-paragraph summary
- Verbose (`-v`): Detailed timeline with milestones and patterns

### Using with Planning

When planning changes to existing code, git history provides valuable context about why code exists and what approaches were tried. There are several ways to integrate this:

**Option 1: Global CLAUDE.md (recommended)**

Add to `~/.claude/CLAUDE.md`:
```markdown
## Planning Guidelines

When planning changes to existing code, use `/view-git-history` on key functions/classes to understand:
- Why the current implementation exists
- What approaches were tried and rejected (check WHY NOT sections in commits)
- How stable/volatile the code is
- Recent changes that might affect your approach
```

**Option 2: Project CLAUDE.md**

Same as above, but add to the project's `CLAUDE.md` for project-specific planning guidance.

**Option 3: Custom planning skill**

Create a `/plan-with-history` skill that wraps the planning process and automatically pulls git history for relevant entities before generating a plan.

## Project Structure

```
gitmemory/
├── src/view_fn_hist/
│   ├── cli.py                 # CLI entry point
│   ├── tui.py                 # Terminal UI (textual)
│   ├── parser.py              # Source code parsing dispatcher
│   ├── ts_parser.py           # Tree-sitter parsing (multi-language)
│   ├── summarizer.py          # LLM summary generation + caching
│   ├── providers/
│   │   ├── base.py            # Abstract provider interface
│   │   ├── git_provider.py    # Local git repository
│   │   └── github_provider.py # GitHub API
│   └── web/
│       ├── app.py             # FastAPI application
│       ├── routes.py          # API endpoints
│       ├── schemas.py         # Pydantic models
│       └── frontend/          # React + TypeScript + Tailwind
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## API Endpoints

When running the web server:

- `POST /api/analyze` — Get entity evolution snapshots
  - Body: `{ github_url, function_name, entity_type? }` (entity_type defaults to "auto")
  - Returns: `{ function_name, file_path, repo, entity_type, snapshots[] }`
- `POST /api/summary` — Get LLM-generated summary
  - Body: `{ github_url, function_name, entity_type? }`
  - Returns: `{ summary, cached }`
- `GET /docs` — Swagger UI documentation

## Caching

**LLM summaries:** Cached in `~/.cache/view-fn-hist/` based on entity identity (name, type, file path) and commit history. Cache is invalidated when commits change.

**GitHub API results:** Cached in-memory during server runtime to avoid redundant API calls.

## Development

```bash
# Install with dev dependencies
uv pip install -e ".[dev]"

# Run tests
uv run pytest

# Run specific test
uv run pytest tests/test_parser.py -v
```

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  CLI / TUI      │     │  Web Frontend   │     │  GitHub API     │
│  (textual)      │     │  (React)        │     │  (PyGithub)     │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         └───────────┬───────────┘                       │
                     │                                   │
              ┌──────▼──────┐                           │
              │  Providers  │◄──────────────────────────┘
              │  (abstract) │
              └──────┬──────┘
                     │
         ┌───────────┼───────────┐
         │           │           │
    ┌────▼────┐ ┌────▼────┐ ┌────▼────┐
    │ Parser  │ │Summarizer│ │  TUI    │
    │(tree-   │ │ (LLM)   │ │ (diff)  │
    │ sitter) │ │         │ │         │
    └─────────┘ └─────────┘ └─────────┘
```
