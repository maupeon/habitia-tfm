import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from predictor_v3.predictor import RUTA_PAQUETE
from predictor_v3.runtime import RuntimePredictor

BASE = dict(propertyCode="sintetico-1", operation="sale", municipality="Madrid", propertyType="flat",
            size=80, rooms=2, bathrooms=1, latitude=40.4168, longitude=-3.7038, floor="2", hasLift=True,
            price=450000, description="Piso con terraza, aire acondicionado, armarios empotrados y trastero.",
            parkingSpace={"hasParkingSpace": True})

class ValidationTests(unittest.TestCase):
    def test_strict_inputs(self):
        for changes in ({"latitude": None}, {"latitude": float("nan")}, {"latitude": 91},
                        {"hasLift": "false"}, {"newDevelopment": "false"}, {"rooms": 2.5}, {"size": float("inf")},
                        {"propertyType": "office"}, {"propertyType": "chalet"}, {"size": 368},
                        {"operation": "unknown"}, {"municipality": "Barcelona"}, {"bathrooms": None}):
            with self.subTest(changes=changes):
                _, error = RuntimePredictor.validate({**BASE, **changes})
                self.assertIsNotNone(error)
        for key in ("operation", "propertyType", "municipality"):
            _, error = RuntimePredictor.validate({k: v for k, v in BASE.items() if k != key})
            self.assertIsNotNone(error)
        row, error = RuntimePredictor.validate(BASE)
        self.assertIsNone(error)
        self.assertEqual(row["description"], BASE["description"])
        self.assertIsNone(RuntimePredictor.validate({**BASE, "operation": "rent", "price": 1500})[1])

