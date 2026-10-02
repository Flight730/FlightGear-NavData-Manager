"""Import view: lets the user pick an existing fix.dat/nav.dat (or
.dat.gz) file, or a dataset -- FAA NASR FIX/NAV (CSV or TXT) or
FlightGear fix.dat/nav.dat, as a file, a .zip, or a whole folder -- to
import. Source files are opened read-only and are never modified by
this application.

Dataset import is two-step: the source is analyzed first, the user
confirms what will be added, and only then is anything stored. The log
shows a per-category summary first, then details (every identifier
conflict; other outcomes grouped by reason).
"""

from __future__ import annotations

import html
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEventLoop, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from flightgear_navdata_manager.application.dataset_import import (
    DatasetImportPlan,
    DatasetImportService,
    RecordTypeNeededError,
    UnrecognizedDatasetError,
)
from flightgear_navdata_manager.application.datasets.base import RecordIssue
from flightgear_navdata_manager.application.import_navdata import ImportService, ImportSummary

from ..components.card import Card
from ..components.feedback import Chip, InlineBanner
from ..theme import icons
from ..theme.tokens import COLORS, FONT, SPACING

LOG_PLACEHOLDER = "Import results will appear here."
READ_ONLY_NOTE = "Read-only: the source file is never modified, moved or deleted."
SUPPORTED_FORMATS = ["fix.dat / nav.dat", "CSV", "TXT", "FAA NASR", "ZIP"]

_MAX_LISTED = 1000
_MAX_LISTED_DUPLICATES = 20
_EXAMPLES_PER_REASON = 3
_DATASET_FILTER = ";;".join([
    "All supported (*.dat *.gz *.csv *.txt *.zip)",
    "FlightGear fix.dat / nav.dat (*.dat *.gz)",
    "CSV (*.csv)",
    "TXT (*.txt)",
    "ZIP archive (*.zip)",
    "All files (*)",
])
TABLE_FORMAT_HELP = """\
CSV / TXT tables -- one record per row.

Navaids (and fixes) with a type column:
  type,ident,name,latitude,longitude,frequency,range_nm
  NDB,ABC,Example NDB,37.500,-122.300,375,50
  VOR,XYZ,Example VOR,37.600,-122.400,113.2,130
  FIX,EBAYE,,37.621,-122.379,,

A list of fixes needs only:
  ident,latitude,longitude        (a name column is allowed and ignored)
  EBAYE,37.123,-122.456

type: FIX, NDB, VOR or DME. Latitude/longitude in decimal degrees (south
and west negative). Frequency is kHz for NDB (whole number, e.g. 375)
and MHz for VOR and DME (e.g. 113.20; a DME's paired VHF frequency).
range_nm in whole nautical miles. Optional columns: elevation_ft (whole
feet; without the column navaids get 0 ft, with a warning),
slaved_variation_deg (VOR), bias_nm (DME).

A navaid table without a type column: you'll be asked whether it holds
NDBs, VORs or DMEs -- the app won't guess from the frequencies.

.csv files are comma-separated. .txt files may be tab-, comma- or
space-separated (quote names that contain spaces), and may leave out
the header if the columns are in one of the orders above. Blank lines
and lines starting with # are ignored. Text is UTF-8."""


