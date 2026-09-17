# /// script
# requires-python = ">=3.12"
# dependencies = ["torch", "transformers==4.57.6", "peft", "huggingface_hub", "num2words"]
# ///
"""Score a checkpoint on the public held-out sets, on Hugging Face Jobs.

    hf jobs uv run hf/jobs/eval.py --flavor t4-small --timeout 1h \
        --secrets HF_TOKEN -- --model flowcorp-ch/scribe-en-next --lang en

Downloads the checkpoint (a private model repo pushed by train.py, or any
transformers-format BudgieScribe checkpoint) and the public held-out sets
(flowcorp-ch/BudgieScribe-eval), then runs scribe/bancs/eval_synth.py and
eval_itn.py exactly as documented in EVALUATION.md, and prints the per-axis
tables. Wire it to a webhook to score every training pull request, or run it
by hand on a candidate build.

The GGUF card examples are reproduced separately by examples/replay_examples.sh.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

from huggingface_hub import snapshot_download

ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True,
                help="model repo (transformers format), 'base' or 'base:<profil>' (nano/mini/standard/large)")
ap.add_argument("--lang", required=True)
ap.add_argument("--code", default="alexxxcoelho/budgie-scribe", help="GitHub repo to clone")
ap.add_argument("--n", type=int, default=0, help="cap the number of cases per set (0 = all)")
args = ap.parse_args()

work = Path("/tmp/scribe-eval"); work.mkdir(parents=True, exist_ok=True)
subprocess.run(["git", "clone", "--depth", "1", f"https://github.com/{args.code}", str(work / "repo")], check=True)
evalset = Path(snapshot_download("flowcorp-ch/BudgieScribe-eval", repo_type="dataset", local_dir=work / "eval"))
model = args.model if args.model.startswith("base") else snapshot_download(args.model, local_dir=work / "model")

env = dict(os.environ, SCRIBE_LANG=args.lang, SCRIBE_TRAVAIL=str(work / "eval"))
bancs = work / "repo/scribe/bancs"
for pairs in sorted((evalset / args.lang).glob("*.jsonl")):
    print(f"\n=== {pairs.name}")
    subprocess.run([sys.executable, str(bancs / "eval_synth.py"), model, str(pairs), str(args.n)], env=env, check=True)
