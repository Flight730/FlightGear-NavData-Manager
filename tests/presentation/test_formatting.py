from datetime import datetime, timedelta

from flightgear_navdata_manager.presentation.formatting import relative_time

NOW = datetime(2026, 10, 2, 14, 30)


def test_relative_time():
    assert relative_time(NOW - timedelta(seconds=20), NOW) == "just now"
    assert relative_time(NOW - timedelta(minutes=5), NOW) == "5 min ago"
    assert relative_time(datetime(2026, 10, 2, 9, 5), NOW) == "today at 09:05"
    assert relative_time(datetime(2026, 10, 1, 22, 15), NOW) == "yesterday at 22:15"
    assert relative_time(datetime(2026, 9, 28, 8, 0), NOW) == "2026-09-28 08:00"
    assert relative_time(NOW + timedelta(minutes=3), NOW) == "today at 14:33"
