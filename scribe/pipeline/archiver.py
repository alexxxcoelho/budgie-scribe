# -*- coding: utf-8 -*-
"""Archive le repertoire de travail d'une langue dans le dataset PRIVE.

    python scribe/pipeline/archiver.py --lang en --build scribe-en-v7 --mix pairs_mix_en7.jsonl <sortie>
    python scribe/pipeline/archiver.py --lang fr --build scribe-v9    --mix pairs_mix9.jsonl    <sortie>
    hf upload flowcorp-ch/BudgieScribe-data <sortie> . --type dataset

POURQUOI
Le depot public ne contient aucune donnee (NOTICE §2), et le repertoire de
travail (SCRIBE_TRAVAIL, un `poc-<lang>` sur un disque local) est tout ce qui
permet de refaire un build : les paires melangees, leurs composantes, les
unites du corpus, les verdicts du professeur, les journaux, les scripts de
nuit. Les donnees francaises d'un build livre ont deja ete perdues une fois
avec un dossier temporaire (TRAINING.md §1). Ce script est la copie « quelque
part ailleurs », rangee pour qu'un autre que l'auteur retrouve chaque piece,
et un manifeste qui dit lequel de ces fichiers a produit quel build.

CE QU'IL FAIT
Lit le repertoire de travail, range chaque fichier dans la disposition de
`hf/BudgieScribe-data/README.md`, et complete <sortie>/manifest.json :

    mix/pairs_mix[_<lang>].jsonl   LE fichier d'entrainement du build (--mix)
    <lang>/pairs/                  ses composantes, une par generateur + le reel
    <lang>/corpus/                 unites, transcriptions ASR, verdicts QC,
                                   references, jeu A/B tenu a l'ecart
    <lang>/teacher/                sorties brutes et arbitrages du professeur
                                   (*.progress, *.adjudged) — des heures de GPU
    <lang>/history/                melanges et composantes des builds precedents
    <lang>/builds/<build>/run.json hyperparametres et courbe de perte de chaque run
    <lang>/logs/, <lang>/scripts/  journaux et chaines de nuit, tels quels
    <lang>/bench/                  sorties des bancs (evalsynth_*, gen_*, ab_*, ...)
    <lang>/pii_<mix>.txt           le rapport complet de pii_scan sur le mix

Il NE copie PAS : l'audio et les parquet (se regenerent depuis le Hub avec
`scribe/corpus/*.py`), les poids (`scribe-*/` : le GGUF livre est sur le Hub
via models/manifest.json, le bf16 reste sur la machine), les archives .zip
et les .md (la doc vit dans le depot).
Ce qu'il ecarte est liste en fin d'execution : une omission doit se voir.

`--code <dossier budgie-scribe>` ajoute sous code/scribe@<sha>/ le code qui a
produit le build (scribe/ et scripts/, sans caches ni donnees). Un build
entraine depuis un worktree detache n'a pas d'autre trace : les commits d'un
worktree disparaissent avec lui, et les generateurs d'une phase peuvent
n'avoir jamais atterri sur la branche que le depot public reflete.

DONNEES PERSONNELLES
`pii_scan.py` tourne sur le mix. Il designe, il ne juge pas : les telephones
et e-mails des familles synthetiques (itn-*, cmp-*, cri-*) sont des chiffres
au hasard et des domaines de gabarit, les identifiants de session VoxPopuli
(`20180612-0900`) ressemblent a des numeros. Le script range le rapport dans
l'archive et compte les signalements PAR FAMILLE dans le manifeste ; toute
famille qui n'est pas un generateur est imprimee pour etre LUE avant l'upload.
Le dataset est prive ; le tri qui rend un jeu publiable est `exporter_heldout.py`.
"""
import argparse
import collections
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

DEPOT = os.path.dirname(chemins.RACINE)
CARTE = os.path.join(DEPOT, "hf", "BudgieScribe-data", "README.md")
PII = os.path.join(chemins.RACINE, "pipeline", "pii_scan.py")

# Prefixes de `file` poses par les generateurs (spec.py / spec_en.py) : un
# signalement dans ces familles est synthetique par construction.
FAMILLES_SYNTH = ("itn-", "frm-", "cor-", "ter-", "cmp-", "cri-", "par-")

