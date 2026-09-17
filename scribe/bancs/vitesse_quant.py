# -*- coding: utf-8 -*-
"""Debit brut du modele charge — Q4_0 (QAT) contre Q4_K_M (standard).

POURQUOI UNE MESURE A PART
Le banc de juge donne des secondes par appel, mais ces appels n'ont ni la meme
longueur de prompt ni la meme longueur de reponse d'un modele a l'autre : un
modele plus bavard parait plus lent sans l'etre. Ici on fige tout — meme
prompt, meme nombre de tokens produits — et on lit les debits que llama-server
rapporte lui-meme dans le champ `timings`, donc mesures par le backend et non
deduits d'un chronometre cote client.

Deux debits, et ils ne dependent pas des memes noyaux :
  PROMPT    tokens lus par seconde, ou domine le produit matriciel dense
  GENERATION tokens ecrits par seconde, ou domine la DEQUANTIFICATION, poste
             sur lequel Q4_0 est structurellement plus simple que Q4_K_M
             (pas de super-blocs, pas de mise a l'echelle a deux niveaux)

Usage : vitesse_quant.py <etiquette> [repetitions]
"""
import json, os, statistics, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd
URL = "http://127.0.0.1:8899/v1/chat/completions"

# Un prompt fixe, assez long pour que la lecture compte, et une consigne qui
# force une reponse longue et previsible pour que la generation compte aussi.
PROMPT = ("Voici un extrait de transcription automatique en francais. "
          "Recopie-le mot pour mot, sans rien changer, sans rien ajouter, "
          "et repete l'operation jusqu'a epuisement de ta reponse.\n\n"
          + ("Alors euh je voulais te dire que vendredi non pardon jeudi on a "
             "rendez-vous a quatorze heures trente pour deux cent cinquante euros. ") * 6)


def mesure(n_tokens):
    corps = json.dumps({
        "model": "x",
        "messages": [{"role": "user", "content": PROMPT}],
        "temperature": 0,
        "max_tokens": n_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
        "reasoning_effort": "none",
        "cache_prompt": False,          # sinon la 2e passe lit un cache et ment
    }).encode("utf-8")
    req = urllib.request.Request(URL, data=corps,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        p = json.load(r)
    t = p.get("timings") or {}
    return t.get("prompt_per_second"), t.get("predicted_per_second"), t.get("predicted_n")


def main():
    etiquette = sys.argv[1]
    reps = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    try:
        with urllib.request.urlopen("http://127.0.0.1:8899/v1/models", timeout=5) as r:
            charge = json.load(r)["data"][0]["id"]
    except Exception:
        print("aucun serveur sur 8899")
        return
    print("\n=== debit brut — %s (charge : %s) ===" % (etiquette, charge))

    mesure(64)                                   # chauffe, jetee
    lec, gen, prod = [], [], []
    for i in range(reps):
        a, b, n = mesure(256)
        if a and b:
            lec.append(a); gen.append(b); prod.append(n)
            print("  passe %d : lecture %6.0f tok/s | generation %5.1f tok/s (%d tokens)"
                  % (i + 1, a, b, n), flush=True)
    if not gen:
        print("  aucune mesure exploitable")
        return
    res = {"etiquette": etiquette, "modele_charge": charge,
           "lecture_tok_s": statistics.median(lec),
           "generation_tok_s": statistics.median(gen),
           "tokens_produits": statistics.median(prod), "passes": len(gen)}
    print("  --- mediane sur %d passes ---" % len(gen))
    print("  lecture     %6.0f tok/s" % res["lecture_tok_s"])
    print("  generation  %6.1f tok/s" % res["generation_tok_s"])
    dst = os.path.join(SP, "vitesse_%s.json" % etiquette)
    json.dump(res, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("  -> %s" % dst)

    # comparaison si les deux cotes existent
    autre = {"qat": "std", "std": "qat"}.get(etiquette)
    p2 = os.path.join(SP, "vitesse_%s.json" % autre) if autre else None
    if p2 and os.path.exists(p2):
        o = json.load(open(p2, encoding="utf-8"))
        a, b = (res, o) if etiquette == "qat" else (o, res)
        print("\n  === Q4_0 (QAT) contre Q4_K_M (standard) ===")
        print("  %-12s %12s %12s %10s" % ("", "QAT Q4_0", "std Q4_K_M", "ecart"))
        for cle, nom in (("lecture_tok_s", "lecture"), ("generation_tok_s", "generation")):
            print("  %-12s %12.0f %12.0f %9.0f%%"
                  % (nom, a[cle], b[cle], 100 * (a[cle] / b[cle] - 1)))


if __name__ == "__main__":
    main()
