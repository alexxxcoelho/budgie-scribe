# -*- coding: utf-8 -*-
"""Ce que la bascule change sur le corpus REEL, et non sur l'echantillon.

Le banc tire 120 cas par classe pour que chaque verdict soit mesure avec la
meme precision. Le corpus, lui, est desequilibre : 675 saines, 373 suspectes,
187 verolees. Lire « 12 laisser-passer contre 7 » sur un echantillon equilibre
sur-represente donc les verolees d'un facteur trois et exagere l'ecart.

On repondere ici la matrice de confusion par la composition reelle, sous la
politique de filtrage effectivement utilisee : ON GARDE CE QUI EST DIT SAIN,
on rejette « suspect » comme « verole ».

Deux chiffres en sortent, et ils tirent en sens contraire :
  VOLUME        combien d'unites sur 1000 entrent dans le corpus d'entrainement
  CONTAMINATION quelle part de ces unites n'aurait pas du y entrer, dont la
                part VEROLEE, qui est la seule vraiment nuisible
"""
import json, os

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd
# Composition mesuree du corpus QC (qc_units_out.jsonl, 1235 unites).
REEL = {"sain": 675, "suspect": 373, "verole": 187}
TOTAL = sum(REEL.values())


def impact(nom):
    r = json.load(open(os.path.join(SP, "juge_%s_qc.json" % nom), encoding="utf-8"))
    c = r["confusion"]
    garde = {}
    for vrai in ("sain", "suspect", "verole"):
        d = c.get(vrai, {})
        n = sum(d.values())
        if not n:
            return None
        # taux auquel le juge declare « sain » une unite de cette vraie classe
        garde[vrai] = d.get("sain", 0) / n
    pour_mille = {k: 1000.0 * REEL[k] / TOTAL for k in REEL}
    retenu = {k: pour_mille[k] * garde[k] for k in REEL}
    total_retenu = sum(retenu.values())
    return {
        "modele": nom,
        "retenues_sur_1000": total_retenu,
        "dont_suspectes": retenu["suspect"],
        "dont_verolees": retenu["verole"],
        "contamination": 100.0 * (retenu["suspect"] + retenu["verole"]) / total_retenu,
        "verolees_pct": 100.0 * retenu["verole"] / total_retenu,
        "rappel_saines": 100.0 * garde["sain"],
    }


def main():
    lignes = [x for x in (impact(n) for n in ("deepseek-v4-flash", "gemma-12b-qat")) if x]
    if not lignes:
        print("aucune mesure QC elargie disponible")
        return
    print("Politique : on garde ce qui est declare SAIN. Corpus reel "
          "(%d saines / %d suspectes / %d verolees)."
          % (REEL["sain"], REEL["suspect"], REEL["verole"]))
    print()
    print("%-20s %10s %10s %12s %12s %10s"
          % ("juge", "retenues", "saines", "contamine", "dont verole", "rappel"))
    print("%-20s %10s %10s %12s %12s %10s"
          % ("", "/1000", "gardees", "% du gardé", "% du gardé", "saines"))
    print("-" * 78)
    for x in lignes:
        print("%-20s %10.0f %10.0f %11.1f%% %11.1f%% %9.1f%%"
              % (x["modele"], x["retenues_sur_1000"],
                 x["retenues_sur_1000"] - x["dont_suspectes"] - x["dont_verolees"],
                 x["contamination"], x["verolees_pct"], x["rappel_saines"]))
    if len(lignes) == 2:
        a, b = lignes
        print()
        print("Bascule DeepSeek -> %s :" % b["modele"])
        print("  volume        %+.0f unites pour 1000 (%.0f -> %.0f)"
              % (b["retenues_sur_1000"] - a["retenues_sur_1000"],
                 a["retenues_sur_1000"], b["retenues_sur_1000"]))
        print("  verolees      %+.1f point (%.1f%% -> %.1f%% du corpus retenu)"
              % (b["verolees_pct"] - a["verolees_pct"], a["verolees_pct"], b["verolees_pct"]))
        print("  contamination %+.1f point (%.1f%% -> %.1f%%)"
              % (b["contamination"] - a["contamination"], a["contamination"], b["contamination"]))
        print()
        print("Lecture : c'est la ligne VEROLEES qui compte. Une « suspecte »")
        print("laissee passer est une unite douteuse — DeepSeek lui-meme ne")
        print("reproduit que 58 %% de ses propres verdicts « suspect » — tandis")
        print("qu'une verolee est une transcription fausse dans l'entrainement.")


if __name__ == "__main__":
    main()
