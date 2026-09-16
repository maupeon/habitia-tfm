"""Instala exclusivamente los seis archivos verificados del predictor XGBoost."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile
import shutil

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, nargs="?", help="ZIP, carpeta habitia_predictor o carpeta con los seis artefactos")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "servicio/manifiesto_v3.json").read_text())["sha256"]
    target = ROOT / "servicio/artefactos_v3"
    if args.check:
        for name, expected in manifest.items():
            if hashlib.sha256((target / name).read_bytes()).hexdigest() != expected:
                raise ValueError(f"Hash incorrecto: {name}")
        print("Seis artefactos v3 verificados")
        return
    if not args.source:
        parser.error("Indica el ZIP o la carpeta del modelo, o utiliza --check")
    with tempfile.TemporaryDirectory() as temp:
        if args.source.is_dir():
            source = args.source
            if (source / "data/models/paquete_produccion").is_dir():
                source = source / "data/models/paquete_produccion"
            for name in manifest:
                (Path(temp) / name).write_bytes((source / name).read_bytes())
        else:
            with zipfile.ZipFile(args.source) as archive:
                for name in manifest:
                    matches = [p for p in archive.namelist() if Path(p).name == name and not p.startswith("__MACOSX/")]
                    if len(matches) != 1:
                        raise ValueError(f"Archivo ausente o ambiguo: {name}")
                    (Path(temp) / name).write_bytes(archive.read(matches[0]))
        # Se verifica el lote completo antes de sustituir ningún artefacto instalado.
        for name, expected in manifest.items():
            if hashlib.sha256((Path(temp) / name).read_bytes()).hexdigest() != expected:
                raise ValueError(f"Hash incorrecto: {name}")
        target.mkdir(parents=True, exist_ok=True)
        for name in manifest:
            shutil.copyfile(Path(temp) / name, target / name)
    print("Predictor v3 instalado y verificado")

if __name__ == "__main__":
    main()
