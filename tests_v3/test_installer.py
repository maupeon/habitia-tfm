import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts import install_predictor_v3 as installer


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        (self.root / "servicio").mkdir(parents=True)
        self.payloads = {name: name.encode() for name in (
            "modelo.json", "metadatos.json", "barrios.parquet", "indices_distrito.parquet",
            "variables_barrio.parquet", "pois.parquet")}
        manifest = {"sha256": {name: hashlib.sha256(data).hexdigest() for name, data in self.payloads.items()}}
        (self.root / "servicio/manifiesto_v3.json").write_text(json.dumps(manifest))
        self.source = Path(self.temp.name) / "nuevo_modelo"
        self.artifacts = self.source / "data/models/paquete_produccion"
        self.artifacts.mkdir(parents=True)
        for name, data in self.payloads.items():
            (self.artifacts / name).write_bytes(data)

    def run_installer(self, *arguments):
        with patch.object(installer, "ROOT", self.root), patch("sys.argv", ["installer", *map(str, arguments)]):
            installer.main()

    def test_received_directory_and_integrity_check(self):
        self.run_installer(self.source)
        self.run_installer("--check")
        self.assertEqual((self.root / "servicio/artefactos_v3/modelo.json").read_bytes(), b"modelo.json")

    def test_release_zip_installs_same_files(self):
        archive = Path(self.temp.name) / "modelo.zip"
        with zipfile.ZipFile(archive, "w") as zipped:
            for name, data in self.payloads.items():
                zipped.writestr("paquete/" + name, data)
        self.run_installer(archive)
        self.run_installer("--check")

    def test_wrong_hash_never_replaces_existing_artifacts(self):
        self.run_installer(self.source)
        (self.artifacts / "pois.parquet").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "Hash incorrecto: pois.parquet"):
            self.run_installer(self.artifacts)
        self.run_installer("--check")

    def test_custom_target_and_environment_are_used_for_install_and_check(self):
        destination = Path(self.temp.name) / "custom"
        with patch.dict(os.environ, {"VALORACION_ARTIFACTS_V3": str(destination)}):
            self.run_installer(self.source)
            self.run_installer("--check")
            self.assertEqual(set(p.name for p in destination.iterdir()), set(self.payloads))
            override = Path(self.temp.name) / "override"
            self.run_installer(self.source, "--target", override)
            self.run_installer("--check", "--target", override)

    def test_ambiguous_zip_never_replaces_existing_artifacts(self):
        self.run_installer(self.source)
        archive = Path(self.temp.name) / "ambiguous.zip"
        with zipfile.ZipFile(archive, "w") as zipped:
            for name, data in self.payloads.items():
                zipped.writestr("paquete/" + name, data)
            zipped.writestr("duplicado/modelo.json", b"modelo.json")
        with self.assertRaisesRegex(ValueError, "Archivo ausente o ambiguo: modelo.json"):
            self.run_installer(archive)
        self.run_installer("--check")

    def test_failed_replacement_restores_previous_installation(self):
        self.run_installer(self.source)
        rename = Path.rename

        def fail_new_directory(path, target):
            if path.name == "nuevo":
                raise OSError("fallo de sustitución simulado")
            return rename(path, target)

        with patch.object(Path, "rename", fail_new_directory):
            with self.assertRaisesRegex(OSError, "fallo de sustitución simulado"):
                self.run_installer(self.source)
        self.run_installer("--check")

    def test_unrelated_files_in_target_are_preserved(self):
        self.run_installer(self.source)
        unrelated = self.root / "servicio/artefactos_v3/notas.txt"
        unrelated.write_text("no pertenece al modelo")
        with self.assertRaisesRegex(ValueError, "archivos ajenos al paquete"):
            self.run_installer(self.source)
        self.assertEqual(unrelated.read_text(), "no pertenece al modelo")
        self.run_installer("--check")


if __name__ == "__main__":
    unittest.main()
