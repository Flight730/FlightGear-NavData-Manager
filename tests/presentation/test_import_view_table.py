"""Import tab with this app's CSV/TXT format: summary, row-numbered
errors, warnings, the format help, and the file-type filter."""

from PySide6.QtWidgets import QFileDialog, QMessageBox

from flightgear_navdata_manager.presentation.views import import_view
from flightgear_navdata_manager.presentation.views.import_view import ImportView
from flightgear_navdata_manager.presentation.views.manage_data_view import ManageDataView

HEADER = "type,ident,name,latitude,longitude,elevation_ft,frequency,range_nm"
MIXED = f"""{HEADER}
FIX,EBAYE,EBAYE,37.621,-122.379,0,,
NDB,ABC,Example NDB,37.500,-122.300,50,375,50
VOR,XYZ,Example VOR,37.600,-122.400,100,113.2,130
DME,XYZ,Example DME,37.600,-122.400,100,113.2,130
FIX,BADLAT,,north,-122.3,,,
NDB,BADF,N,37.5,-122.3,50,abc,50
FIX,WARNF,,37.7,-122.5,,113.2,
"""


def _view(gui_env):
    manage = ManageDataView(gui_env["waypoint_service"], gui_env["navaid_service"])
    view = ImportView(gui_env["import_service"], on_imported=manage.refresh, dataset_service=gui_env["dataset_service"])
    return view, manage


def _run(view, monkeypatch, path, answer=QMessageBox.StandardButton.Yes):
    asked, infos = [], []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), ""))
    monkeypatch.setattr(QMessageBox, "question", lambda p, t, text, *a, **k: (asked.append(text), answer)[1])
    monkeypatch.setattr(QMessageBox, "information", lambda p, t, text, *a, **k: infos.append((t, text)))
    view._dataset_btn.click()
    return asked, infos


def test_csv_import_shows_concise_summary_then_details(gui_env, monkeypatch, tmp_path):
    path = tmp_path / "mine.csv"
    path.write_text(MIXED)
    view, manage = _view(gui_env)
    asked, _ = _run(view, monkeypatch, path)

    assert "Total: 5 new, 2 invalid rows, 1 warnings" in asked[0]
    log = view._log.toPlainText()
    assert log.startswith(
        "Dataset import complete\n\nRecords read: 7\nImported: 5\nDuplicates skipped: 0\n"
        "Identifier conflicts: 0\nInvalid rows: 2\nUnsupported: 0\nWarnings: 1\n"
    )
    assert f"NavData Manager CSV/TXT: {path}" in log
    assert "mine.csv line 6: FIX BADLAT -- malformed latitude 'north'" in log
    assert "mine.csv line 7: NDB BADF -- malformed frequency 'abc'" in log
    assert "mine.csv line 8: FIX WARNF -- frequency ignored: FIX has no frequency" in log
    assert manage._model.rowCount() == 5


def test_reimporting_csv_reports_duplicates_skipped(gui_env, monkeypatch, tmp_path):
    path = tmp_path / "mine.csv"
    path.write_text(MIXED)
    view, _ = _view(gui_env)
    _run(view, monkeypatch, path)
    asked, infos = _run(view, monkeypatch, path)
    assert asked == []
    assert "Total: 0 new, 5 duplicates skipped, 2 invalid rows, 1 warnings" in infos[0][1]
    assert "Duplicates skipped: 5" in view._log.toPlainText()


def test_tab_separated_txt_import(gui_env, monkeypatch, tmp_path):
    path = tmp_path / "mine.txt"
    path.write_text(MIXED.replace(",", "\t"))
    view, manage = _view(gui_env)
    _run(view, monkeypatch, path)
    assert "NavData Manager CSV/TXT" in view._log.toPlainText()
    assert manage._model.rowCount() == 5


def test_undeterminable_txt_shows_a_useful_error(gui_env, monkeypatch, tmp_path):
    path = tmp_path / "mine.txt"
    path.write_text("type ident name latitude longitude frequency range_nm\n"
                    "NDB ABC Big Bear 37.5 -122.3 375 50\nVOR XYZ Palo Alto 37.6 -122.4 113.2 130\n")
    view, _ = _view(gui_env)
    _, infos = _run(view, monkeypatch, path)
    assert infos[0][0] == "Nothing to import"
    assert "mine.txt: not a recognized navigation data file" in infos[0][1]
    assert gui_env["navaid_service"].list_all() == []


