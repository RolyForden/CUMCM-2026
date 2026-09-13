"""按真实墙钟区间汇总充放电量和日界 SOC。

计划所属日与自然日并不总是一致：冻结的槽位方案中，计划日槽 143
实际位于次日 00:00--00:10。因此本模块只读取 ``interval_start`` 和
``interval_end``，不使用计划日或槽号决定归属。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from collections.abc import Iterable, Mapping, Sequence
from typing import Any


BLOCK_HOURS = (0, 4, 8, 12, 16, 20, 24)
SLOT_MINUTES = 10


class WallclockOutputError(ValueError):
    """墙钟汇总所需的时间轴或边界记录不完整。"""


@dataclass(frozen=True)
class WallclockBlock:
    label: str
    charge: float
    discharge: float


@dataclass(frozen=True)
class WallclockDaySummary:
    day: date
    blocks: tuple[WallclockBlock, ...]
    soc_0000: float
    soc_2400: float
    interval_count: int


def _as_datetime(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise WallclockOutputError(f"{field} 不是合法时间: {value!r}") from exc


def _as_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise WallclockOutputError(f"目标日期不合法: {value!r}") from exc


def _normalise_record(record: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "interval_start", "interval_end", "charge", "discharge",
        "soc_start", "soc_end",
    }
    missing = sorted(required - record.keys())
    if missing:
        raise WallclockOutputError(f"墙钟记录缺少字段: {', '.join(missing)}")
    start = _as_datetime(record["interval_start"], "interval_start")
    end = _as_datetime(record["interval_end"], "interval_end")
    if end - start != timedelta(minutes=SLOT_MINUTES):
        raise WallclockOutputError(
            f"区间必须恰为10分钟: {start.isoformat()}--{end.isoformat()}"
        )
    return {
        "interval_start": start,
        "interval_end": end,
        "charge": float(record["charge"]),
        "discharge": float(record["discharge"]),
        "soc_start": float(record["soc_start"]),
        "soc_end": float(record["soc_end"]),
    }


def _project_record(
    record: Mapping[str, Any],
    *,
    charge_field: str,
    discharge_field: str,
    soc_start_field: str,
    soc_end_field: str,
) -> dict[str, Any]:
    projected = dict(record)
    aliases = {
        "charge": charge_field,
        "discharge": discharge_field,
        "soc_start": soc_start_field,
        "soc_end": soc_end_field,
    }
    for target, source in aliases.items():
        if source not in record:
            raise WallclockOutputError(f"墙钟记录缺少字段: {source}")
        projected[target] = record[source]
    return _normalise_record(projected)


def aggregate_wallclock_days(
    records: Iterable[Mapping[str, Any]],
    days: Sequence[date | datetime | str],
    *,
    boundary_records: Iterable[Mapping[str, Any]] = (),
    charge_field: str = "charge_actual",
    discharge_field: str = "discharge_actual",
    soc_start_field: str = "soc_start",
    soc_end_field: str = "soc_end",
    tolerance: float = 1e-6,
) -> list[WallclockDaySummary]:
    """把逐槽记录汇总为严格的自然日六个四小时块。

    ``records`` 可保留原计划日分组；本函数不会读取该分组。对于评价期首日，
    调用方应通过 ``boundary_records`` 提供覆盖首日 00:00--00:10 的前一计划日
    槽 143。缺少该记录时会明确失败，不会把 00:10--04:10 冒充 0:00--4:00。
    """
    target_days = [_as_date(day) for day in days]
    if not target_days:
        return []
    if len(set(target_days)) != len(target_days):
        raise WallclockOutputError("目标日期存在重复")

    combined = [*boundary_records, *records]
    normalised = [
        _project_record(
            record,
            charge_field=charge_field,
            discharge_field=discharge_field,
            soc_start_field=soc_start_field,
            soc_end_field=soc_end_field,
        )
        for record in combined
    ]
    by_start: dict[datetime, dict[str, Any]] = {}
    for record in normalised:
        start = record["interval_start"]
        if start in by_start:
            raise WallclockOutputError(f"区间起点重复: {start.isoformat()}")
        by_start[start] = record

    summaries: list[WallclockDaySummary] = []
    step = timedelta(minutes=SLOT_MINUTES)
    for day in target_days:
        midnight = datetime.combine(day, time.min)
        expected_starts = [midnight + i * step for i in range(144)]
        missing = [start for start in expected_starts if start not in by_start]
        if missing:
            first = missing[0]
            hint = "；请通过 boundary_records 提供前一计划日槽143" if first == midnight else ""
            raise WallclockOutputError(
                f"{day.isoformat()} 墙钟日缺少 {len(missing)} 个10分钟区间，"
                f"首个缺失起点为 {first.isoformat()}{hint}"
            )
        day_records = [by_start[start] for start in expected_starts]
        for previous, current in zip(day_records, day_records[1:]):
            if previous["interval_end"] != current["interval_start"]:
                raise WallclockOutputError(
                    f"时间轴断裂: {previous['interval_end'].isoformat()} != "
                    f"{current['interval_start'].isoformat()}"
                )
            if abs(previous["soc_end"] - current["soc_start"]) > tolerance:
                raise WallclockOutputError(
                    f"SOC断裂于 {current['interval_start'].isoformat()}: "
                    f"{previous['soc_end']} != {current['soc_start']}"
                )

        blocks: list[WallclockBlock] = []
        for left, right in zip(BLOCK_HOURS, BLOCK_HOURS[1:]):
            part = day_records[left * 6:right * 6]
            blocks.append(
                WallclockBlock(
                    label=f"{left}:00-{right}:00",
                    charge=float(sum(row["charge"] for row in part)),
                    discharge=float(sum(row["discharge"] for row in part)),
                )
            )
        summaries.append(
            WallclockDaySummary(
                day=day,
                blocks=tuple(blocks),
                soc_0000=day_records[0]["soc_start"],
                soc_2400=day_records[-1]["soc_end"],
                interval_count=len(day_records),
            )
        )
    return summaries
