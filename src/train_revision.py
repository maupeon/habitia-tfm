"""Evaluación retrospectiva y exportación del modelo de oferta de HabitIA.

Ejecutar desde cualquier directorio:
    python src/train_revision.py --output revision_2026-09-08/experimento

No carga parámetros ni métricas de los experimentos antiguos. El ajuste,
selección, calibración y evaluación tienen grupos de inmuebles separados.
El notebook del proyecto explica y llama estas mismas funciones.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import time

# Importar sklearn primero evita el conflicto OpenMP observado en este Mac.
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold, GroupShuffleSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
import lightgbm as lgb
import numpy as np
import pandas as pd

from model_pipeline import ModelPipeline, historical_eligibility, historical_to_payloads
from revision_data import load_revision_data, asset_weights
from valorador import conformal_log_interval

ROOT = Path(__file__).resolve().parents[1]
MODEL_VERSION = "habitIA-oferta-2018-v2"
CONFIG = {
    "version": MODEL_VERSION, "seed": 17, "outer_folds": 3, "inner_folds": 3,
    "calibration_fraction": 0.20, "alpha": 0.10, "trees": 600,
    "learning_rate": 0.05, "n_jobs": 2,
    "lightgbm_candidates": [{"num_leaves": n, "min_child_samples": m}
                            for n in [15, 31, 63] for m in [30, 100]],
    "ridge_alphas": [1.0, 10.0, 100.0],
    "selection_metric": "MdAPE_pct por observación; pesos iguales por activo al ajustar",
    "calibration_unit": "máximo residual conformal por ASSETID",
    "historical_data_already_explored": True,
    "support_distance_km": 1.0,
}


def json_default(obj):
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, (Path, datetime)):
        return str(obj)
    raise TypeError(type(obj).__name__)


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    default=json_default, allow_nan=False), encoding="utf-8")


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare_data(path=None):
    """Aplica únicamente criterios fijos, conservando rastro de exclusiones."""
    data, audit = load_revision_data(path)
    keep, reasons = historical_eligibility(data)
    audit["exclusiones_contrato_compartido"] = reasons
    data = data.loc[keep].reset_index(drop=True)
    audit["filas_elegibles_pipeline"] = len(data)
    audit["activos_elegibles_pipeline"] = data.ASSETID.nunique()
    audit["periodos_elegibles"] = {str(k): int(v) for k, v in data.PERIOD.value_counts().sort_index().items()}
    return data, audit


def weighted_median(values, weights):
    values, weights = np.asarray(values, float), np.asarray(weights, float)
    order = np.argsort(values, kind="stable")
    return float(values[order][np.searchsorted(np.cumsum(weights[order]), weights.sum() / 2)])


class TerritorialBaseline:
    """Mediana ponderada de €/m² por barrio; distrito/global para zona desconocida."""
    def fit(self, x, price, weights):
        d = pd.DataFrame({"barrio": x.barrio.astype(str).to_numpy(),
                          "distrito": x.distrito.astype(str).to_numpy(),
                          "unit": np.asarray(price) / x.CONSTRUCTEDAREA.to_numpy(),
                          "weight": weights})
        self.global_ = weighted_median(d.unit, d.weight)
        self.tables = {col: {str(key): weighted_median(g.unit, g.weight)
                            for key, g in d.groupby(col, observed=True)}
                       for col in ["barrio", "distrito"]}
        return self

    def predict(self, x):
        unit = [self.tables["barrio"].get(str(b), self.tables["distrito"].get(str(d), self.global_))
                for b, d in zip(x.barrio, x.distrito)]
        return np.asarray(unit) * x.CONSTRUCTEDAREA.to_numpy()


def ridge_matrix(x):
    """Transformaciones deterministas compartidas para la referencia hedónica."""
    z = x.copy()
    for c in ["CONSTRUCTEDAREA", "m2_por_habitacion", "DISTANCE_TO_CITY_CENTER"]:
        z[c] = np.log1p(z[c])
    return z


def make_ridge(x, alpha):
    cats = [c for c in x if isinstance(x[c].dtype, pd.CategoricalDtype)]
    nums = [c for c in x if c not in cats]
    prep = ColumnTransformer([
        ("numericas", make_pipeline(SimpleImputer(strategy="median"), StandardScaler()), nums),
        ("categoricas", OneHotEncoder(handle_unknown="ignore", sparse_output=True), cats),
    ])
    return make_pipeline(prep, Ridge(alpha=float(alpha), solver="lsqr"))


def make_lgb(params, config, quantile=None):
    args = dict(n_estimators=config["trees"], learning_rate=config["learning_rate"],
                objective="regression_l1" if quantile is None else "quantile",
                reg_lambda=1.0, random_state=config["seed"], n_jobs=config["n_jobs"],
                verbosity=-1, deterministic=True, force_col_wise=True, **params)
    if quantile is not None:
        args["alpha"] = quantile
    return lgb.LGBMRegressor(**args)


def group_calibration_split(data, fraction, seed):
    fit, cal = next(GroupShuffleSplit(n_splits=1, test_size=fraction, random_state=seed)
                    .split(data, groups=data.ASSETID))
    return data.iloc[fit].reset_index(drop=True), data.iloc[cal].reset_index(drop=True)


def assert_group_separation(**parts):
    sets = {name: set(d.ASSETID) for name, d in parts.items()}
    names = list(sets)
    for i, a in enumerate(names):
        for b in names[i+1:]:
            shared = sets[a] & sets[b]
            if shared:
                raise AssertionError(f"Fuga entre {a} y {b}: {len(shared)} activos")
    return {name: {"filas": len(parts[name]), "activos": len(sets[name])} for name in sets}


def supported_data(pipeline, data):
    """Selecciona sin ver PRICE y devuelve también el registro de abstenciones."""
    meta = pd.DataFrame(pipeline.metadata(data, enforce_support=False))
    mask = meta.distancia_soporte_km.le(pipeline.max_support_distance_km).to_numpy()
    accepted = data.loc[mask].reset_index(drop=True)
    rejected = data.loc[~mask, ["source_row_id", "ASSETID", "PERIOD"]].copy()
    rejected["motivo"] = "distancia al soporte territorial de entrenamiento superior a 1 km"
    rejected["distancia_km"] = meta.loc[~mask, "distancia_soporte_km"].to_numpy()
    return accepted, rejected, meta.loc[mask].reset_index(drop=True)


def metric_values(y, pred, groups=None, lo=None, hi=None):
    y, pred = np.asarray(y, float), np.asarray(pred, float)
    if not len(y):
        return {"n": 0}
    ape = np.abs(pred - y) / y
    r = {"n": len(y), "MdAPE_pct": float(np.median(ape) * 100),
         "MAPE_pct": float(ape.mean() * 100), "MAE_eur": float(np.abs(pred-y).mean()),
         "MdAE_eur": float(np.median(np.abs(pred-y))),
         "sesgo_mediano_pct": float(np.median((pred-y)/y) * 100),
         "dentro_10_pct": float(np.mean(ape <= .10) * 100),
         "dentro_20_pct": float(np.mean(ape <= .20) * 100)}
    if groups is not None:
        series = pd.Series(ape).groupby(np.asarray(groups)).median()
        r["n_activos"] = int(len(series))
        r["mediana_APE_mediano_por_activo_pct"] = float(series.median() * 100)
    if lo is not None:
        lo, hi = np.asarray(lo), np.asarray(hi)
        covered = (lo <= y) & (y <= hi)
        r.update(cobertura_pct=float(covered.mean()*100),
                 anchura_mediana_eur=float(np.median(hi-lo)),
                 anchura_relativa_mediana_pct=float(np.median((hi-lo)/y)*100),
                 puntos_fuera_intervalo=int(((pred<lo)|(pred>hi)).sum()),
                 intervalos_invertidos=int((lo>hi).sum()))
        if groups is not None:
            r["cobertura_activos_todos_registros_pct"] = float(
                pd.Series(covered).groupby(np.asarray(groups)).all().mean()*100)
    return r


def select_parameters(fit, config, label):
    """Selección interna; prepara de nuevo las variables dentro de cada fold."""
    rows, split_records = [], []
    folds = GroupKFold(n_splits=config["inner_folds"], shuffle=True, random_state=config["seed"])
    for k, (ia, ib) in enumerate(folds.split(fit, groups=fit.ASSETID)):
        train, valid = fit.iloc[ia].reset_index(drop=True), fit.iloc[ib].reset_index(drop=True)
        separation = assert_group_separation(train=train, valid=valid)
        pipeline = ModelPipeline(max_support_distance_km=config["support_distance_km"]).fit(train)
        valid, rejected, _ = supported_data(pipeline, valid)
        xtr = pipeline.transform(train, enforce_support=False)
        xva = pipeline.transform(valid)
        ytr = np.log(train.PRICE.to_numpy(float))
        weights = np.asarray(asset_weights(train), float)
        split_records.append({"fold": k, "particiones": separation, "abstenciones": len(rejected)})
        for j, params in enumerate(config["lightgbm_candidates"]):
            model = make_lgb(params, config).fit(xtr, ytr, sample_weight=weights)
            m = metric_values(valid.PRICE, np.exp(model.predict(xva)))
            rows.append({"fold": k, "familia": "LightGBM", "candidato": j, **m})
        rxtr, rxva = ridge_matrix(xtr), ridge_matrix(xva)
        for j, alpha in enumerate(config["ridge_alphas"]):
            model = make_ridge(rxtr, alpha).fit(rxtr, ytr, ridge__sample_weight=weights)
            m = metric_values(valid.PRICE, np.exp(model.predict(rxva)))
            rows.append({"fold": k, "familia": "Hedónico Ridge", "candidato": j, **m})
        print(f"[{label}] selección interna {k+1}/{config['inner_folds']} terminada", flush=True)
    scores = pd.DataFrame(rows).groupby(["familia", "candidato"]).MdAPE_pct.mean()
    li = int(scores.loc["LightGBM"].idxmin())
    ri = int(scores.loc["Hedónico Ridge"].idxmin())
    return {"lightgbm": config["lightgbm_candidates"][li], "ridge_alpha": config["ridge_alphas"][ri],
            "resultados_internos": rows, "particiones_internas": split_records,
            "regla": "menor media de MdAPE en folds internos; empate por orden predefinido"}


def raw_log_intervals(point_model, lower, upper, x):
    point = point_model.predict(x)
    lo, hi = conformal_log_interval(point, lower.predict(x), upper.predict(x), 0.0)
    return point, lo, hi


def calibrate_groups(ylog, point, lo, hi, groups, alpha):
    scores = np.maximum(lo-np.asarray(ylog), np.asarray(ylog)-hi)
    grouped = pd.Series(scores).groupby(np.asarray(groups)).max().to_numpy()
    rank = int(math.ceil((len(grouped)+1)*(1-alpha)))
    if rank > len(grouped):
        raise ValueError("Insuficientes activos para la calibración finita solicitada")
    q = max(0.0, float(np.sort(grouped)[rank-1]))
    return q, {"metodo": "CQR con máximo residual por activo", "unidad": "ASSETID",
               "alpha": alpha, "n_activos": len(grouped), "n_observaciones": len(scores),
               "rango_orden": rank, "Q_log": q, "incluye_punto_antes_calibrar": True,
               "garantia_individual_2026": False}


def fit_and_evaluate(fit, cal, test, selected, config, label, destination=None):
    """Modelos y transformaciones se ajustan sin datos de calibración/evaluación."""
    partitions = assert_group_separation(fit=fit, calibracion=cal, evaluacion=test)
    pipeline = ModelPipeline(max_support_distance_km=config["support_distance_km"]).fit(fit)
    cal, rejected_cal, _ = supported_data(pipeline, cal)
    test, rejected_test, meta = supported_data(pipeline, test)
    xtr = pipeline.transform(fit, enforce_support=False)
    xcal, xte = pipeline.transform(cal), pipeline.transform(test)
    weights = np.asarray(asset_weights(fit), float)
    ylog = np.log(fit.PRICE.to_numpy(float))
    point = make_lgb(selected["lightgbm"], config).fit(xtr, ylog, sample_weight=weights)
    qs = [make_lgb(selected["lightgbm"], config, quantile=q).fit(xtr, ylog, sample_weight=weights)
          for q in [config["alpha"]/2, 1-config["alpha"]/2]]
    cp, cl, ch = raw_log_intervals(point, *qs, xcal)
    q, calibration = calibrate_groups(np.log(cal.PRICE.to_numpy(float)), cp, cl, ch,
                                      cal.ASSETID, config["alpha"])
    p, low, high = raw_log_intervals(point, *qs, xte)
    baseline = TerritorialBaseline().fit(xtr, fit.PRICE, weights)
    ridge = make_ridge(ridge_matrix(xtr), selected["ridge_alpha"])
    ridge.fit(ridge_matrix(xtr), ylog, ridge__sample_weight=weights)
    output = test[["source_row_id", "ASSETID", "PERIOD", "PRICE", "CONSTRUCTEDAREA", "barrio", "distrito"]].copy()
    output["fold"] = label
    output["pred_baseline"] = baseline.predict(xte)
    output["pred_ridge"] = np.exp(ridge.predict(ridge_matrix(xte)))
    output["pred_lgb"] = np.exp(p)
    output["limite_inferior"] = np.exp(low-q)
    output["limite_superior"] = np.exp(high+q)
    output["barrio_inferido"] = meta.barrio.to_numpy()
    output["distancia_soporte_km"] = meta.distancia_soporte_km.to_numpy()
    metrics = summarize_predictions(output)
    result = {"particiones": partitions, "seleccion": selected, "calibracion": calibration,
              "metricas": metrics, "abstenciones_evaluacion": len(rejected_test),
              "abstenciones_calibracion": len(rejected_cal), "n_features": len(xtr.columns)}
    # SHAP nativo del modelo evaluado: magnitudes en log euros, sin causalidad.
    take = np.random.default_rng(config["seed"]).choice(len(xte), min(1000, len(xte)), replace=False)
    contributions = point.booster_.predict(xte.iloc[take], pred_contrib=True)
    result["shap"] = {"n": len(take), "unidad": "contribución en log euros",
                      "media_absoluta": dict(zip(xte.columns, np.abs(contributions[:, :-1]).mean(axis=0)))}
    if destination is not None:
        dest = Path(destination)
        dest.mkdir(parents=True, exist_ok=True)
        pipeline.save(dest/"pipeline.json")
        point.booster_.save_model(str(dest/"modelo_precio.txt"))
        qs[0].booster_.save_model(str(dest/"modelo_q_lo.txt"))
        qs[1].booster_.save_model(str(dest/"modelo_q_hi.txt"))
        # Este artefacto es exactamente el de la partición final reservada.
        # No se reajusta sobre su evaluación después de publicar la métrica.
        manifest = {"version": "2.0.0", "model_id": MODEL_VERSION, "schema_version": 2, "pipeline": "pipeline.json",
                    "columnas": pipeline.columns, "categoricas": pipeline.categoricals,
                    "smearing": 1.0, "conformal_Q": q, "alpha": config["alpha"],
                    "calibracion": calibration, "periodo_entrenamiento": "2018",
                    "objetivo": "precio anunciado; mediana condicional aproximada en escala log",
                    "tipo_evaluacion": "retrospectiva agrupada; histórico previamente explorado",
                    "metricas_test": metrics["LightGBM"], "particiones": partitions,
                    "renivelado": {"factor": 1.5534, "periodo": "2026T1", "base": "2018",
                                   "fuente": "IPV INE Comunidad de Madrid segunda mano; escenario heredado",
                                   "es_escenario": True, "validado_2026": False,
                                   "actualizacion_automatica": False},
                    "alquiler": {"referencia_verificada": False},
                    "limitaciones": ["Precios de oferta perturbados, no transacciones",
                                     "Coordenadas desplazadas; sección aproximada",
                                     "Tipología bruta histórica no disponible; adaptador con supuestos",
                                     "Datos de 2018 ya explorados; sin validación externa en 2026"]}
        manifest["sha256"] = {f: fingerprint(dest/f) for f in
                               ["pipeline.json", "modelo_precio.txt", "modelo_q_lo.txt", "modelo_q_hi.txt"]}
        write_json(dest/"manifiesto.json", manifest)
        pd.DataFrame({"source_row_id": fit.source_row_id, "ASSETID": fit.ASSETID,
                      "parte": "fit"}).to_csv(dest/"fit_ids.csv", index=False)
        cal[["source_row_id", "ASSETID"]].to_csv(dest/"calibracion_ids.csv", index=False)
        # Paridad del contrato usando exactamente los modelos exportados.
        sample = test.head(25)
        sx = pipeline.transform(sample)
        px = pipeline.transform(historical_to_payloads(sample))
        pd.testing.assert_frame_equal(sx, px)
        loaded = ModelPipeline.load(dest/"pipeline.json")
        pd.testing.assert_frame_equal(sx, loaded.transform(sample))
        result["paridad_transformacion"] = {"casos": len(sample), "igualdad_exacta": True}
    return output, result, rejected_test


def summarize_predictions(frame):
    return {name: metric_values(frame.PRICE, frame[col], frame.ASSETID,
                               frame.limite_inferior if name == "LightGBM" else None,
                               frame.limite_superior if name == "LightGBM" else None)
            for name, col in [("Referencia territorial", "pred_baseline"),
                              ("Hedónico Ridge", "pred_ridge"), ("LightGBM", "pred_lgb")]}


def segment_metrics(frame):
    result = {}
    for key in ["distrito", "PERIOD"]:
        result[key] = [{"segmento": str(label), **metric_values(g.PRICE, g.pred_lgb, g.ASSETID,
                                        g.limite_inferior, g.limite_superior)}
                       for label, g in frame.groupby(key, observed=True, sort=True)]
    d = frame.copy()
    # Descripción posterior a la evaluación: no afecta fit ni selección.
    d["decil_precio"] = pd.qcut(d.PRICE, 10, labels=False, duplicates="drop") + 1
    result["decil_precio"] = [{"segmento": int(label), "precio_min": float(g.PRICE.min()),
                               "precio_max": float(g.PRICE.max()),
                               **metric_values(g.PRICE, g.pred_lgb, g.ASSETID,
                                               g.limite_inferior, g.limite_superior)}
                              for label, g in d.groupby("decil_precio", sort=True)]
    return result


def bootstrap_by_asset(frame, repetitions=400, seed=17):
    """IC descriptivos por remuestreo de activos completos, sin mezclar sus filas."""
    codes, unique = pd.factorize(frame.ASSETID, sort=True)
    order = np.argsort(codes, kind="stable")
    groups = np.split(order, np.flatnonzero(np.diff(codes[order]))+1)
    rng = np.random.default_rng(seed)
    y, p = frame.PRICE.to_numpy(), frame.pred_lgb.to_numpy()
    baseline = frame.pred_baseline.to_numpy()
    covered = ((frame.limite_inferior <= frame.PRICE) & (frame.PRICE <= frame.limite_superior)).to_numpy()
    values = []
    for _ in range(repetitions):
        take = np.concatenate([groups[i] for i in rng.integers(0, len(unique), len(unique))])
        mdape = np.median(np.abs(p[take]-y[take])/y[take])*100
        base = np.median(np.abs(baseline[take]-y[take])/y[take])*100
        values.append([mdape, base-mdape, covered[take].mean()*100])
    arr = np.asarray(values)
    return {"unidad": "ASSETID", "repeticiones": repetitions, "tipo": "percentil 95 % descriptivo",
            "alcance": "variación de observaciones evaluadas; no incluye toda la incertidumbre del ajuste",
            **{name: np.quantile(arr[:, j], [.025, .975]).tolist()
               for j, name in enumerate(["MdAPE_pct", "mejora_frente_baseline_pp", "cobertura_pct"])}}


def evaluate_nested(data, config, output):
    output = Path(output)
    fold_results, predictions, rejected = [], [], []
    folds = GroupKFold(n_splits=config["outer_folds"], shuffle=True, random_state=config["seed"])
    assignments = []
    for k, (idev, itest) in enumerate(folds.split(data, groups=data.ASSETID)):
        dev, test = data.iloc[idev].reset_index(drop=True), data.iloc[itest].reset_index(drop=True)
        fit, cal = group_calibration_split(dev, config["calibration_fraction"], config["seed"]+k)
        for label, d in [("fit", fit), ("calibracion", cal), ("evaluacion", test)]:
            ids = d[["source_row_id", "ASSETID"]].copy()
            ids["fold"], ids["parte"] = k, label
            assignments.append(ids)
        print(f"[exterior {k+1}] fit={len(fit)} cal={len(cal)} test={len(test)}", flush=True)
        selected = select_parameters(fit, config, f"exterior {k+1}")
        pred, result, reject = fit_and_evaluate(fit, cal, test, selected, config, f"exterior_{k}")
        predictions.append(pred)
        rejected.append(reject.assign(fold=k))
        fold_results.append(result)
        write_json(output/f"fold_{k}.json", result)
        print(f"[exterior {k+1}] {result['metricas']}", flush=True)
    frame = pd.concat(predictions, ignore_index=True)
    frame.to_parquet(output/"predicciones_exteriores.parquet", index=False)
    pd.concat(assignments, ignore_index=True).to_parquet(output/"particiones_exteriores.parquet", index=False)
    pd.concat(rejected, ignore_index=True).to_csv(output/"abstenciones_exteriores.csv", index=False)
    return {"folds": fold_results, "metricas": summarize_predictions(frame),
            "segmentos": segment_metrics(frame), "bootstrap": bootstrap_by_asset(frame),
            "n_elegibles": len(data), "n_evaluadas": len(frame),
            "abstenciones": sum(len(d) for d in rejected)}, frame


def evaluate_final_artifact(data, config, output):
    """Reserva fija histórica para evaluar exactamente el artefacto exportado."""
    dev, test = group_calibration_split(data, .20, config["seed"]+100)
    fit, cal = group_calibration_split(dev, config["calibration_fraction"], config["seed"]+101)
    selected = select_parameters(fit, config, "artefacto final")
    pred, result, rejected = fit_and_evaluate(fit, cal, test, selected, config, "artefacto_final",
                                             Path(output)/"artefacto")
    pred.to_parquet(Path(output)/"predicciones_artefacto.parquet", index=False)
    rejected.to_csv(Path(output)/"abstenciones_artefacto.csv", index=False)
    result["nota"] = "Partición retrospectiva fija; reutiliza datos antes explorados, no prueba externa nueva"
    result["segmentos"] = segment_metrics(pred)
    result["bootstrap"] = bootstrap_by_asset(pred)
    return result, pred


def evaluate_temporal(data, config, output):
    """Todo el ajuste y la elección de parámetros usa Q1–Q3; Q4 solo se evalúa."""
    development = data[data.PERIOD < 201812].reset_index(drop=True)
    test = data[data.PERIOD == 201812].reset_index(drop=True)
    fit, cal = group_calibration_split(development, config["calibration_fraction"], config["seed"]+200)
    selected = select_parameters(fit, config, "temporal")
    pred, result, rejected = fit_and_evaluate(fit, cal, test, selected, config, "temporal")
    pred.to_parquet(Path(output)/"predicciones_temporales.parquet", index=False)
    rejected.to_csv(Path(output)/"abstenciones_temporales.csv", index=False)
    result["nota"] = "Diagnóstico temporal retrospectivo corregido; Q4 ya fue explorado anteriormente"
    result["segmentos"] = segment_metrics(pred)
    return result, pred


def run_experiment(output=None, config=None, temporal=True):
    output = Path(output or ROOT/"revision_2026-09-08"/"experimento")
    output.mkdir(parents=True, exist_ok=True)
    config = dict(CONFIG if config is None else config)
    start = time.time()
    config_hash = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    if (output/"resultados_revision.json").exists():
        raise FileExistsError("Resultados ya presentes; use otro --output para no sobrescribir evidencia")
    write_json(output/"configuracion.json", config)
    data, audit = prepare_data()
    write_json(output/"datos_audit.json", audit)
    print(f"Datos elegibles: {len(data)} observaciones, {data.ASSETID.nunique()} activos", flush=True)
    nested, _ = evaluate_nested(data, config, output)
    final, _ = evaluate_final_artifact(data, config, output)
    temporal_result = evaluate_temporal(data, config, output)[0] if temporal else None
    result = {"version": MODEL_VERSION, "created_at": datetime.now(timezone.utc).isoformat(),
              "configuracion": config, "config_sha256": config_hash, "datos": audit,
              "evaluacion_exterior": nested, "artefacto_final": final, "temporal": temporal_result,
              "duracion_segundos": round(time.time()-start, 2),
              "entorno": {"python": platform.python_version(), "plataforma": platform.platform(),
                           **{p: importlib.metadata.version(p) for p in
                              ["numpy", "pandas", "scikit-learn", "lightgbm", "pyarrow", "scipy"]}},
              "codigo_sha256": {p: fingerprint(ROOT/"src"/p) for p in
                                  ["train_revision.py", "model_pipeline.py", "revision_data.py"]}}
    write_json(output/"resultados_revision.json", result)
    print(f"Experimento terminado en {(time.time()-start)/60:.1f} minutos: {output}", flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT/"revision_2026-09-08"/"experimento")
    parser.add_argument("--sin-temporal", action="store_true")
    args = parser.parse_args()
    run_experiment(args.output, temporal=not args.sin_temporal)
