#!/usr/bin/env python3
"""Assemble the folders that publish.yml uploads to the Hub, from models/manifest.json.

    python hf/jobs/assemble.py <out-dir> [Family ...]

For every family with at least one file: download each GGUF from its
`source`, refuse it unless the SHA-256 matches the manifest, then lay out
<out-dir>/<repo>/ with the card, LICENSE-MODEL, NOTICE, manifest.json (the
family's entry) and the GGUFs under their published names. Families with no
file are skipped: their Hub repo stays as it is.

Prints one line per assembled family, `<Family> <repo>`, which the workflow
reads to set HF_OIDC_RESOURCE per upload step. Stdlib only.
"""
import hashlib
import json
import os
import shutil
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url, dst):
    with urllib.request.urlopen(url) as r, open(dst, "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)


def main():
    out = sys.argv[1]
    only = set(sys.argv[2:])
    man = json.load(open(os.path.join(ROOT, "models", "manifest.json"), encoding="utf-8"))
    assembled = []
    for name, fam in man["families"].items():
        if only and name not in only:
            continue
        if not fam["files"]:
            print("skip %s: no file in manifest" % name, file=sys.stderr)
            continue
        dst = os.path.join(out, fam["repo"])
        os.makedirs(dst, exist_ok=True)
        shutil.copy(os.path.join(ROOT, fam["card"]), os.path.join(dst, "README.md"))
        shutil.copy(os.path.join(ROOT, "LICENSE-MODEL"), dst)
        shutil.copy(os.path.join(ROOT, "NOTICE"), dst)
        json.dump({"namespace": man["namespace"], "family": name, **fam},
                  open(os.path.join(dst, "manifest.json"), "w", encoding="utf-8"),
                  indent=2, ensure_ascii=False)
        for lang, spec in fam["files"].items():
            path = os.path.join(dst, spec["file"])
            print("%s/%s <- %s" % (name, lang, spec["source"]), file=sys.stderr)
            fetch(spec["source"], path)
            got = sha256(path)
            if got != spec["sha256"]:
                raise SystemExit("SHA-256 mismatch for %s: manifest %s, downloaded %s"
                                 % (spec["file"], spec["sha256"], got))
            if os.path.getsize(path) != spec["bytes"]:
                raise SystemExit("size mismatch for %s" % spec["file"])
            with open(path + ".sha256", "w") as f:
                f.write(got + "\n")
        assembled.append((name, fam["repo"]))
    for name, repo in assembled:
        print(name, repo)


if __name__ == "__main__":
    main()
