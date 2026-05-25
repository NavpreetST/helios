from datetime import datetime, timezone

from aegis.renderer._quota import _today_pacific


def test_mid_pdt_utc_midnight_maps_to_previous_pt_day():
    assert _today_pacific(datetime(2026, 5, 25, 0, 30, tzinfo=timezone.utc)) == "2026-05-24"


def test_dst_forward_day_uses_named_zone():
    assert _today_pacific(datetime(2026, 3, 8, 9, 30, tzinfo=timezone.utc)) == "2026-03-08"
    assert _today_pacific(datetime(2026, 3, 8, 10, 30, tzinfo=timezone.utc)) == "2026-03-08"


def test_dst_back_day_uses_named_zone():
    assert _today_pacific(datetime(2026, 11, 1, 8, 30, tzinfo=timezone.utc)) == "2026-11-01"
    assert _today_pacific(datetime(2026, 11, 1, 9, 30, tzinfo=timezone.utc)) == "2026-11-01"
