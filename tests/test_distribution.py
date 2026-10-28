"""Packaging regression tests using temporary, synthetic artifacts only."""
import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_distribution as dist
import maintain


class DistributionTests(unittest.TestCase):
    def test_unreviewed_or_changed_image_is_rejected(self):
        name = "references/images/example.jpg"
        raw = b"\xff\xd8\xff" + b"synthetic-test-image" + b"\xff\xd9"
        proof = {"reviewed_images": {name: {"sha256": hashlib.sha256(raw).hexdigest(), "format": "JPEG", "synthetic": True}}}
        self.assertEqual(maintain.scan_content(name, raw, proof), [])
        self.assertIn("unverified_documentation_image", maintain.scan_content(name, raw + b"changed", proof))
        with self.assertRaises(UnicodeDecodeError):
            maintain.scan_content(name, raw, {})

    def test_image_review_cannot_hide_text_or_non_documentation_files(self):
        raw = b"synthetic secret text"
        for name in ("scripts/hidden.jpg", "references/images/example.jpg"):
            proof = {"reviewed_images": {name: {"sha256": hashlib.sha256(raw).hexdigest(), "format": "JPEG", "synthetic": True}}}
            self.assertIn("unverified_documentation_image", maintain.scan_content(name, raw, proof))

    def test_variant_manifest_and_repacking_are_consistent(self):
        metadata = json.loads((ROOT / "distribution.json").read_text())
        variants = ["redskill"]
        if metadata["build_kind"] == "github-full":
            variants.insert(0, "github-full")
        with tempfile.TemporaryDirectory(prefix="ledger-package-test-") as directory:
            tmp = Path(directory)
            for variant in variants:
                first = tmp / (variant + ".zip")
                receipt = dist.build(ROOT, variant, first)
                expected_private = metadata.get("repository_visibility") != "public"
                self.assertEqual(receipt["private_review_only"], expected_private)
                manifest = json.loads(first.with_suffix(".manifest.json").read_text())
                self.assertEqual(manifest["private_review_only"], expected_private)
                extracted = tmp / variant
                with zipfile.ZipFile(first) as archive:
                    archive.extractall(extracted)
                    paths = archive.namelist()
                declared = json.loads((extracted / "release-files.json").read_text())["files"]
                self.assertEqual(paths, declared)
                self.assertEqual(dist.verify_core(extracted)["candidate_version"], metadata["candidate_version"])
                if variant == "redskill":
                    self.assertTrue(dist.RED_EXCLUDED.isdisjoint(paths))
                    self.assertEqual(dist.validate_redskill(extracted, paths)["filter_would_drop"], [])
                    with self.assertRaisesRegex(ValueError, "full build requires"):
                        dist.build(extracted, "github-full", tmp / "impossible.zip")
                second = tmp / (variant + "-repacked.zip")
                dist.build(extracted, variant, second)
                self.assertEqual(hashlib.sha256(first.read_bytes()).hexdigest(),
                                 hashlib.sha256(second.read_bytes()).hexdigest())

    def test_redskill_rejects_unsupported_file_instead_of_silently_dropping(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "SKILL.md").write_text("synthetic skill")
            (root / "fixture.csv").write_text("synthetic")
            with self.assertRaisesRegex(ValueError, "unsupported RedSkill suffix"):
                dist.validate_redskill(root, ["SKILL.md", "fixture.csv"])

    def test_core_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "example.py").write_text("changed")
            (root / "distribution.json").write_text(json.dumps({
                "core_files_sha256": {"example.py": hashlib.sha256(b"original").hexdigest()}}))
            with self.assertRaisesRegex(ValueError, "core differs"):
                dist.verify_core(root)


if __name__ == "__main__":
    unittest.main()