def test_format_help_explains_columns_and_units(gui_env, monkeypatch):
    view, _ = _view(gui_env)
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda p, title, text, *a, **k: shown.append((title, text)))
    [button] = [b for b in view.findChildren(type(view._dataset_btn)) if b.text() == "CSV/TXT format..."]
    button.click()
    title, text = shown[0]
    assert title == "CSV/TXT format"
    assert "type,ident,name,latitude,longitude,frequency,range_nm" in text
    assert "ident,latitude,longitude" in text
    assert "kHz for NDB" in text and "MHz for VOR and DME" in text


def test_file_dialog_offers_all_supported_types(gui_env, monkeypatch):
    view, _ = _view(gui_env)
    filters = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda parent, title, folder, f: (filters.append(f), ("", ""))[1])
    view._dataset_btn.click()
    offered = filters[0].split(";;")
    assert offered[0] == "All supported (*.dat *.gz *.csv *.txt *.zip)"
    assert {"FlightGear fix.dat / nav.dat (*.dat *.gz)", "CSV (*.csv)", "TXT (*.txt)"} <= set(offered)


def test_format_hint_is_visible_on_the_tab(gui_env):
    view, _ = _view(gui_env)
    labels = [w.text() for w in view.findChildren(import_view.QLabel)]
    assert any("type, ident, name, latitude, longitude, frequency, range_nm" in t for t in labels)


UNTYPED = "ident,name,latitude,longitude,frequency,range_nm\nXYZ,Example,37.6,-122.4,113.2,130\n"


def _ask(monkeypatch, answer):
    from PySide6.QtWidgets import QInputDialog

    asked = []
    monkeypatch.setattr(
        QInputDialog, "getItem",
        lambda parent, title, label, items, current, editable: (asked.append((label, items)), answer)[1],
    )
    return asked


def test_ambiguous_navaid_table_asks_for_the_type(gui_env, monkeypatch, tmp_path):
    path = tmp_path / "navaids.csv"
    path.write_text(UNTYPED)
    asked = _ask(monkeypatch, ("VOR", True))
    view, manage = _view(gui_env)
    _run(view, monkeypatch, path)

    label, items = asked[0]
    assert items == ["NDB", "VOR", "DME"]
    assert "navaids.csv has no type column" in label
    [vor] = gui_env["navaid_service"].list_all()
    assert (vor.type.value, vor.frequency_mhz) == ("VOR", 113.2)
    assert manage._model.rowCount() == 1


def test_cancelling_the_type_question_imports_nothing(gui_env, monkeypatch, tmp_path):
    path = tmp_path / "navaids.csv"
    path.write_text(UNTYPED)
    _ask(monkeypatch, ("", False))
    view, _ = _view(gui_env)
    asked, infos = _run(view, monkeypatch, path)
    assert asked == [] and infos == []
    assert gui_env["navaid_service"].list_all() == []


def test_fix_list_needs_no_question(gui_env, monkeypatch, tmp_path):
    path = tmp_path / "fixes.txt"
    path.write_text("# my fixes\n\nEBAYE 37.123 -122.456\nWAYPT 38.0 -121.0\n")
    view, _ = _view(gui_env)            # the autouse guard fails the test if asked
    asked, _ = _run(view, monkeypatch, path)
    assert "FIX: 2 new" in asked[0]
    assert len(gui_env["waypoint_service"].list_all()) == 2


def test_duplicates_are_not_created_and_existing_preserved(gui_env, monkeypatch, tmp_path):
    ns = gui_env["navaid_service"]
    mine = ns.create_vor("XYZ", "Mine", 37.6, -122.4, 100, 113.2, 130)
    path = tmp_path / "navaids.csv"
    path.write_text("type,ident,name,latitude,longitude,frequency,range_nm\n"
                    "VOR,XYZ,Theirs,37.6,-122.4,113.2,130\nNDB,ABC,New,37.5,-122.3,375,50\n")
    view, manage = _view(gui_env)
    asked, _ = _run(view, monkeypatch, path)

    assert "1 duplicates skipped" in asked[0]
    log = view._log.toPlainText()
    assert "Records read: 2\nImported: 1\nDuplicates skipped: 1" in log
    assert "navaids.csv line 2: VOR XYZ -- Exact duplicate of VOR XYZ (custom)" in log
    vors = [n for n in ns.list_all() if n.type.value == "VOR"]
    assert [(v.id, v.name) for v in vors] == [(mine.id, "Mine VOR")]
