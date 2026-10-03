"""Cron 五字段表达式解析与匹配。

字段顺序：分 时 日 月 星期。支持数字、星号、逗号并集、闭区间，
以及附在星号或闭区间后的正整数步长（从范围下界起算）。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class FieldSpec:
    """单个 cron 字段的解析结果。"""

    values: frozenset[int]
    is_plain_star: bool


def _parse_field(text: str, lo: int, hi: int) -> FieldSpec:
    is_plain_star = text == "*"
    values: set[int] = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            raise ValueError(f"空的 cron 片段: {text!r}")
        if "/" in part:
            base, step_text = part.split("/", 1)
            step = int(step_text)
            if step <= 0:
                raise ValueError(f"步长必须为正整数: {part!r}")
        else:
            base, step = part, 1
        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            start_text, end_text = base.split("-", 1)
            start, end = int(start_text), int(end_text)
            if start > end:
                raise ValueError(f"区间下界大于上界: {part!r}")
        else:
            start = end = int(base)
        if start < lo or end > hi:
            raise ValueError(f"cron 字段越界 [{lo},{hi}]: {part!r}")
        values.update(range(start, end + 1, step))
    return FieldSpec(values=frozenset(values), is_plain_star=is_plain_star)


@dataclass(frozen=True)
class CronExpression:
    """五字段 cron 表达式：分 时 日 月 星期。"""

    minute: FieldSpec
    hour: FieldSpec
    day_of_month: FieldSpec
    month: FieldSpec
    day_of_week: FieldSpec

    @classmethod
    def parse(cls, text: str) -> "CronExpression":
        fields = text.split()
        if len(fields) != 5:
            raise ValueError(f"cron 表达式必须有 5 个字段: {text!r}")
        return cls(
            minute=_parse_field(fields[0], 0, 59),
            hour=_parse_field(fields[1], 0, 23),
            day_of_month=_parse_field(fields[2], 1, 31),
            month=_parse_field(fields[3], 1, 12),
            day_of_week=_parse_field(fields[4], 0, 6),
        )

    def matches(self, local: datetime) -> bool:
        """判断给定的本地（naive）时刻是否匹配该表达式。"""
        if local.minute not in self.minute.values:
            return False
        if local.hour not in self.hour.values:
            return False
        if local.month not in self.month.values:
            return False
        dom_star = self.day_of_month.is_plain_star
        dow_star = self.day_of_week.is_plain_star
        if dom_star and dow_star:
            return True
        # Python weekday(): 周一=0..周日=6；cron: 周日=0..周六=6
        cron_dow = (local.weekday() + 1) % 7
        dom_ok = local.day in self.day_of_month.values
        dow_ok = cron_dow in self.day_of_week.values
        if dom_star:
            return dow_ok
        if dow_star:
            return dom_ok
        return dom_ok or dow_ok
