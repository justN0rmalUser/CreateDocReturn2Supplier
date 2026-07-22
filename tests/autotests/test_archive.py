import json
import pickle
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

from src.utils.archive import archive_json, archive_pkl, flush


class ArchiveTestCase(unittest.TestCase):
    def test_archive_raw_groups_json_by_supplier_and_date(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = archive_json(
                {"answer": "готово"},
                "supplier-a",
                date(2026, 7, 20),
                archive_dir=root,
            )

            self.assertEqual(target, root / "supplier-a" / "2026-07-20.json")
            self.assertEqual(
                json.loads(target.read_text(encoding="utf-8")),
                {"answer": "готово"},
            )

    def test_archive_raw_accepts_a_custom_json_adapter(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = archive_json(
                {"created": date(2026, 7, 20)},
                "supplier-a",
                archive_dir=tmp_dir,
                json_default=lambda value: value.isoformat(),
            )

            self.assertEqual(
                json.loads(target.read_text(encoding="utf-8")),
                {"created": "2026-07-20"},
            )

    def test_archive_processed_roundtrip(self):
        payload = {"rows": [(1, "value")]}
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = archive_pkl(
                payload,
                "supplier-b",
                datetime(2026, 7, 21, 10, 30),
                archive_dir=root,
            )

            self.assertEqual(target, root / "supplier-b" / "2026-07-21.pkl")
            with target.open("rb") as archive_file:
                self.assertEqual(pickle.load(archive_file), payload)

    def test_flush_removes_only_archives_older_than_cutoff(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            old_json = archive_json({}, "supplier-a", "2026-07-01", archive_dir=root)
            old_pickle = archive_pkl({}, "supplier-b", "2026-07-02", archive_dir=root)
            cutoff_json = archive_json({}, "supplier-a", "2026-07-03", archive_dir=root)
            new_pickle = archive_pkl({}, "supplier-a", "2026-07-04", archive_dir=root)
            unrelated = root / "supplier-a" / "notes.txt"
            unrelated.write_text("keep", encoding="utf-8")
            invalid_date = root / "supplier-a" / "not-a-date.json"
            invalid_date.write_text("{}", encoding="utf-8")

            deleted = flush("2026-07-03", archive_dir=root)

            self.assertEqual(set(deleted), {old_json, old_pickle})
            self.assertFalse(old_json.exists())
            self.assertFalse(old_pickle.exists())
            self.assertTrue(cutoff_json.exists())
            self.assertTrue(new_pickle.exists())
            self.assertTrue(unrelated.exists())
            self.assertTrue(invalid_date.exists())

    def test_flush_missing_root_is_a_noop(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing = Path(tmp_dir) / "missing"
            self.assertEqual(flush(date(2026, 7, 3), archive_dir=missing), ())

    def test_invalid_supplier_cannot_escape_archive_root(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            for supplier in ("", ".", "..", "nested/supplier"):
                with self.subTest(supplier=supplier):
                    with self.assertRaises(ValueError):
                        archive_json({}, supplier, archive_dir=tmp_dir)

    def test_invalid_archive_date_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(ValueError):
                archive_pkl({}, "supplier", "2026-02-30", archive_dir=tmp_dir)
            with self.assertRaises(TypeError):
                flush(123, archive_dir=tmp_dir)  # type: ignore[arg-type]

    def test_default_date_supplier_and_archive_directory_validation(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("src.utils.archive.date") as fake_date:
                fake_date.today.return_value = date(2026, 7, 22)
                target = archive_json({}, "supplier", archive_dir=tmp_dir)
            self.assertEqual(target.name, "2026-07-22.json")

            with self.assertRaises(TypeError):
                archive_json({}, 123, archive_dir=tmp_dir)  # type: ignore[arg-type]
            with self.assertRaises(TypeError):
                archive_json({}, "supplier", archive_dir=object())  # type: ignore[arg-type]

    def test_failed_atomic_write_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            supplier_dir = Path(tmp_dir) / "supplier"
            with self.assertRaises(TypeError):
                archive_json(object(), "supplier", archive_dir=tmp_dir)
            self.assertEqual(list(supplier_dir.iterdir()), [])

        with tempfile.TemporaryDirectory() as tmp_dir, patch(
            "src.utils.archive.Path.mkdir", side_effect=PermissionError("denied")
        ):
            with self.assertRaises(PermissionError):
                archive_json({}, "supplier", archive_dir=tmp_dir)

        with tempfile.TemporaryDirectory() as tmp_dir, patch(
            "src.utils.archive.tempfile.NamedTemporaryFile",
            side_effect=PermissionError("denied"),
        ):
            with self.assertRaises(PermissionError):
                archive_json({}, "supplier", archive_dir=tmp_dir)

    def test_flush_validates_root_and_skips_non_archives(self):
        with self.assertRaises(TypeError):
            flush("2026-07-03", archive_dir=object())  # type: ignore[arg-type]

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            plain_file = root / "plain"
            plain_file.write_text("x", encoding="utf-8")
            with self.assertRaises(NotADirectoryError):
                flush("2026-07-03", archive_dir=plain_file)

            (root / "top.txt").write_text("x", encoding="utf-8")
            supplier = root / "supplier"
            supplier.mkdir()
            (supplier / "nested").mkdir()
            (supplier / "2026-07-01.txt").write_text("x", encoding="utf-8")
            self.assertEqual(flush("2026-07-03", archive_dir=root), ())


if __name__ == "__main__":
    unittest.main()
