# -*- coding: utf-8 -*-
"""Des verdicts QC aux unites pretes pour le professeur — et au jeu d'A/B.

POURQUOI CE FICHIER EXISTE
En francais, cette etape a ete faite a la main entre qc_pass.py et teach.py :
un filtre sur le verdict, un tirage de ligne de controle par unite, et un
jeu d'evaluation de 80 cas mis de cote. Trois gestes sans trace, qu'il a
fallu reconstituer pour l'anglais. Ils sont ici, et ils sont deterministes.

Entrees :
  <cohere.jsonl>   sortie du harnais Cohere (poc_scribe_corpus.rs) : {id, text, ...}
  <qc.jsonl>       verdicts de qc_pass.py : {id, verdict, causes, ...}
  <ref.jsonl>      references d'unites (voxpopuli.py / summre_units.py) :
                   {id, held_out, session_id|meeting_id, ...}
Sorties :
  <unites.jsonl>   ce que teach.py attend : {id, dirty, lang, source, file,
                   styling, structure, context, held_out}
  <eval_set.jsonl> 80 unites TENUES A L'ECART, verdict OK, pour l'A/B :
                   {id, file, lang, styling, structure, context, control, dirty}

La ligne de controle est TIREE par unite avec spec.sample_control (40 % de
defaut, le reste au sort) : c'est ce que le professeur recevra, donc ce que
le modele apprendra a suivre. Les unites tenues a l'ecart gardent leur
drapeau : teach.py les enseigne aussi, mais train_rocm.py les ecarte, et
c'est parmi elles que l'A/B tire ses cas — aucun contenu d'evaluation ne
traverse l'entrainement.

Usage : preparer_unites.py <cohere.jsonl> <qc.jsonl> <ref.jsonl> <unites.jsonl> <eval_set.jsonl> [source=voxpopuli]
"""
import collections, json, os, random, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd
spec = chemins.spec()
SEED = 20260905
N_EVAL = 80


def _p(x):
    return x if os.path.isabs(x) else os.path.join(SP, x)


def main():
    if len(sys.argv) < 6:
        print(__doc__)
        return 2
    cohere_p, qc_p, ref_p, out_p, eval_p = [_p(a) for a in sys.argv[1:6]]
    source = sys.argv[6] if len(sys.argv) > 6 else "voxpopuli"

    cohere = {}
    for l in open(cohere_p, encoding="utf-8"):
        r = json.loads(l)
        cohere[r["id"]] = r
    qc = {}
    for l in open(qc_p, encoding="utf-8"):
        r = json.loads(l)
        qc[r["id"]] = r
    ref = {}
    for l in open(ref_p, encoding="utf-8"):
        r = json.loads(l)
        ref[r["id"]] = r

    rng = random.Random(SEED)
    stats = collections.Counter()
    unites = []
    for uid in sorted(cohere):
        c = cohere[uid]
        v = qc.get(uid)
        if not v:
            stats["sans verdict"] += 1
            continue
        if (v.get("verdict") or "").strip().upper() != "OK":
            stats["KO:" + ",".join(v.get("causes") or ["?"])] += 1
            continue
        text = (c.get("text") or "").strip()
        if not text:
            stats["vide"] += 1
            continue
        r = ref.get(uid, {})
        styling, structure, context = spec.sample_control(rng)
        unites.append({
            "id": uid, "dirty": text, "lang": c.get("lang", spec.LANG), "source": source,
            "file": r.get("session_id") or r.get("meeting_id") or uid.split("_")[0],
            "styling": styling, "structure": structure, "context": context,
            "held_out": bool(r.get("held_out")),
        })
        stats["OK"] += 1

    with open(out_p, "w", encoding="utf-8") as f:
        for u in unites:
            f.write(json.dumps(u, ensure_ascii=False) + "\n")

    # Le jeu d'A/B : 80 unites tenues a l'ecart, verdict OK, en DEFAUT de
    # controle (semi-formal/prose/general) — c'est le reglage que le produit
    # enverra presque toujours, et celui de tous les A/B francais.
    tenues = [u for u in unites if u["held_out"]]
    rng2 = random.Random(SEED + 1)
    choisies = rng2.sample(tenues, min(N_EVAL, len(tenues)))
    with open(eval_p, "w", encoding="utf-8") as f:
        for u in choisies:
            f.write(json.dumps({
                "id": u["id"], "file": u["file"], "lang": u["lang"],
                "styling": "semi-formal", "structure": "prose", "context": "general",
                "control": spec.control_line("semi-formal", "prose", "general", u["lang"]),
                "dirty": u["dirty"],
            }, ensure_ascii=False) + "\n")

    n = len(cohere)
    print("=== %d unites transcrites -> %d retenues (%.0f %%) ===" % (n, len(unites), 100.0 * len(unites) / max(1, n)))
    for k, v in stats.most_common():
        print("   %-28s %5d" % (k, v))
    combos = collections.Counter((u["styling"], u["structure"], u["context"]) for u in unites)
    print("   lignes de controle : %d combinaisons, defaut %d (%.0f %%)"
          % (len(combos), combos[("semi-formal", "prose", "general")],
             100.0 * combos[("semi-formal", "prose", "general")] / max(1, len(unites))))
    print("   tenues a l'ecart : %d  |  jeu d'A/B : %d" % (len(tenues), len(choisies)))
    print("-> %s\n-> %s" % (out_p, eval_p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
