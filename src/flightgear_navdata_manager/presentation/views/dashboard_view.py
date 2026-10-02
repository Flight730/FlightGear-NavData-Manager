"""Dashboard: live data summary, FlightGear installation, and the custom
scenery output folder.

Read-only detection; this view never offers to modify FlightGear's own
configuration. It surfaces the custom scenery path so the user can add
it themselves via the FlightGear Launcher or --fg-scenery.

All numbers come from DashboardStatsService (COUNT queries over the
current database) and are refreshed by MainWindow whenever DataEvents
reports a change, and whenever the page is shown.
"""

from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from flightgear_navdata_manager.application.dashboard_stats import (
    DashboardStatsService,
    ExportState,
)
from flightgear_navdata_manager.application.export_navdata import ExportService
from flightgear_navdata_manager.application.install_detection import InstallDetectionService
from flightgear_navdata_manager.domain.models import NavaidType
from flightgear_navdata_manager.infrastructure import config
from flightgear_navdata_manager.infrastructure.fg_detect.macos_locator import FlightGearInstallation

from ..components.card import Card
from ..components.elided_label import ElidedLabel
from ..components.feedback import InlineBanner, StatusPill
from ..components.stat_card import StatCard
from ..formatting import relative_time
from ..install_state import InstallationState
from ..theme import icons
from ..theme.tokens import COLORS, SPACING

_log = logging.getLogger(__name__)

# Below this content width the four stats go 2x2 and the two cards stack.
NARROW_WIDTH = 900

SAFETY_MESSAGE = (
    "FlightGear's own navdata and settings are never modified. This app only "
    "writes to its own custom scenery folder, which you add to FlightGear yourself."
)
NOT_FOUND_HELP = (
    "Install FlightGear from flightgear.org, or keep importing and adding data "
    "here and add the scenery folder to FlightGear later."
)


def _describe_error(exc: Exception) -> str:
    if isinstance(exc, OSError):
        reason = exc.strerror or str(exc)
        return f"{reason} ({exc.filename})" if exc.filename else reason
    return f"{type(exc).__name__}: {exc}"


