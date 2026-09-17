# -*- coding: utf-8 -*-
"""Met les juges cote a cote et tranche.

La lecture du tableau, dans l'ordre ou elle doit se faire :

  1. JSON casse       eliminatoire. Un juge qu'on doit reparer a la main n'est
                      pas un juge, c'est une corvee.
  2. EGALITE          verite terrain. 18 cas ou les deux sorties sont identiques
                      au caractere pres ; toute reponse autre que « egalite »
                      prouve que le juge n'a pas lu. DeepSeek : 18/18.
  3. MIROIR           verite terrain. Le meme cas pose dans les deux sens doit
                      donner la reponse inverse. C'est ici qu'on voit la
                      difference entre juger et deviner.
  4. LAISSER-PASSER   le risque metier : une transcription verolee declaree
                      saine entre dans le corpus d'entrainement.
  5. ACCORD QC        le plus faible des cinq. DeepSeek n'est pas la verite, et
                      un desaccord de SEUIL (« suspect » au lieu de « verole »)
                      se corrige par la consigne, pas par un plus gros modele.
"""
import glob, json, os

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd

# Taille sur disque, pour rapporter la qualite au cout reel en VRAM.
GO = {
    "qwen3.5-9b": 5.2, "gemma-12b-qat": 6.5, "gemma-12b": 6.9,
    "gemma-26b-a4b-qat": 13.5, "qwen3.8-27b": 15.7, "gemma-31b-qat": 16.4,
    "deepseek-v4-flash": 0.0,
}


def miroir_dur(r):
    """Le miroir SANS les cas gagnes d'avance.

    Les 18 cas ou les deux sorties sont identiques passent le miroir
    trivialement — « egalite » d'un cote, « egalite » de l'autre. Comme tous
    les modeles y font 18/18, chacun encaisse 22,5 % de points offerts. Le
    chiffre qui discrimine est celui des 62 cas reellement disputes. Il ne
    change pas le classement ; il en creuse les ecarts, et il evite de
    presenter comme « coherence » ce qui est en partie « facilite ».
    """
    n = r.get("ab_n") or 0
    if not n:
        return 0.0
    ident_ok, ident_n = 0, 0
    try:
        ident_ok, ident_n = (int(x) for x in r["ab_egalite_forcee"].split("/"))
    except Exception:
        pass
    miroir_ok = round(r["ab_miroir"] / 100.0 * n)
    durs = n - ident_n
    return 100.0 * (miroir_ok - ident_ok) / durs if durs > 0 else 0.0


def charge():
    rows = []
    for p in sorted(glob.glob(os.path.join(SP, "juge_*.json"))):
        try:
            r = json.load(open(p, encoding="utf-8"))
            r["_src"] = os.path.basename(p)
            rows.append(r)
        except Exception:
            pass
    # le plus petit d'abord : on cherche le plancher, pas le plafond
    return sorted(rows, key=lambda r: (GO.get(r["modele"], 99), r.get("reflexion", False)))


