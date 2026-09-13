"""Genera un cuaderno Colab y su ZIP privado a partir de la entrega canónica.

Uso: python scripts/build_colab.py PAQUETE_PRIVADO.zip DIRECTORIO_SALIDA
Los datos solo van al directorio de salida, nunca al repositorio.
"""
from pathlib import Path, PurePosixPath
import argparse
import copy
import hashlib
import json
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DATA_SHA = '7c20dce686fb415430660167f092eb3e0ab44dae2e1221bc3db61fd94d3600ca'


def cell(kind, source, ident):
    result = {'cell_type': kind, 'id': ident, 'metadata': {},
              'source': source.splitlines(keepends=True)}
    if kind == 'code':
        result.update(execution_count=None, outputs=[])
    return result


def build(private_archive, output):
    output = output.resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('El paquete con datos debe guardarse fuera del repositorio.')
    output.mkdir(parents=True, exist_ok=True)
    # Solo archivos explícitamente necesarios, sin entornos, secretos ni historial Git.
    members = {}
    for directory in ['src', 'tests', 'servicio', 'docs']:
        tracked = subprocess.check_output(
            ['git', 'ls-files', '-z', directory], cwd=ROOT).decode().split('\0')
        for name in filter(None, tracked):
            members[name] = (ROOT / name).read_bytes()
    for name in ['README.md', 'requirements_revision.txt', 'TFM_HabitIA_entrenamiento.ipynb']:
        members[name] = (ROOT / name).read_bytes()
    with zipfile.ZipFile(private_archive) as archive:
        for name in archive.namelist():
            if name == 'LEEME.txt':
                continue
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or '\\' in name:
                raise ValueError('Ruta de ZIP no admitida: ' + name)
            if not (name.startswith('data/') or name.startswith('revision_2026-09-08/experimento/')):
                raise ValueError('Contenido privado inesperado: ' + name)
            members[name] = archive.read(name)
    if hashlib.sha256(members['data/habitia_madrid_2018.parquet']).hexdigest() != DATA_SHA:
        raise ValueError('El parquet no coincide con el del estudio.')
    provenance = {
        'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
        'sha256': {name: hashlib.sha256(data).hexdigest() for name, data in sorted(members.items())},
        'purpose': 'Prueba privada en Google Colab; no reentrena ni publica datos.'}
    members['COLAB_MANIFIESTO.json'] = json.dumps(provenance, indent=2).encode()
    archive_path = output / 'HabitIA_Colab_datos_y_codigo.zip'
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(members.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 13, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    archive_sha = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    scientific = [line for line in (ROOT / 'requirements_revision.txt').read_text().splitlines()
                  if line.split('==')[0] in ['numpy', 'pandas', 'scipy', 'scikit-learn',
                                            'lightgbm', 'pyarrow', 'matplotlib']]
    requirements = dict(line.split('==') for line in scientific)
    intro = '''# HabitIA · probar el estudio en Google Colab

Esta copia ejecuta las tablas, los gráficos y las comprobaciones del estudio de 2018 con el experimento guardado. **No inicia un entrenamiento nuevo.** Las salidas aparecen al ejecutar las celdas.

1. En **Entorno de ejecución → Cambiar tipo de entorno de ejecución**, elige **CPU** y la versión **2026.07** (Python 3.12).
2. Pulsa **Ejecutar todo**. Cuando aparezca el selector, carga **HabitIA_Colab_datos_y_codigo.zip**, facilitado por el equipo. Contiene el código, los datos y los modelos de esta prueba.
3. Si la instalación pide reiniciar, selecciona **Entorno de ejecución → Reiniciar la sesión y ejecutar todas las celdas**. El ZIP permanece en la sesión y no tienes que volver a cargarlo.
4. Al final debe aparecer **PRUEBA COMPLETA**. Puedes modificar las celdas de análisis y ejecutarlas de nuevo.

El ZIP se carga en la máquina temporal de Colab de tu cuenta. No se publica ni se monta Google Drive. Cuando Colab elimina la máquina hay que cargarlo otra vez. Compartir el enlace al cuaderno no comparte estos archivos; quien lo ejecute necesita su propia copia del ZIP.

La primera instalación puede tardar varios minutos. No se necesita GPU, Idealista ni una API de pago. Estas métricas históricas no validan precios de compraventa ni precisión en 2026.
'''
    upload = '''from pathlib import Path, PurePosixPath
import sys, os, json, hashlib, tempfile, zipfile

if sys.version_info[:2] != (3, 12):
    raise RuntimeError('Selecciona CPU y versión 2026.07 en Entorno de ejecución → Cambiar tipo de entorno de ejecución (Python 3.12).')

ARCHIVE_SHA = __ARCHIVE_SHA__
archive_path = Path('/content/HabitIA_Colab_datos_y_codigo.zip')
if not archive_path.is_file() or hashlib.sha256(archive_path.read_bytes()).hexdigest() != ARCHIVE_SHA:
    from google.colab import files
    print('Selecciona HabitIA_Colab_datos_y_codigo.zip')
    uploaded = files.upload()
    matches = [data for data in uploaded.values() if hashlib.sha256(data).hexdigest() == ARCHIVE_SHA]
    if len(matches) != 1:
        raise ValueError('No se ha recibido el ZIP exacto de esta versión. Usa el ZIP que acompaña a este notebook.')
    archive_path.write_bytes(matches[0])
    del uploaded, matches

ROOT = Path(tempfile.mkdtemp(prefix='habitia-colab-', dir='/content'))
with zipfile.ZipFile(archive_path) as archive:
    for info in archive.infolist():
        p = PurePosixPath(info.filename)
        if p.is_absolute() or '..' in p.parts or '\\\\' in info.filename:
            raise ValueError('Ruta no admitida en el ZIP.')
    archive.extractall(ROOT)
manifest = json.loads((ROOT / 'COLAB_MANIFIESTO.json').read_text())
for name, expected in manifest['sha256'].items():
    if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
        raise ValueError('Archivo ausente o modificado: ' + name)
os.chdir(ROOT)
os.environ['OMP_NUM_THREADS'] = '2'
os.environ['OPENBLAS_NUM_THREADS'] = '2'
print('Código, datos y experimento: integridad correcta.')
print('Carpeta de trabajo:', ROOT)
print('Python:', sys.version.split()[0])
'''.replace('__ARCHIVE_SHA__', repr(archive_sha))
    install = '''import subprocess, importlib, importlib.metadata

REQUIRED = __REQUIRED__
def installed_version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None
missing = [f'{name}=={version}' for name, version in REQUIRED.items()
           if installed_version(name) != version]
if missing:
    print('Instalando las versiones del estudio. Espera a que termine esta celda…', flush=True)
    result = subprocess.run([sys.executable, '-m', 'pip', 'install', '--quiet',
                             '--disable-pip-version-check', *missing],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (ROOT / 'instalacion-colab.log').write_text(result.stdout)
    if result.returncode:
        print(result.stdout[-6000:])
        raise RuntimeError('La instalación falló. Consulta el mensaje anterior.')
modules = {name: ('sklearn' if name == 'scikit-learn' else name) for name in REQUIRED}
loaded_different = [name for name, module in modules.items() if module in sys.modules
                    and getattr(sys.modules[module], '__version__', None) != REQUIRED[name]]
if loaded_different:
    raise RuntimeError('INSTALACIÓN COMPLETADA. Selecciona Entorno de ejecución → Reiniciar la sesión y ejecutar todas las celdas. No vuelvas a subir el ZIP.')
for name, module in modules.items():
    imported = importlib.import_module(module)
    if imported.__version__ != REQUIRED[name]:
        raise RuntimeError('Versión incompatible: ' + name)
print('Dependencias correctas. Continúa la comprobación del estudio.')
'''.replace('__REQUIRED__', repr(requirements))
    check = '''OUT = ROOT / 'revision_2026-09-08' / 'experimento'
required_files = ['resultados_revision.json', 'predicciones_exteriores.parquet',
                  'predicciones_artefacto.parquet', 'particiones_exteriores.parquet',
                  'artefacto/manifiesto.json', 'artefacto/pipeline.json',
                  'artefacto/modelo_precio.txt', 'artefacto/modelo_q_lo.txt', 'artefacto/modelo_q_hi.txt']
missing = [name for name in required_files if not (OUT / name).is_file()]
if missing:
    raise FileNotFoundError('Falta evidencia del experimento. No se entrenará automáticamente: ' + ', '.join(missing))
subprocess.run([sys.executable, 'tests/verify_experiment_partitions.py'], check=True)
print('Preparación completada. Se reutiliza el experimento guardado, sin entrenar.')
'''
    nb = copy.deepcopy(json.loads((ROOT / 'TFM_HabitIA_entrenamiento.ipynb').read_text()))
    nb['metadata'] = {'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
                      'language_info': {'name': 'python'}, 'colab': {'provenance': []},
                      'habitia': {'purpose': 'Prueba en Colab sin reentrenamiento', 'payload_sha256': archive_sha}}
    nb['cells'][0]['source'] = ['# Estudio y resultados\n\nLas celdas siguientes proceden del cuaderno canónico. Se conservan los métodos y cálculos, se adapta la ruta y se sustituye la celda de entrenamiento por una lectura obligatoria de la evidencia. El código Python del modelo se conserva íntegro.\n']
    first = ''.join(nb['cells'][1]['source'])
    start = first.index('ROOT = next(')
    end = first.index('sys.path.insert', start)
    first = first[:start] + "ROOT = Path.cwd()\nassert (ROOT / 'src' / 'train_revision.py').is_file(), 'Ejecuta antes las celdas de preparación.'\n" + first[end:]
    first = first.replace("if REENTRENAR:\n    OUT = ROOT / 'revision_2026-09-08' / ('repeticion_' + datetime.now().strftime('%Y%m%d_%H%M%S'))", "assert REENTRENAR is False, 'Este cuaderno comprueba la entrega; usa el cuaderno canónico para reentrenar.'")
    nb['cells'][1]['source'] = first.splitlines(keepends=True)
    nb['cells'][12]['source'] = ['## 8 Cargar el experimento guardado\n\nEsta copia comprueba la configuración y lee los resultados. Si falta el experimento, se detiene. Las celdas siguientes recalculan métricas y gráficos desde las predicciones guardadas.\n']
    nb['cells'][13]['source'] = '''result_path = OUT / 'resultados_revision.json'
if not result_path.is_file():
    raise FileNotFoundError('Faltan resultados guardados; esta copia no inicia entrenamientos.')
results = json.loads(result_path.read_text())
assert results['configuracion'] == CONFIG, 'El resultado usa otra configuración.'
print('Se leen resultados completos de:', results['created_at'])
print('Duración del entrenamiento histórico, minutos:', round(results['duracion_segundos'] / 60, 2))
print('Hash de configuración:', results['config_sha256'])
'''.splitlines(keepends=True)
    for i, c in enumerate(nb['cells']):
        c['id'] = f'estudio-{i:02d}'
        c['metadata'] = {}
        if c['cell_type'] == 'code':
            c['execution_count'] = None
            c['outputs'] = []
    nb['cells'] = [cell('markdown', intro, 'colab-intro'),
                   cell('markdown', '## A · Cargar y verificar los archivos', 'colab-load-title'),
                   cell('code', upload, 'colab-load'),
                   cell('markdown', '## B · Preparar las dependencias', 'colab-deps-title'),
                   cell('code', install, 'colab-deps'),
                   cell('markdown', '## C · Verificar el experimento', 'colab-check-title'),
                   cell('code', check, 'colab-check')] + nb['cells'] + [
        cell('markdown', '## Prueba final · todas las predicciones del artefacto', 'colab-final-title'),
        cell('code', '''subprocess.run([sys.executable, 'tests/verify_exported_evaluation.py'], check=True)
print('PRUEBA COMPLETA: métricas, gráficos, particiones y 18.782 predicciones verificadas. No se ha reentrenado el modelo.')
''', 'colab-final')]
    path = output / 'HabitIA_Colab.ipynb'
    path.write_text(json.dumps(nb, ensure_ascii=False, indent=1) + '\n')
    (output / 'LEEME.md').write_text(intro + '\nSHA-256 del ZIP: `' + archive_sha + '`\n')
    print(path)
    print(archive_path, round(archive_path.stat().st_size / 1024**2, 2), 'MiB')
    return path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('private_archive', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    build(args.private_archive, args.output)