@unittest.skipUnless(RUTA_PAQUETE.exists(), "Instala los artefactos v3 para las pruebas de integración")
class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = RuntimePredictor()

    def test_mixed_batch(self):
        result, errors = self.runtime.valorar([BASE, {**BASE, "propertyCode": "missing", "latitude": None},
                                             {**BASE, "propertyCode": "chalet", "propertyType": "chalet"}])
        self.assertEqual(len(result), 1)
        self.assertEqual([e["estado"] for e in errors], ["datos_insuficientes", "fuera_ambito"])
        self.assertIsNone(result[0]["intervalo"])
        self.assertIsNone(result[0]["banda"])
        self.assertFalse(result[0]["alquiler_validado"])
        self.assertEqual(result[0]["nivel_precios"], "2025")

    def test_native_coordinate_fix(self):
        rows = self.runtime.predictor.predecir([BASE, {**BASE, "latitude": None}])
        self.assertEqual(rows.valido.tolist(), [True, False])
        self.assertIn("sin_coordenadas", rows.iloc[1].motivo_no_valido)

    def test_price_is_not_a_feature(self):
        result, _ = self.runtime.valorar([BASE, {**BASE, "propertyCode": "higher", "price": 900000},
                                         {**BASE, "propertyCode": "no-price", "price": None}])
        self.assertEqual(len({r["precio_estimado"] for r in result}), 1)
        self.assertIsNone(result[2]["brecha_pct"])
        self.assertAlmostEqual(result[0]["precio_estimado"], 482507.2956710526, places=3)

    def test_rental_compares_monthly_amounts_and_preserves_sale_estimate(self):
        rental = {**BASE, "propertyCode": "rent", "operation": "rent", "price": 1500}
        result, errors = self.runtime.valorar([BASE, rental, {**rental, "propertyCode": "high-rent", "price": 2500},
                                             {**rental, "propertyCode": "no-rent", "price": None}])
        self.assertEqual(errors, [])
        sale, rent, high, missing = result
        self.assertEqual(sale["precio_comparacion"], sale["precio_estimado"])
        self.assertEqual(sale["unidad_comparacion"], "EUR")
        self.assertEqual(rent["operation"], "rent")
        self.assertEqual(rent["unidad_comparacion"], "EUR/mes")
        self.assertEqual(len({r["precio_estimado"] for r in result}), 1)
        self.assertEqual(rent["precio_comparacion"], rent["renta_mensual_estimada"])
        self.assertAlmostEqual(rent["precio_comparacion"], 1362.4487843552, places=5)
        self.assertAlmostEqual(rent["brecha_pct"], (1500 / rent["renta_mensual_estimada"] - 1) * 100)
        self.assertGreater(high["brecha_pct"], 60)
        self.assertIsNone(missing["brecha_pct"])
        self.assertIsNone(rent["intervalo"])
        self.assertIsNone(rent["banda"])
        self.assertFalse(rent["alquiler_validado"])
        native = self.runtime.predictor.predecir([rental]).iloc[0]
        self.assertTrue(native.valido)
        self.assertAlmostEqual(native.anunciado_sobre_estimado, 1500 / native.renta_mensual_estimada)

    def test_input_evidence_and_domains(self):
        for key, changes in {
            "no-description": {"description": None, "parkingSpace": None},
            "no-floor": {"floor": None}, "outside": {"latitude": 41.3851, "longitude": 2.1734},
        }.items():
            with self.subTest(key=key):
                result, errors = self.runtime.valorar([{**BASE, "propertyCode": key, **changes}])
                if key == "outside": self.assertEqual(errors[0]["estado"], "fuera_ambito")
                else:
                    self.assertTrue(result[0]["calidad"]["sin_descripcion" if key == "no-description" else "planta_imputada"])
        result, errors = self.runtime.valorar([BASE, BASE])
        self.assertEqual(result, [])
        self.assertEqual(len(errors), 2)

    def test_description_domain_abstentions_preserve_negations(self):
        for description, reason in [
            ("Vivienda a reformar.", "a_reformar"),
            ("Necesita una reforma integral.", "a_reformar"),
            ("Piso para actualizar.", "a_reformar"),
            ("Vivienda ocupada y sin posesión.", "ocupada"),
            ("Actualmente alquilado con contrato de alquiler vigente.", "ocupada"),
            ("Se vende nuda propiedad.", "ocupada"),
            ("Piso a reformar y ocupado.", "a_reformar;ocupada"),
        ]:
            for operation in ("sale", "rent"):
                with self.subTest(description=description, operation=operation):
                    rows, errors = self.runtime.valorar([{**BASE, "description": description, "operation": operation}])
                    self.assertEqual(rows, [])
                    self.assertEqual(errors[0]["estado"], "fuera_ambito")
                    self.assertEqual(errors[0]["detalle"], reason)
        for description in ["Sin necesidad de reformar.", "No requiere ninguna reforma.",
                            "Piso libre de inquilinos, desocupado.",
                            "Agencia: nuda propiedad - valoración de viviendas."]:
            with self.subTest(description=description):
                rows, errors = self.runtime.valorar([{**BASE, "description": description}])
                self.assertEqual(errors, [])
                self.assertEqual(len(rows), 1)

    def test_new_development_is_a_warning_without_changing_prediction(self):
        rows, errors = self.runtime.valorar([
            {**BASE, "propertyCode": "existing"},
            {**BASE, "propertyCode": "new", "newDevelopment": True},
            {**BASE, "propertyCode": "false", "newDevelopment": False},
            {**BASE, "propertyCode": "null", "newDevelopment": None},
        ])
        self.assertEqual(errors, [])
        self.assertEqual([r["calidad"]["obra_nueva"] for r in rows], [False, True, False, False])
        self.assertEqual(len({r["precio_estimado"] for r in rows}), 1)
        self.assertTrue(any("promoción" in warning for warning in rows[1]["advertencias"]))

    def test_current_model_identity_and_metadata(self):
        health = self.runtime.health()
        self.assertEqual(health["arboles"], 410)
        self.assertEqual(health["exportado"], "2026-09-15T22:56:50")
        self.assertEqual(health["modelo_sha256"], "e5526aca6001741f24eb976dbd9607df131b3822b5b5a01b66c6c92af2a9d748")
        self.assertEqual((health["ano_base"], health["ano_precio"], health["ano_renta"]), (2018, 2025, 2024))

    def test_http_auth_limits_and_json(self):
        from fastapi.testclient import TestClient
        from servicio.api_v3 import app
        with patch.dict(os.environ, {"VALORACION_TOKEN": "synthetic-test-token"}), TestClient(app) as client:
            self.assertEqual(client.get("/salud").json()["model_version"], "3.2.0")
            self.assertEqual(client.get("/salud").json()["operaciones"], ["sale", "rent"])
            self.assertEqual(client.post("/valorar", json={"anuncios": [BASE]}).status_code, 401)
            headers = {"Authorization": "Bearer synthetic-test-token"}
            response = client.post("/valorar", json={"anuncios": [BASE], "explicar": True}, headers=headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["resultados"][0]["propertyCode"], BASE["propertyCode"])
            self.assertNotIn("explicacion", response.json()["resultados"][0])
            self.assertFalse(response.json()["resultados"][0]["calidad"]["obra_nueva"])
            domain = client.post("/valorar", json={"anuncios": [
                {**BASE, "propertyCode": "occupied", "description": "Vivienda ocupada."},
                {**BASE, "propertyCode": "new", "newDevelopment": True},
            ]}, headers=headers).json()
            self.assertEqual(domain["errores"][0]["estado"], "fuera_ambito")
            self.assertTrue(domain["resultados"][0]["calidad"]["obra_nueva"])
            rental = client.post("/valorar", json={"anuncios": [BASE, {**BASE, "propertyCode": "rental-http", "operation": "rent", "price": 1500}]}, headers=headers)
            self.assertEqual(rental.status_code, 200)
            self.assertEqual([r["unidad_comparacion"] for r in rental.json()["resultados"]], ["EUR", "EUR/mes"])
            for rows in ([], [BASE] * 25):
                self.assertEqual(client.post("/valorar", json={"anuncios": rows}, headers=headers).status_code, 422)
            bad = client.post("/valorar", json={"anuncios": [{**BASE, "latitude": None}]}, headers=headers)
            self.assertEqual(bad.status_code, 200)
            self.assertEqual(bad.json()["resultados"], [])
            json.dumps(bad.json(), allow_nan=False)

if __name__ == "__main__":
    unittest.main()