def main():
    rows = charge()
    if not rows:
        print("aucun resultat — lancez d'abord banc_juges.ps1")
        return

    entete = ("%-20s %5s %4s | %6s %7s %8s | %5s %6s %6s | %6s %6s"
              % ("modele", "Go", "refl", "egal", "miroir", "mir.dur", "laisse",
                 "acc.3", "acc.2", "s/app", "min"))
    print(entete)
    print("-" * len(entete))
    for r in rows:
        if not r.get("ab_n"):
            continue          # les passes QC-seules ont leur tableau plus bas
        ref = "oui" if r.get("reflexion") else "non"
        print("%-20s %5.1f %4s | %6s %6.1f%% %7.1f%% | %5d %5.1f%% %5.1f%% | %6.2f %6.1f"
              % (r["modele"], GO.get(r["modele"], 0), ref,
                 r["ab_egalite_forcee"], r["ab_miroir"], miroir_dur(r),
                 r["qc_laisser_passer"], r["qc_accord_3"], r["qc_accord_binaire"],
                 r["s_par_appel"], r["minutes_total"]))
        if r["json_casse"] or r["erreurs"]:
            print("%-20s   ^ JSON casse %d, erreurs %d"
                  % ("", r["json_casse"], r["erreurs"]))

    qc = [r for r in rows if not r.get("ab_n") and r.get("qc_verole_total")]
    if qc:
        print("\n=== QC elargi : le laisser-passer sur un vrai echantillon ===")
        print("  (sur 20 verolees l'ecart 3 contre 5 n'etait que du bruit ;")
        print("   ces lignes en comptent %d)" % max(r["qc_verole_total"] for r in qc))
        print("  %-34s %8s %10s %10s" % ("juge", "laisse", "signalees", "etiquetees"))
        for r in sorted(qc, key=lambda r: r["qc_laisser_passer"]):
            n = r["qc_verole_total"]
            nom = r["modele"] + (" +prompt calibre" if "_cal" in str(r.get("_src", "")) else "")
            print("  %-34s %3d/%-4d %9.1f%% %9.1f%%"
                  % (nom, r["qc_laisser_passer"], n,
                     r["qc_verole_signale"], r["qc_verole_attrape"]))

    # La question pratique : le juge local aurait-il conduit a la MEME decision ?
    # DeepSeek, sur ces 80 cas, a tranche 41 victoires pour p3-1200 contre 12
    # pour la base — c'est ce verdict-la qui a valide l'entrainement.
    print("\n=== la decision, pas seulement l'accord ===")
    print("  %-28s %6s %6s %8s   %s" % ("juge", "tuned", "base", "egalite", "conclusion"))
    for r in rows:
        v = r.get("verdict_brut") or {}
        t, b, e = v.get("tuned", 0), v.get("base", 0), v.get("egalite", 0)
        if t + b + e == 0:
            continue
        # DeepSeek a tranche « p3-1200 gagne ». La seule chose qui compte est
        # donc le SENS, pas un seuil arbitraire : 35/24 et 35/23 sont le meme
        # resultat et ne doivent pas recevoir deux etiquettes differentes.
        ratio = t / b if b else float("inf")
        concl = ("MEME SENS (x%.1f)" % ratio) if t > b else "SENS INVERSE"
        etiquette = "%s%s" % (r["modele"], " +refl" if r.get("reflexion") else "")
        print("  %-28s %6d %6d %8d   %s" % (etiquette, t, b, e, concl))

    ref = next((r for r in rows
                if r["modele"] == "deepseek-v4-flash" and r.get("ab_n")), None)
    if ref:
        print("\nreference payante : DeepSeek fait %s en egalite et %.1f%% en miroir."
              % (ref["ab_egalite_forcee"], ref["ab_miroir"]))
        seuil_miroir = ref["ab_miroir"]
        seuil_laisse = ref["qc_laisser_passer"]
    else:
        print("\n(pas de ligne DeepSeek : les seuils ci-dessous sont poses a la main)")
        seuil_miroir, seuil_laisse = 90.0, 2

    # Un candidat « suffisant » ne doit etre battu sur AUCUNE verite terrain.
    print("\n=== candidats suffisants ===")
    print("  eliminatoire : JSON intact, egalite 18/18, miroir >= %.1f%% "
          "(le niveau de DeepSeek)" % seuil_miroir)
    print("  le laisser-passer est reporte apres, comme un cout, pas comme "
          "une porte.")
    retenus = []
    for r in rows:
        # on ne juge que les passes COMPLETES : une passe QC-seule n'a ni
        # miroir ni egalite, elle echouerait sur des criteres qu'elle
        # n'a pas mesures.
        if r["modele"] == "deepseek-v4-flash" or not r.get("ab_n"):
            continue
        manques = []
        if r["json_casse"]:
            manques.append("JSON casse x%d" % r["json_casse"])
        if r["ab_egalite_pct"] < 100:
            manques.append("egalite %s" % r["ab_egalite_forcee"])
        if r["ab_miroir"] < seuil_miroir:
            manques.append("miroir %.1f%%" % r["ab_miroir"])
        # Le laisser-passer n'est PAS une porte ici. Dans le banc complet il
        # n'est mesure que sur 20 verolees, ou l'ecart « 3 contre 5 » s'est
        # revele pur bruit une fois porte a 120. On le reporte plus bas comme
        # un cout a peser, jamais comme un critere eliminatoire.
        etiquette = "%s%s" % (r["modele"], " +reflexion" if r.get("reflexion") else "")
        if manques:
            print("  NON  %-30s %s" % (etiquette, ", ".join(manques)))
        else:
            print("  OUI  %-30s %.1f Go, %.2f s/appel"
                  % (etiquette, GO.get(r["modele"], 0), r["s_par_appel"]))
            retenus.append(r)

    if retenus:
        # Le plus petit qui passe. C'est la consigne : suffisant, pas maximal.
        meilleur_qc = {}
        for x in rows:
            t = x.get("qc_verole_total") or 0
            if t > meilleur_qc.get(x["modele"], (0, None))[0]:
                meilleur_qc[x["modele"]] = (t, x)
        print("")
        print("=== le cout, une fois les incoherents ecartes ===")
        for nom in ["deepseek-v4-flash"] + [x["modele"] for x in retenus]:
            e = meilleur_qc.get(nom)
            if not e:
                continue
            n, d = e
            marque = "  (repere payant)" if nom == "deepseek-v4-flash" else ""
            print("  %-22s %5.1f%% de laisser-passer (%d/%d)%s"
                  % (nom, 100.0 * d["qc_laisser_passer"] / n,
                     d["qc_laisser_passer"], n, marque))
        best = min(retenus, key=lambda r: (GO.get(r["modele"], 99), r["s_par_appel"]))
        print("\n=> le plus petit qui tienne : %s%s (%.1f Go)"
              % (best["modele"], " avec reflexion" if best.get("reflexion") else "",
                 GO.get(best["modele"], 0)))
    else:
        print("\n=> aucun candidat ne passe tous les criteres")


if __name__ == "__main__":
    main()
