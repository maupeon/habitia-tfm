"""Pruebas sobre filas sintéticas: identidad, dominio y ponderación por activo."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from revision_data import ORIGINAL_COLUMNS, asset_weights, load_revision_data


def row(**changes):
    record = dict.fromkeys(ORIGINAL_COLUMNS, 0)
    record.update(ASSETID="A1", PERIOD=201803, PRICE=200000, UNITPRICE=2500,
                  CONSTRUCTEDAREA=80, ROOMNUMBER=2, BATHNUMBER=1,
                  LATITUDE=40.42, LONGITUDE=-3.70, FLOORCLEAN=2)
    record.update(changes)
    return record


class RevisionDataTests(unittest.TestCase):
    def load(self, rows):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.parquet"
            pd.DataFrame(rows).to_parquet(path, index=False)
            result = load_revision_data(path)
        json.dumps(result[1])  # El registro se puede guardar sin serializadores especiales.
        return result

    def test_dedup_uses_original_fields_and_preserves_different_observations(self):
        rows = [row(n_viviendas_alquiler=None, alq_imputado=True),
                row(n_viviendas_alquiler=153, alq_imputado=False),
                row(PRICE=210000, UNITPRICE=2625, n_viviendas_alquiler=153)]
        frame, audit = self.load(rows)
        self.assertEqual(frame.source_row_id.tolist(), [0, 2])
        self.assertEqual(frame.PRICE.tolist(), [200000, 210000])
        self.assertNotIn("n_viviendas_alquiler", frame)
        self.assertEqual(audit["deduplication"]["rows_removed"], 1)
        self.assertEqual(audit["deduplication"]["merged_rows"][0]["removed_source_row_ids"], [1])
        self.assertEqual(audit["output"]["assets_with_multiple_rows"], 1)

    def test_price_extremes_remain_and_rules_are_sequential(self):
        frame, audit = self.load([
            row(ASSETID="low", PRICE=1), row(ASSETID="high", PRICE=1e10),
            row(ASSETID="bad", PRICE=-1, CONSTRUCTEDAREA=1),
            row(ASSETID="area", CONSTRUCTEDAREA=1001),
            row(ASSETID="geo", LATITUDE=41.4),
        ])
        self.assertEqual(frame.ASSETID.tolist(), ["low", "high"])
        counts = {item["reason"]: item["rows_removed"] for item in audit["exclusions"]}
        self.assertEqual(counts["invalid_price"], 1)
        self.assertEqual(counts["area_outside_20_1000"], 1)
        self.assertEqual(counts["coordinates_outside_madrid_bbox"], 1)

    def test_missing_optional_values_remain_but_nonfinite_values_fail(self):
        frame, audit = self.load([
            row(ASSETID="missing", ROOMNUMBER=None, BATHNUMBER=None, FLOORCLEAN=None,
                barrio=None, codigo_censal=None),
            row(ASSETID="rooms", ROOMNUMBER=13),
            row(ASSETID="bath", BATHNUMBER=np.inf),
            row(ASSETID="floor", FLOORCLEAN=-3),
            row(ASSETID="price", PRICE=np.nan),
            row(ASSETID="  "), row(ASSETID=None),
        ])
        self.assertEqual(frame.ASSETID.tolist(), ["missing"])
        self.assertTrue(frame.ROOMNUMBER.isna().all())
        self.assertTrue(frame.barrio.isna().all())
        self.assertEqual(audit["rows_excluded_by_validation"], 6)

    def test_conflicting_territory_is_unknown_instead_of_arbitrarily_chosen(self):
        frame, audit = self.load([row(barrio="Uno"), row(barrio="Dos")])
        self.assertTrue(frame.barrio.isna().all())
        self.assertEqual(audit["deduplication"]["conflicting_extra_columns"], {"barrio": 1})

    def test_each_asset_has_equal_total_weight_and_mean_weight_is_one(self):
        frame = pd.DataFrame({"ASSETID": ["A", "A", "A", "B"]})
        weights = asset_weights(frame)
        self.assertAlmostEqual(weights.mean(), 1)
        self.assertAlmostEqual(weights[:3].sum(), weights[3])
        self.assertEqual(len(asset_weights(frame.iloc[:0])), 0)
        with self.assertRaises(ValueError):
            asset_weights(pd.DataFrame({"ASSETID": [None]}))

    def test_original_schema_is_required(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "incomplete.parquet"
            pd.DataFrame([row()]).drop(columns="PRICE").to_parquet(path, index=False)
            with self.assertRaisesRegex(ValueError, "PRICE"):
                load_revision_data(path)


if __name__ == "__main__":
    unittest.main()
