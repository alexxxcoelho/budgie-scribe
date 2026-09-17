# -*- coding: utf-8 -*-
"""Tri mecanique des unites SUMM-RE avant la lecture.

La lecon du filtre de paires (notes d'entrainement §0.15) s'applique ici aussi, mais dans
l'autre sens : un comparateur de surface ne doit pas TRANCHER, en revanche il
trie tres bien. Sur des unites courtes alignees 1:1 avec une reference humaine,
deux signaux suffisent a isoler l'ambigu :

  - le RATIO de mots contre la reference humaine, qui attrape l'effondrement
    (trop peu) et l'hallucination (trop) ;
  - la REPETITION maximale d'un n-gramme, qui attrape la boucle.

Ce qui tombe dans la bande franche part directement a l'entrainement ; le reste
seul va au juge. Sur 7 724 unites, ca divise la facture de lecture par six.
"""
import json, os, sys, collections, statistics

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd

# Bandes calibrees sur la distribution mesuree : mediane 0,92, p10 0,74, p90 1,20.
CLEAR_LOW, CLEAR_HIGH = 0.75, 1.30
DOUBT_LOW, DOUBT_HIGH = 0.45, 2.00
MAX_NGRAM_REPEAT = 3
NGRAM = 6


def max_ngram_repeat(text, n=NGRAM):
    w = text.split()
    if len(w) < n * 2:
        return 1
    counts = collections.Counter(" ".join(w[i:i + n]) for i in range(len(w) - n + 1))
    return counts.most_common(1)[0][1]


def main():
    refs = {json.loads(l)["id"]: json.loads(l)
            for l in open(os.path.join(SP, "summre_unit_ref.jsonl"), encoding="utf-8")}
    rows = [json.loads(l) for l in open(os.path.join(SP, "cohere_units.jsonl"), encoding="utf-8")]

    clear, doubt, reject = [], [], []
    stats = collections.Counter()
    for r in rows:
        ref = refs.get(r["id"])
        if not ref or ref["words"] < 8:
            reject.append((r["id"], "reference trop courte")); stats["ref courte"] += 1; continue
        if r.get("error"):
            reject.append((r["id"], "erreur de decodage")); stats["erreur"] += 1; continue
        text = r["text"].strip()
        if not text:
            reject.append((r["id"], "sortie vide")); stats["vide"] += 1; continue
        ratio = r["words"] / ref["words"]
        rep = max_ngram_repeat(text)
        if rep > MAX_NGRAM_REPEAT:
            reject.append((r["id"], "boucle (%d-gramme x%d)" % (NGRAM, rep))); stats["boucle"] += 1; continue
        if ratio < DOUBT_LOW or ratio > DOUBT_HIGH:
            reject.append((r["id"], "ratio hors bande (%.2f)" % ratio)); stats["ratio extreme"] += 1; continue
        if CLEAR_LOW <= ratio <= CLEAR_HIGH:
            clear.append(r["id"]); stats["bande franche"] += 1
        else:
            doubt.append(r["id"]); stats["a faire lire"] += 1

    print("unites : %d" % len(rows))
    for k, v in stats.most_common():
        print("   %-18s %5d  (%.0f%%)" % (k, v, 100.0 * v / len(rows)))
    print()
    print("-> %d partent directement, %d vont au juge, %d ecartees mecaniquement"
          % (len(clear), len(doubt), len(reject)))

    with open(os.path.join(SP, "units_clear.json"), "w") as f:
        json.dump(clear, f)
    with open(os.path.join(SP, "units_doubt.json"), "w") as f:
        json.dump(doubt, f)
    with open(os.path.join(SP, "units_rejected.jsonl"), "w", encoding="utf-8") as f:
        for i, why in reject:
            f.write(json.dumps({"id": i, "motif": why}, ensure_ascii=False) + "\n")

    # Le sous-ensemble a lire, au format attendu par qc_pass.py
    idx = {r["id"]: r for r in rows}
    with open(os.path.join(SP, "qc_units_in.jsonl"), "w", encoding="utf-8") as f:
        for i in doubt:
            f.write(json.dumps(idx[i], ensure_ascii=False) + "\n")
    print("ecrit : units_clear.json, units_doubt.json, qc_units_in.jsonl")


if __name__ == "__main__":
    main()
