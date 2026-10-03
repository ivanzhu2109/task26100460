"""Cron 表达式解析与本地时刻匹配。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class CronField:
    """单个 cron 字段：取值集合 + 是否为单独的星号。"""

    values: frozenset
    lone_star: bool


@dataclass(frozen=True)
class CronExpr:
    """五字段 cron：分钟 小时 日 月 星期。"""

    minute: CronField
    hour: CronField
    day_of_month: CronField
    month: CronField
    day_of_week: CronField

    @classmethod
    def parse(cls, text: str) -> "CronExpr":
        parts = text.split()
        if len(parts) != 5:
            raise ValueError(f"cron 表达式必须包含 5 个字段: {text!r}")
        ranges = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 6))
        fields = [
            _parse_field(part, lo, hi) for part, (lo, hi) in zip(parts, ranges)
        ]
        return cls(*fields)

    def day_matches(self, day: date) -> bool:
        dom_star = self.day_of_month.lone_star
        dow_star = self.day_of_week.lone_star
        if dom_star and dow_star:
            return True
        dom_ok = day.day in self.day_of_month.values
        # date.weekday(): 周一=0..周日=6，转换为周日=0..周六=6
        dow_ok = (day.weekday() + 1) % 7 in self.day_of_week.values
        if dom_star:
            return dow_ok
        if dow_star:
            return dom_ok
        return dom_ok or dow_ok

    def matches_local(self, naive: datetime) -> bool:
        return (
            naive.minute in self.minute.values
            and naive.hour in self.hour.values
            and naive.month in self.month.values
            and self.day_matches(naive.date())
        )


def _parse_field(text: str, lo: int, hi: int) -> CronField:
    values = set()
    for item in text.split(","):
        if not item:
            raise ValueError(f"空的 cron 字段项: {text!r}")
        values.update(_parse_item(item, lo, hi))
    return CronField(values=frozenset(values), lone_star=(text == "*"))


def _parse_item(item: str, lo: int, hi: int) -> range:
    if "/" in item:
        base, step_text = item.split("/", 1)
        step = int(step_text)
        if step <= 0:
            raise ValueError(f"步长必须为正整数: {item!r}")
    else:
        base, step = item, 1
    if base == "*":
        start, end = lo, hi
    elif "-" in base:
        start_text, end_text = base.split("-", 1)
        start, end = int(start_text), int(end_text)
    else:
        start = end = int(base)
    if not (lo <= start <= end <= hi):
        raise ValueError(f"cron 字段项越界 [{lo},{hi}]: {item!r}")
    return range(start, end + 1, step)
