# scanplan — 终端扫描计划库

由上层直接调用的 Python 库：登记终端扫描策略，并查询确定、可重复的扫描计划。

## 能力

- 每条策略：IANA 时区 + 快速扫描 cron + 完整扫描 cron + 基准时刻（最近一次成功完整扫描的 UTC 时刻）。
- cron 为五字段（分 时 日 月 星期），支持数字、`*`、逗号并集、闭区间、`*/n` 与 `a-b/n` 步长（从范围下界起算）；星期 0=周日。
- 日/星期组合规则：都不是单独 `*` 时满足任意一项；只有一项是单独 `*` 时仅检查另一项；都是 `*` 则不限制日期。
- 按策略时区本地时间匹配：春季缺失分钟不触发不补跑，秋季重复分钟两个 UTC 时刻都触发；计划按 UTC 严格递增。
- 距最近一次完整扫描满 7×24 小时即安排强制完整扫描；任何完整扫描重新起算期限。
- 同一 UTC 时刻最多一次扫描；快速/完整/强制重合时合并为一次完整扫描。
- 查询区间左闭右开；从基准时刻起确定性模拟，窗口切分拼接与合并查询结果一致。

## 用法

```python
from datetime import datetime, timezone
from scanplan import ScanScheduler, ScanType

s = ScanScheduler()
s.register_policy(
    "nyc-laptops",
    tz_name="America/New_York",
    quick_cron="30 1 * * *",      # 每日 01:30 快速扫描
    full_cron="0 3 * * 0",        # 每周日 03:00 完整扫描
    baseline_utc=datetime(2026, 10, 26, 0, 0, tzinfo=timezone.utc),
)
events = s.plan("nyc-laptops",
                datetime(2026, 11, 1, tzinfo=timezone.utc),
                datetime(2026, 11, 8, tzinfo=timezone.utc))
for e in events:
    print(e.at.isoformat(), e.scan_type.value)
```

## 测试

```bash
python3 -m pytest tests/ -q
```