class ImportView(QWidget):
    def __init__(
        self,
        import_service: ImportService,
        on_imported: Callable[[], None] | None = None,
        parent: QWidget | None = None,
        dataset_service: DatasetImportService | None = None,
    ):
        super().__init__(parent)
        self._service = import_service
        self._dataset_service = dataset_service
        self._on_imported = on_imported
        self._busy_depth = 0
        self._action_buttons: list[QPushButton] = []

        layout = QVBoxLayout(self)
        layout.setSpacing(SPACING.lg)

        # Page-level result of the last import (or "Analyzing..." while busy).
        self.result_banner = InlineBanner()
        layout.addWidget(self.result_banner)

        if dataset_service is not None:
            layout.addWidget(self._build_dataset_card())

        sources = QHBoxLayout()
        sources.setSpacing(SPACING.lg)
        fix_card, fix_btn = _source_card(
            "fix.dat", "map-pin", "FlightGear / X-Plane fix list",
            "Imports waypoints (fixes). Plain text or .gz.",
            "Choose fix.dat file...",
        )
        fix_btn.clicked.connect(self._import_fix)
        nav_card, nav_btn = _source_card(
            "nav.dat", "radio-tower", "FlightGear / X-Plane navaid list",
            "Imports NDB, VOR and DME navaids. Other row types (ILS, markers) are skipped "
            "and counted in the log. Plain text or .gz.",
            "Choose nav.dat file...",
        )
        nav_btn.clicked.connect(self._import_nav)
        sources.addWidget(fix_card, 1)
        sources.addWidget(nav_card, 1)
        layout.addLayout(sources)
        self._action_buttons += [fix_btn, nav_btn]

        log_card = Card("Import log", "file-text")
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setProperty("role", "log")
        self._log.setPlaceholderText(LOG_PLACEHOLDER)
        self._log.setMinimumHeight(180)
        log_card.body.addWidget(self._log, 1)
        layout.addWidget(log_card, 1)

    def _build_dataset_card(self) -> Card:
        card = Card(
            "Import dataset", "download",
            "Analyze a file, a .zip or a whole folder, review what was found, then confirm.",
        )
        chips = QHBoxLayout()
        chips.setSpacing(SPACING.sm)
        for text in SUPPORTED_FORMATS:
            chips.addWidget(Chip(text))
        chips.addStretch(1)
        card.body.addLayout(chips)

        dataset_label = QLabel(
            "CSV/TXT columns: type, ident, name, latitude, longitude, frequency, range_nm -- "
            "or just ident, latitude, longitude for fixes. FAA NASR: the FIX and NAV files "
            "(CSV or TXT) from a 28-day subscription you have downloaded. Nothing is added "
            "until you confirm; duplicates are skipped."
        )
        dataset_label.setProperty("role", "secondary")
        dataset_label.setWordWrap(True)
        card.body.addWidget(dataset_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(SPACING.sm)
        self._dataset_btn = QPushButton("Import Dataset...")
        self._dataset_btn.setProperty("variant", "primary")
        icons.set_button_icon(self._dataset_btn, "file-archive", COLORS.text_on_accent)
        self._dataset_btn.clicked.connect(self._import_dataset_file)
        buttons.addWidget(self._dataset_btn)
        self._dataset_folder_btn = QPushButton("Import Folder...")
        icons.set_button_icon(self._dataset_folder_btn, "folder-open", COLORS.text_primary)
        self._dataset_folder_btn.clicked.connect(self._import_dataset_folder)
        buttons.addWidget(self._dataset_folder_btn)
        buttons.addStretch(1)
        format_btn = QPushButton("CSV/TXT format...")
        format_btn.setProperty("variant", "link")
        format_btn.clicked.connect(self._show_table_format_help)
        buttons.addWidget(format_btn)
        card.body.addLayout(buttons)
        self._action_buttons += [self._dataset_btn, self._dataset_folder_btn]
        return card

    # -- busy state ------------------------------------------------------------------
    @contextmanager
    def _busy(self):
        """Disables the import actions for the whole pick -> analyze ->
        confirm -> apply sequence (nestable: the record-type retry
        re-enters), and re-enables them however it ends."""
        self._busy_depth += 1
        if self._busy_depth == 1:
            for button in self._action_buttons:
                button.setEnabled(False)
        try:
            yield
        finally:
            self._busy_depth -= 1
            if self._busy_depth == 0:
                for button in self._action_buttons:
                    button.setEnabled(True)
                if self.result_banner.property("busy"):
                    self.result_banner.clear()
                    self.result_banner.setProperty("busy", False)

    def is_busy(self) -> bool:
        return self._busy_depth > 0

    def _show_progress(self, text: str) -> None:
        """Shows the step in progress and repaints now -- the work that
        follows runs on this thread, so nothing would be drawn until it
        ends. User input is not processed meanwhile."""
        self.result_banner.show_message(text, "info")
        self.result_banner.setProperty("busy", True)
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

    def _show_result(self, text: str, tone: str) -> None:
        self.result_banner.setProperty("busy", False)
        self.result_banner.show_message(text, tone)

    # -- actions ---------------------------------------------------------------------
    def _import_fix(self) -> None:
        if self.is_busy():
            return
        with self._busy():
            path, _ = QFileDialog.getOpenFileName(
                self, "Choose fix.dat", "", "FIX data (*.dat *.dat.gz *.gz);;All files (*)"
            )
            if not path:
                return
            self._show_progress(f"Importing {Path(path).name}...")
            try:
                summary = self._service.import_fix_file(path)
            except OSError as exc:
                self.result_banner.clear()
                QMessageBox.warning(self, "Could not read file", f"{path}\n\n{exc}")
                return
            self._log_summary("fix.dat", path, summary)
            self._show_result(f"Imported {summary.imported_count:,} record(s) from fix.dat.", "success")
            if self._on_imported:
                self._on_imported()

    def _import_nav(self) -> None:
        if self.is_busy():
            return
        with self._busy():
            path, _ = QFileDialog.getOpenFileName(
                self, "Choose nav.dat", "", "NAV data (*.dat *.dat.gz *.gz);;All files (*)"
            )
            if not path:
                return
            self._show_progress(f"Importing {Path(path).name}...")
            try:
                summary = self._service.import_nav_file(path)
            except OSError as exc:
                self.result_banner.clear()
                QMessageBox.warning(self, "Could not read file", f"{path}\n\n{exc}")
                return
            self._log_summary("nav.dat", path, summary)
            self._show_result(f"Imported {summary.imported_count:,} record(s) from nav.dat.", "success")
            if self._on_imported:
                self._on_imported()

    def _show_table_format_help(self) -> None:
        QMessageBox.information(self, "CSV/TXT format", format_help_html(TABLE_FORMAT_HELP))

    def _import_dataset_file(self) -> None:
        if self.is_busy():
            return
        with self._busy():
            path, _ = QFileDialog.getOpenFileName(self, "Import dataset", "", _DATASET_FILTER)
            if path:
                self._import_dataset(path)

    def _import_dataset_folder(self) -> None:
        if self.is_busy():
            return
        with self._busy():
            path = QFileDialog.getExistingDirectory(self, "Import dataset folder")
            if path:
                self._import_dataset(path)

    def _import_dataset(self, path: str, record_type: str | None = None) -> None:
        assert self._dataset_service is not None
        with self._busy():
            self._show_progress(f"Analyzing {Path(path).name}...")
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                plan = self._dataset_service.analyze(path, record_type)
            except RecordTypeNeededError as exc:
                QApplication.restoreOverrideCursor()
                self.result_banner.clear()
                choice, ok = QInputDialog.getItem(
                    self, "Choose record type",
                    f"{exc}\n\nWhat does this file contain?", list(exc.choices), 0, False,
                )
                if ok and choice:
                    self._import_dataset(path, choice)
                return
            except UnrecognizedDatasetError as exc:
                QApplication.restoreOverrideCursor()
                self.result_banner.clear()
                QMessageBox.information(self, "Nothing to import", f"{path}\n\n{exc}")
                return
            except (OSError, UnicodeError) as exc:
                QApplication.restoreOverrideCursor()
                self.result_banner.clear()
                QMessageBox.warning(self, "Could not read file", f"{path}\n\n{exc}")
                return
            QApplication.restoreOverrideCursor()

            if not plan.to_import:
                self._append_report(format_dataset_report(plan, "Dataset analyzed: nothing new to import"))
                self._show_result("Nothing new to import. See the import log for details.", "info")
                QMessageBox.information(
                    self, "Nothing new to import",
                    format_dataset_counts(plan) + "\n\nSee the import log for details.",
                )
                return

            self.result_banner.clear()
            reply = QMessageBox.question(
                self,
                "Import dataset",
                format_dataset_counts(plan) + f"\n\nAdd {len(plan.to_import):,} new record(s) to your data?",
            )
            if reply != QMessageBox.StandardButton.Yes:
                self._append_report(format_dataset_report(plan, "Import cancelled: nothing was added"))
                self._show_result("Import cancelled. Nothing was added.", "neutral")
                return

            self._show_progress(f"Importing {len(plan.to_import):,} record(s)...")
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                summary = self._dataset_service.apply(plan)
            finally:
                QApplication.restoreOverrideCursor()
            self._append_report(format_dataset_report(summary.plan, "Dataset import complete"))
            self._show_result(
                f"Imported {summary.imported_count:,} new record(s). The import log has the details.",
                "success",
            )
            if self._on_imported:
                self._on_imported()

    def _append_report(self, text: str) -> None:
        """Appends a (possibly long) report and scrolls so its first line
        -- the headline counts -- is at the top, not its tail."""
        document = self._log.document()
        # append() starts a new block -- except into an empty log, where it
        # fills the existing empty first block.
        first_block = document.blockCount() if not document.isEmpty() else 0
        self._log.append(text)

        def scroll_to_report() -> None:
            # Deferred: QTextEdit lays out appended text lazily, so the
            # scroll range isn't final until the event loop has run.
            doc = self._log.document()
            top = doc.documentLayout().blockBoundingRect(doc.findBlockByNumber(first_block)).top()
            self._log.verticalScrollBar().setValue(int(top))

        # The log is the timer's context: if the view is destroyed first,
        # Qt cancels the call instead of running it on a deleted widget.
        QTimer.singleShot(0, self._log, scroll_to_report)

    def _log_summary(self, kind: str, path: str, summary: ImportSummary) -> None:
        lines = [f"Imported {summary.imported_count} record(s) from {kind}: {path}"]
        if summary.skipped_unsupported:
            for row_code, count in sorted(summary.skipped_unsupported.items()):
                lines.append(
                    f"  Skipped {count} record(s) with unsupported row code {row_code} "
                    "(not one of NDB/VOR/DME supported in MVP 1)"
                )
        for warning in summary.warnings:
            lines.append(f"  Warning: {warning}")
        self._log.append("\n".join(lines) + "\n")


def _source_card(title: str, icon_name: str, subtitle: str, imports: str,
                 button_text: str) -> tuple[Card, QPushButton]:
    """A card for one dedicated source type: what it is, what it imports,
    its action, and that the file is only read."""
    card = Card(title, icon_name, subtitle)
    what = QLabel(imports)
    what.setProperty("role", "secondary")
    what.setWordWrap(True)
    card.body.addWidget(what)
    card.body.addStretch(1)
    # Action and the read-only note share a row to keep the card short.
    row = QHBoxLayout()
    row.setSpacing(SPACING.md)
    button = QPushButton(button_text)
    icons.set_button_icon(button, "folder-open", COLORS.text_primary)
    row.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)
    note = QLabel(READ_ONLY_NOTE)
    note.setProperty("role", "helper")
    note.setWordWrap(True)
    row.addWidget(note, 1, Qt.AlignmentFlag.AlignVCenter)
    card.body.addLayout(row)
    return card, button


