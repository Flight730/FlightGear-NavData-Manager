from datetime import datetime, timezone

from flightgear_navdata_manager.application.navaid_service import build_ndb
from flightgear_navdata_manager.domain.models import DataSource, Fix
from flightgear_navdata_manager.infrastructure.storage.db import connect
from flightgear_navdata_manager.infrastructure.storage.fix_repository import FixRepository
from flightgear_navdata_manager.infrastructure.storage.navaid_repository import NavaidRepository


def _fix(ident: str, enabled: bool = True) -> Fix:
    return Fix(id=None, source=DataSource.CUSTOM, enabled=enabled,
               created_at=datetime.now(timezone.utc), ident=ident, latitude=1.0, longitude=2.0)


def test_counts_include_disabled_records_and_follow_deletes():
    conn = connect(":memory:")
    fixes, navaids = FixRepository(conn), NavaidRepository(conn)
    assert fixes.count() == 0 and navaids.count() == 0

    first = fixes.add(_fix("CNTA"))
    fixes.add(_fix("CNTB", enabled=False))
    navaids.add(build_ndb("CNT", "Count", 1.0, 2.0, 0, 375, 50))
    assert fixes.count() == 2
    assert navaids.count() == 1

    fixes.delete(first.id)
    assert fixes.count() == 1
