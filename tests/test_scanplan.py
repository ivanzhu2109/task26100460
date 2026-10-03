"""扫描计划库自动化测试。"""

from datetime import datetime, timedelta, timezone

import pytest

from scanplan import ScanKind, ScanPlanner

UTC = timezone.utc
NEVER_CRON = "0 0 30 2 *"  # 2月30日，永不触发


def utc(month, day, hour=0, minute=0, year=2026):
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def make_planner(timezone_name, quick_cron, full_cron, base):
    planner = ScanPlanner()
    planner.register_policy("p", timezone_name, quick_cron, full_cron, base)
    return planner


def test_spring_forward_missing_minute():
    """春季跳时：不存在的本地分钟不触发也不补跑。"""
    # 2026-03-08 02:30 在 America/New_York 不存在（02:00 -> 03:00）
    planner = make_planner(
        "America/New_York", "30 2 * * *", NEVER_CRON, utc(3, 7, 12)
    )
    events = planner.query("p", utc(3, 8), utc(3, 10))
    assert [(e.time, e.kind) for e in events] == [
        (utc(3, 9, 6, 30), ScanKind.QUICK),  # 3/9 02:30 EDT = 06:30 UTC
    ]


def test_fall_back_repeated_hour_ordering():
    """秋季回拨：重复小时内的多个扫描时刻按 UTC 严格递增。"""
    # 2026-11-01 01:00-01:59 在 America/New_York 出现两次
    planner = make_planner(
        "America/New_York", "0,30 1 * * *", NEVER_CRON, utc(10, 31, 12)
    )
    events = planner.query("p", utc(11, 1, 4), utc(11, 1, 8))
    assert [(e.time, e.kind) for e in events] == [
        (utc(11, 1, 5, 0), ScanKind.QUICK),   # 01:00 EDT
        (utc(11, 1, 5, 30), ScanKind.QUICK),  # 01:30 EDT
        (utc(11, 1, 6, 0), ScanKind.QUICK),   # 01:00 EST
        (utc(11, 1, 6, 30), ScanKind.QUICK),  # 01:30 EST
    ]
    times = [e.time for e in events]
    assert all(b > a for a, b in zip(times, times[1:]))


@pytest.fixture
def merge_planner():
    # 快速扫描每日 00:00 与 12:00；完整 cron 为 1/5 与 1/12 的 12:00。
    # 基准 1/1 00:00 -> 期限 1/8 00:00；1/5 12:00 的提前完整扫描把期限推迟到
    # 1/12 12:00，该时刻快速 cron、完整 cron、强制期限三者重合。
    return make_planner(
        "UTC", "0 0,12 * * *", "0 12 5,12 1 *", utc(1, 1)
    ), (utc(1, 1), utc(1, 22))


def test_early_full_scan_postpones_deadline(merge_planner):
    planner, (start, end) = merge_planner
    events = planner.query("p", start, end)
    fulls = [e.time for e in events if e.kind is ScanKind.FULL]
    assert fulls == [utc(1, 5, 12), utc(1, 12, 12), utc(1, 19, 12)]


def test_triple_overlap_merges_into_single_full(merge_planner):
    planner, (start, end) = merge_planner
    events = planner.query("p", start, end)
    at_noon_12th = [e for e in events if e.time == utc(1, 12, 12)]
    assert len(at_noon_12th) == 1
    assert at_noon_12th[0].kind is ScanKind.FULL
    times = [e.time for e in events]
    assert len(times) == len(set(times))  # 同一时刻最多一次扫描


def test_full_scan_gap_never_exceeds_seven_days(merge_planner):
    planner, (start, end) = merge_planner
    events = planner.query("p", start, end)
    fulls = [utc(1, 1)] + [e.time for e in events if e.kind is ScanKind.FULL]
    for prev, cur in zip(fulls, fulls[1:]):
        assert cur - prev <= timedelta(days=7)


@pytest.mark.parametrize("split", [utc(1, 12, 12), utc(1, 12, 11, 59), utc(1, 13, 7)])
def test_split_query_concatenation_matches_merged(merge_planner, split):
    planner, (start, end) = merge_planner
    merged = planner.query("p", start, end)
    left = planner.query("p", start, split)
    right = planner.query("p", split, end)
    assert left + right == merged
    # 重复查询结果一致
    assert planner.query("p", start, end) == merged


def test_out_of_window_full_scan_still_bounds_deadline(merge_planner):
    """区间外的完整扫描仍影响区间内期限；区间起点不成为新基准。"""
    planner, _ = merge_planner
    events = planner.query("p", utc(1, 12), utc(1, 22))
    fulls = [e.time for e in events if e.kind is ScanKind.FULL]
    # 1/5 的完整扫描在区间外，但期限仍从它起算：1/12 12:00 强制触发
    assert fulls == [utc(1, 12, 12), utc(1, 19, 12)]


def test_no_events_before_base_time(merge_planner):
    planner, _ = merge_planner
    events = planner.query("p", utc(1, 1) - timedelta(days=2), utc(1, 2))
    assert events[0].time == utc(1, 1, 12)  # 基准时刻本身不产生扫描
    assert all(e.time > utc(1, 1) for e in events)


def test_forced_full_scans_continue_without_cron_matches():
    """两条 cron 都无匹配日期时，仍持续生成到期的强制完整扫描。"""
    planner = make_planner("UTC", NEVER_CRON, NEVER_CRON, utc(1, 1))
    events = planner.query("p", utc(1, 1), utc(1, 30))
    assert [(e.time, e.kind) for e in events] == [
        (utc(1, 8), ScanKind.FULL),
        (utc(1, 15), ScanKind.FULL),
        (utc(1, 22), ScanKind.FULL),
        (utc(1, 29), ScanKind.FULL),
    ]