RE_CORPUS = re.compile(
    r"^(units_|cohere_units_|qc_units_|eval_set_)|_(unit_ref|unit_jobs|manifest)\.jsonl$"
    r"|_eval_(sessions|meetings)\.json$")
RE_HISTORIQUE = re.compile(r"^pairs_mix|\.v\d+\.jsonl$|^pairs_[a-z_]+\d+\.jsonl$")
RE_SESSION = re.compile(r"^\d{8}-\d{2,4}$")


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def lignes(p):
    with open(p, "rb") as f:
        return sum(1 for _ in f)


def destination(nom, lang, mix):
    """Le chemin relatif d'un fichier du travail dans l'archive, ou None."""
    if nom == mix:
        return "mix/pairs_mix%s.jsonl" % ("" if lang == "fr" else "_" + lang)
    if nom.endswith((".jsonl.progress", ".jsonl.adjudged")):
        return "%s/teacher/%s" % (lang, nom)
    if nom.startswith("pairs_") and nom.endswith(".jsonl"):
        return "%s/%s/%s" % (lang, "history" if RE_HISTORIQUE.search(nom) else "pairs", nom)
    if nom.endswith(".log"):
        return "%s/logs/%s" % (lang, nom)
    if RE_CORPUS.search(nom):
        return "%s/corpus/%s" % (lang, nom)
    if nom.endswith((".sh", ".cmd", ".ps1", ".py")):
        return "%s/scripts/%s" % (lang, nom)
    if nom.endswith((".jsonl", ".json", ".txt")):
        return "%s/bench/%s" % (lang, nom)
    return None


def copier(src, rel, sortie, manifeste):
    dst = os.path.join(sortie, rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)
    entree = {"bytes": os.path.getsize(dst), "sha256": sha256(dst)}
    if rel.endswith(".jsonl"):
        entree["lines"] = lignes(dst)
    manifeste[rel] = entree


