# -*- coding: utf-8 -*-
"""Accord entre deux juges sur la MEME grille — le vrai test de determinisme.

POURQUOI PAS L'ACCORD AVEC L'OR
L'or vient de l'ancien prompt a trois classes, dont on a montre qu'il ne se
reproduit lui-meme qu'a 57 % sur la frontiere suspect/verole, et dont la
taxonomie de defauts n'a que cinq entrees sur les huit du nouveau schema.
Comparer la nouvelle grille a cet or mesure surtout l'ecart entre deux
definitions, pas la stabilite de la nouvelle.

CE QUI SE MESURE ICI
Deux modeles DIFFERENTS, la meme consigne, les memes entrees. Une grille
deterministe les fait converger ; une grille floue les laisse diverger. C'est
exactement la propriete demandee : « rendre le juge le plus deterministe
possible ».

  ACCORD VERDICT   part des cas ou les deux disent la meme chose, OK ou KO
  KAPPA            le meme accord, corrige du hasard. Deux juges qui diraient
                   KO partout seraient d'accord a 100 % sans rien juger ;
                   kappa vaut 0 dans ce cas et 1 pour un accord parfait.
  ACCORD CAUSE     quand les deux disent KO, citent-ils la meme cause ?
                   Mesure en exact (memes ensembles) et en intersection
                   (au moins une cause commune).

Usage : accord_juges.py <nomA> <nomB>
"""
import collections, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd


def charge(nom):
    p = os.path.join(SP, "qcbin_cas_%s.jsonl" % nom.replace("/", "_").replace(":", "_"))
    if not os.path.exists(p):
        raise SystemExit("absent : %s" % p)
    return {r["id"]: r for r in (json.loads(l) for l in open(p, encoding="utf-8"))}


def kappa(a, b):
    """Kappa de Cohen sur deux listes de verdicts alignees."""
    n = len(a)
    if not n:
        return 0.0
    acc = sum(1 for x, y in zip(a, b) if x == y) / n
    ca, cb = collections.Counter(a), collections.Counter(b)
    hasard = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return (acc - hasard) / (1 - hasard) if hasard < 1 else 0.0


def main():
    nomA, nomB = sys.argv[1], sys.argv[2]
    A, B = charge(nomA), charge(nomB)
    ids = sorted(set(A) & set(B))
    va = [A[i]["verdict"] for i in ids]
    vb = [B[i]["verdict"] for i in ids]

    n = len(ids)
    acc = sum(1 for x, y in zip(va, vb) if x == y)
    croise = collections.Counter((x, y) for x, y in zip(va, vb))

    ko_deux = [i for i in ids if A[i]["verdict"] == "KO" and B[i]["verdict"] == "KO"]
    exact = inter = 0
    paires = collections.Counter()
    for i in ko_deux:
        ca, cb = set(A[i]["causes"]), set(B[i]["causes"])
        exact += (ca == cb)
        inter += bool(ca & cb)
        for x in sorted(ca):
            for y in sorted(cb):
                if x != y:
                    paires[tuple(sorted((x, y)))] += 1

    print("\n=== %s  contre  %s — %d cas communs ===" % (nomA, nomB, n))
    print("  accord sur le verdict   %5.1f%%  (%d/%d)" % (100.0 * acc / max(1, n), acc, n))
    print("  kappa de Cohen          %5.2f   (0 = hasard, 1 = parfait)" % kappa(va, vb))
    print("\n  %-22s %8s %8s" % ("", nomB + " OK", nomB + " KO"))
    for x in ("OK", "KO"):
        print("  %-22s %8d %8d" % (nomA + " " + x, croise[(x, "OK")], croise[(x, "KO")]))
    if ko_deux:
        print("\n  quand LES DEUX disent KO (%d cas) :" % len(ko_deux))
        print("    meme ensemble de causes exactement %5.1f%%" % (100.0 * exact / len(ko_deux)))
        print("    au moins une cause commune         %5.1f%%" % (100.0 * inter / len(ko_deux)))
        if paires:
            print("\n    causes confondues le plus souvent :")
            for (x, y), k in paires.most_common(6):
                print("      %-16s <-> %-16s %3d" % (x, y, k))

    # L'or replie, pour situer les deux juges par rapport a la reference payante
    print("\n  situation contre l'or replie (sain -> OK) :")
    for nom, M in ((nomA, A), (nomB, B)):
        d = [M[i] for i in ids]
        acc_or = sum(1 for r in d if (r["verdict"] == "OK") == (r["or"] == "sain"))
        ko_manque = sum(1 for r in d if r["or"] != "sain" and r["verdict"] == "OK")
        faux_ko = sum(1 for r in d if r["or"] == "sain" and r["verdict"] == "KO")
        print("    %-18s accord %5.1f%%  | KO manques %3d | faux KO %3d"
              % (nom, 100.0 * acc_or / max(1, len(d)), ko_manque, faux_ko))


if __name__ == "__main__":
    main()
