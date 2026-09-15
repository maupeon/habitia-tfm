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
    parser.add_argument("zip", type=Path, nargs="?")
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
    if not args.zip:
        parser.error("Indica el ZIP del modelo o utiliza --check")
    with tempfile.TemporaryDirectory() as temp, zipfile.ZipFile(args.zip) as archive:
        for name, expected in manifest.items():
            matches = [p for p in archive.namelist() if Path(p).name == name and not p.startswith("__MACOSX/")]
            if len(matches) != 1:
                raise ValueError(f"Archivo ausente o ambiguo: {name}")
            payload = archive.read(matches[0])
            if hashlib.sha256(payload).hexdigest() != expected:
                raise ValueError(f"Hash incorrecto: {name}")
            (Path(temp) / name).write_bytes(payload)
        target.mkdir(parents=True, exist_ok=True)
        for name in manifest:
            shutil.copyfile(Path(temp) / name, target / name)
    print("Predictor v3 instalado y verificado")

if __name__ == "__main__":
    main()
