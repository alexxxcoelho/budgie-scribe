# /// script
# requires-python = ">=3.12"
# dependencies = ["torch", "peft", "huggingface_hub", "num2words"]
# ///
# `transformers` is deliberately NOT in that list. The right pin depends on the
# profile being trained, and a wrong one is silent: 4.x has no `qwen3_5` at all,
# while 5.16/5.17 break gradient-checkpointing recomputation on some torch
# builds (`CheckpointError`, minutes into the first backward pass). Pass it at
# launch with `--with`, so the version is visible in the command that ran.
"""Train a BudgieScribe build on Hugging Face Jobs.

    hf jobs uv run hf/jobs/train.py --flavor a10g-small --timeout 2h \
        --secrets HF_TOKEN --with transformers==4.57.6 \
        -- --lang en \
        --source 'flowcorp-ch/BudgieScribe-contrib@<commit>:contrib/en/*.jsonl' \
        --out flowcorp-ch/scribe-en-next --epochs 2 --batch 4

    # a bigger profile: 1.7B / 4B in LoRA fit an A10G (24 GB); 8B wants an A100.
    hf jobs uv run hf/jobs/train.py --flavor a10g-large --timeout 4h \
        --secrets HF_TOKEN --with transformers==4.57.6 \
        -- --lang fr --profil standard \
        --source 'flowcorp-ch/BudgieScribe-data@<commit>:mix/pairs_mix.jsonl' \
        --out flowcorp-ch/scribe-standard-fr-next

    # Qwen3.5 is the one profile that wants 5.x: `qwen3_5` exists in no 4.x.
    # The profile turns gradient checkpointing off by itself, which is exactly
    # what makes 5.17 safe here.
    hf jobs uv run hf/jobs/train.py --flavor a10g-large --timeout 4h \
        --secrets HF_TOKEN --with transformers==5.17.0 \
        -- --lang fr --profil qwen35 \
        --source 'flowcorp-ch/BudgieScribe-data@<commit>:mix/pairs_mix.jsonl' \
        --out flowcorp-ch/scribe-qwen35-fr-next

`--with transformers==...` installs into the same uv environment PEP-723
builds from the header above, so `sys.executable` -- the interpreter the
cloned trainer runs on -- sees it.

No `--selection-module`: `hf jobs uv run` uploads the script and nothing else,
so a neighbouring file is not in the container. The helper is read from the
clone the script makes itself. The flag remains an override for a local run.

Each repeatable --source selects ``repo[@revision]:glob`` from a Hub dataset.
The selected JSONL files are sorted, validated and merged; selection.json in
the private output checkpoint records the exact Hub commit and content hashes.
The resulting checkpoint is pushed to a PRIVATE model repo under --out. A
LoRA profile pushes the merged model plus `adaptateur/`. GGUF conversion and
evaluation are separate jobs (eval.py); nothing is published from here.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download


def build_training_command(
    *,
    python,
    script,
    pairs,
    out,
    profil,
    epochs,
    methode=None,
    base=None,
    batch=None,
    accum=None,
):
    """Build the explicit CLI contract expected by the cloned trainer."""
    command = [
        str(python), "-u", str(script),
        "--pairs", str(pairs),
        "--out", str(out),
        "--profil", str(profil),
        "--epochs", str(epochs),
    ]
    for option, value in (
        ("--methode", methode),
        ("--base", base),
        ("--batch", batch),
        ("--accum", accum),
    ):
        if value is not None:
            command.extend([option, str(value)])
    return command


ap = argparse.ArgumentParser()
ap.add_argument("--lang", required=True)
ap.add_argument("--source", action="append", default=[], help="repeatable: <dataset repo>[@revision]:<glob>")
ap.add_argument("--pairs", help="legacy alias for one exact --source path")
ap.add_argument(
    "--selection-module",
    help="path to dataset_selection.py; default: the copy inside the cloned repo",
)
ap.add_argument("--out", required=True, help="model repo to push the checkpoint to (private)")
ap.add_argument("--profil", default="nano", choices=["nano", "mini", "standard", "large", "qwen35"])
ap.add_argument("--methode", choices=["full", "lora"], help="override the profile's method")
ap.add_argument("--base", help="override the profile's Hugging Face base model")
ap.add_argument("--epochs", type=int, default=2)
ap.add_argument("--batch", type=int, help="default: the profile's (nano: 8)")
ap.add_argument("--accum", type=int, help="gradient accumulation; default: the profile's")
ap.add_argument("--code", default="alexxxcoelho/budgie-scribe", help="GitHub repo to clone")
args = ap.parse_args()

work = Path("/tmp/scribe-work"); work.mkdir(parents=True, exist_ok=True)
subprocess.run(["git", "clone", "--depth", "1", f"https://github.com/{args.code}", str(work / "repo")], check=True)

# L'import vient APRES le clone, et son defaut pointe DANS le clone.
# `hf jobs uv run` ne televerse que le SCRIPT, pas ses fichiers voisins : un
# chemin relatif comme `hf/jobs/dataset_selection.py` n'existe pas dans le
# conteneur, et l'import etait resolu avant que le clone ne l'apporte. Le clone
# l'apporte toujours, donc c'est lui le defaut. `--selection-module` reste une
# surcharge, pour un run hors conteneur qui veut un autre exemplaire.
helper = (Path(args.selection_module).resolve() if args.selection_module
          else work / "repo" / "hf" / "jobs" / "dataset_selection.py")
sys.path.insert(0, str(helper.parent))
try:
    from dataset_selection import merge_jsonl, parse_source, selected_files
except ModuleNotFoundError:
    ap.error("dataset_selection.py introuvable (%s); passez --selection-module" % helper)

source_values = list(args.source)
if args.pairs:
    source_values.append(args.pairs)
if not source_values:
    ap.error("at least one --source (or legacy --pairs) is required")

api = HfApi()
all_files = []
source_manifest = []
for index, value in enumerate(source_values):
    source = parse_source(value)
    info = api.repo_info(source.repo_id, repo_type="dataset", revision=source.revision)
    snapshot = Path(snapshot_download(
        source.repo_id,
        repo_type="dataset",
        revision=source.revision,
        allow_patterns=[source.pattern],
        local_dir=work / "data" / str(index),
    ))
    files = selected_files(snapshot, source.pattern)
    all_files.extend(files)
    source_manifest.append({
        "repo": source.repo_id,
        "requested_revision": source.revision,
        "resolved_revision": info.sha,
        "pattern": source.pattern,
        "files": [str(path.relative_to(snapshot)) for path in files],
    })

pairs = work / "data" / "selected_pairs.jsonl"
selection = merge_jsonl(all_files, pairs, args.lang)
selection["sources"] = source_manifest
(work / "selection.json").write_text(json.dumps(selection, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps({
    "input_rows": selection["input_rows"],
    "selected_rows": selection["rows"],
    "duplicates_skipped": selection["duplicates_skipped"],
    "duplicate_ids_skipped": selection["duplicate_ids_skipped"],
    "duplicate_dirty_skipped": selection["duplicate_dirty_skipped"],
    "sources": source_manifest,
}, indent=2))

env = dict(os.environ, SCRIBE_LANG=args.lang, SCRIBE_TRAVAIL=str(work / "data"),
           SCRIBE_PROFIL=args.profil, SCRIBE_EPOCHS=str(args.epochs),
           SCRIBE_PAIRS=str(pairs), SCRIBE_OUT=str(work / "out"))
if args.methode:
    env["SCRIBE_METHODE"] = args.methode
if args.base:
    env["SCRIBE_BASE"] = args.base
if args.batch:
    env["SCRIBE_BATCH"] = str(args.batch)
if args.accum:
    env["SCRIBE_ACCUM"] = str(args.accum)
subprocess.run(build_training_command(
    python=sys.executable,
    script=work / "repo/scribe/entrainement/train.py",
    pairs=pairs,
    out=work / "out",
    profil=args.profil,
    epochs=args.epochs,
    methode=args.methode,
    base=args.base,
    batch=args.batch,
    accum=args.accum,
), env=env, check=True)

(work / "out" / "selection.json").write_bytes((work / "selection.json").read_bytes())
api.create_repo(args.out, private=True, exist_ok=True)
api.upload_folder(folder_path=str(work / "out"), repo_id=args.out)
print("checkpoint pushed to", args.out, "(private)")
