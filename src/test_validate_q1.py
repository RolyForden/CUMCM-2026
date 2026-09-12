from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

import validate_q1


class Q1ValidationTests(unittest.TestCase):
    def test_explicit_milp_respects_terminal_soc_and_energy_balance(self) -> None:
        result = validate_q1.solve_explicit_milp(
            price=np.array([0.5, 1.0]),
            load=np.array([10.0, 10.0]),
            pv=np.zeros(2),
            eta_charge=0.9,
            eta_discharge=0.9,
            soc_min=0.0,
            soc_max=100.0,
            energy_limit=20.0,
            soc0=50.0,
        )
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["soc"][0], 50.0, places=7)
        self.assertAlmostEqual(result["soc"][-1], 50.0, places=7)
        residual = result["grid"] + result["pv_used"] + result["discharge"] - np.array([10.0, 10.0]) - result["charge"]
        self.assertLess(float(np.max(np.abs(residual))), 1e-7)
        self.assertFalse(bool(np.any((result["charge"] > 1e-7) & (result["discharge"] > 1e-7))))

    def test_load_dispatch_rejects_duplicate_slots(self) -> None:
        frame = pd.DataFrame(
            {
                "slot": [0, 0],
                "interval_start": ["2025-01-01T00:10:00", "2025-01-01T00:20:00"],
                "interval_end": ["2025-01-01T00:20:00", "2025-01-01T00:30:00"],
                "price": [1.0, 1.0],
                "load": [1.0, 1.0],
                "pv_available": [0.0, 0.0],
                "pv_used": [0.0, 0.0],
                "pv_curtail": [0.0, 0.0],
                "grid_delivered": [1.0, 1.0],
                "grid_contract": [1.0, 1.0],
                "grid_unused": [0.0, 0.0],
                "grid_emergency": [0.0, 0.0],
                "charge": [0.0, 0.0],
                "discharge": [0.0, 0.0],
                "soc_start": [5.0, 5.0],
                "soc_end": [5.0, 5.0],
                "normal_cost": [1.0, 1.0],
                "emergency_cost": [0.0, 0.0],
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            frame.to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, "slot"):
                validate_q1.load_dispatch(path, expected_rows=2)


if __name__ == "__main__":
    unittest.main()
