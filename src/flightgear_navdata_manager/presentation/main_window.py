"""Main application window: a sidebar of pages (Dashboard, Import,
Manage Data, Add Waypoint, Add Navaid) beside a content stack showing
the current one.

MainWindow also owns the app-wide shared state: DataEvents (data
changed) and InstallationState (FlightGear detected once at startup).
"""

from __future__ import annotations

from PySide6.QtCore import QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QStackedWidget, QWidget

from flightgear_navdata_manager.application.dashboard_stats import DashboardStatsService
from flightgear_navdata_manager.application.dataset_import import DatasetImportService
from flightgear_navdata_manager.application.export_navdata import ExportService
from flightgear_navdata_manager.application.import_navdata import ImportService
from flightgear_navdata_manager.application.install_detection import InstallDetectionService
from flightgear_navdata_manager.application.navaid_service import NavaidService
from flightgear_navdata_manager.application.waypoint_service import WaypointService

from .components.page import PageScaffold
from .components.sidebar import Sidebar
from .data_events import ChangeKind, DataChange, DataEvents
from .install_state import InstallationState
from .views.add_fix_form import AddFixForm
from .views.add_nav_form import AddNavForm
from .views.dashboard_view import DashboardView
from .views.import_view import ImportView
from .views.manage_data_view import ManageDataView

DEFAULT_SIZE = QSize(1200, 780)
MINIMUM_SIZE = QSize(980, 640)
SETTINGS_ORG = "FlightGearNavDataManager"
SETTINGS_APP = "FlightGear NavData Manager"
_GEOMETRY_KEY = "window/geometry"

# Sidebar order, which the Go menu (⌘1-⌘5) follows:
# (group heading or None, icon, label, page description)
_PAGES = [
    ("Overview", "layout-dashboard", "Dashboard",
     "Your FlightGear installation and the custom scenery folder this app maintains."),
    ("Data", "download", "Import",
     "Bring in fix.dat / nav.dat files, CSV/TXT tables or FAA NASR data. Source files are only ever read."),
    (None, "database", "Manage Data",
     "Enable, disable or delete your imported and custom records."),
    ("Create", "map-pin", "Add Waypoint",
     "Create a custom fix from an identifier and coordinates."),
    (None, "radio-tower", "Add Navaid",
     "Create a custom NDB, VOR or standalone DME."),
]
DASHBOARD, IMPORT, MANAGE_DATA, ADD_WAYPOINT, ADD_NAVAID = range(len(_PAGES))


