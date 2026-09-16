#!/usr/bin/env python3
"""Empaqueta una entrega verificada sin credenciales, caches ni datos privados.

El codigo sale exclusivamente de git archive de repositorios limpios. Los seis
artefactos se contrastan con el manifiesto antes de crear ningun ZIP. No publica
ni sobrescribe una entrega existente. Solo utiliza la biblioteca estandar.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path


DOCUMENTS = ("01_HabitIA_memoria.docx", "01_HabitIA_memoria.pdf",
             "02_HabitIA_anexos.docx", "02_HabitIA_anexos.pdf")
ARTIFACTS = {"modelo.json", "metadatos.json", "barrios.parquet",
             "indices_distrito.parquet", "pois.parquet", "variables_barrio.parquet"}


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def public_path(name):
    parts = Path(name).parts
    if any(p in {".git", "node_modules", ".next", "__pycache__", ".DS_Store",
                 "archivo-privado"} or p.startswith(".venv") for p in parts):
        return False
    return not any((p == ".env" or p.startswith(".env.")) and p != ".env.example"
                   or p.endswith((".pem", ".key", ".pyc")) for p in parts)


def archive_files(target, files):
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source, name in sorted(files, key=lambda item: item[1]):
            if not public_path(name):
                raise ValueError(f"Archivo privado o regenerable en entrega: {name}")
            archive.write(source, name)
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise ValueError(f"ZIP danado: {target.name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True,
                        help="Carpeta que contiene ambos repos y habitia_predictor original")
    parser.add_argument("--documents", type=Path, required=True)
    parser.add_argument("--readme", type=Path, required=True, help="00_LEEME.md revisado")
    parser.add_argument("--verification", type=Path, required=True,
                        help="Informes publicables y revisados, sin datos de usuarios")
    parser.add_argument("--metadata", type=Path, required=True,
                        help="JSON con documentos, verificacion, despliegue y precision")
    parser.add_argument("--name", required=True, help="HabitIA_TFM_YYYY-MM-DD-rN")
    parser.add_argument("--tag", required=True, help="tfm-YYYY-MM-DD-rN")
    args = parser.parse_args()
    if not re.fullmatch(r"HabitIA_TFM_\d{4}-\d{2}-\d{2}-r[1-9]\d*", args.name):
        parser.error("Nombre de entrega invalido")
    if args.tag != args.name.replace("HabitIA_TFM_", "tfm-"):
        parser.error("Nombre y tag deben identificar la misma revision")
    workspace = args.workspace.resolve()
    destination = workspace / "entrega" / args.name
    outer_zip = destination.with_suffix(".zip")
    if destination.exists() or outer_zip.exists():
        raise FileExistsError("La entrega ya existe; elija una revision nueva")
    repos = {name: workspace / name for name in ("agente-inmobiliario", "habitia-tfm")}
    commits = {}
    for name, repo in repos.items():
        if git(repo, "status", "--porcelain"):
            raise ValueError(f"El repositorio {name} contiene cambios sin commit")
        commits[name] = git(repo, "rev-parse", "HEAD")
    service = repos["habitia-tfm"] / "servicio"
    manifest = json.loads((service / "manifiesto_v3.json").read_text())
    hashes = manifest["sha256"]
    if set(hashes) != ARTIFACTS:
        raise ValueError("El manifiesto debe contener exactamente los seis artefactos")
    package_hash = hashlib.sha256(json.dumps(hashes, sort_keys=True,
                                            separators=(",", ":")).encode()).hexdigest()
    if package_hash != manifest["paquete_sha256"]:
        raise ValueError("Huella de paquete incoherente")
    original = workspace / "habitia_predictor"
    original_artifacts = original / "data/models/paquete_produccion"
    installed = service / "artefactos_v3"
    for name, expected in hashes.items():
        if any(sha256(folder / name) != expected for folder in (installed, original_artifacts)):
            raise ValueError(f"Artefacto distinto al original: {name}")
    for name, expected in manifest["source_code_sha256"].items():
        if Path(name).name != name or sha256(original / "src" / name) != expected:
            raise ValueError("Codigo original modificado")
    for name in DOCUMENTS:
        doc = args.documents / name
        if doc.suffix == ".pdf":
            with doc.open("rb") as stream:
                if stream.read(5) != b"%PDF-":
                    raise ValueError(f"PDF invalido: {name}")
        else:
            with zipfile.ZipFile(doc) as archive:
                if "word/document.xml" not in archive.namelist() or archive.testzip():
                    raise ValueError(f"DOCX invalido: {name}")
    extra = json.loads(args.metadata.read_text())
    allowed = {"documentos", "verificacion", "despliegue", "precision", "alcance"}
    if set(extra) - allowed:
        raise ValueError("Metadatos extra fuera de los campos permitidos")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".entrega-", dir=destination.parent) as temp:
        staging = Path(temp) / args.name
        staging.mkdir()
        shutil.copy2(args.readme, staging / "00_LEEME.md")
        for name in DOCUMENTS:
            shutil.copy2(args.documents / name, staging / name)
        code = staging / "03_codigo"
        code.mkdir()
        for name, repo in repos.items():
            target = code / f"{name}.zip"
            subprocess.run(["git", "-C", str(repo), "archive", "--format=zip",
                            f"--prefix={name}/", "-o", str(target), commits[name]], check=True)
            with zipfile.ZipFile(target) as archive:
                if archive.testzip() or not all(public_path(n) for n in archive.namelist()):
                    raise ValueError(f"Archivo de codigo no publicable: {name}")
        model = staging / "04_modelo"
        model.mkdir()
        archive_files(model / "habitia-modelo-v3.3.zip",
                      [(installed / name, name) for name in hashes])
        originals = [(original / name, f"habitia_predictor/{name}")
                     for name in ("LEEME.md", "requirements.txt")]
        originals += [(original / "src" / name, f"habitia_predictor/src/{name}")
                      for name in manifest["source_code_sha256"]]
        originals += [(original_artifacts / name,
                       f"habitia_predictor/data/models/paquete_produccion/{name}") for name in hashes]
        archive_files(model / "habitia_predictor_original_2026.zip", originals)
        verification = staging / "05_verificacion"
        verification.mkdir()
        for source in sorted(args.verification.rglob("*")):
            if not source.is_file():
                continue
            relative = source.relative_to(args.verification)
            if source.is_symlink() or not public_path(str(relative)):
                raise ValueError(f"Informe no publicable: {relative}")
            target = verification / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        versions = {
            "fecha_paquete": args.tag[4:14], "revision": int(args.tag.rsplit("-r", 1)[1]),
            "generado_utc": datetime.now(timezone.utc).isoformat(), "repositorios": commits,
            "archivos_codigo": "git archive de los commits indicados, sin credenciales ni dependencias locales",
            "modelo": {"id": manifest["model_id"], "version_http": manifest["model_version"],
                       "paquete_sha256": package_hash, "sha256_artefactos": hashes,
                       "archivo": "04_modelo/habitia-modelo-v3.3.zip",
                       "original": "04_modelo/habitia_predictor_original_2026.zip",
                       "artefactos_recibidos_modificados": False},
            "publicacion_github": {"repositorio": "maupeon/habitia-tfm", "tag": args.tag,
                                   "url": f"https://github.com/maupeon/habitia-tfm/releases/tag/{args.tag}"},
            **extra,
        }
        (staging / "VERSIONES.json").write_text(json.dumps(versions, indent=2, ensure_ascii=False) + "\n")
        files = sorted(p for p in staging.rglob("*") if p.is_file())
        checksums = "".join(f"{sha256(p)}  {p.relative_to(staging).as_posix()}\n" for p in files)
        (staging / "SHA256SUMS.txt").write_text(checksums)
        archive_files(Path(temp) / outer_zip.name,
                      [(p, f"{args.name}/{p.relative_to(staging).as_posix()}")
                       for p in staging.rglob("*") if p.is_file()])
        staging.rename(destination)
        (Path(temp) / outer_zip.name).rename(outer_zip)
    print(json.dumps({"carpeta": str(destination), "zip": str(outer_zip),
                      "zip_sha256": sha256(outer_zip), "repositorios": commits}, indent=2))


if __name__ == "__main__":
    main()