def scanner(mix_local, rapport_local):
    """pii_scan sur le mix : rapport complet dans l'archive, comptes par
    (genre, famille) pour le manifeste, et les lignes a lire sur stdout."""
    res = subprocess.run([sys.executable, PII, mix_local], capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    with open(rapport_local, "w", encoding="utf-8") as f:
        f.write(res.stdout)
    rows = open(mix_local, encoding="utf-8").read().split("\n")
    par_genre, par_famille, a_lire = collections.Counter(), collections.Counter(), []
    for l in res.stdout.splitlines():
        m = re.match(r".*?:(\d+)\s+(\S+)\s+(.*)", l)
        if not m:
            continue
        r = json.loads(rows[int(m.group(1)) - 1])
        famille = r.get("file") or r.get("source") or "?"
        genre, valeur = m.group(2), m.group(3)
        synth = famille.startswith(FAMILLES_SYNTH)
        # L'identifiant de session d'une unite reelle (`20180612-0900-PLENARY`)
        # est dans la ligne que le scanner lit : un « telephone » qui commence
        # par la date de la famille est cet identifiant, pas un numero.
        if genre == "telephone" and RE_SESSION.match(valeur) and famille.startswith(valeur[:8]):
            genre = "id_session"
        par_genre[genre] += 1
        par_famille["%s/%s" % (genre, famille if synth else "REEL:" + famille)] += 1
        if not synth and genre != "id_session":
            a_lire.append("  %s:%s  %-18s %-24s %s" % (
                os.path.basename(mix_local), m.group(1), genre, famille, valeur[:60]))
    return {"lignes_signalees": sum(par_genre.values()), "par_genre": dict(par_genre),
            "par_famille": dict(sorted(par_famille.items()))}, a_lire


def archiver_code(dossier, sortie, fichiers):
    """scribe/ et scripts/ du depot qui a produit le build, sous code/scribe@<sha>/."""
    try:
        sha = subprocess.run(["git", "-C", dossier, "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        sha = os.path.basename(os.path.abspath(dossier))
    ignores = shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", "*.log", "*.gguf")
    racine = "code/scribe@%s" % sha
    for sous in ("scribe", "scripts"):
        src = os.path.join(dossier, sous)
        if not os.path.isdir(src):
            continue
        dst = os.path.join(sortie, racine, sous)
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst, ignore=ignores)
        for d, _, noms in os.walk(dst):
            for nom in noms:
                p = os.path.join(d, nom)
                rel = os.path.relpath(p, sortie).replace(os.sep, "/")
                fichiers[rel] = {"bytes": os.path.getsize(p), "sha256": sha256(p)}
    return racine


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("sortie", help="dossier de l'archive (le meme pour toutes les langues)")
    ap.add_argument("--lang", default=chemins.LANG)
    ap.add_argument("--build", required=True, help="nom du build livre, ex. scribe-en-v7")
    ap.add_argument("--mix", required=True, help="le pairs_mix*.jsonl qui l'a produit")
    ap.add_argument("--travail", default=chemins.TRAVAIL, help="defaut : SCRIBE_TRAVAIL")
    ap.add_argument("--code", help="le budgie-scribe/ (worktree) dont le code a produit le build")
    a = ap.parse_args()

    travail, sortie, lang = a.travail, a.sortie, a.lang
    if not os.path.isfile(os.path.join(travail, a.mix)):
        raise SystemExit("mix introuvable : %s" % os.path.join(travail, a.mix))
    if not os.path.isfile(os.path.join(travail, a.build, "run.json")):
        raise SystemExit("pas de run.json dans %s" % os.path.join(travail, a.build))
    os.makedirs(sortie, exist_ok=True)

    chemin_manifeste = os.path.join(sortie, "manifest.json")
    manifeste = json.load(open(chemin_manifeste, encoding="utf-8")) if os.path.exists(chemin_manifeste) \
        else {"$comment": "Ecrit par scribe/pipeline/archiver.py ; une entree par langue "
                          "sous `langues`, une par fichier sous `fichiers` (SHA-256, octets, lignes).",
              "langues": {}, "fichiers": {}}
    fichiers = manifeste["fichiers"]
    ecartes, runs = [], {}

    for nom in sorted(os.listdir(travail)):
        src = os.path.join(travail, nom)
        if os.path.isdir(src):
            run = os.path.join(src, "run.json")
            if nom.startswith("scribe-") and os.path.isfile(run):
                rel = "%s/builds/%s/run.json" % (lang, nom)
                copier(run, rel, sortie, fichiers)
                r = json.load(open(run, encoding="utf-8"))
                r.pop("log", None)
                runs[nom] = r
            else:
                ecartes.append(nom + "/")
            continue
        rel = destination(nom, lang, a.mix)
        if rel is None:
            ecartes.append(nom)
            continue
        copier(src, rel, sortie, fichiers)

    rel_mix = "mix/pairs_mix%s.jsonl" % ("" if lang == "fr" else "_" + lang)
    rapport = "%s/pii_%s.txt" % (lang, a.mix.replace(".jsonl", ""))
    pii, a_lire = scanner(os.path.join(travail, a.mix), os.path.join(sortie, rapport))
    fichiers[rapport] = {"bytes": os.path.getsize(os.path.join(sortie, rapport))}

    manifeste["langues"][lang] = {
        "build": a.build,
        "mix": rel_mix,
        "mix_source": a.mix,
        "train": runs.get(a.build),
        "code": archiver_code(a.code, sortie, fichiers) if a.code else None,
        "builds": runs,
        "pii_scan": pii,
        "archive": time.strftime("%Y-%m-%d"),
    }
    with open(chemin_manifeste, "w", encoding="utf-8") as f:
        json.dump(manifeste, f, ensure_ascii=False, indent=2)
    if os.path.isfile(CARTE):
        shutil.copyfile(CARTE, os.path.join(sortie, "README.md"))

    n = sum(1 for k in fichiers if k.startswith(lang + "/") or k == rel_mix)
    print("%s : %d fichiers ranges sous %s ; mix %s -> %s (%d lignes)" % (
        lang, n, sortie, a.mix, rel_mix, fichiers[rel_mix]["lines"]))
    print("pii_scan : %d ligne(s) signalee(s), par genre %s" % (pii["lignes_signalees"], pii["par_genre"]))
    if a_lire:
        print("A LIRE avant l'upload — signalements hors familles synthetiques :")
        print("\n".join(a_lire))
    if ecartes:
        print("ecartes (audio, poids, archives, doc) : " + ", ".join(ecartes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
