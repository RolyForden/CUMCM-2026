"""墙钟输出聚合的独立小测试。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import unittest

from core.wallclock_output import WallclockOutputError, aggregate_wallclock_days


DAY = date(2025, 2, 1)


def record(start: datetime, index: int) -> dict:
    return {
        # 故意提供无关且错误的计划日/槽号，确认聚合只看真实时间戳。
        "date": "2099-12-31",
        "slot": 999 - index,
        "interval_start": start.isoformat(),
        "interval_end": (start + timedelta(minutes=10)).isoformat(),
        "charge_actual": float(index + 1),
        "discharge_actual": float(2 * (index + 1)),
        "soc_start": float(5000 + index),
        "soc_end": float(5001 + index),
    }


class WallclockOutputTests(unittest.TestCase):
    def setUp(self) -> None:
        midnight = datetime.combine(DAY, datetime.min.time())
        self.boundary = [record(midnight, 0)]
        # 模拟“本计划日”正式记录：从00:10一直到次日00:10。
        self.plan_day = [record(midnight + timedelta(minutes=10 * i), i) for i in range(1, 145)]

    def test_uses_true_intervals_and_excludes_next_day_slot(self) -> None:
        result = aggregate_wallclock_days(
            list(reversed(self.plan_day)), [DAY], boundary_records=self.boundary
        )[0]
        self.assertEqual(result.interval_count, 144)
        self.assertEqual(result.soc_0000, 5000.0)
        self.assertEqual(result.soc_2400, 5144.0)
        self.assertEqual(result.blocks[0].charge, sum(range(1, 25)))
        self.assertEqual(result.blocks[-1].charge, sum(range(121, 145)))
        self.assertEqual(result.blocks[-1].discharge, 2 * sum(range(121, 145)))
        # 次日00:00--00:10的第145条计划记录不得混入当天。
        self.assertNotEqual(result.blocks[-1].charge, sum(range(122, 146)))

    def test_missing_first_boundary_fails_explicitly(self) -> None:
        with self.assertRaisesRegex(
            WallclockOutputError, "boundary_records.*前一计划日槽143"
        ):
            aggregate_wallclock_days(self.plan_day, [DAY])

    def test_soc_discontinuity_is_rejected(self) -> None:
        broken = [dict(row) for row in self.plan_day]
        broken[20]["soc_start"] += 3.0
        with self.assertRaisesRegex(WallclockOutputError, "SOC断裂"):
            aggregate_wallclock_days(broken, [DAY], boundary_records=self.boundary)

    def test_non_ten_minute_interval_is_rejected(self) -> None:
        broken_boundary = [dict(self.boundary[0])]
        broken_boundary[0]["interval_end"] = (
            datetime.combine(DAY, datetime.min.time()) + timedelta(minutes=20)
        ).isoformat()
        with self.assertRaisesRegex(WallclockOutputError, "恰为10分钟"):
            aggregate_wallclock_days(self.plan_day, [DAY], boundary_records=broken_boundary)


if __name__ == "__main__":
    unittest.main()