class MainWindow(QMainWindow):
    def __init__(
        self,
        waypoint_service: WaypointService,
        navaid_service: NavaidService,
        import_service: ImportService,
        export_service: ExportService,
        install_service: InstallDetectionService,
        dataset_import_service: DatasetImportService | None = None,
        settings: QSettings | None = None,
        stats_service: DashboardStatsService | None = None,
    ):
        super().__init__()
        self.setWindowTitle("FlightGear NavData Manager")
        self.setMinimumSize(MINIMUM_SIZE)
        self._waypoint_service = waypoint_service
        self._navaid_service = navaid_service
        # defaultFormat() is the native plist in the app; tools can redirect it.
        self._settings = settings or QSettings(
            QSettings.defaultFormat(), QSettings.Scope.UserScope, SETTINGS_ORG, SETTINGS_APP
        )

        self.data_events = DataEvents(self)
        self.install_state = InstallationState(install_service, self)   # the one startup detection

        self.manage_view = ManageDataView(
            waypoint_service, navaid_service,
            on_changed=lambda what: self.data_events.notify(
                ChangeKind.RECORD_TOGGLED if what == "toggled" else ChangeKind.RECORD_DELETED,
                self.manage_view,
            ),
            on_navigate=lambda target: self.set_current_page(
                {"import": IMPORT, "add_waypoint": ADD_WAYPOINT}[target]
            ),
            # Loaded just after the window appears (a full FAA dataset takes
            # a moment), not while it is being built.
            load_now=False,
        )
        self.import_view = ImportView(
            import_service,
            on_imported=lambda: self.data_events.notify(ChangeKind.RECORDS_IMPORTED, self.import_view),
            dataset_service=dataset_import_service,
        )
        self.dashboard_view = DashboardView(
            install_service, export_service,
            install_state=self.install_state,
            on_regenerated=lambda: self.data_events.notify(
                ChangeKind.EXPORT_REGENERATED, self.dashboard_view
            ),
            stats_service=stats_service,
        )
        self.add_fix_form = AddFixForm(
            waypoint_service,
            on_created=lambda: self.data_events.notify(ChangeKind.RECORD_ADDED, self.add_fix_form),
        )
        self.add_nav_form = AddNavForm(
            navaid_service,
            on_created=lambda: self.data_events.notify(ChangeKind.RECORD_ADDED, self.add_nav_form),
        )
        views = [self.dashboard_view, self.import_view, self.manage_view,
                 self.add_fix_form, self.add_nav_form]

        self.sidebar = Sidebar()
        self._stack = QStackedWidget()
        self._stack.setObjectName("ContentStack")
        # Takes focus on page changes so no page control starts focused.
        self._stack.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._pages: list[PageScaffold] = []
        for (group, icon_name, label, description), view in zip(_PAGES, views):
            if group:
                self.sidebar.add_group(group)
            self.sidebar.add_item(icon_name, label)
            page = PageScaffold(icon_name, label, description, view)
            self._pages.append(page)
            self._stack.addWidget(page)
        self.sidebar.finish()
        self.sidebar.pageRequested.connect(self.set_current_page)
        self.manage_view.summaryChanged.connect(self._pages[MANAGE_DATA].description_label.setText)

        central = QWidget()
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self.sidebar)
        row.addWidget(self._stack, 1)
        self.setCentralWidget(central)

        self._build_go_menu()
        self.install_state.changed.connect(self.sidebar.set_installation)
        self.sidebar.set_installation(self.install_state.installation)
        self.data_events.changed.connect(self._on_data_changed)
        self._update_record_count()

        self.set_current_page(DASHBOARD)
        self._restore_geometry()
        QTimer.singleShot(0, self, self.manage_view.refresh)

    # -- pages ---------------------------------------------------------------
    def set_current_page(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        self.sidebar.set_current(index)
        self._stack.setFocus(Qt.FocusReason.OtherFocusReason)

    def current_page(self) -> int:
        return self._stack.currentIndex()

    def show_page(self, view: QWidget) -> None:
        """Shows the page containing `view` (one of the five page views)."""
        for index, page in enumerate(self._pages):
            if page.content is view:
                self.set_current_page(index)
                return
        raise ValueError(f"{view!r} is not a page of this window")

    def _build_go_menu(self) -> None:
        menu = self.menuBar().addMenu("Go")
        self.go_actions: list[QAction] = []
        for index, (_, _, label, _) in enumerate(_PAGES):
            action = QAction(label, self)
            # Ctrl is the Command key on macOS: ⌘1 ... ⌘5.
            action.setShortcut(QKeySequence(f"Ctrl+{index + 1}"))
            action.triggered.connect(lambda _=False, i=index: self.set_current_page(i))
            menu.addAction(action)
            self.addAction(action)   # shortcuts also work while the menu bar is hidden
            self.go_actions.append(action)

    # -- shared state --------------------------------------------------------
    def _on_data_changed(self, change: DataChange) -> None:
        # Manage Data already shows its own toggles and deletes; reloading
        # it then would lose the user's scroll position for nothing.
        if change.kind in (ChangeKind.RECORD_ADDED, ChangeKind.RECORDS_IMPORTED):
            self.manage_view.refresh()
        if change.kind.changes_records:
            self._update_record_count()
        # Every change (records or export) can move a Dashboard number.
        self.dashboard_view.refresh_stats()

    def _update_record_count(self) -> None:
        total = self._waypoint_service.count() + self._navaid_service.count()
        self.sidebar.set_count(MANAGE_DATA, total)

    # -- window geometry -----------------------------------------------------
    def _restore_geometry(self) -> None:
        saved = self._settings.value(_GEOMETRY_KEY)
        if saved is not None and self.restoreGeometry(saved):
            return
        self.resize(DEFAULT_SIZE)
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            frame = self.frameGeometry()
            frame.moveCenter(screen.availableGeometry().center())
            self.move(frame.topLeft())

    def closeEvent(self, event) -> None:
        self._settings.setValue(_GEOMETRY_KEY, self.saveGeometry())
        self._settings.sync()
        super().closeEvent(event)
