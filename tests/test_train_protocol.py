"""Invariantes independientes del protocolo, sin ejecutar un experimento completo."""
import math
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from train_revision import assert_group_separation, calibrate_groups, group_calibration_split


class TrainingProtocolTests(unittest.TestCase):
    def test_split_keeps_all_observations_of_each_asset_together(self):
        frame = pd.DataFrame({"ASSETID": np.repeat(np.arange(30), 3), "PRICE": np.arange(90) + 1})
        fit, cal = group_calibration_split(frame, .2, 17)
        self.assertEqual(len(set(fit.ASSETID) & set(cal.ASSETID)), 0)
        self.assertEqual(len(fit) + len(cal), len(frame))
        assert_group_separation(fit=fit, calibracion=cal)
        with self.assertRaisesRegex(AssertionError, "Fuga"):
            assert_group_separation(fit=frame, calibracion=cal)

    def test_conformal_order_statistic_uses_assets_not_rows(self):
        y = np.asarray([.1, .8, .2, .1, .3, .2, .4, .3, .5, .1,
                        .6, .2, .7, .1, .8, .2, .9, .1, 1., .1])
        groups = np.repeat(np.arange(10), 2)
        q, metadata = calibrate_groups(y, np.zeros(20), np.zeros(20), np.zeros(20), groups, .2)
        maxima = np.asarray([.8, .2, .3, .4, .5, .6, .7, .8, .9, 1.])
        rank = math.ceil((10 + 1) * .8)
        self.assertAlmostEqual(q, sorted(maxima)[rank - 1])
        self.assertEqual(metadata["n_activos"], 10)
        self.assertEqual(metadata["n_observaciones"], 20)
        self.assertEqual(metadata["rango_orden"], 9)
        # Duplicar registros dentro del mismo activo no cambia el cuantil grupal.
        duplicated, _ = calibrate_groups(np.repeat(y, 2), np.zeros(40), np.zeros(40), np.zeros(40), np.repeat(groups, 2), .2)
        self.assertEqual(q, duplicated)

    def test_calibration_never_contracts_and_requires_enough_assets(self):
        q, _ = calibrate_groups(np.zeros(20), np.zeros(20), -np.ones(20), np.ones(20), np.arange(20), .1)
        self.assertEqual(q, 0)
        with self.assertRaises(ValueError):
            calibrate_groups(np.zeros(4), np.zeros(4), -np.ones(4), np.ones(4), np.arange(4), .1)


if __name__ == "__main__":
    unittest.main()
