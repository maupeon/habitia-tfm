"""Pruebas de invariantes científicos y contrato HTTP, sin red ni datos privados.

    python -m unittest discover -s tests -v

Los modelos diminutos de la prueba verifican exportación e inferencia, no se usan
para informar precisión del TFM. La evaluación real la produce el entrenamiento.
"""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import sklearn  # noqa: F401 -- cargar antes de LightGBM en macOS
import lightgbm as lgb
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
from pandas.testing import assert_frame_equal

from model_pipeline import (FEATURES, InputDataError, ModelPipeline, OutOfDomainError,
                            haversine_km, historical_to_payloads)
from valorador import Valorador, conformal_log_interval
from servicio import api


def historical_fixture():
    data = []
    for i in range(36):
        east = i >= 18
        data.append({"ASSETID": str(i // 2), "PRICE": 100000 + i * 7000,
                     "CONSTRUCTEDAREA": 40 + i * 3, "ROOMNUMBER": i % 4,
                     "BATHNUMBER": 1 + i % 2, "FLOORCLEAN": None if i % 7 == 0 else i % 6,
                     "HASLIFT": i % 2, "FLATLOCATIONID": i % 3,
                     "LATITUDE": 40.43 + (i % 18) * .0001,
                     "LONGITUDE": -3.70 + int(east) * .025,
                     "ISSTUDIO": int(i % 12 == 0), "ISDUPLEX": int(i % 9 == 0),
                     "ISINTOPFLOOR": i % 2,
                     "codigo_censal": "2807901001" if not east else "2807904001",
                     "barrio": "A" if not east else "B", "distrito": "Centro"})
    return pd.DataFrame(data)


class PipelineInvariants(unittest.TestCase):
    def setUp(self):
        self.history = historical_fixture()
        self.pipeline = ModelPipeline().fit(self.history)
        self.payload = historical_to_payloads(self.history)[2]

    def test_history_and_search_json_have_identical_matrix(self):
        assert_frame_equal(self.pipeline.transform(self.history),
                           self.pipeline.transform(historical_to_payloads(self.history)))

    def test_fit_statistics_never_use_price_or_holdout(self):
        state = copy.deepcopy(self.pipeline.to_dict())
        altered = self.history.copy()
        altered["PRICE"] = 999999999
        altered["rentabilidad_pct"] = -987654
        altered["alq_mediana_eur_m2"] = 1000000
        self.assertEqual(state, ModelPipeline().fit(altered).to_dict())
        holdout = self.history.iloc[:1].copy()
        holdout["FLOORCLEAN"] = 40
        holdout["barrio"] = "BARRIO_QUE_SOLO_APARECE_EN_TEST"
        self.pipeline.transform(holdout)
        self.assertEqual(state, self.pipeline.to_dict())
        self.assertNotIn("BARRIO_QUE_SOLO_APARECE_EN_TEST", self.pipeline.categoricals["barrio"])

    def test_advertised_price_cannot_change_features(self):
        cheap = {**self.payload, "price": 1}
        expensive = {**self.payload, "price": 999999999, "priceByArea": 300000}
        assert_frame_equal(self.pipeline.transform(cheap), self.pipeline.transform(expensive))
        self.assertFalse(any(name.startswith("alq") or name in {"PRICE", "UNITPRICE", "ISINTOPFLOOR"} for name in FEATURES))

    def test_last_floor_is_not_attic(self):
        flipped = self.history.copy()
        flipped["ISINTOPFLOOR"] = 1 - flipped.ISINTOPFLOOR
        self.assertEqual(historical_to_payloads(self.history), historical_to_payloads(flipped))
        attic = {**self.payload, "propertyType": "penthouse", "detailedType": None}
        x = self.pipeline.transform(attic)
        self.assertEqual(x.iloc[0].ISSTUDIO, 0)
        self.assertEqual(x.iloc[0].ISDUPLEX, 0)

    def test_missing_is_distinct_from_false_and_zero(self):
        unknown = {**self.payload, "hasLift": None, "rooms": None, "floor": None, "exterior": None}
        known = {**self.payload, "hasLift": False, "rooms": 0, "floor": "bj", "exterior": False}
        a, b = self.pipeline.transform(unknown).iloc[0], self.pipeline.transform(known).iloc[0]
        self.assertEqual(a.HASLIFT_ausente, 1)
        self.assertEqual(b.HASLIFT_ausente, 0)
        self.assertEqual(a.ROOMNUMBER, self.pipeline.medians["ROOMNUMBER"])
        self.assertEqual(b.ROOMNUMBER, 0)
        self.assertEqual(b.FLOORCLEAN, 0)
        self.assertNotEqual(a.FLATLOCATIONID_cat, b.FLATLOCATIONID_cat)

    def test_domain_abstains_instead_of_returning_madrid_price_anywhere(self):
        for change in [{"latitude": 41.3874, "longitude": 2.1686},
                       {"latitude": 40.53, "longitude": -3.85},
                       {"municipality": "Pozuelo de Alarcón"},
                       {"propertyType": "chalet"}, {"size": 1}, {"size": 2000},
                       {"detailedType": {"typology": "chalet"}},
                       {"rooms": 13}, {"bathrooms": -1}, {"floor": "100"}]:
            with self.subTest(change=change), self.assertRaises(OutOfDomainError):
                self.pipeline.transform({**self.payload, **change})
        for change in [{"latitude": float("nan")}, {"longitude": float("inf")}, {"size": None},
                       {"rooms": float("inf")}, {"bathrooms": "desconocido"}]:
            with self.subTest(change=change), self.assertRaises(InputDataError):
                self.pipeline.transform({**self.payload, **change})

    def test_nearest_uses_haversine_kilometers_and_roundtrip_is_exact(self):
        indices, distances = self.pipeline.nearest(np.array([self.payload["latitude"]]),
                                                  np.array([self.payload["longitude"]]))
        sec = self.pipeline.sections[indices[0]]
        self.assertAlmostEqual(distances[0], haversine_km(self.payload["latitude"], self.payload["longitude"], sec["lat"], sec["lon"]), places=12)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pipeline.json"
            self.pipeline.save(path)
            assert_frame_equal(self.pipeline.transform(self.history), ModelPipeline.load(path).transform(self.history))

    def test_interval_rule_handles_crossing_before_calibration(self):
        p = np.array([5., 10., 15.])
        lo, hi = conformal_log_interval(p, np.array([7., 8., 9.]), np.array([6., 12., 11.]), .2)
        np.testing.assert_allclose(lo, [4.8, 7.8, 8.8])
        np.testing.assert_allclose(hi, [7.2, 12.2, 15.2])
        with self.assertRaises(ValueError):
            conformal_log_interval(p, p, p, -.1)


class ExportAndHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        history = historical_fixture()
        pipeline = ModelPipeline().fit(history)
        pipeline.save(cls.root / "pipeline.json")
        x, y = pipeline.transform(history), np.log(history.PRICE.to_numpy())
        params = dict(n_estimators=5, num_leaves=4, min_child_samples=2, n_jobs=1, verbosity=-1, random_state=7)
        for suffix, extra in [("precio", {"objective": "regression_l1"}),
                              ("q_lo", {"objective": "quantile", "alpha": .05}),
                              ("q_hi", {"objective": "quantile", "alpha": .95})]:
            model = lgb.LGBMRegressor(**params, **extra).fit(x, y)
            model.booster_.save_model(str(cls.root / f"modelo_{suffix}.txt"))
        cls.manifest = {
            "version": "2.0.0", "columnas": pipeline.columns, "smearing": 1., "conformal_Q": .1,
            "alpha": .1, "renivelado": {"factor": 1.5534, "periodo": "2026T1", "es_escenario": True},
            "sha256": {f: hashlib.sha256((cls.root / f).read_bytes()).hexdigest() for f in
                       ["pipeline.json", "modelo_precio.txt", "modelo_q_lo.txt", "modelo_q_hi.txt"]}}
        (cls.root / "manifiesto.json").write_text(json.dumps(cls.manifest))
        cls.valorador = Valorador(cls.root)
        cls.payload = historical_to_payloads(history, include_price=True)[2]
        cls.client = TestClient(api.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.tmp.cleanup()
        api.V = None

    def setUp(self):
        api.V = self.valorador
        api.TOKEN = None

    def test_served_matrix_equals_training_pipeline_after_export(self):
        assert_frame_equal(self.valorador.pipeline.transform(self.payload),
                           self.valorador._matriz([self.valorador.fila(self.payload)]), check_dtype=False)
        result = self.valorador.valorar(self.payload)
        x = self.valorador.pipeline.transform(self.payload)
        direct = round(float(np.exp(self.valorador.modelo.predict(x, num_threads=1)[0])))
        self.assertEqual(result["precio_justo"], direct)

    def test_price_changes_comparison_never_prediction_or_interval(self):
        cheap = self.valorador.valorar({**self.payload, "price": 1})
        expensive = self.valorador.valorar({**self.payload, "price": 9999999})
        missing = self.valorador.valorar({**self.payload, "price": None})
        self.assertEqual(cheap["precio_justo"], expensive["precio_justo"])
        self.assertEqual(cheap["intervalo"], expensive["intervalo"])
        self.assertTrue(cheap["oportunidad"])
        self.assertTrue(expensive["sobrevalorado"])
        self.assertIsNone(missing["brecha_pct"])
        self.assertFalse(missing["oportunidad"])
        for price in [0, -1, float("inf"), float("nan")]:
            with self.subTest(price=price), self.assertRaises(InputDataError):
                self.valorador.valorar({**self.payload, "price": price})

    def test_temporal_scenario_is_opt_in_and_marked_unvalidated(self):
        historical = self.valorador.valorar(self.payload)
        scenario = self.valorador.valorar(self.payload, renivelar=True)
        self.assertEqual(historical["nivel_precios"], "2018")
        self.assertFalse(historical["extrapolacion_temporal"])
        self.assertTrue(scenario["extrapolacion_temporal"])
        self.assertFalse(scenario["precision_actual_validada"])
        self.assertAlmostEqual(scenario["precio_justo"] / historical["precio_justo"], 1.5534, places=4)
        self.assertLessEqual(historical["intervalo"][0], historical["precio_justo"])
        self.assertGreaterEqual(historical["intervalo"][1], historical["precio_justo"])

    def test_http_partial_batch_reports_rejected_rows(self):
        r = self.client.post("/valorar", json={"anuncios": [self.payload, {**self.payload, "propertyCode": "chalet", "propertyType": "chalet"}]})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(len(body["resultados"]), 1)
        self.assertEqual(body["errores"][0]["propertyCode"], "chalet")
        self.assertEqual(body["errores"][0]["estado"], "fuera_ambito")
        self.assertEqual(body["nivel_precios"], "2018")

    def test_http_invalid_unavailable_auth_and_batch_limits(self):
        r = self.client.post("/valorar", json={"anuncios": [{**self.payload, "price": -1}]})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["detail"]["errores"][0]["estado"], "datos_insuficientes")
        self.assertEqual(self.client.post("/valorar", json={"anuncios": [self.payload] * (api.MAX_LOTE + 1)}).status_code, 413)
        api.TOKEN = "test-only-token"
        self.assertEqual(self.client.post("/valorar", json={"anuncios": [self.payload]}).status_code, 401)
        self.assertEqual(self.client.post("/valorar", json={"anuncios": [self.payload]}, headers={"Authorization": "Bearer test-only-token"}).status_code, 200)
        api.TOKEN = None
        api.V = None
        self.assertEqual(self.client.get("/salud").status_code, 503)
        self.assertEqual(self.client.post("/valorar", json={"anuncios": [self.payload]}).status_code, 503)

    def test_unverified_rental_is_not_presented_as_model_output(self):
        r = self.client.post("/valorar-alquiler", json={"anuncios": [self.payload]})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["detail"]["estado"], "referencia_no_verificada")
        self.assertFalse(self.client.get("/salud").json()["alquiler"])

    def test_artifact_hash_rejects_mismatched_export(self):
        file = self.root / "pipeline.json"
        original = file.read_bytes()
        try:
            file.write_bytes(original + b"\n")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                Valorador(self.root)
        finally:
            file.write_bytes(original)

    def test_optional_shap_is_additive_in_log_space_and_not_causal(self):
        self.assertNotIn("explicacion", self.valorador.valorar(self.payload))
        response = self.client.post("/valorar", json={"anuncios": [self.payload], "explicar": True})
        self.assertEqual(response.status_code, 200)
        explain = response.json()["resultados"][0]["explicacion"]
        total = explain["base_log_euros"] + explain["suma_otras_contribuciones_log_euros"] + sum(f["contribucion_log_euros"] for f in explain["factores"])
        self.assertAlmostEqual(total, explain["prediccion_log_euros"], places=10)
        self.assertEqual(len(explain["factores"]), 3)
        self.assertTrue(explain["no_causal"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