def format_help_html(text: str) -> str:
    """Shows the plain-text help as rich text: indented lines (column lists
    and examples) keep their layout in a monospace block; the hard-wrapped
    prose between them is joined into paragraphs the dialog can wrap
    cleanly. The words themselves are unchanged."""
    blocks: list[str] = []
    prose: list[str] = []
    code: list[str] = []

    def flush() -> None:
        if prose:
            blocks.append(f"<p>{html.escape(' '.join(prose), quote=False)}</p>")
            prose.clear()
        if code:
            # &nbsp; keeps the column spacing inside example lines.
            body = "<br>".join(html.escape(line.strip(), quote=False).replace("  ", "&nbsp; ")
                               for line in code)
            blocks.append(f'<p style="font-family:{FONT.mono_family}; font-size:12px">{body}</p>')
            code.clear()

    for line in text.splitlines():
        if not line.strip():
            flush()
        elif line.startswith("  "):
            if prose:
                flush()
            code.append(line)
        else:
            if code:
                flush()
            prose.append(line.strip())
    flush()
    return "".join(blocks)


def format_dataset_counts(plan: DatasetImportPlan) -> str:
    """Short counts for the confirmation dialog."""
    lines = []
    if plan.effective_dates:
        lines.append(f"FAA effective date: {', '.join(plan.effective_dates)}")
    groups = [(c, plan.counts(c)) for c in plan.categories]
    if len(groups) != 1 or plan.counts() != groups[0][1]:
        groups.append(("Total", plan.counts()))
    for label, counts in groups:
        parts = [f"{counts.pop('Imported'):,} new"]
        parts += [f"{n:,} {name.lower()}" for name, n in counts.items() if n]
        lines.append(f"{label}: " + ", ".join(parts))
    return "\n".join(lines)


