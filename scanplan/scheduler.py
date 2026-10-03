"""扫描计划调度器。

cron 按策略时区的当地时间匹配；通过 fold 往返校验处理夏令时：
春季不存在的本地分钟不触发，秋季重复的本地分钟产生两个 UTC 触发时刻。
距离最近一次完整扫描满 7*24 小时即安排强制完整扫描。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from .cron import CronExpression

FULL_SCAN_INTERVAL = timedelta(days=7)
_ONE_MINUTE = timedelta(minutes=1)
_ONE_DAY = timedelta(days=1)


class ScanType(str, Enum):
    QUICK = "quick"
    FULL = "full"


@dataclass(frozen=True)
class ScanEvent:
    """一次计划扫描：UTC 时刻 + 类型。"""

    at: datetime
    scan_type: ScanType


@dataclass(frozen=True)
class Policy:
    """一条扫描策略。"""

    policy_id: str
    tz_name: str
    quick_cron: CronExpression
    full_cron: CronExpression
    baseline_utc: datetime


def _normalize_utc(moment: datetime) -> datetime:
    """统一为 UTC 感知时刻并对齐到分钟。"""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    moment = moment.astimezone(timezone.utc)
    return moment.replace(second=0, microsecond=0)


def _local_to_utc(naive: datetime, tz: ZoneInfo) -> List[datetime]:
    """把本地 naive 时刻映射为 UTC 时刻列表。

    正常时刻返回 1 个；秋季重复时刻返回 2 个；春季不存在时刻返回 0 个。
    """
    results: List[datetime] = []
    for fold in (0, 1):
        aware = naive.replace(tzinfo=tz, fold=fold)
        utc = aware.astimezone(timezone.utc)
        if utc.astimezone(tz).replace(tzinfo=None) == naive:
            if utc not in results:
                results.append(utc)
    return results


def _next_trigger(
    policy: Policy,
    tz: ZoneInfo,
    after_utc: datetime,
    limit_utc: datetime,
) -> Optional[Tuple[datetime, bool]]:
    """在 (after_utc, limit_utc] 内找最早的 cron 触发时刻。

    返回 (utc 时刻, 是否匹配完整扫描 cron)；无触发返回 None。
    """
    first_date = after_utc.astimezone(tz).date()
    last_date = limit_utc.astimezone(tz).date() + _ONE_DAY
    best: Optional[Tuple[datetime, bool]] = None
    day = first_date
    while day <= last_date:
        for hour in sorted(policy.quick_cron.hour.values | policy.full_cron.hour.values):
            for minute in sorted(
                policy.quick_cron.minute.values | policy.full_cron.minute.values
            ):
                naive = datetime(day.year, day.month, day.day, hour, minute)
                quick_hit = policy.quick_cron.matches(naive)
                full_hit = policy.full_cron.matches(naive)
                if not (quick_hit or full_hit):
                    continue
                for utc in _local_to_utc(naive, tz):
                    if after_utc < utc <= limit_utc:
                        if best is None or utc < best[0]:
                            best = (utc, full_hit)
        if best is not None and day > best[0].astimezone(tz).date():
            break
        day += _ONE_DAY
    return best


class ScanScheduler:
    """策略登记与计划查询。"""

    def __init__(self) -> None:
        self._policies: Dict[str, Policy] = {}

    def register_policy(
        self,
        policy_id: str,
        tz_name: str,
        quick_cron: str,
        full_cron: str,
        baseline_utc: datetime,
    ) -> None:
        self._policies[policy_id] = Policy(
            policy_id=policy_id,
            tz_name=tz_name,
            quick_cron=CronExpression.parse(quick_cron),
            full_cron=CronExpression.parse(full_cron),
            baseline_utc=_normalize_utc(baseline_utc),
        )

    def plan(
        self,
        policy_id: str,
        start_utc: datetime,
        end_utc: datetime,
    ) -> List[ScanEvent]:
        """查询 [start_utc, end_utc) 内的扫描计划，按 UTC 严格递增。"""
        policy = self._policies[policy_id]
        tz = ZoneInfo(policy.tz_name)
        start = _normalize_utc(start_utc)
        end = _normalize_utc(end_utc)
        if end <= start:
            return []

        events: List[ScanEvent] = []
        cursor = policy.baseline_utc
        last_full = policy.baseline_utc
        while True:
            deadline = last_full + FULL_SCAN_INTERVAL
            trigger = _next_trigger(policy, tz, cursor, deadline)
            if trigger is not None:
                at, is_full = trigger
                if at == deadline:
                    is_full = True  # 强制期限与 cron 重合，合并为一次完整扫描
            else:
                at, is_full = deadline, True
            if at >= end:
                break
            if at >= start:
                events.append(
                    ScanEvent(at=at, scan_type=ScanType.FULL if is_full else ScanType.QUICK)
                )
            if is_full:
                last_full = at
            cursor = at
        return events
