# /// script
# requires-python = ">=3.12"
# dependencies = ["torch", "transformers==4.57.6", "peft", "huggingface_hub", "num2words"]
# ///
"""Train a BudgieScribe build on Hugging Face Jobs.

    hf jobs uv run hf/jobs/train.py --flavor a10g-small --timeout 2h \
        --secrets HF_TOKEN -- --lang en --pairs flowcorp-ch/BudgieScribe-data:mix/pairs_mix_en.jsonl \
        --out flowcorp-ch/scribe-en-next --epochs 2 --batch 4

    # a bigger profile: 1.7B / 4B in LoRA fit an A10G (24 GB); 8B wants an A100.
    hf jobs uv run hf/jobs/train.py --flavor a10g-large --timeout 4h \
        --secrets HF_TOKEN -- --lang fr --profil standard --pairs ...:mix/pairs_mix.jsonl \
        --out flowcorp-ch/scribe-standard-fr-next

The pairs file is downloaded from the Hub, the training script of the
repository is run unchanged, and the resulting checkpoint is pushed to a
PRIVATE model repo under --out. A LoRA profile pushes the merged model plus
`adaptateur/`. GGUF conversion and evaluation are separate jobs (eval.py);
nothing is published from here.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download, snapshot_download

ap = argparse.ArgumentParser()
ap.add_argument("--lang", required=True)
ap.add_argument("--pairs", required=True, help="<dataset repo>:<path in repo>")
ap.add_argument("--out", required=True, help="model repo to push the checkpoint to (private)")
ap.add_argument("--profil", default="nano", choices=["nano", "mini", "standard", "large"])
ap.add_argument("--methode", choices=["full", "lora"], help="override the profile's method")
ap.add_argument("--epochs", type=int, default=2)
ap.add_argument("--batch", type=int, help="default: the profile's (nano: 8)")
ap.add_argument("--code", default="alexxxcoelho/budgie-scribe", help="GitHub repo to clone")
args = ap.parse_args()

work = Path("/tmp/scribe-work"); work.mkdir(parents=True, exist_ok=True)
subprocess.run(["git", "clone", "--depth", "1", f"https://github.com/{args.code}", str(work / "repo")], check=True)
repo_id, path = args.pairs.split(":", 1)
pairs = hf_hub_download(repo_id, path, repo_type="dataset", local_dir=work / "data")

env = dict(os.environ, SCRIBE_LANG=args.lang, SCRIBE_TRAVAIL=str(work / "data"),
           SCRIBE_PROFIL=args.profil, SCRIBE_EPOCHS=str(args.epochs),
           SCRIBE_PAIRS=str(pairs), SCRIBE_OUT=str(work / "out"))
if args.methode:
    env["SCRIBE_METHODE"] = args.methode
if args.batch:
    env["SCRIBE_BATCH"] = str(args.batch)
subprocess.run([sys.executable, "-u", str(work / "repo/scribe/entrainement/train.py")], env=env, check=True)

api = HfApi()
api.create_repo(args.out, private=True, exist_ok=True)
api.upload_folder(folder_path=str(work / "out"), repo_id=args.out)
print("checkpoint pushed to", args.out, "(private)")