def format_dataset_report(plan: DatasetImportPlan, title: str) -> str:
    """Totals, sources, per-category counts, then details."""
    lines = [title, "", f"Records read: {sum(plan.records_read.values()):,}"]
    lines.extend(f"{label}: {n:,}" for label, n in plan.counts().items())
    lines += ["", "Source:"]
    lines.extend(f"  {description}: {display}" for description, display in plan.sources)
    if plan.effective_dates:
        lines.append(f"FAA effective date: {', '.join(plan.effective_dates)}")
    if len(plan.categories) > 1:  # with one category the totals above already say it all
        for category in plan.categories:
            lines.append("")
            lines.append(f"{category} ({plan.records_read[category]:,} records read)")
            lines.extend(f"  {label}: {n:,}" for label, n in plan.counts(category).items())

    details: list[str] = []
    if plan.invalid:
        details.append("Invalid rows (not imported):")
        details.extend(_listed(plan.invalid, _MAX_LISTED))
    if plan.warnings:
        details.append("Warnings:")
        details.extend(_listed(plan.warnings, _MAX_LISTED))
    if plan.conflicts:
        details.append("Identifier conflicts (not imported; existing records unchanged -- "
                       "to use the new one, disable or delete the existing record and import again):")
        details.extend(_listed(plan.conflicts, _MAX_LISTED))
    if plan.existing:
        details.append("Duplicates skipped (already in your data):")
        details.extend(_listed(plan.existing, _MAX_LISTED_DUPLICATES))
    if plan.unsupported:
        details.append("Unsupported:")
        details.extend(_grouped(plan.unsupported))
    if plan.ignored:
        details.append(f"Files not used ({len(plan.ignored)}):")
        details.extend(_grouped_files(plan.ignored))
    details.extend(f"Note: {note}" for note in plan.notes)
    if details:
        lines += ["", "Details:", *details]
    return "\n".join(lines) + "\n"


