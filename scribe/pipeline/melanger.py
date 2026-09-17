# -*- coding: utf-8 -*-
"""Melange de jeux de paires en un fichier d'entrainement — et rien d'autre.

POURQUOI UN FICHIER POUR SI PEU
Les huit melanges francais (pairs_mix.jsonl a pairs_mix8.jsonl) ont ete faits
a la main, sans trace : la composition de chacun se retrouve en recomptant les
champs `source` apres coup. Pour l'anglais, et pour toute langue suivante, la
composition est un FAIT de mesure — « 86 % de synthetique, 14 % de reel » est
une des lignes de §0.21 — donc elle doit sortir du script qui la produit, pas
d'une archeologie.

Le script ne filtre rien : `held_out` reste porte par chaque paire, et c'est
l'entrainement (train_rocm.py) qui ecarte les paires tenues a l'ecart. Melanger
et filtrer dans le meme geste ferait disparaitre le jeu d'evaluation du
fichier, donc de la trace.

Usage : melanger.py <sortie.jsonl> <entree1.jsonl> [entree2.jsonl ...]
"""
import collections, json, os, random, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd
SEED = 20260905


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    out = sys.argv[1] if os.path.isabs(sys.argv[1]) else os.path.join(SP, sys.argv[1])
    rows, par_source, par_fichier, langues = [], collections.Counter(), {}, collections.Counter()
    for src in sys.argv[2:]:
        p = src if os.path.isabs(src) else os.path.join(SP, src)
        n = 0
        for l in open(p, encoding="utf-8"):
            r = json.loads(l)
            rows.append(r)
            par_source[r.get("source", "?")] += 1
            langues[r.get("lang", "?")] += 1
            n += 1
        par_fichier[os.path.basename(p)] = n
    if len(langues) > 1:
        # Un modele par langue : un melange bilingue est presque surement une
        # erreur de ligne de commande, pas une intention.
        print("!!! plusieurs langues dans le melange : %s" % dict(langues))
        return 1
    random.Random(SEED).shuffle(rows)
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    total = len(rows)
    tenues = sum(1 for r in rows if r.get("held_out"))
    print("=== %s — %d paires, langue %s ===" % (os.path.basename(out), total, next(iter(langues))))
    for nom, n in par_fichier.items():
        print("   %-28s %6d" % (nom, n))
    print()
    synth = sum(n for s, n in par_source.items() if s in ("itn", "correction", "forme", "compo", "coritn"))
    for s, n in par_source.most_common():
        print("   %-12s %6d  %5.1f %%" % (s, n, 100.0 * n / total))
    print("   synthetique %6d  %5.1f %%  |  reel %6d  %5.1f %%"
          % (synth, 100.0 * synth / total, total - synth, 100.0 * (total - synth) / total))
    print("   tenues a l'ecart (exclues par l'entrainement) : %d" % tenues)
    print("-> %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
