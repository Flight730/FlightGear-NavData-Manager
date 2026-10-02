"""This app's CSV/TXT table format through DatasetImportService:
mapping via the same builders as manual entry, per-row validation with
row numbers, warnings, duplicates, and the import summary."""

import pytest

from flightgear_navdata_manager.application.dataset_import import UnrecognizedDatasetError
from flightgear_navdata_manager.domain.models import DataSource, Dme, Ndb, Vor
from flightgear_navdata_manager.infrastructure import config

HEADER = "type,ident,name,latitude,longitude,elevation_ft,frequency,range_nm"
EXAMPLE = f"""{HEADER}
FIX,EBAYE,EBAYE,37.621,-122.379,0,,
NDB,ABC,Example NDB,37.500,-122.300,50,375,50
VOR,XYZ,Example VOR,37.600,-122.400,100,113.2,130
DME,XYZ,Example DME,37.600,-122.400,100,113.2,130
"""


def _file(tmp_path, text, name="data.csv"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def _import(app_env, tmp_path, text, name="data.csv"):
    return app_env["dataset_service"].import_dataset(_file(tmp_path, text, name))


def _by_key(app_env):
    records = [*app_env["waypoint_service"].list_all(), *app_env["navaid_service"].list_all()]
    return {("FIX" if not hasattr(r, "type") else r.type.value, r.ident): r for r in records}


# --- valid records ------------------------------------------------------------------

def test_spec_example_imports_all_four_types(app_env, tmp_path):
    summary = _import(app_env, tmp_path, EXAMPLE)
    assert summary.plan.sources == [("NavData Manager CSV/TXT", str(tmp_path / "data.csv"))]
    assert summary.plan.counts() == {
        "Imported": 4, "Duplicates skipped": 0, "Identifier conflicts": 0,
        "Invalid rows": 0, "Unsupported": 0, "Warnings": 0,
    }
    assert summary.plan.counts("FIX")["Imported"] == 1
    assert summary.plan.counts("NAV")["Imported"] == 3


def test_valid_fix(app_env, tmp_path):
    _import(app_env, tmp_path, EXAMPLE)
    fix = _by_key(app_env)[("FIX", "EBAYE")]
    assert (fix.latitude, fix.longitude) == (37.621, -122.379)
    assert fix.source == DataSource.IMPORTED
    assert fix.origin_file == str(tmp_path / "data.csv")


def test_valid_ndb_frequency_is_khz(app_env, tmp_path):
    _import(app_env, tmp_path, EXAMPLE)
    ndb = _by_key(app_env)[("NDB", "ABC")]
    assert isinstance(ndb, Ndb)
    assert (ndb.frequency_khz, ndb.range_nm, ndb.elevation_ft, ndb.name) == (375, 50, 50, "Example NDB")


def test_valid_vor_frequency_is_mhz(app_env, tmp_path):
    _import(app_env, tmp_path, EXAMPLE)
    vor = _by_key(app_env)[("VOR", "XYZ")]
    assert isinstance(vor, Vor)
    assert (vor.frequency_mhz, vor.range_nm, vor.slaved_variation_deg) == (113.2, 130, 0.0)


def test_valid_dme_paired_frequency_is_mhz(app_env, tmp_path):
    _import(app_env, tmp_path, EXAMPLE)
    dme = _by_key(app_env)[("DME", "XYZ")]
    assert isinstance(dme, Dme)
    assert (dme.paired_frequency_mhz, dme.range_nm, dme.bias_nm) == (113.2, 130, 0.0)


def test_names_get_the_same_type_suffix_as_manual_entry(app_env, tmp_path):
    _import(app_env, tmp_path, HEADER + "\nNDB,ABC,Example,37.5,-122.3,50,375,50\n")
    assert _by_key(app_env)[("NDB", "ABC")].name == "Example NDB"


def test_optional_columns(app_env, tmp_path):
    text = HEADER + ",slaved_variation_deg,bias_nm\n" \
        "VOR,XYZ,Example,37.6,-122.4,100,113.2,130,-14.5,\n" \
        "DME,XYZ,Example,37.6,-122.4,100,113.2,130,,0.5\n"
    _import(app_env, tmp_path, text)
    records = _by_key(app_env)
    assert records[("VOR", "XYZ")].slaved_variation_deg == -14.5
    assert records[("DME", "XYZ")].bias_nm == 0.5


def test_quoted_name_with_commas_and_whitespace(app_env, tmp_path):
    _import(app_env, tmp_path, HEADER + '\n NDB , abc ,  "Smith, Jones NDB" , 37.5 , -122.3 , 50 , 375 , 50 \n')
    assert _by_key(app_env)[("NDB", "ABC")].name == "Smith, Jones NDB"


def test_blank_optional_fields_for_fix(app_env, tmp_path):
    summary = _import(app_env, tmp_path, HEADER + "\nFIX,EBAYE,,37.621,-122.379,,,\n")
    assert summary.imported_count == 1
    assert summary.plan.warnings == []


# --- invalid rows -------------------------------------------------------------------

@pytest.mark.parametrize(
    "row, reason",
    [
        ("FIX,A,,north,-122.3,,,", "malformed latitude 'north'"),
        ("FIX,A,,37.5,,,,", "missing longitude"),
        ("FIX,A,,95,-122.3,,,", "Latitude must be between -90 and 90."),
        ("NDB,ABC,N,37.5,-122.3,50,abc,50", "malformed frequency 'abc'"),
        ("NDB,ABC,N,37.5,-122.3,50,375.5,50", "frequency must be a whole number kHz, got '375.5'"),
        ("NDB,ABC,N,37.5,-122.3,50,113,50", "NDB frequency should be between 190 and 1750 kHz."),
        ("VOR,XYZ,V,37.6,-122.4,100,375,130", "VOR frequency should be between 108.00 and 117.95 MHz."),
        ("VOR,XYZ,V,37.6,-122.4,100,,130", "missing frequency"),
        ("DME,XYZ,,37.6,-122.4,100,113.2,130", "missing name"),
        ("DME,XYZ,D,37.6,-122.4,,113.2,130", "missing elevation_ft"),
        ("VOR,XYZ,V,37.6,-122.4,100,113.2,nan", "malformed range_nm 'nan'"),
        ("ILS,IABC,Localizer,37.6,-122.4,100,110.3,18", "unknown type 'ILS' (expected FIX, NDB, VOR, DME)"),
        (",EBAYE,,37.6,-122.4,,,", "unknown type '(blank)' (expected FIX, NDB, VOR, DME)"),
        ("FIX,TOOLONGIDENT,,37.6,-122.4,,,", "Identifier must be 10 characters or fewer."),
    ],
)
def test_invalid_rows_report_row_number_and_reason(app_env, tmp_path, row, reason):
    summary = _import(app_env, tmp_path, EXAMPLE + row + "\n")
    [issue] = summary.plan.invalid
    assert (issue.line_number, issue.reason) == (6, reason)
    assert summary.imported_count == 4       # the bad row never aborts the rest


def test_mixed_valid_and_invalid_rows(app_env, tmp_path):
    text = f"""{HEADER}
FIX,GOOD1,,37.1,-122.1,,,
FIX,BAD1,,x,-122.1,,,
NDB,GD2,N,37.2,-122.2,0,400,25
NDB,BAD2,N,37.2,-122.2,0,99999,25
VOR,GD3,V,37.3,-122.3,0,110.4,40
TACAN,BAD3,T,37.3,-122.3,0,110.4,40
VOR,SHORT,row
"""
    summary = _import(app_env, tmp_path, text)
    assert summary.imported_count == 3
    assert sorted(i.line_number for i in summary.plan.invalid) == [3, 5, 7, 8]
    assert summary.plan.counts()["Invalid rows"] == 4


def test_missing_required_column_is_a_clear_error(app_env, tmp_path):
    with pytest.raises(UnrecognizedDatasetError, match="missing required column\\(s\\): longitude"):
        app_env["dataset_service"].analyze(_file(tmp_path, "type,ident,name,latitude\nFIX,A,,1\n"))


def test_undecodable_file_is_reported_not_crashed(app_env, tmp_path):
    path = tmp_path / "data.csv"
    path.write_bytes((HEADER + "\nNDB,ABC,Caf\xe9,1,2,0,375,50\n").encode("latin-1"))
    summary = app_env["dataset_service"].import_dataset(str(path))
    assert summary.imported_count == 0
    assert summary.plan.invalid[0].reason.startswith("not valid UTF-8")


# --- warnings ---------------------------------------------------------------------------

def test_values_a_type_does_not_have_are_ignored_with_a_warning(app_env, tmp_path):
    text = HEADER + ",slaved_variation_deg\n" \
        "FIX,EBAYE,,37.621,-122.379,,113.2,50,\n" \
        "NDB,ABC,N,37.5,-122.3,50,375,50,5\n"
    summary = _import(app_env, tmp_path, text)
    assert summary.imported_count == 2
    assert [(w.line_number, w.reason) for w in summary.plan.warnings] == [
        (2, "frequency ignored: FIX has no frequency"),
        (2, "range_nm ignored: FIX has no range nm"),
        (3, "slaved_variation_deg ignored: NDB has no slaved variation deg"),
    ]
    assert summary.plan.counts()["Warnings"] == 3


# --- duplicates ---------------------------------------------------------------------

def test_duplicate_import_is_skipped_and_counted(app_env, tmp_path):
    service = app_env["dataset_service"]
    service.import_dataset(_file(tmp_path, EXAMPLE))
    again = service.import_dataset(_file(tmp_path, EXAMPLE))
    assert again.imported_count == 0
    assert again.plan.counts()["Duplicates skipped"] == 4
    assert len(app_env["navaid_service"].list_all()) == 3


def test_duplicates_do_not_stop_the_rest_of_the_file(app_env, tmp_path):
    app_env["waypoint_service"].create("EBAYE", 37.621, -122.379)
    app_env["navaid_service"].create_ndb("ABC", "Example", 37.5, -122.3, 50, 375, 50)
    summary = _import(app_env, tmp_path, EXAMPLE + "FIX,NEWFX,,37.7,-122.5,,,\n")
    assert summary.plan.counts() == {
        "Imported": 3, "Duplicates skipped": 2, "Identifier conflicts": 0,
        "Invalid rows": 0, "Unsupported": 0, "Warnings": 0,
    }


def test_duplicate_rows_within_the_file_are_skipped(app_env, tmp_path):
    summary = _import(app_env, tmp_path, EXAMPLE + "FIX,EBAYE,EBAYE,37.621,-122.379,0,,\n")
    assert summary.imported_count == 4
    [dup] = summary.plan.existing
    assert dup.line_number == 6
    assert dup.reason.startswith("Exact duplicate of FIX EBAYE (earlier in this import)")


def test_same_identifier_different_type_is_not_a_duplicate(app_env, tmp_path):
    summary = _import(app_env, tmp_path, EXAMPLE)   # VOR XYZ and DME XYZ share everything but type
    assert summary.plan.existing == []
    assert {("VOR", "XYZ"), ("DME", "XYZ")} <= set(_by_key(app_env))


# --- TXT --------------------------------------------------------------------------

def test_txt_tab_separated(app_env, tmp_path):
    summary = _import(app_env, tmp_path, EXAMPLE.replace(",", "\t"), "data.txt")
    assert summary.imported_count == 4


def test_txt_comma_separated(app_env, tmp_path):
    assert _import(app_env, tmp_path, EXAMPLE, "data.txt").imported_count == 4


def test_txt_without_header(app_env, tmp_path):
    body = "\n".join(EXAMPLE.splitlines()[1:]).replace(",", "\t") + "\n"
    summary = _import(app_env, tmp_path, body, "data.txt")
    assert summary.imported_count == 4
    assert _by_key(app_env)[("NDB", "ABC")].frequency_khz == 375


def test_txt_mixed_valid_and_invalid_rows(app_env, tmp_path):
    text = EXAMPLE.replace(",", "\t") + "NDB\tBROKEN\n" + "VOR\tBAD\tV\t37\t-122\t0\t999\t40\n"
    summary = _import(app_env, tmp_path, text, "data.txt")
    assert summary.imported_count == 4
    assert [(i.line_number, i.reason) for i in summary.plan.invalid] == [
        (6, "expected 8 fields, found 2"),
        (7, "VOR frequency should be between 108.00 and 117.95 MHz."),
    ]


def test_undeterminable_txt_is_a_clear_error(app_env, tmp_path):
    with pytest.raises(UnrecognizedDatasetError, match="data.txt: not a recognized navigation data file"):
        app_env["dataset_service"].analyze(_file(tmp_path, "some notes about a flight\n", "data.txt"))
    with pytest.raises(UnrecognizedDatasetError, match="data.txt: not a recognized navigation data file"):
        app_env["dataset_service"].analyze(_file(
            tmp_path,
            "type ident name latitude longitude frequency range_nm\n"
            "NDB ABC Big Bear 37.5 -122.3 375 50\nVOR XYZ Palo Alto 37.6 -122.4 113.2 130\n",
            "data.txt",
        ))


# --- export ----------------------------------------------------------------------

def test_imported_table_records_are_exported(app_env, tmp_path):
    _import(app_env, tmp_path, EXAMPLE)
    assert "37.62100000 -122.37900000 EBAYE" in config.FIX_DAT_OUTPUT.read_text()
    nav = config.NAV_DAT_OUTPUT.read_text()
    assert "2 37.50000000 -122.30000000 50 375 50 0.0 ABC Example NDB" in nav
    assert "3 37.60000000 -122.40000000 100 11320 130 0.000 XYZ Example VOR" in nav
    assert "13 37.60000000 -122.40000000 100 11320 130 0.000 XYZ Example DME" in nav


# --- this cycle: fix lists, navaid tables without type/elevation ------------------------

def test_fix_csv_with_header_and_no_type(app_env, tmp_path):
    summary = _import(app_env, tmp_path, "ident,latitude,longitude\nEBAYE,37.123,-122.456\n")
    assert summary.plan.counts("FIX")["Imported"] == 1
    assert _by_key(app_env)[("FIX", "EBAYE")].latitude == 37.123


def test_fix_csv_with_optional_name(app_env, tmp_path):
    summary = _import(app_env, tmp_path, "ident,name,latitude,longitude\nEBAYE,Bay point,37.123,-122.456\n")
    assert summary.imported_count == 1
    assert summary.plan.warnings == []      # a fix name is documented as ignored


def test_navaid_csv_in_the_short_format(app_env, tmp_path):
    text = """type,ident,name,latitude,longitude,frequency,range_nm
NDB,ABC,Example NDB,37.5,-122.3,375,50
VOR,XYZ,Example VOR,37.6,-122.4,113.2,130
DME,XYZ,Example DME,37.6,-122.4,113.2,130
"""
    summary = _import(app_env, tmp_path, text)
    records = _by_key(app_env)
    assert records[("NDB", "ABC")].frequency_khz == 375                 # kHz
    assert records[("VOR", "XYZ")].frequency_mhz == 113.2               # MHz
    assert records[("DME", "XYZ")].paired_frequency_mhz == 113.2        # MHz
    assert {r.elevation_ft for k, r in records.items() if k[0] != "FIX"} == {0}
    [warning] = summary.plan.warnings
    assert warning.reason == "no elevation_ft column: navaids were given 0 ft, the Add NAV form's default"
    assert summary.plan.counts()["Warnings"] == 1


def test_navaid_table_without_type_asks_which(app_env, tmp_path):
    from flightgear_navdata_manager.application.dataset_import import RecordTypeNeededError

    path = _file(tmp_path, "ident,name,latitude,longitude,frequency,range_nm\nXYZ,Example,37.6,-122.4,113.2,130\n")
    with pytest.raises(RecordTypeNeededError) as info:
        app_env["dataset_service"].analyze(path)
    assert info.value.choices == ("NDB", "VOR", "DME")
    assert app_env["navaid_service"].list_all() == []
    summary = app_env["dataset_service"].import_dataset(path, record_type="VOR")
    assert summary.imported_count == 1
    assert _by_key(app_env)[("VOR", "XYZ")].frequency_mhz == 113.2


def test_chosen_type_still_validates_units(app_env, tmp_path):
    path = _file(tmp_path, "ident,name,latitude,longitude,frequency,range_nm\nXYZ,Example,37.6,-122.4,113.2,130\n")
    summary = app_env["dataset_service"].import_dataset(path, record_type="NDB")   # 113.2 is not kHz
    assert summary.imported_count == 0
    assert summary.plan.invalid[0].reason == "frequency must be a whole number kHz, got '113.2'"


def test_untyped_navaid_table_in_a_folder_is_left_out_with_a_reason(app_env, tmp_path):
    (tmp_path / "navaids.csv").write_text("ident,name,latitude,longitude,frequency,range_nm\nXYZ,E,37.6,-122.4,113.2,130\n")
    (tmp_path / "fixes.csv").write_text("ident,latitude,longitude\nEBAYE,37.1,-122.4\n")
    plan = app_env["dataset_service"].analyze(str(tmp_path))
    assert [c.record.ident for c in plan.to_import] == ["EBAYE"]
    assert dict(plan.ignored)["navaids.csv"].startswith("a table of navaids with no type column")


def test_whitespace_txt_with_comments(app_env, tmp_path):
    text = """# my navaids
type ident name latitude longitude frequency range_nm

NDB ABC "Example NDB" 37.5 -122.3 375 50
# a VOR
VOR XYZ "Example VOR" 37.6 -122.4 113.2 130
VOR BAD Unquoted Name 37.6 -122.4 113.2 130
"""
    summary = _import(app_env, tmp_path, text, "navaids.txt")
    assert summary.imported_count == 2
    assert [(i.line_number, i.reason) for i in summary.plan.invalid] == [
        (7, "expected 7 fields, found 8 (quote names that contain spaces)"),
    ]


@pytest.mark.parametrize(
    "existing, row",
    [
        (("create_ndb", "ABC", "Mine", 37.5, -122.3, 50, 375, 50), "NDB,ABC,Theirs,37.5,-122.3,375,50"),
        (("create_vor", "XYZ", "Mine", 37.6, -122.4, 100, 113.2, 130), "VOR,XYZ,Theirs,37.6,-122.4,113.2,130"),
        (("create_dme", "XYZ", "Mine", 37.6, -122.4, 100, 113.2, 130), "DME,XYZ,Theirs,37.6,-122.4,113.2,130"),
    ],
)
def test_duplicate_navaids_are_skipped_and_existing_preserved(app_env, tmp_path, existing, row):
    ns = app_env["navaid_service"]
    method, *args = existing
    mine = getattr(ns, method)(*args)
    summary = _import(app_env, tmp_path, "type,ident,name,latitude,longitude,frequency,range_nm\n" + row + "\n")
    assert summary.imported_count == 0
    [dup] = summary.plan.existing
    assert dup.line_number == 2
    assert dup.reason.startswith(f"Exact duplicate of {mine.type.value} {mine.ident} (custom)")
    [stored] = ns.list_all()
    assert (stored.id, stored.name, stored.elevation_ft) == (mine.id, mine.name, mine.elevation_ft)
