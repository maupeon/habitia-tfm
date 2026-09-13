"""Ejecuta y conserva salidas del notebook; un error impide marcarlo terminado."""
from pathlib import Path
from datetime import datetime, timezone
import json
import nbformat
from nbclient import NotebookClient
from nbconvert import HTMLExporter

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "TFM_HabitIA_entrenamiento.ipynb"
nb = nbformat.read(path, as_version=4)
record = {"inicio": datetime.now(timezone.utc).isoformat(), "celdas_ejecutadas": [], "completo": False}
audit = ROOT / "revision_2026-09-08" / "ejecucion_notebook.json"


def started(cell, cell_index, **kwargs):
    print(f"Ejecutando celda {cell_index+1}/{len(nb.cells)}", flush=True)


def completed(cell, cell_index, **kwargs):
    record["celdas_ejecutadas"].append(cell_index)
    nbformat.write(nb, path)
    audit.write_text(json.dumps(record, indent=2))
    for output in cell.get("outputs", []):
        if output.output_type == "stream":
            print(output.text, end="", flush=True)


client = NotebookClient(nb, timeout=14400, kernel_name="habitia",
                        resources={"metadata": {"path": str(ROOT)}},
                        on_cell_execute=started, on_cell_executed=completed)
try:
    client.execute()
    record["completo"] = True
    record["fin"] = datetime.now(timezone.utc).isoformat()
    body, _ = HTMLExporter().from_notebook_node(nb)
    (ROOT / "TFM_HabitIA_entrenamiento.html").write_text(body, encoding="utf-8")
finally:
    nbformat.write(nb, path)
    audit.write_text(json.dumps(record, indent=2))
print("Notebook ejecutado y HTML exportado", flush=True)
