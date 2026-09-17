# -*- coding: utf-8 -*-
"""Genere les sorties d'un modele sur un jeu d'evaluation, sur ROCm.

Meme sortie que gen_dml.py — {id, control, dirty, out} — pour rester
comparable aux generations deja faites. Seul l'appareil change.
"""
import json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd
os.environ.setdefault("HF_HOME", os.path.join(SP, "..", "hf"))
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
import torch
sys.path.insert(0, os.path.join(chemins.RACINE, "bancs"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import modeles                 # profils, chargement, construction du prompt
from eval_synth import choisir_gpu

def main():
    which, src, dst = sys.argv[1], sys.argv[2], sys.argv[3]
    n = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    gi = choisir_gpu()
    dev = torch.device("cuda:%d" % gi) if gi is not None else "cpu"
    # `base` compare a la base du profil courant (SCRIBE_PROFIL) ; un dossier
    # entraine porte sa propre base dans run.json.
    tok, model, template = modeles.charger(which, dev)
    rows = [json.loads(l) for l in open(src, encoding="utf-8")]
    if n: rows = rows[:n]
    print("%s : %d cas" % (which, len(rows)), flush=True)
    t0 = time.time()
    with open(dst, "w", encoding="utf-8") as f:
        for i, r in enumerate(rows):
            p = modeles.construire_prompt(tok, r["control"], r["dirty"], template)
            ids = tok(p, return_tensors="pt").to(dev)
            with torch.no_grad():
                out = model.generate(**ids,
                                     max_new_tokens=int(1.3 * ids.input_ids.shape[1]) + 32,
                                     do_sample=False, use_cache=True,
                                     pad_token_id=tok.eos_token_id)
            got = tok.decode(out[0][ids.input_ids.shape[1]:], skip_special_tokens=True).strip()
            f.write(json.dumps({"id": r["id"], "control": r["control"],
                                "dirty": r["dirty"], "out": got}, ensure_ascii=False) + "\n")
            f.flush()
            if (i + 1) % 20 == 0:
                print("   %d/%d (%.1f min)" % (i + 1, len(rows), (time.time()-t0)/60), flush=True)
    print("-> %s en %.1f min" % (dst, (time.time()-t0)/60))

if __name__ == "__main__":
    main()
