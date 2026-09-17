# -*- coding: utf-8 -*-
"""Compositions ITN — plusieurs expressions numeriques dans UNE phrase.

LE TROU QUE CE FICHIER BOUCHE
`gen_itn.py` produit exactement UNE expression numerique par paire, et
`gen_forme.py` n'en produit qu'une aussi (le compte d'une liste). Mesure sur
pairs_mix3.jsonl : 3 familles d'expression ou plus, **0,0 %**. Le modele n'a
donc jamais vu de phrase contenant une heure ET un montant.

Ce que ca casse, verifie sur trois cas :

    « a quatorze heures trente pour deux cent cinquante euros »
        -> « a 14h30 euros. »            le montant est perdu
    « a neuf heures pour trois cents euros »
        -> « a 9h03 euros. »             heure et montant FUSIONNES
    « vingt-trois mille quatre cent cinquante euros ... trois mars deux mille vingt-six »
        -> « 23 450,26 euros. »          la date absorbee en decimales

C'est la lecon des contre-exemples vue sous un autre angle : ce qu'on ne montre
jamais, le modele apprend a ne jamais produire. Ici il a appris « un nombre par
sortie » et fusionne tout ce qui depasse.

Usage : gen_compo.py [n] [sortie.jsonl]
"""
import collections, json, os, random, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd
SEED = 20260904
CONTROL = "[Styling: semi-formal] [Structure: prose] [Context: general] [Lang: fr]"
HESITATIONS = ["euh ", "bah ", "ben ", "alors euh ", "hum ", "", "", ""]

from num2words import num2words

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]
PRENOMS = ["Marie", "Julie", "Thomas", "Sophie", "Camille", "Lucas", "Antoine",
           "Claire", "Pierre", "Sarah", "Hugo", "Laura", "Manon", "Inès"]
OBJETS = ["le devis", "la facture", "le contrat", "la commande", "le dossier",
          "le rapport", "la prestation", "l'acompte"]
DOMAINES = ["google", "github", "gobudgie", "anthropic", "leboncoin",
            "service-public", "ameli"]


def mot(n):
    return num2words(n, lang="fr")


def esp(n):
    """Espace de milliers, comme le corpus l'ecrit : « 23 450 »."""
    return "{:,}".format(n).replace(",", " ")


# ── Fragments : (dicte, ecrit). Aucune phrase porteuse ici — c'est justement
#    ce qui manquait pour pouvoir les COMBINER.
def f_heure(rng):
    h = rng.randint(7, 20)
    forme = rng.choices(["pile", "minutes", "demie", "quart"], weights=[35, 35, 20, 10])[0]
    if forme == "pile":
        return "%s heures" % mot(h), "%dh" % h
    if forme == "demie":
        return "%s heures et demie" % mot(h), "%dh30" % h
    if forme == "quart":
        return "%s heures et quart" % mot(h), "%dh15" % h
    mn = rng.choice([5, 10, 15, 20, 30, 40, 45, 50])
    return "%s heures %s" % (mot(h), mot(mn)), "%dh%02d" % (h, mn)


def f_montant(rng):
    n = rng.choice([50, 80, 120, 150, 250, 300, 450, 800, 1200, 2500, 4800,
                    12000, 23450, 35000])
    dev = rng.choices(["euros", "dollars"], weights=[9, 1])[0]
    return "%s %s" % (mot(n), dev), "%s %s" % (esp(n), dev)


def f_date(rng):
    j = rng.randint(1, 28)
    m = rng.choice(MOIS)
    a = rng.randint(2024, 2027)
    if rng.random() < 0.35:
        return "%s %s" % (mot(j) if j > 1 else "premier", m), \
               "%d %s" % (j, m)
    return "%s %s %s" % (mot(j) if j > 1 else "premier", m, mot(a)), \
           "%d %s %d" % (j, m, a)


def f_pourcent(rng):
    n = rng.choice([5, 10, 15, 20, 25, 30, 40, 50, 60, 75])
    return "%s pour cent" % mot(n), "%d %%" % n


def f_entier(rng):
    n = rng.randint(2, 60)
    return mot(n), str(n)


def f_email(rng):
    u = rng.choice(["contact", "support", "compta", "info", "devis"])
    d = rng.choice(DOMAINES)
    t = rng.choice(["com", "fr"])
    return "%s arobase %s point %s" % (u, d.replace("-", " tiret "), t), \
           "%s@%s.%s" % (u, d, t)


def f_url(rng):
    d = rng.choice(DOMAINES)
    t = rng.choice(["com", "fr", "org"])
    return "%s point %s" % (d.replace("-", " tiret "), t), "%s.%s" % (d, t)


def f_tel(rng):
    """Un couple qui commence par 0 se DIT « zero sept », jamais « sept » :
    sans ca, « 07 92 » se dicterait « sept quatre-vingt-douze », ce qu'aucun
    locuteur ne prononce."""
    n = [0, rng.choice([6, 7])] + [rng.randint(0, 9) for _ in range(8)]
    couples = [(n[i], n[i + 1]) for i in range(0, 10, 2)]
    dit = " ".join(("zero " + mot(b)) if a == 0 else mot(a * 10 + b)
                   for a, b in couples)
    ecrit = " ".join("%d%d" % c for c in couples)
    return dit, ecrit


