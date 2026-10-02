"""Import outcome rules: Already exists vs Identifier conflict vs Imported."""

from ._faa import FIX_CSV, NAV_CSV, NAV_TXT, csv_table, nav1, write_csv, write_lines

# QXALL (FIX_BASE sample) is at 33.12018888, -60.14176111
QXALL = (33.12018888, -60.14176111)
# QET VORTAC (NAV sample) is at 51.78483694, -150.82433
QET = (186425.413 / 3600, -542967.587 / 3600)


def _only(summary, outcome, category):
    return summary.plan.counts(category)[outcome]


# --- FIX --------------------------------------------------------------------------

def test_same_fix_same_place_already_exists(app_env):
    app_env["waypoint_service"].create("QXALL", QXALL[0] + 0.001, QXALL[1])   # ~0.06 nm off
    plan = app_env["dataset_service"].analyze(str(FIX_CSV))
    assert plan.counts("FIX")["Duplicates skipped"] == 1
    assert plan.existing[0].reason.startswith(
        "Nearby duplicate of FIX QXALL (custom) at 33.121189, -60.141761 -- 0.1 nm away"
    )


def test_same_fix_ident_materially_different_location_is_a_conflict(app_env):
    ws = app_env["waypoint_service"]
    mine = ws.create("QXALL", 33.70, -60.14)                                  # ~35 nm north
    summary = app_env["dataset_service"].import_dataset(str(FIX_CSV))

    assert _only(summary, "Identifier conflicts", "FIX") == 1
    reason = summary.plan.conflicts[0].reason
    assert reason == (
        "Identifier conflict: FIX QXALL (custom) at 33.700000, -60.140000 -- 34.8 nm away; "
        "this record is at 33.120189, -60.141761"
    )
    # Neither record is lost or changed: the user's stays, FAA's isn't added.
    qxall = [f for f in ws.list_all() if f.ident == "QXALL"]
    assert len(qxall) == 1
    assert (qxall[0].id, qxall[0].latitude, qxall[0].source) == (mine.id, 33.70, mine.source)


def test_same_fix_ident_far_away_is_a_different_fix(app_env):
    app_env["waypoint_service"].create("QXALL", 10.0, 10.0)
    summary = app_env["dataset_service"].import_dataset(str(FIX_CSV))
    assert _only(summary, "Imported", "FIX") == 6
    assert len([f for f in app_env["waypoint_service"].list_all() if f.ident == "QXALL"]) == 2


def test_disabled_conflicting_record_lets_the_new_one_in(app_env):
    ws = app_env["waypoint_service"]
    old = ws.create("QXALL", 42.70, -60.14)
    ws.set_enabled(old.id, False)
    summary = app_env["dataset_service"].import_dataset(str(FIX_CSV))
    assert _only(summary, "Identifier conflicts", "FIX") == 0
    assert _only(summary, "Imported", "FIX") == 6


def test_disabled_equivalent_record_is_not_resurrected(app_env):
    service = app_env["dataset_service"]
    ws = app_env["waypoint_service"]
    service.import_dataset(str(FIX_CSV))
    qxall = next(f for f in ws.list_all() if f.ident == "QXALL")
    ws.set_enabled(qxall.id, False)

    again = service.import_dataset(str(FIX_CSV))
    assert again.imported_count == 0
    assert any(
        i.reason.startswith("Exact duplicate of FIX QXALL (imported, disabled)") for i in again.plan.existing
    )
    assert next(f for f in ws.list_all() if f.ident == "QXALL").enabled is False


def test_reimport_of_whole_dataset_creates_nothing(app_env):
    service = app_env["dataset_service"]
    service.import_dataset(str(FIX_CSV))
    service.import_dataset(str(NAV_CSV))
    fixes, navaids = len(app_env["waypoint_service"].list_all()), len(app_env["navaid_service"].list_all())
    for path in (FIX_CSV, NAV_CSV):
        assert service.import_dataset(str(path)).imported_count == 0
    assert len(app_env["waypoint_service"].list_all()) == fixes
    assert len(app_env["navaid_service"].list_all()) == navaids


# --- NAV --------------------------------------------------------------------------

def test_duplicate_navaid_already_exists(app_env):
    app_env["navaid_service"].create_vor("QET", "MY TESTER", *QET, 100, 114.10, 130)
    plan = app_env["dataset_service"].analyze(str(NAV_CSV))
    assert any(i.reason.startswith("Exact duplicate of VOR QET (custom)") for i in plan.existing)
    # The DME half is a different navaid type, so it is imported.
    assert ("DME", "QET") in {(c.record.type.value, c.record.ident) for c in plan.to_import}


def test_same_navaid_position_different_frequency_is_a_conflict(app_env):
    # e.g. a VOR whose frequency FAA has since changed
    app_env["navaid_service"].create_vor("QET", "OLD TESTER", *QET, 100, 110.20, 130)
    plan = app_env["dataset_service"].analyze(str(NAV_CSV))
    [conflict] = plan.conflicts
    assert conflict.reason == (
        "Identifier conflict: VOR QET (custom) at 51.784837, -150.824330, 110.20 MHz -- 0.0 nm away; "
        "this record is at 51.784837, -150.824330, 114.10 MHz"
    )


def test_same_navaid_ident_nearby_different_place_is_a_conflict(app_env):
    app_env["navaid_service"].create_ndb("QNI", "SOMEWHERE", 52.90, -148.60, 0, 359, 50)  # ~19 nm
    plan = app_env["dataset_service"].analyze(str(NAV_CSV))
    assert [c.label for c in plan.conflicts] == ["QNI NDB (Bravo, AK)"]


def test_same_navaid_ident_far_away_is_imported(app_env):
    app_env["navaid_service"].create_ndb("QNI", "FAR AWAY", 40.0, -100.0, 0, 359, 50)
    plan = app_env["dataset_service"].analyze(str(NAV_CSV))
    assert plan.conflicts == []
    assert ("NDB", "QNI") in {(c.record.type.value, c.record.ident) for c in plan.to_import}


def test_same_ident_different_navaid_type_is_unrelated(app_env):
    app_env["navaid_service"].create_ndb("QET", "TESTER BEACON", *QET, 100, 300, 50)
    plan = app_env["dataset_service"].analyze(str(NAV_CSV))
    assert plan.conflicts == [] and plan.existing == []


def test_repeats_within_one_import_are_detected(app_env, tmp_path):
    summary = app_env["dataset_service"].import_dataset(
        write_lines(tmp_path / "NAV.txt", [nav1("QNI"), nav1("QNI")])
    )
    assert summary.imported_count == 1
    [repeat] = summary.plan.existing
    assert repeat.reason.startswith("Exact duplicate of NDB QNI (earlier in this import)")
    assert repeat.line_number == 2


def test_existing_records_are_never_modified(app_env):
    ns = app_env["navaid_service"]
    mine = ns.create_vor("QET", "MINE", *QET, 100, 110.20, 130)
    app_env["dataset_service"].import_dataset(str(NAV_TXT))
    stored = next(n for n in ns.list_all() if n.id == mine.id)
    assert (stored.name, stored.frequency_mhz, stored.enabled) == ("MINE VOR", 110.20, True)
