# -*- coding: utf-8 -*-
"""Reprise et tracabilite des appels API payants.

Le principe, apres la nuit du 2026-09-01 : CE QUI A ETE PAYE EST GARDE.

Un lot de 7 724 unites s'etait vide en cours de route ; 278 verdicts etaient
valides et 7 446 en erreur. Relancer le lot entier aurait rejete les 278 deja
payes. La bonne reponse n'est pas de plafonner la depense — c'est de ne jamais
repayer ce qu'on possede deja.

Ce module fournit donc :
  - `done_ids(path, valid)` : ce qui est deja acquis dans un fichier de sortie,
    selon un predicat de validite fourni par l'appelant ;
  - `open_append(path)` : reprendre l'ecriture sans tronquer ;
  - un journal de depense, informatif, qui n'interdit rien.
"""
import json, os, time

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd
LEDGER = os.path.join(SP, "depenses.jsonl")


def balance():
    import llm
    ok, detail = llm.deepseek_ok()
    if not ok:
        return None, detail
    try:
        return float(detail.split()[1]), detail
    except Exception:
        return None, detail


def record(label, usd, items, note=""):
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps({"t": time.strftime("%Y-%m-%d %H:%M:%S"), "label": label,
                            "usd": round(usd, 4), "items": items, "note": note},
                           ensure_ascii=False) + "\n")


def spent_total():
    if not os.path.exists(LEDGER):
        return 0.0
    return sum(json.loads(l).get("usd", 0) for l in open(LEDGER, encoding="utf-8"))


def done_ids(path, valid):
    """Identifiants deja acquis dans `path`, selon le predicat `valid`.

    Une ligne illisible ou un enregistrement juge invalide (verdict en erreur,
    sortie vide…) n'est PAS compte comme acquis : il sera refait. Tout le reste
    est conserve tel quel.
    """
    got = {}
    if not os.path.exists(path):
        return got
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        rid = rec.get("id")
        if rid and valid(rec):
            got[rid] = rec
    return got


def rewrite_kept(path, kept):
    """Reecrit le fichier avec uniquement ce qui est acquis, puis rend un
    descripteur ouvert en ajout pour la suite. Les lignes en erreur du run
    precedent disparaissent ; les bonnes restent."""
    with open(path, "w", encoding="utf-8") as f:
        for rec in kept.values():
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return open(path, "a", encoding="utf-8")


def announce(label, n_total, n_done, per_item_usd=None, log=print):
    """Dit ce qui reste a payer. N'interdit rien — c'est une information, pas
    une barriere : le seul vrai gaspillage est de repayer l'acquis."""
    n_left = n_total - n_done
    bal, detail = balance()
    msg = "[budget] %s : %d/%d deja acquis, %d a faire" % (label, n_done, n_total, n_left)
    if per_item_usd:
        msg += " (~%.2f $)" % (per_item_usd * n_left)
    msg += " | %s" % detail
    log(msg)
    if bal is not None and per_item_usd and per_item_usd * n_left > bal:
        log("[budget] ATTENTION : le reste coute plus que le solde. Le lot ira "
            "aussi loin que possible et TOUT CE QUI EST PAYE SERA CONSERVE ; "
            "une relance ne refera que ce qui manque.")
    return n_left


if __name__ == "__main__":
    print("solde :", balance()[1])
    print("depense tracee : %.3f $" % spent_total())