# ── Gabarits. Chaque %s consomme UN fragment, dans l'ordre donne. ───────────
GABARITS_2 = [
    ("on se voit {J} à %s pour %s", "On se voit {J} à %s pour %s.", (f_heure, f_montant)),
    ("{O} de %s est dû le %s", "{O} de %s est dû le %s.", (f_montant, f_date)),
    ("rendez-vous le %s à %s", "Rendez-vous le %s à %s.", (f_date, f_heure)),
    ("il faut régler %s avant le %s", "Il faut régler %s avant le %s.", (f_montant, f_date)),
    ("appelle-moi au %s avant %s", "Appelle-moi au %s avant %s.", (f_tel, f_heure)),
    ("compte %s de remise sur %s", "Compte %s de remise sur %s.", (f_pourcent, f_montant)),
    ("envoie {O} à %s avant le %s", "Envoie {O} à %s avant le %s.", (f_email, f_date)),
    ("on était %s et ça a coûté %s", "On était %s et ça a coûté %s.", (f_entier, f_montant)),
    ("{P} arrive à %s le %s", "{P} arrive à %s le %s.", (f_heure, f_date)),
    ("le devis passe de %s à %s", "Le devis passe de %s à %s.", (f_montant, f_montant)),
    ("tout est sur %s, réponse avant le %s", "Tout est sur %s, réponse avant le %s.", (f_url, f_date)),
    ("{P} a facturé %s pour %s heures", "{P} a facturé %s pour %s heures.", (f_montant, f_entier)),
]
GABARITS_3 = [
    ("le %s à %s on signe pour %s", "Le %s à %s, on signe pour %s.",
     (f_date, f_heure, f_montant)),
    ("rendez-vous le %s à %s avec %s personnes",
     "Rendez-vous le %s à %s avec %s personnes.", (f_date, f_heure, f_entier)),
    ("%s de remise sur %s, valable jusqu'au %s",
     "%s de remise sur %s, valable jusqu'au %s.", (f_pourcent, f_montant, f_date)),
    ("appelle au %s avant %s pour {O} de %s",
     "Appelle au %s avant %s pour {O} de %s.", (f_tel, f_heure, f_montant)),
    ("envoie à %s le %s le montant de %s",
     "Envoie à %s le %s le montant de %s.", (f_email, f_date, f_montant)),
]


def compose(rng, gabarits):
    d_tpl, c_tpl, frags = rng.choice(gabarits)
    dits, ecrits = [], []
    for f in frags:
        a, b = f(rng)
        dits.append(a)
        ecrits.append(b)
    subs = {"{J}": rng.choice(JOURS), "{O}": rng.choice(OBJETS),
            "{P}": rng.choice(PRENOMS)}
    for k, v in subs.items():
        d_tpl = d_tpl.replace(k, v)
        c_tpl = c_tpl.replace(k, v.lower() if c_tpl.startswith(k) else v)
    d, c = d_tpl % tuple(dits), c_tpl % tuple(ecrits)
    return d[0].lower() + d[1:], c[0].upper() + c[1:]


def gen_compo2(rng):
    return compose(rng, GABARITS_2)


def gen_compo3(rng):
    return compose(rng, GABARITS_3)


FAMILLES = [("compo2", gen_compo2, 65), ("compo3", gen_compo3, 35)]


def main():
    n_total = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(SP, "pairs_compo.jsonl")
    rng = random.Random(SEED)
    noms = [f[0] for f in FAMILLES]
    poids = [f[2] for f in FAMILLES]
    fns = {f[0]: f[1] for f in FAMILLES}

    seen, rows, stats = set(), [], collections.Counter()
    tries = 0
    while len(rows) < n_total and tries < n_total * 60:
        tries += 1
        fam = rng.choices(noms, weights=poids)[0]
        try:
            d, c = fns[fam](rng)
        except Exception:
            continue
        if d in seen:
            continue
        seen.add(d)
        if rng.random() < 0.18:
            h = rng.choice(HESITATIONS)
            if h:
                d = h + d
        stats[fam] += 1
        rows.append({"id": "cmp-%05d" % len(rows), "file": "cmp-%s" % fam,
                     "source": "compo", "lang": "fr", "held_out": False,
                     "styling": "semi-formal", "structure": "prose",
                     "context": "general", "control": CONTROL,
                     "dirty": d, "clean": c})

    par_fam = collections.defaultdict(list)
    for r in rows:
        par_fam[r["file"]].append(r)
    for fam, group in par_fam.items():
        for r in rng.sample(group, max(1, int(len(group) * 0.08))):
            r["held_out"] = True

    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    n = len(rows)
    print("compositions ITN : %d  (%d tentatives, %d doublons ecartes)"
          % (n, tries, tries - n))
    for fam, _, _ in FAMILLES:
        print("  %-10s %6d  %5.1f %%" % (fam, stats[fam], 100.0 * stats[fam] / max(1, n)))
    print("  tenues a l'ecart : %d" % sum(1 for r in rows if r["held_out"]))
    print("-> %s" % out)


if __name__ == "__main__":
    main()
