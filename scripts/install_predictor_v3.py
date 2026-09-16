"""Instala exclusivamente los seis archivos verificados del predictor XGBoost."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile
import shutil
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def verificar(directory: Path, manifest: dict[str, str]):
    for name, expected in manifest.items():
        with (directory / name).open("rb") as artifact:
            actual = hashlib.file_digest(artifact, "sha256").hexdigest()
        if actual != expected:
            raise ValueError(f"Hash incorrecto: {name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, nargs="?", help="ZIP, carpeta habitia_predictor o carpeta con los seis artefactos")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--target", type=Path, help="Destino; por defecto VALORACION_ARTIFACTS_V3 o servicio/artefactos_v3")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "servicio/manifiesto_v3.json").read_text())["sha256"]
    target = (args.target or Path(os.getenv("VALORACION_ARTIFACTS_V3") or ROOT / "servicio/artefactos_v3")).resolve()
    if args.check:
        verificar(target, manifest)
        print("Seis artefactos v3 verificados")
        return
    if not args.source:
        parser.error("Indica el ZIP o la carpeta del modelo, o utiliza --check")
    target.parent.mkdir(parents=True, exist_ok=True)
    # Preparar y verificar en el mismo sistema de archivos permite sustituir
    # la carpeta completa, sin mezclar artefactos si falla una copia.
    with tempfile.TemporaryDirectory(prefix=".artefactos-v3-", dir=target.parent) as temp:
        staged = Path(temp) / "nuevo"
        staged.mkdir()
        if args.source.is_dir():
            source = args.source
            if (source / "data/models/paquete_produccion").is_dir():
                source = source / "data/models/paquete_produccion"
            for name in manifest:
                shutil.copyfile(source / name, staged / name)
        else:
            with zipfile.ZipFile(args.source) as archive:
                for name in manifest:
                    matches = [p for p in archive.namelist() if Path(p).name == name and not p.startswith("__MACOSX/")]
                    if len(matches) != 1:
                        raise ValueError(f"Archivo ausente o ambiguo: {name}")
                    with archive.open(matches[0]) as origin, (staged / name).open("wb") as destination:
                        shutil.copyfileobj(origin, destination)
        # Se verifica el lote completo antes de sustituir ningún artefacto instalado.
        verificar(staged, manifest)
        # Si hasta la restauración fallase, conservar el respaldo fuera del
        # temporal impide que su limpieza borre la instalación anterior.
        backup = target.parent / f".{target.name}.anterior-{uuid4().hex}"
        if target.exists():
            if not target.is_dir():
                raise ValueError(f"El destino no es una carpeta: {target}")
            # La carpeta de artefactos es exclusiva del instalador. No eliminar
            # contenido ajeno al paquete en un destino indicado por accidente.
            unexpected = {entry.name for entry in target.iterdir()} - set(manifest)
            if unexpected:
                raise ValueError("El destino contiene archivos ajenos al paquete: " + ", ".join(sorted(unexpected)))
            target.rename(backup)
        try:
            staged.rename(target)
        except OSError:
            if backup.exists():
                backup.rename(target)
            raise
        else:
            if backup.exists():
                shutil.rmtree(backup)
    print("Predictor v3 instalado y verificado")

if __name__ == "__main__":
    main()
