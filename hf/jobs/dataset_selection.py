"""Resolve explicit Hub dataset selections into one reproducible JSONL.

A source has the form ``repo[@revision]:glob``.  The revision is optional;
the glob is relative to the dataset repository.  The caller downloads each
snapshot, then this module validates and concatenates the selected JSONL files
in deterministic order while refusing mixed languages and duplicate rows.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DatasetSource:
    repo_id: str
    revision: str
    pattern: str


def parse_source(value: str) -> DatasetSource:
    try:
        repo_revision, pattern = value.split(":", 1)
    except ValueError as exc:
        raise ValueError(f"invalid source {value!r}: expected repo[@revision]:glob") from exc
    if not repo_revision or not pattern:
        raise ValueError(f"invalid source {value!r}: repo and glob are required")
    if "@" in repo_revision:
        repo_id, revision = repo_revision.rsplit("@", 1)
    else:
        repo_id, revision = repo_revision, "main"
    if not repo_id or not revision:
        raise ValueError(f"invalid source {value!r}: repo and revision must not be empty")
    return DatasetSource(repo_id=repo_id, revision=revision, pattern=pattern)


def selected_files(snapshot: Path, pattern: str) -> list[Path]:
    files = sorted(path for path in snapshot.glob(pattern) if path.is_file() and path.suffix == ".jsonl")
    if not files:
        raise ValueError(f"selection {pattern!r} matched no JSONL file in {snapshot}")
    return files


def merge_jsonl(files: list[Path], output: Path, lang: str) -> dict[str, object]:
    """Merge validated training rows and return a content manifest."""
    required = {"id", "lang", "control", "dirty", "clean", "source"}
    seen_ids: dict[str, Path] = {}
    seen_dirty: dict[str, Path] = {}
    rows: list[str] = []
    per_file: list[dict[str, object]] = []

    for path in files:
        count = 0
        digest = hashlib.sha256()
        with path.open(encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle, 1):
                if not raw.strip():
                    continue
                digest.update(raw.encode("utf-8"))
                try:
                    row = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{line_number}: invalid JSON ({exc})") from exc
                missing = required - row.keys() if isinstance(row, dict) else required
                if missing:
                    raise ValueError(f"{path}:{line_number}: missing keys {sorted(missing)}")
                if row["lang"] != lang:
                    raise ValueError(f"{path}:{line_number}: language {row['lang']!r}, expected {lang!r}")
                row_id = str(row["id"])
                dirty_key = " ".join(str(row["dirty"]).split()).casefold()
                if row_id in seen_ids:
                    raise ValueError(f"duplicate id {row_id!r} in {seen_ids[row_id]} and {path}")
                if dirty_key in seen_dirty:
                    raise ValueError(f"duplicate dirty transcript in {seen_dirty[dirty_key]} and {path}")
                seen_ids[row_id] = path
                seen_dirty[dirty_key] = path
                rows.append(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
                count += 1
        per_file.append({"path": str(path), "rows": count, "sha256": digest.hexdigest()})

    if not rows:
        raise ValueError("dataset selection contains no training row")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return {
        "language": lang,
        "rows": len(rows),
        "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "files": per_file,
    }
