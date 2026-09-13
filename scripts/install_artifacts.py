"""Instala únicamente el artefacto identificado por el manifiesto del repositorio."""
from pathlib import Path
import argparse
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'servicio'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', nargs='?', type=Path)
    parser.add_argument('--check', action='store_true', help='Solo comprobar archivos instalados')
    args = parser.parse_args()
    manifest = (TARGET / 'manifiesto.json').read_bytes()
    expected = {**json.loads(manifest)['sha256'], 'manifiesto.json': digest(manifest)}
    if args.check:
        if args.archive:
            parser.error('--check no admite un ZIP')
        for name, sha in expected.items():
            path = TARGET / name
            if not path.is_file() or digest(path.read_bytes()) != sha:
                raise SystemExit(f'Artefacto ausente o distinto: {name}')
        print('Integridad correcta: manifiesto, pipeline y tres modelos v2')
        return
    if not args.archive:
        parser.error('Indique habitia-modelo-v2.zip o --check')
    with zipfile.ZipFile(args.archive) as archive:
        names = archive.namelist()
        if len(names) != len(expected) or set(names) != set(expected):
            raise SystemExit('ZIP inesperado: debe contener exactamente los cinco archivos del artefacto')
        content = {}
        for name, sha in expected.items():
            if archive.getinfo(name).file_size > 20_000_000:
                raise SystemExit(f'Archivo excesivo: {name}')
            data = archive.read(name)
            if digest(data) != sha:
                raise SystemExit(f'Hash incorrecto: {name}; no se ha instalado ningún archivo')
            content[name] = data
    # Validar el conjunto completo antes de modificar el destino.
    for name, data in content.items():
        path = TARGET / name
        if path.is_symlink():
            raise SystemExit(f'El destino no puede ser un enlace: {name}')
        if path.exists() and path.read_bytes() != data:
            raise SystemExit(f'Ya existe otro artefacto en {name}; consérvelo antes de instalar')
    for name, data in content.items():
        path = TARGET / name
        if not path.exists():
            path.write_bytes(data)
    print('Instalación verificada: modelo habitIA-oferta-2018-v2, versión 2.0.0')


if __name__ == '__main__':
    main()