class DashboardView(QWidget):
    def __init__(
        self,
        install_service: InstallDetectionService,
        export_service: ExportService,
        parent: QWidget | None = None,
        install_state: InstallationState | None = None,
        on_regenerated: Callable[[], None] | None = None,
        stats_service: DashboardStatsService | None = None,
    ):
        super().__init__(parent)
        self._install_service = install_service
        self._export_service = export_service
        self._stats_service = stats_service
        self._on_regenerated = on_regenerated
        # The exception from the last failed "Regenerate now", for debugging.
        self.last_regenerate_error: Exception | None = None
        # Shared with the sidebar when given; detection then isn't repeated here.
        self._install_state = install_state or InstallationState(install_service, self)
        self._install_state.changed.connect(self._show_installation)

        layout = QVBoxLayout(self)
        layout.setSpacing(SPACING.xl)

        self.safety_banner = InlineBanner("info", SAFETY_MESSAGE)
        layout.addWidget(self.safety_banner)

        self.stat_cards = {
            "records": StatCard("database", "Records"),
            "waypoints": StatCard("map-pin", "Waypoints"),
            "navaids": StatCard("radio-tower", "Navaids"),
            "export": StatCard("hard-drive", "Export"),
        }
        self._stats_row = QWidget()
        self._stats_grid = QGridLayout(self._stats_row)
        self._stats_grid.setContentsMargins(0, 0, 0, 0)
        self._stats_grid.setSpacing(SPACING.lg)
        layout.addWidget(self._stats_row)
        self._stats_row.setVisible(stats_service is not None)

        self._cards = QWidget()
        self._cards_grid = QGridLayout(self._cards)
        self._cards_grid.setContentsMargins(0, 0, 0, 0)
        self._cards_grid.setSpacing(SPACING.lg)
        self._install_card = self._build_install_card()
        self._scenery_card = self._build_scenery_card()
        layout.addWidget(self._cards)
        layout.addStretch(1)
        self._narrow: bool | None = None
        self._arrange(narrow=False)

        self._show_installation(self._install_state.installation)
        self.refresh_stats()

    # -- building --------------------------------------------------------------
    def _build_install_card(self) -> Card:
        card = Card("FlightGear installation", "plane")
        self._install_pill = StatusPill()
        card.add_header_widget(self._install_pill)

        self._status_headline_label = QLabel()
        self._status_headline_label.setProperty("role", "headline")
        card.body.addWidget(self._status_headline_label)
        self._not_found_help = QLabel(NOT_FOUND_HELP)
        self._not_found_help.setProperty("role", "secondary")
        self._not_found_help.setWordWrap(True)
        card.body.addWidget(self._not_found_help)

        grid = QGridLayout()
        grid.setHorizontalSpacing(SPACING.lg)
        grid.setVerticalSpacing(SPACING.sm)
        grid.setColumnStretch(1, 1)
        self._app_bundle_label = ElidedLabel()
        self._executable_label = ElidedLabel()
        self._fg_root_label = ElidedLabel()
        self._fg_home_label = ElidedLabel()
        rows = [
            ("App", self._app_bundle_label),
            ("Executable", self._executable_label),
            ("Navdata (FG_ROOT)", self._fg_root_label),
            ("Settings (FG_HOME)", self._fg_home_label),
        ]
        for row, (key, value) in enumerate(rows):
            key_label = QLabel(key)
            key_label.setProperty("role", "fieldKey")
            grid.addWidget(key_label, row, 0)
            grid.addWidget(value, row, 1)
        card.body.addLayout(grid)

        buttons = QHBoxLayout()
        self._rescan_btn = QPushButton("Re-scan")
        icons.set_button_icon(self._rescan_btn, "refresh-cw", COLORS.text_primary)
        self._rescan_btn.clicked.connect(self.refresh_detection)
        buttons.addWidget(self._rescan_btn)
        buttons.addStretch(1)
        card.body.addLayout(buttons)
        card.body.addStretch(1)      # extra height goes below the button, not above it
        return card

    def _build_scenery_card(self) -> Card:
        card = Card("Custom scenery output", "folder")
        help_label = QLabel(
            "Add this folder to FlightGear's Additional Scenery Paths "
            "(Launcher) or pass it via --fg-scenery. It only ever contains "
            "data you imported or created here."
        )
        help_label.setProperty("role", "secondary")
        help_label.setWordWrap(True)
        card.body.addWidget(help_label)

        self._scenery_path_field = QLineEdit(str(config.CUSTOM_SCENERY_DIR))
        self._scenery_path_field.setReadOnly(True)
        self._scenery_path_field.setProperty("role", "path")
        self._scenery_path_field.setCursorPosition(0)
        self._scenery_path_field.setToolTip(str(config.CUSTOM_SCENERY_DIR))
        card.body.addWidget(self._scenery_path_field)

        buttons = QHBoxLayout()
        buttons.setSpacing(SPACING.sm)
        copy_btn = QPushButton("Copy path")
        icons.set_button_icon(copy_btn, "copy", COLORS.text_primary)
        copy_btn.clicked.connect(self._copy_scenery_path)
        buttons.addWidget(copy_btn)
        self._regenerate_btn = QPushButton("Regenerate now")
        self._regenerate_btn.setProperty("variant", "primary")
        icons.set_button_icon(self._regenerate_btn, "refresh-cw", COLORS.text_on_accent)
        self._regenerate_btn.clicked.connect(self._regenerate)
        buttons.addWidget(self._regenerate_btn)
        buttons.addStretch(1)
        card.body.addLayout(buttons)

        # Results of Copy path / Regenerate now, success or error.
        self.status_banner = InlineBanner()
        self._status_label = self.status_banner.text_label
        card.body.addWidget(self.status_banner)
        card.body.addStretch(1)
        return card

    # -- responsive layout -----------------------------------------------------------
    def _arrange(self, narrow: bool) -> None:
        """Wide: four stats in a row, the two cards side by side. Narrow:
        stats 2x2 and the cards stacked, so nothing is squeezed."""
        if narrow == self._narrow:
            return
        self._narrow = narrow
        for grid in (self._stats_grid, self._cards_grid):
            for col in range(4):
                grid.setColumnStretch(col, 0)
        stat_columns = 2 if narrow else 4
        for i, card in enumerate(self.stat_cards.values()):
            self._stats_grid.addWidget(card, i // stat_columns, i % stat_columns)
        for col in range(stat_columns):
            self._stats_grid.setColumnStretch(col, 1)
        if narrow:
            self._cards_grid.addWidget(self._install_card, 0, 0)
            self._cards_grid.addWidget(self._scenery_card, 1, 0)
            self._cards_grid.setColumnStretch(0, 1)
        else:
            self._cards_grid.addWidget(self._install_card, 0, 0)
            self._cards_grid.addWidget(self._scenery_card, 0, 1)
            self._cards_grid.setColumnStretch(0, 1)
            self._cards_grid.setColumnStretch(1, 1)

    def is_narrow(self) -> bool:
        return bool(self._narrow)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._arrange(event.size().width() < NARROW_WIDTH)

    # -- FlightGear installation -------------------------------------------------
    def refresh_detection(self) -> None:
        """Re-runs detection; every view sharing the state updates."""
        self._install_state.rescan()

    def _show_installation(self, installation: FlightGearInstallation) -> None:
        if installation.found:
            version = installation.version or "version unknown"
            self._install_pill.set_status("Detected", "success")
            self._status_headline_label.setText(f"FlightGear {version}")
        else:
            self._install_pill.set_status("Not found", "warning")
            self._status_headline_label.setText("FlightGear not detected")
        self._not_found_help.setVisible(not installation.found)
        for label, value in (
            (self._app_bundle_label, installation.app_bundle),
            (self._executable_label, installation.fgfs_binary),
            (self._fg_root_label, installation.fg_root),
            (self._fg_home_label, installation.fg_home),
        ):
            label.setText(str(value) if value is not None else "Not found")
            label.setProperty("role", "fieldValue" if value is not None else "fieldValueMissing")
            label.style().unpolish(label)
            label.style().polish(label)

    # -- live statistics -----------------------------------------------------------
    def refresh_stats(self) -> None:
        if self._stats_service is None:
            return
        s = self._stats_service.summary()
        records = self.stat_cards["records"]
        records.set_value(f"{s.total:,}")
        records.set_detail(f"{s.enabled:,} enabled · {s.disabled:,} disabled")

        waypoints = self.stat_cards["waypoints"]
        waypoints.set_value(f"{s.fixes:,}")
        waypoints.set_detail(f"{s.fixes_custom:,} custom · {s.fixes_imported:,} imported")

        navaids = self.stat_cards["navaids"]
        navaids.set_value(f"{s.navaids:,}")
        # Non-breaking space inside each pair: lines break only between pairs.
        navaids.set_detail(" · ".join(f"{t.value}\u00a0{s.navaid_count(t):,}" for t in NavaidType))

        export = self._stats_service.export_status()
        card = self.stat_cards["export"]
        written = (f"Last written {relative_time(export.last_written)}"
                   if export.last_written else "Nothing written yet")
        if export.state is ExportState.FAILED:
            card.set_value("Failed", compact=True)
            card.set_detail(f"Last attempt failed · {written[0].lower()}{written[1:]}")
        elif export.state is ExportState.NOT_WRITTEN:
            card.set_value("Not written", compact=True)
            card.set_detail("Written after your first change")
        else:
            card.set_value("Up to date", compact=True)
            card.set_detail(written)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh_stats()      # keeps "N min ago" current

    # -- scenery output ------------------------------------------------------------
    def _copy_scenery_path(self) -> None:
        QApplication.clipboard().setText(str(config.CUSTOM_SCENERY_DIR))
        self.status_banner.show_message("Path copied to clipboard.", "success")

    def _regenerate(self) -> None:
        try:
            self._export_service.regenerate()
        except Exception as exc:  # shown to the user here, and logged with its traceback
            self.last_regenerate_error = exc
            _log.exception("Regenerating the custom NavData files failed")
            self.status_banner.show_message(
                "Couldn't regenerate the custom NavData files: "
                f"{_describe_error(exc)}. Your records are unchanged.",
                "danger",
            )
            self.refresh_stats()
            return
        self.last_regenerate_error = None
        self.status_banner.show_message("Custom NavData files regenerated.", "success")
        if self._on_regenerated:
            self._on_regenerated()
