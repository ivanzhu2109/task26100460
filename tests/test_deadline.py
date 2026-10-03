"""强制完整扫描期限：推迟、同刻合并、窗口切分一致性。"""
from datetime import datetime, timedelta, timezone

from scanplan import FULL_SCAN_INTERVAL, ScanScheduler, ScanType

UTC = timezone.utc
NEVER_CRON = "0 0 31 2 *"  # 永不触发


def dt(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


def assert_plan_invariants(events, baseline):
    """严格递增、无重复、完整扫描间隔不超过 7*24 小时（含基准时刻）。"""
    timestamps = [e.at for e in events]
    assert all(a < b for a, b in zip(timestamps, timestamps[1:]))
    fulls = [baseline] + [e.at for e in events if e.scan_type is ScanType.FULL]
    assert all(b - a <= FULL_SCAN_INTERVAL for a, b in zip(fulls, fulls[1:]))


def test_early_full_scan_postpones_deadline():
    # 基准为周一 2026-01-05 00:00 UTC；1月8日中午的 cron 完整扫描
    # 把原本 1月12日 00:00 的强制期限推迟到 1月15日 12:00。
    s = ScanScheduler()
    s.register_policy("postpone", "UTC", NEVER_CRON, "0 12 8 1 *", dt(2026, 1, 5))
    events = s.plan("postpone", dt(2026, 1, 5), dt(2026, 1, 20))
    assert [(e.at, e.scan_type) for e in events] == [
        (dt(2026, 1, 8, 12), ScanType.FULL),   # cron 完整扫描，重新起算期限
        (dt(2026, 1, 15, 12), ScanType.FULL),  # 新的强制期限到期
    ]
    assert_plan_invariants(events, dt(2026, 1, 5))


def test_triple_coincidence_merges_into_one_full_scan():
    # 快速 cron 每日 00:00，完整 cron 每周一 00:00，基准周一 2026-01-05 00:00 UTC。
    # 1月12日 00:00：快速、完整、强制期限三者重合，只保留一次完整扫描。
    s = ScanScheduler()
    s.register_policy("merge", "UTC", "0 0 * * *", "0 0 * * 1", dt(2026, 1, 5))
    events = s.plan("merge", dt(2026, 1, 5), dt(2026, 1, 20))
    at_jan12 = [e for e in events if e.at == dt(2026, 1, 12)]
    assert at_jan12 == [type(events[0])(at=dt(2026, 1, 12), scan_type=ScanType.FULL)]
    # 期限从 1月12日 重新起算：1月19日（周一）再次三者重合为一次完整扫描
    at_jan19 = [e for e in events if e.at == dt(2026, 1, 19)]
    assert len(at_jan19) == 1 and at_jan19[0].scan_type is ScanType.FULL
    # 期间每日 00:00 为快速扫描
    quicks = [e.at for e in events if e.scan_type is ScanType.QUICK]
    assert quicks == [dt(2026, 1, d) for d in range(6, 12)] + \
                     [dt(2026, 1, d) for d in range(13, 19)]
    assert_plan_invariants(events, dt(2026, 1, 5))


def test_split_windows_concat_equals_merged():
    s = ScanScheduler()
    s.register_policy("split", "UTC", "30 6 * * *", NEVER_CRON, dt(2026, 1, 5))
    begin, finish = dt(2026, 1, 5), dt(2026, 1, 26)
    deadline = dt(2026, 1, 12)  # 强制期限恰好落在切分点上
    merged = s.plan("split", begin, finish)

    # 在期限处切分；也在期限前后各 1 分钟处切分
    cuts = [begin, deadline, finish]
    pieces = [s.plan("split", a, b) for a, b in zip(cuts, cuts[1:])]
    assert sum(pieces, []) == merged

    cuts2 = [begin, deadline - timedelta(minutes=1),
             deadline + timedelta(minutes=1), finish]
    pieces2 = [s.plan("split", a, b) for a, b in zip(cuts2, cuts2[1:])]
    assert sum(pieces2, []) == merged

    # 查询顺序与重复查询不改变结果
    again = s.plan("split", begin, deadline)
    assert again == pieces[0] == s.plan("split", begin, deadline)
    assert s.plan("split", deadline, finish) == pieces[1]

    # 无重复时刻，完整扫描间隔（含基准）不超过 7*24 小时
    assert_plan_invariants(merged, dt(2026, 1, 5))
    assert deadline in [e.at for e in merged]  # 强制完整扫描落在期限时刻


def test_no_cron_match_still_forces_full_scans():
    # 两条 cron 都无可匹配日期，仍持续生成到期的强制完整扫描
    s = ScanScheduler()
    s.register_policy("forced", "America/New_York", NEVER_CRON, NEVER_CRON,
                      dt(2026, 3, 1, 12, 0))
    events = s.plan("forced", dt(2026, 3, 1, 12, 0), dt(2026, 4, 1, 0, 0))
    assert [e.at for e in events] == [
        dt(2026, 3, 8, 12), dt(2026, 3, 15, 12),
        dt(2026, 3, 22, 12), dt(2026, 3, 29, 12),
    ]
    assert all(e.scan_type is ScanType.FULL for e in events)
    assert_plan_invariants(events, dt(2026, 3, 1, 12, 0))
