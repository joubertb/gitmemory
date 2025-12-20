"""TUI for navigating function evolution using textual."""

import difflib

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Static, Rule

from .providers import FunctionSnapshot
from .summarizer import generate_evolution_summary


def compute_changed_lines(old_source: str | None, new_source: str) -> set[int]:
    """
    Compute which lines in new_source are different from old_source.

    Returns set of 0-indexed line numbers that changed.
    """
    if old_source is None:
        # All lines are new
        return set(range(len(new_source.split("\n"))))

    old_lines = old_source.split("\n")
    new_lines = new_source.split("\n")

    changed = set()

    # Use SequenceMatcher to find differences
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "insert"):
            # Lines j1 to j2 in new are changed/added
            for j in range(j1, j2):
                changed.add(j)

    return changed


class FunctionSourceView(Static):
    """Widget to display function source code with diff highlighting."""

    def __init__(self, source: str = "", start_line: int = 1, **kwargs):
        super().__init__(**kwargs)
        self._source = source
        self._start_line = start_line
        self._changed_lines: set[int] = set()

    def update_source(
        self, source: str, start_line: int, changed_lines: set[int] | None = None
    ):
        """Update the displayed source code."""
        self._source = source
        self._start_line = start_line
        self._changed_lines = changed_lines or set()
        self._render_source()

    def _render_source(self):
        """Render source with line numbers and highlighting."""
        lines = self._source.split("\n")
        text = Text()

        for i, line in enumerate(lines):
            line_num = self._start_line + i

            # Check if this line changed
            is_changed = i in self._changed_lines

            # Format line number
            line_num_str = f"{line_num:5d} │ "

            if is_changed:
                # Highlight changed lines in green
                text.append(line_num_str, style="bold green")
                text.append(line, style="green")
            else:
                text.append(line_num_str, style="dim")
                text.append(line)

            if i < len(lines) - 1:
                text.append("\n")

        self.update(text)

    def on_mount(self):
        """Called when widget is mounted."""
        self._render_source()


class SummaryBar(Static):
    """Widget to display LLM-generated evolution summary."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._summary = "Generating summary..."

    def set_summary(self, summary: str):
        """Set the summary text."""
        self._summary = summary
        self.update(self._summary)

    def on_mount(self):
        """Called when widget is mounted."""
        self.update(self._summary)


class CommitInfoBar(Static):
    """Widget to display current commit info."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._index = 0
        self._total = 0
        self._snapshot: FunctionSnapshot | None = None

    def update_commit(self, snapshot: FunctionSnapshot, index: int, total: int):
        """Update the displayed commit info."""
        self._snapshot = snapshot
        self._index = index
        self._total = total
        self._render_info()

    def _render_info(self):
        """Render commit information."""
        if self._snapshot is None:
            self.update("")
            return

        commit = self._snapshot.commit
        date_str = commit.timestamp.strftime("%Y-%m-%d %H:%M")
        change_type = self._snapshot.change_type.upper()

        # Navigation indicator
        nav = f"[{self._index + 1}/{self._total}]"

        # Build info string
        info = (
            f"{nav} {date_str} | {commit.short_hash} | {change_type}\n{commit.subject}"
        )
        self.update(info)


