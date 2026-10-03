"""cron 字段语义：步长、并集、日/星期组合规则。"""
from datetime import datetime, timezone

from scanplan import CronExpression, ScanScheduler, ScanType

UTC = timezone.utc


def dt(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


def test_step_and_union_parsing():
    c = CronExpression.parse("5-25/10 0 1 * *")
    assert c.minute.values == frozenset({5, 15, 25})
    c2 = CronExpression.parse("*/20 * * * *")
    assert c2.minute.values == frozenset({0, 20, 40})
    assert not c2.minute.is_plain_star  # 带步长不视为单独的星号


def test_dom_dow_or_semantics():
    # 日和星期都不是单独的星号：满足任意一项即可
    c = CronExpression.parse("0 0 15 * 1")
    assert c.matches(datetime(2026, 1, 15))  # 15号（周四），dom 匹配
    assert c.matches(datetime(2026, 1, 12))  # 周一，dow 匹配
    assert not c.matches(datetime(2026, 1, 14))
    # 只有一项是单独的星号：仅检查另一项
    c2 = CronExpression.parse("0 0 * * 1")
    assert c2.matches(datetime(2026, 1, 12))
    assert not c2.matches(datetime(2026, 1, 15))
    # 两项都是单独的星号：不限制日期
    c3 = CronExpression.parse("0 0 * * *")
    assert c3.matches(datetime(2026, 1, 14))


def test_stepped_dom_is_not_plain_star():
    # "*/2" 不视为单独的星号：与星期组合时按 OR 处理
    c = CronExpression.parse("0 0 */2 * 1")  # dom 从 1 起算：1,3,5,...,31
    assert c.matches(datetime(2026, 1, 12))  # 周一，dow 匹配
    assert c.matches(datetime(2026, 1, 3))   # 3号（周六），dom 匹配
    assert not c.matches(datetime(2026, 1, 8))  # 8号周四，均不匹配


def test_nonexistent_date_never_triggers():
    s = ScanScheduler()
    s.register_policy("feb31", "UTC", "0 0 31 2 *", "0 0 31 2 *", dt(2026, 1, 1))
    events = s.plan("feb31", dt(2026, 1, 1), dt(2026, 1, 22))
    assert all(e.scan_type is ScanType.FULL for e in events)
    assert [e.at for e in events] == [dt(2026, 1, 8), dt(2026, 1, 15)]


def test_full_scan_before_window_affects_deadline_inside():
    # 窗口起点不是新基准：1月8日的完整扫描推迟窗口内的强制期限
    s = ScanScheduler()
    s.register_policy("anchor", "UTC", "0 0 31 2 *", "0 12 8 1 *", dt(2026, 1, 5))
    events = s.plan("anchor", dt(2026, 1, 10), dt(2026, 1, 20))
    assert [(e.at, e.scan_type) for e in events] == [
        (dt(2026, 1, 15, 12), ScanType.FULL),  # 自1月8日12:00起算，而非窗口起点
    ]
