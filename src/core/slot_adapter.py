"""144 槽位适配器：输入数据列 → slot_id → 结果模板列。

冻结口径（DECISIONS.md D002 P0-1 + D003，方案A，起点对齐、不平移）：
- 官方输入表 144 列标签为 `00:10`…`23:50`, `0:00+1`；
  官方结果模板 144 行区间为 `0:10-0:20`…`23:50-0:00+1`, `0:00+1-0:10+1`。
- 输入列 k、槽位 k、模板行 k 按位置一一对应（无平移）：
  槽位 k 的区间 = [标签_k, 标签_k + 10min)：
    slot 0   = [00:10, 00:20)
    slot 142 = [23:50, 24:00)   ← 跨日区间（终点 = 次日 0:00）
    slot 143 = [24:00, 24:10)   ← 次日第一个 10 分钟（标签 0:00+1）
- 计算以整数 slot_id = 0..143 为唯一主键，禁止用时间字符串拼接表。
- 映射集中在本模块；若未来推翻方案A，必须同时修改终端SOC、模板解释和测试。

注意（D002 冻结口径的推论，已在探针报告记录）：
该映射下一天的 144 槽覆盖 [00:10, 次日 00:10)；当天 [00:00, 00:10)
没有输入列（官方表无 00:00 列），不参与调度（无动作，SOC 不变）。
Q1 的 0:00 储电量 = E_0（附录初值），24:00 储电量 = E_143
（第 143 个槽开始时刻），E_144 为次日 00:10 的 SOC。
D002 P0-2 冻结的终端约束 E_144 = E_0 视为"144 槽周期首尾相等"。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

N_SLOTS = 144
SLOT_MINUTES = 10


@dataclass(frozen=True)
class Slot:
    """一个 10 分钟槽位（冻结的起点对齐口径）。"""

    slot_id: int          # 0..143
    day: date             # 提供输入值的自然日（槽 143 的区间落在次日）
    interval_start: datetime
    interval_end: datetime
    source_label: str     # 输入表点标签：00:10…23:50 或 "0:00+1"
    template_interval: str    # 模板区间标签："0:10-0:20" … "0:00+1-0:10+1"

    @property
    def source_column(self) -> int:
        """输入宽表中的列号（第 k+2 列：第 1 列是日期）。"""
        return self.slot_id + 2

    @property
    def template_column(self) -> int:
        """结果模板中的列号（第 k+2 列：第 1 列是日期）。"""
        return self.slot_id + 2

    @property
    def is_cross_day(self) -> bool:
        """区间是否跨自然日边界（slot 142：23:50→24:00）。"""
        return self.interval_start.date() != self.interval_end.date()

    @property
    def is_next_day_slot(self) -> bool:
        """区间是否完全落在次日（slot 143：0:00+1-0:10+1）。"""
        return self.interval_start.date() != self.day


def _fmt_t(dt: datetime) -> str:
    # 官方模板/输入表风格：小时不补零、分钟两位（'0:10'、'23:50'）
    return f"{dt.hour}:{dt.minute:02d}"


def _fmt_source_label(start: datetime) -> str:
    """输入表点标签：次日 0:00 写作 '0:00+1'（官方写法）。"""
    if start.hour == 0 and start.minute == 0:
        return "0:00+1"
    return _fmt_t(start)


def _fmt_template_interval(day: date, start: datetime, end: datetime) -> str:
    """模板区间标签（官方写法）。"""
    s = _fmt_t(start)
    e = _fmt_t(end)
    if start.date() == day and end.date() == day + timedelta(days=1):
        # 当天 23:50 → 24:00（次日 0:00）
        return f"{s}-0:00+1"
    if start.date() == end.date() == day + timedelta(days=1):
        # 次日 00:00 → 00:10
        return f"{s}+1-{e}+1"
    return f"{s}-{e}"


def build_day_slots(day: date) -> list[Slot]:
    """构造某自然日全部 144 个槽位（冻结口径）。

    slot k 的区间 = [day 00:00 + 10(k+1) 分钟, +10 分钟)：
    k=0 → [00:10,00:20)，k=142 → [23:50,24:00)，k=143 → [24:00,24:10)。
    """
    slots = []
    base = datetime.combine(day, datetime.min.time())
    for k in range(N_SLOTS):
        start = base + timedelta(minutes=SLOT_MINUTES * (k + 1))
        end = start + timedelta(minutes=SLOT_MINUTES)
        slots.append(
            Slot(
                slot_id=k,
                day=day,
                interval_start=start,
                interval_end=end,
                source_label=_fmt_source_label(start),
                template_interval=_fmt_template_interval(day, start, end),
            )
        )
    return slots


def parse_input_time_label(label: str, day: date) -> datetime:
    """解析输入表时间标签为该标签所代表槽位的区间起点（datetime）。

    - '00:10' … '23:50' → 当天该时刻；
    - '0:00+1' → 次日 0:00（= 当天 24:00，槽 143 的起点）。
    带秒的写法（官方表 '00:10:00' 与 '23:50' 混用）也接受。
    """
    s = str(label).strip()
    cross = "+1" in s
    s = s.replace("+1", "").strip()
    if s == "24:00":
        s = "0:00"
    hh, mm = s.split(":")[:2]
    h = int(hh)
    m = int(mm)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"无法解析时间标签: {label!r}")
    base = datetime.combine(day, datetime.min.time())
    if cross:
        return base + timedelta(days=1)
    return base + timedelta(hours=h, minutes=m)


def slot_id_from_input_label(label: str, day: date) -> int:
    """输入标签 → slot_id（起点对齐口径，无平移）。

    标签 '0:00+1'（= 24:00）是槽 143 的区间起点 → slot_id 143。
    '00:10' → slot 0。官方输入表没有 '00:00' 列，遇之报错。
    """
    start = parse_input_time_label(label, day)
    base = datetime.combine(day, datetime.min.time())
    minutes = (start - base).total_seconds() / 60
    k = int(round(minutes / SLOT_MINUTES)) - 1
    if not 0 <= k <= N_SLOTS - 1:
        raise ValueError(f"标签 {label!r} 不是官方输入标签（槽位 {k}）")
    return k


def template_column_label(k: int, day: date) -> str:
    """slot_id k 的模板区间标签。"""
    return build_day_slots(day)[k].template_interval