class FunctionEvolutionApp(App):
    """TUI app for viewing function evolution through git history."""

    CSS = """
    Screen {
        layout: vertical;
    }

    #header-bar {
        height: 1;
        background: $primary;
        color: $text;
        text-align: center;
        padding: 0 1;
    }

    #summary-container {
        height: auto;
        max-height: 8;
        background: $surface;
        padding: 0 1;
    }

    #summary-bar {
        color: $text;
    }

    #summary-rule {
        margin: 0;
        color: $primary;
    }

    #commit-info {
        height: 3;
        background: $surface;
        padding: 0 1;
    }

    #source-container {
        height: 1fr;
        overflow-y: auto;
        padding: 0 1;
    }

    #source-view {
        width: 100%;
    }

    #nav-help {
        height: 1;
        background: $surface;
        text-align: center;
        color: $text-muted;
    }

    .hidden {
        display: none;
    }
    """

    BINDINGS = [
        Binding("up", "previous", "Older", show=True),
        Binding("down", "next", "Newer", show=True),
        Binding("k", "previous", "Older", show=False),
        Binding("j", "next", "Newer", show=False),
        Binding("home", "first", "First", show=True),
        Binding("end", "last", "Last", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(
        self,
        entity_name: str,
        file_path: str,
        snapshots: list[FunctionSnapshot],
        debug: bool = False,
        entity_type: str = "function",
    ):
        super().__init__()
        self.entity_name = entity_name
        self.file_path = file_path
        self.snapshots = snapshots
        self.current_index = len(snapshots) - 1  # Start at newest
        self.has_summary = False  # Track if valid summary was generated
        self.debug_mode = debug
        self.entity_type = entity_type

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Static(
            f"{self.entity_type.capitalize()}: {self.entity_name} | File: {self.file_path}",
            id="header-bar",
        )
        yield Container(
            SummaryBar(id="summary-bar"),
            Rule(id="summary-rule"),
            id="summary-container",
            classes="hidden",  # Hidden until summary is generated
        )
        yield CommitInfoBar(id="commit-info")
        yield Container(
            FunctionSourceView(id="source-view"),
            id="source-container",
        )
        yield Static(
            "↑/k older  ↓/j newer  Home first  End last  q quit", id="nav-help"
        )

    def on_mount(self):
        """Called when app is mounted."""
        self._update_view()
        # Generate summary in background
        self._generate_summary()

    @work(thread=True)
    def _generate_summary(self):
        """Generate LLM summary in background thread."""
        summary = generate_evolution_summary(
            self.entity_name,
            self.file_path,
            self.snapshots,
            debug=self.debug_mode,
            entity_type=self.entity_type,
        )
        # Update the summary bar from the main thread
        self.call_from_thread(self._set_summary, summary)

    def _set_summary(self, summary: str):
        """Set the summary text (called from main thread)."""
        summary_container = self.query_one("#summary-container")
        if not summary:
            # Hide summary if empty (e.g., API key not configured)
            self.has_summary = False
            summary_container.add_class("hidden")
            return
        self.has_summary = True
        summary_bar = self.query_one("#summary-bar", SummaryBar)
        summary_bar.set_summary(summary)
        # Show summary if we're on the latest version
        if self.current_index == len(self.snapshots) - 1:
            summary_container.remove_class("hidden")

    def _update_view(self):
        """Update the view with current snapshot."""
        if not self.snapshots:
            return

        snapshot = self.snapshots[self.current_index]

        # Get previous snapshot for diff comparison
        prev_source = None
        if self.current_index > 0:
            prev_source = self.snapshots[self.current_index - 1].source

        # Compute which lines changed
        changed_lines = compute_changed_lines(prev_source, snapshot.source)

        # Show summary if we have one (always visible)
        summary_container = self.query_one("#summary-container")
        if self.has_summary:
            summary_container.remove_class("hidden")
        else:
            summary_container.add_class("hidden")

        # Update commit info
        commit_info = self.query_one("#commit-info", CommitInfoBar)
        commit_info.update_commit(snapshot, self.current_index, len(self.snapshots))

        # Update source view with highlighting
        source_view = self.query_one("#source-view", FunctionSourceView)
        source_view.update_source(snapshot.source, snapshot.start_line, changed_lines)

    def action_previous(self):
        """Go to previous (older) snapshot."""
        if self.current_index > 0:
            self.current_index -= 1
            self._update_view()

    def action_next(self):
        """Go to next (newer) snapshot."""
        if self.current_index < len(self.snapshots) - 1:
            self.current_index += 1
            self._update_view()

    def action_first(self):
        """Go to first (oldest) snapshot."""
        self.current_index = 0
        self._update_view()

    def action_last(self):
        """Go to last (newest) snapshot."""
        self.current_index = len(self.snapshots) - 1
        self._update_view()


def run_tui(
    entity_name: str,
    file_path: str,
    snapshots: list[FunctionSnapshot],
    debug: bool = False,
    entity_type: str = "function",
):
    """Run the TUI app."""
    app = FunctionEvolutionApp(
        entity_name, file_path, snapshots, debug=debug, entity_type=entity_type
    )
    app.run()
