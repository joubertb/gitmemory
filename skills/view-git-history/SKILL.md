---
name: view-git-history
description: View the git history of a function, class, struct, or other code entity. Use when understanding how code evolved over time, tracking changes to specific functions, or analyzing why code changed.
argument-hint: <entity-name> [file-path] [-v]
allowed-tools: Bash(view-fn-hist *), Bash(rg *), Grep, Read
---

# View Git History

Show how a code entity (function, class, struct, enum, interface) has evolved through git commits.

## Prerequisites

Install via pipx (one-time setup):
```bash
# Clone repo
git clone https://github.com/joubertb/gitmemory.git
cd gitmemory

# Install CLI globally
pipx install .

# Symlink skill to Claude
ln -s "$(pwd)/skills/view-git-history" ~/.claude/skills/view-git-history
```

## Arguments

- `$0` - Entity name (required)
- `$1` - File path (optional, will search if not provided)
- `-v` - Verbose output with detailed timeline (optional)

## Instructions

1. **If file path not provided**, search for the entity:
   ```bash
   rg -l "def $0|class $0|fn $0|struct $0|enum $0|interface $0"
   ```

2. **Run view-fn-hist** with `--plain --no-summary` flags:
   ```bash
   view-fn-hist "$(pwd)" "<file-path>" "$0" --plain --no-summary
   ```

3. **Analyze the output yourself** and provide a summary.
   - Pay attention to WHY and WHY NOT sections in commit messages - these explain the reasoning behind changes and alternatives that were considered but rejected.

## Output Format

### Default (concise)

Format your response with a header and structured content:

```
## `entity_name` — Git History

**Purpose:** 1-2 sentences describing what the entity does.

**Evolution:** Brief narrative of how it evolved, highlighting significant functional changes only. Skip housekeeping (renaming, constants, formatting). Incorporate reasoning from WHY/WHY NOT sections when present.

**Key changes:**
- Change 1: brief description
- Change 2: brief description
- (only include 3-5 most significant changes)
```

Example:
```
## `process_document` — Git History

**Purpose:** Orchestrates the PDF-to-audio pipeline, coordinating PDF parsing, text processing, and audio generation.

**Evolution:** Started as a simple sequential processor. Gained abort handling for user cancellations and progress reporting for large documents. Later refactored to use dependency injection for better testability.

**Key changes:**
- Added abort handling to support user cancellations mid-processing
- Implemented progress tracking with percentage updates for large documents
- Refactored to dependency injection for improved testability
```

### Verbose (`-v` flag)

If the user includes `-v`, provide the detailed format:

```
## `entity_name` — Git History

**Purpose:** 1-2 sentences describing what the entity does.

**Evolution:** Brief narrative of significant functional changes.

### Timeline

| Date | Author | Change |
|------|--------|--------|
| YYYY-MM | Name | Created: initial description |
| YYYY-MM | Name | Added: feature description |
| YYYY-MM | Name | Fixed: bug description |

### Patterns

- **Stability:** How often it changes, recent activity level
- **Change types:** Bug fixes, features, refactoring patterns
- **Design decisions:** Key choices from WHY/WHY NOT sections
```

## Supported Languages

Python, Rust, TypeScript, JavaScript, Go, Java, C, C++, Ruby

$ARGUMENTS
