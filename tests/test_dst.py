"""America/New_York 夏令时场景：春季缺失分钟与秋季重复小时。"""
from datetime import datetime, timezone

from scanplan import ScanScheduler, ScanType

UTC = timezone.utc
NEVER_CRON = "0 0 31 2 *"  # 2月31日，永不触发


def dt(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


def test_spring_forward_missing_minute_not_triggered():
    # 2026-03-08 02:00-02:59 本地时间不存在（EST->EDT）
    s = ScanScheduler()
    s.register_policy("spring", "America/New_York", "30 2 * * *", NEVER_CRON,
                      dt(2026, 3, 7, 0, 0))
    events = s.plan("spring", dt(2026, 3, 7, 0, 0), dt(2026, 3, 10, 0, 0))
    assert [(e.at, e.scan_type) for e in events] == [
        (dt(2026, 3, 7, 7, 30), ScanType.QUICK),   # 02:30 EST = 07:30 UTC
        (dt(2026, 3, 9, 6, 30), ScanType.QUICK),   # 02:30 EDT = 06:30 UTC
    ]


def test_spring_forward_no_makeup_run():
    # 缺失分钟不补跑：3月8日全天无任何扫描
    s = ScanScheduler()
    s.register_policy("spring2", "America/New_York", "0,30 2 * * *", NEVER_CRON,
                      dt(2026, 3, 7, 0, 0))
    events = s.plan("spring2", dt(2026, 3, 8, 0, 0), dt(2026, 3, 9, 0, 0))
    assert events == []


def test_fall_back_repeated_hour_fires_twice():
    # 2026-11-01 01:00-01:59 本地时间出现两次（EDT->EST）
    s = ScanScheduler()
    s.register_policy("fall", "America/New_York", "15,45 1 * * *", "0 3 * * 0",
                      dt(2026, 10, 31, 0, 0))
    events = s.plan("fall", dt(2026, 11, 1, 0, 0), dt(2026, 11, 2, 0, 0))
    assert [(e.at, e.scan_type) for e in events] == [
        (dt(2026, 11, 1, 5, 15), ScanType.QUICK),  # 01:15 EDT
        (dt(2026, 11, 1, 5, 45), ScanType.QUICK),  # 01:45 EDT
        (dt(2026, 11, 1, 6, 15), ScanType.QUICK),  # 01:15 EST（重复小时第二次）
        (dt(2026, 11, 1, 6, 45), ScanType.QUICK),  # 01:45 EST
        (dt(2026, 11, 1, 8, 0), ScanType.FULL),    # 周日 03:00 EST
    ]
    # UTC 时刻严格递增
    timestamps = [e.at for e in events]
    assert all(a < b for a, b in zip(timestamps, timestamps[1:]))
