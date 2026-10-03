"""本地时间到 UTC 的映射与下一次 cron 触发时刻搜索。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

from .cron import CronExpr

# 真实 IANA 时区的 UTC 偏移跳变不超过 2 小时，取 3 小时作为安全余量。
_OFFSET_SHIFT_MARGIN = timedelta(hours=3)
# 任何合法 cron 在一个闰年周期（4 年）内必然命中，否则视为永不触发。
_MAX_SEARCH_DAYS = 366 * 4 + 1


def local_to_utc(tz: ZoneInfo, naive: datetime) -> List[datetime]:
    """本地分钟映射到 0、1 或 2 个 UTC 时刻（升序）。"""
    results: List[datetime] = []
    for fold in (0, 1):
        aware = naive.replace(tzinfo=tz, fold=fold)
        utc = aware.astimezone(timezone.utc)
        if utc.astimezone(tz).replace(tzinfo=None) != naive:
            continue  # 春季跳时中不存在的本地分钟
        if not results or results[0] != utc:
            results.append(utc)
    results.sort()
    return results


def next_match(expr: CronExpr, tz: ZoneInfo, after: datetime) -> Optional[datetime]:
    """严格晚于 after（UTC）的下一个 cron 触发 UTC 时刻；不存在则 None。"""
    after = after.astimezone(timezone.utc)
    # 秋季回拨时，略早于本地当前时刻的分钟仍可能映射出晚于 after 的 UTC，
    # 因此搜索起点向前回退一个偏移跳变安全余量，由 utc > after 过滤保证正确。
    local_start = after.astimezone(tz).replace(tzinfo=None) - _OFFSET_SHIFT_MARGIN
    best: Optional[datetime] = None
    best_local: Optional[datetime] = None
    day = local_start.date()
    for _ in range(_MAX_SEARCH_DAYS):
        if day.month in expr.month.values and expr.day_matches(day):
            for hour in sorted(expr.hour.values):
                for minute in sorted(expr.minute.values):
                    naive = datetime.combine(day, datetime.min.time()).replace(
                        hour=hour, minute=minute
                    )
                    if naive < local_start:
                        continue
                    if best_local is not None and naive > best_local + _OFFSET_SHIFT_MARGIN:
                        return best
                    for utc in local_to_utc(tz, naive):
                        if utc > after and (best is None or utc < best):
                            best, best_local = utc, naive
        day += timedelta(days=1)
    return best
