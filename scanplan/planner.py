"""策略登记与扫描计划查询。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as _timezone
from enum import Enum
from typing import Dict, List
from zoneinfo import ZoneInfo

from .cron import CronExpr
from .scheduler import next_match

# 两次完整扫描之间最多允许的时间跨度。
MAX_FULL_GAP = timedelta(days=7)


class ScanKind(Enum):
    QUICK = "quick"
    FULL = "full"


@dataclass(frozen=True)
class ScanEvent:
    time: datetime  # UTC，对齐到分钟
    kind: ScanKind


@dataclass(frozen=True)
class Policy:
    policy_id: str
    timezone: str
    quick_cron: CronExpr
    full_cron: CronExpr
    base_time: datetime  # 最近一次成功完整扫描的 UTC 时刻


class ScanPlanner:
    """策略注册表 + 计划查询入口。"""

    def __init__(self) -> None:
        self._policies: Dict[str, Policy] = {}

    def register_policy(
        self,
        policy_id: str,
        timezone: str,
        quick_cron: str,
        full_cron: str,
        base_time: datetime,
    ) -> Policy:
        if policy_id in self._policies:
            raise ValueError(f"策略已存在: {policy_id!r}")
        _require_minute_aligned(base_time, "base_time")
        policy = Policy(
            policy_id=policy_id,
            timezone=timezone,
            quick_cron=CronExpr.parse(quick_cron),
            full_cron=CronExpr.parse(full_cron),
            base_time=base_time.astimezone(_timezone.utc),
        )
        ZoneInfo(policy.timezone)  # 提前校验时区名称
        self._policies[policy_id] = policy
        return policy

    def get_policy(self, policy_id: str) -> Policy:
        try:
            return self._policies[policy_id]
        except KeyError:
            raise KeyError(f"未知策略: {policy_id!r}") from None

    def query(self, policy_id: str, start: datetime, end: datetime) -> List[ScanEvent]:
        """返回 [start, end) 内的扫描计划，按 UTC 严格递增。"""
        policy = self.get_policy(policy_id)
        _require_minute_aligned(start, "start")
        _require_minute_aligned(end, "end")
        start = start.astimezone(_timezone.utc)
        end = end.astimezone(_timezone.utc)
        if end <= start:
            raise ValueError("查询区间必须满足 start < end")
        tz = ZoneInfo(policy.timezone)
        events: List[ScanEvent] = []
        # 始终从基准时刻起模拟，保证结果与查询窗口无关、可拼接。
        last_full = policy.base_time
        cursor = policy.base_time
        while True:
            deadline = last_full + MAX_FULL_GAP
            t_quick = next_match(policy.quick_cron, tz, cursor)
            t_full = next_match(policy.full_cron, tz, cursor)
            t_next = _min_time(t_quick, t_full)
            if t_next is None or t_next >= deadline:
                # 到期强制完整扫描；与 cron 触发同刻时合并为一次完整扫描。
                moment, kind = deadline, ScanKind.FULL
            else:
                moment = t_next
                kind = ScanKind.FULL if t_full == t_next else ScanKind.QUICK
            if moment >= end:
                break
            if moment >= start:
                events.append(ScanEvent(time=moment, kind=kind))
            if kind is ScanKind.FULL:
                last_full = moment
            cursor = moment
        return events


def _min_time(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


def _require_minute_aligned(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} 必须携带时区信息")
    if value.second or value.microsecond:
        raise ValueError(f"{name} 必须对齐到分钟")
