import hashlib
import json
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


if __name__ == "__main__":
    unittest.main()