def _listed(issues: list[RecordIssue], limit: int) -> list[str]:
    lines = [f"  {_where(i)}{i.label} -- {i.reason}" for i in issues[:limit]]
    if len(issues) > limit:
        lines.append(f"  ...and {len(issues) - limit:,} more")
    return lines


def _where(issue: RecordIssue) -> str:
    source = f"{issue.source} " if issue.source else ""
    return f"{source}line {issue.line_number}: " if issue.line_number else source


def _grouped(issues: list[RecordIssue]) -> list[str]:
    by_reason: dict[str, list[RecordIssue]] = {}
    for issue in issues:
        by_reason.setdefault(issue.reason, []).append(issue)
    lines = []
    for reason, group in sorted(by_reason.items(), key=lambda kv: -len(kv[1])):
        examples = ", ".join(i.label for i in group[:_EXAMPLES_PER_REASON])
        more = "..." if len(group) > _EXAMPLES_PER_REASON else ""
        lines.append(f"  {len(group):,} x {reason} (e.g. {examples}{more})")
    return lines


def _grouped_files(ignored: list[tuple[str, str]]) -> list[str]:
    by_reason: dict[str, list[str]] = {}
    for name, reason in ignored:
        by_reason.setdefault(reason, []).append(name)
    lines = []
    for reason, names in sorted(by_reason.items(), key=lambda kv: len(kv[1])):
        shown = ", ".join(names[:_EXAMPLES_PER_REASON]) + ("..." if len(names) > _EXAMPLES_PER_REASON else "")
        lines.append(f"  {len(names)} x {reason}: {shown}")
    return lines
