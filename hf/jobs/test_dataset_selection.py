import json
import tempfile
import unittest
from pathlib import Path

from dataset_selection import merge_jsonl, parse_source, selected_files


def row(row_id: str, lang: str = "fr", dirty: str = "texte brut") -> dict[str, str]:
    return {
        "id": row_id,
        "file": "fixture",
        "lang": lang,
        "control": f"[Styling: semi-formal] [Structure: prose] [Context: general] [Lang: {lang}]",
        "dirty": dirty,
        "clean": "Texte propre.",
        "source": "fixture-asr",
    }


class DatasetSelectionTests(unittest.TestCase):
    def test_source_supports_pinned_revision_and_glob(self):
        parsed = parse_source("flowcorp-ch/BudgieScribe-contrib@abc123:contrib/fr/*.jsonl")
        self.assertEqual(parsed.repo_id, "flowcorp-ch/BudgieScribe-contrib")
        self.assertEqual(parsed.revision, "abc123")
        self.assertEqual(parsed.pattern, "contrib/fr/*.jsonl")

    def test_selection_and_merge_are_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "contrib/fr"
            folder.mkdir(parents=True)
            (folder / "b.jsonl").write_text(json.dumps(row("b", dirty="brut deux")) + "\n", encoding="utf-8")
            (folder / "a.jsonl").write_text(json.dumps(row("a", dirty="brut un")) + "\n", encoding="utf-8")
            files = selected_files(root, "contrib/fr/*.jsonl")
            output = root / "selected.jsonl"
            manifest = merge_jsonl(files, output, "fr")
            self.assertEqual([path.name for path in files], ["a.jsonl", "b.jsonl"])
            self.assertEqual(manifest["rows"], 2)
            self.assertEqual([json.loads(line)["id"] for line in output.read_text().splitlines()], ["a", "b"])

    def test_merge_refuses_mixed_languages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first.jsonl"
            second = root / "second.jsonl"
            first.write_text(json.dumps(row("same", dirty="meme texte")) + "\n", encoding="utf-8")
            second.write_text(json.dumps(row("other", lang="en", dirty="other text")) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "language"):
                merge_jsonl([first, second], root / "out.jsonl", "fr")

    def test_merge_keeps_first_duplicate_and_reports_skipped_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first.jsonl"
            second = root / "second.jsonl"
            first.write_text(
                "\n".join([
                    json.dumps(row("first", dirty="meme texte")),
                    json.dumps(row("kept", dirty="texte unique")),
                ]) + "\n",
                encoding="utf-8",
            )
            second.write_text(
                "\n".join([
                    json.dumps(row("first", dirty="autre texte")),
                    json.dumps(row("other", dirty="  MEME   TEXTE  ")),
                    json.dumps(row("last", dirty="dernier texte")),
                ]) + "\n",
                encoding="utf-8",
            )

            output = root / "out.jsonl"
            manifest = merge_jsonl([first, second], output, "fr")

            self.assertEqual(
                [json.loads(line)["id"] for line in output.read_text().splitlines()],
                ["first", "kept", "last"],
            )
            self.assertEqual(manifest["rows"], 3)
            self.assertEqual(manifest["duplicates_skipped"], 2)
            self.assertEqual(manifest["duplicate_ids_skipped"], 1)
            self.assertEqual(manifest["duplicate_dirty_skipped"], 1)
            self.assertEqual(manifest["files"][0]["rows"], 2)
            self.assertEqual(manifest["files"][0]["duplicates_skipped"], 0)
            self.assertEqual(manifest["files"][1]["rows"], 1)
            self.assertEqual(manifest["files"][1]["duplicates_skipped"], 2)


if __name__ == "__main__":
    unittest.main()
