# -*- coding: utf-8 -*-
"""Evaluation ITN par comparaison litterale — aucun juge, aucun cout.

L'ITN est le seul bloc du projet dont la verite terrain est EXACTE : la paire
a ete fabriquee en partant de la valeur, donc la sortie attendue est connue au
caractere pres. On mesure donc par egalite de chaines, pas par lecture.

Trois chiffres, et ils ne disent pas la meme chose :

  EXACT      la sortie est identique a l'attendu. C'est la barre haute.
  VALEURS    tous les nombres attendus sont presents et aucun nombre etranger
             n'apparait. C'est la barre qui compte pour la SURETE : un modele
             qui ecrit « 14 h 30 » au lieu de « 14h30 » se trompe de forme,
             pas de fait.
  INVENTE    un nombre apparait en sortie sans exister dans l'attendu. C'est la
             faute grave — celle qui a fait ecrire « 20 000 » pour
             « vingt-trois mille quatre cent cinquante ».

Usage : eval_itn.py <modele|base> [n]
"""
import json, os, re, sys, time, collections

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd
os.environ.setdefault("HF_HOME", os.path.join(SP, "..", "hf"))
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "entrainement"))
import modeles                 # profils, chargement, construction du prompt

NUM = re.compile(r"\d[\d  ]*(?:,\d+)?")


def numbers(s):
    """Les valeurs numeriques d'une chaine, espaces de milliers retires, pour
    que « 23 450 » et « 23450 » comptent comme la meme valeur."""
    out = []
    for m in NUM.finditer(s):
        v = m.group(0).replace(" ", "").replace(" ", "").rstrip(",")
        if v:
            out.append(v)
    return collections.Counter(out)


def main():
    which = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    # Meme choix d'appareil que les autres bancs (ROCm/CUDA, sinon CPU) ;
    # torch-directml, qui vivait ici, est parti avec train_dml.py.
    from eval_synth import choisir_gpu
    gi = choisir_gpu()
    if gi is None:
        dev, where = "cpu", "CPU"
        torch.set_num_threads(os.cpu_count())
    else:
        dev = torch.device("cuda:%d" % gi)
        where = torch.cuda.get_device_properties(gi).name

    rows = [json.loads(l) for l in open(os.path.join(SP, "pairs_itn.jsonl"), encoding="utf-8")
            if json.loads(l)["held_out"]]
    if limit:
        rows = rows[:limit]

    tok, model, template = modeles.charger(which, dev)
    path = modeles.resoudre(which)[0]     # nomme le fichier de resultats
    print("%s sur %s : %d cas tenus a l'ecart" % (which, where, len(rows)), flush=True)

    stats = collections.Counter()
    per_family = collections.defaultdict(lambda: collections.Counter())
    faults = []
    t0 = time.time()
    for i, r in enumerate(rows):
        prompt = modeles.construire_prompt(tok, r["control"], r["dirty"], template)
        ids = tok(prompt, return_tensors="pt").to(dev)
        with torch.no_grad():
            out = model.generate(**ids, max_new_tokens=min(120, int(1.3 * ids.input_ids.shape[1]) + 32),
                                 do_sample=False, use_cache=True, pad_token_id=tok.eos_token_id)
        got = tok.decode(out[0][ids.input_ids.shape[1]:], skip_special_tokens=True).strip()
        fam = r["file"][4:]
        want = r["clean"]

        exact = got.strip() == want.strip()
        nw, ng = numbers(want), numbers(got)
        valeurs = (nw == ng)
        invente = bool(ng - nw)

        stats["n"] += 1
        stats["exact"] += exact
        stats["valeurs"] += valeurs
        stats["invente"] += invente
        per_family[fam]["n"] += 1
        per_family[fam]["exact"] += exact
        per_family[fam]["valeurs"] += valeurs
        per_family[fam]["invente"] += invente
        if invente or not valeurs:
            faults.append({"famille": fam, "entree": r["dirty"], "attendu": want, "obtenu": got})
        if (i + 1) % 100 == 0:
            print("   %d/%d (%.1f min)" % (i + 1, len(rows), (time.time() - t0) / 60), flush=True)

    n = max(1, stats["n"])
    print("\n=== %s — %d cas ===" % (which, n))
    print("EXACT            %4d  %5.1f%%" % (stats["exact"], 100 * stats["exact"] / n))
    print("VALEURS justes   %4d  %5.1f%%" % (stats["valeurs"], 100 * stats["valeurs"] / n))
    print("NOMBRE INVENTE   %4d  %5.1f%%   <-- la faute grave" % (stats["invente"], 100 * stats["invente"] / n))
    print()
    print("%-16s %5s %8s %9s %9s" % ("famille", "n", "exact", "valeurs", "invente"))
    for fam in sorted(per_family):
        c = per_family[fam]
        print("%-16s %5d %7.0f%% %8.0f%% %8.0f%%"
              % (fam, c["n"], 100 * c["exact"] / c["n"], 100 * c["valeurs"] / c["n"],
                 100 * c["invente"] / c["n"]))

    out_path = os.path.join(SP, "eval_itn_%s.json" % os.path.basename(str(path)).replace("/", "_"))
    json.dump({"model": str(path), "stats": dict(stats),
               "per_family": {k: dict(v) for k, v in per_family.items()},
               "faults": faults[:60]}, open(out_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    if faults:
        print("\n=== 5 fautes ===")
        for f in faults[:5]:
            print("  [%s] %s" % (f["famille"], f["entree"][:90]))
            print("      attendu : %s" % f["attendu"][:90])
            print("      obtenu  : %s" % f["obtenu"][:90])
    print("\n-> %s" % out_path)


if __name__ == "__main__":
    main()
