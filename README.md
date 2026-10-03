# task26100460

终端扫描计划库：安全团队按策略为终端安排快速/完整扫描，纯 Python 实现，无外部依赖。

## 用法

```python
from datetime import datetime, timezone
from scanplan import ScanPlanner, ScanKind

planner = ScanPlanner()
planner.register_policy(
    policy_id="nyc-terminals",
    timezone="America/New_York",   # IANA 时区
    quick_cron="0,30 1 * * *",     # 快速扫描 cron（分 时 日 月 星期）
    full_cron="0 3 * * 0",         # 完整扫描 cron
    base_time=datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc),  # 基准时刻
)
events = planner.query(
    "nyc-terminals",
    datetime(2026, 11, 1, tzinfo=timezone.utc),
    datetime(2026, 11, 8, tzinfo=timezone.utc),
)  # -> [ScanEvent(time=..., kind=ScanKind.QUICK/FULL), ...] 按 UTC 严格递增
```

- cron 支持数字、`*`、逗号并集、闭区间及 `*`/闭区间后的正整数步长；星期 0-6，0 为周日。
- 春季跳时中不存在的本地分钟不触发；秋季重复的本地分钟在两个 UTC 时刻各触发一次。
- 距最近一次完整扫描满 7×24 小时即安排强制完整扫描，任何完整扫描重新起算期限。
- 查询区间左闭右开；相邻区间分别查询后拼接与合并查询结果一致。

## 测试

```sh
python3 -m pytest tests -q
```
