# -*- coding: utf-8 -*-
"""Generateur synthetique d'ITN francais — nombres, montants, dates, heures.

POURQUOI IL EXISTE. Le corpus reel ne contient que 17 cas d'ITN sur 90 000 mots
(notes d'entrainement §0.8) : le modele en voit assez pour TENTER la conversion, jamais
assez pour la reussir. Mesure du 2026-09-02 : a 4 510 paires, « vingt-trois
mille quatre cent cinquante euros » devient « 20 000 euros ». Un montant faux,
enonce avec aplomb, que personne n'attrape en relisant.

POURQUOI IL EST FIABLE. Les deux cotes sont exacts PAR CONSTRUCTION : on tire
une valeur, `num2words` en donne la forme parlee, et la forme ecrite est celle
qu'on a tiree. Aucun professeur, aucune API, aucune verification necessaire —
la verite terrain n'est pas jugee, elle est connue.

CE QU'IL GENERE, et pourquoi chaque bloc compte :
  - les conversions elles-memes, dans des phrases porteuses realistes ;
  - des CONTRE-EXEMPLES ou le nombre est DEJA en chiffres et ne doit pas bouger ;
  - des phrases SANS aucun nombre, pour que le modele n'apprenne pas a en
    fabriquer la ou il n'y en a pas.

Sans les deux derniers blocs, on remplacerait un biais par un autre.
"""
import json, os, random, re, sys, unicodedata
from num2words import num2words

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd
SEED = 20260902

MOIS = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet",
        "aout", "septembre", "octobre", "novembre", "decembre"]
MOIS_ACC = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
            "août", "septembre", "octobre", "novembre", "décembre"]

# Phrases porteuses : le modele doit apprendre l'ITN EN CONTEXTE, pas sur des
# nombres nus. Le marqueur {} recoit la valeur.
PORTEUSES = [
    "Le devis monte à {}.", "Ça nous fait {} au total.", "Il me reste {} sur le compte.",
    "Je te dois {}.", "Le budget est de {}.", "On a dépensé {} ce mois-ci.",
    "Le virement de {} est parti.", "Compte {} pour la prestation.",
    "Il faut prévoir {} minimum.", "La facture s'élève à {}.",
]
PORTEUSES_NB = [
    "Il y a {} personnes dans la salle.", "On a reçu {} inscriptions.",
    "J'ai {} messages non lus.", "Le fichier fait {} lignes.",
    "Elle a {} abonnés maintenant.", "Ça représente {} heures de travail.",
    "On en est à {} tickets ouverts.", "Le dossier compte {} pages.",
    "Il reste {} places disponibles.", "J'ai fait {} kilomètres aujourd'hui.",
]
PORTEUSES_DATE = [
    "On se voit le {}.", "L'échéance est le {}.", "Le contrat démarre le {}.",
    "Elle est née le {}.", "La réunion est reportée au {}.",
    "Il faut rendre ça pour le {}.", "Le paiement est dû le {}.",
    "On a signé le {}.", "La livraison est prévue le {}.",
]
PORTEUSES_HEURE = [
    "On se retrouve à {}.", "Le train part à {}.", "Rendez-vous à {} devant la gare.",
    "La réunion commence à {}.", "Je serai là vers {}.", "Il m'a appelé à {}.",
    "Le magasin ferme à {}.", "L'appel est calé à {}.",
]
PORTEUSES_PCT = [
    "On est à {} de marge.", "Ça représente {} du total.", "Il manque {} pour finir.",
    "Le taux est passé à {}.", "On a gagné {} sur l'année.",
]
# Aucune de ces phrases ne contient de nombre : elles apprennent au modele a ne
# pas en inventer.
SANS_NOMBRE = [
    "Je voulais te dire que le dossier est prêt.", "On en reparle demain si tu veux.",
    "Il faut que je relise le contrat avant de signer.",
    "Elle m'a dit qu'elle passerait dans l'après-midi.",
    "Le fichier est sur le serveur, tu peux le récupérer.",
    "J'ai relu ta proposition, c'est bien vu.",
    "On va attendre son retour avant de décider.",
    "Le client a validé la maquette hier soir.",
    "Il faudra penser à relancer le fournisseur.",
    "Je te renvoie la version corrigée dès que possible.",
]

HESITATIONS = ["euh ", "alors euh ", "bah ", "donc euh ", ""]


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def espace_milliers(n):
    """Format francais : espace tous les trois chiffres. 23450 -> « 23 450 »."""
    s = str(abs(int(n)))
    out = ""
    while len(s) > 3:
        out = " " + s[-3:] + out
        s = s[:-3]
    return ("-" if n < 0 else "") + s + out


def mot(n):
    return num2words(n, lang="fr")


# ── Un generateur par famille ────────────────────────────────────────────────

def gen_entier(rng):
    # Distribution realiste : les petits nombres dominent la parole courante.
    bucket = rng.choices(["petit", "moyen", "grand", "tres_grand"], weights=[45, 30, 20, 5])[0]
    n = {"petit": lambda: rng.randint(1, 99),
         "moyen": lambda: rng.randint(100, 9999),
         "grand": lambda: rng.randint(10000, 999999),
         "tres_grand": lambda: rng.randint(10 ** 6, 50 * 10 ** 6)}[bucket]()
    porteuse = rng.choice(PORTEUSES_NB)
    return porteuse.format(mot(n)), porteuse.format(espace_milliers(n))


def gen_montant(rng):
    devise = rng.choices(["euros", "dollars", "francs"], weights=[80, 15, 5])[0]
    centimes = rng.random() < 0.20
    n = rng.choice([rng.randint(1, 999), rng.randint(1, 99) * 10,
                    rng.randint(1, 500) * 100, rng.randint(1000, 99999)])
    if centimes:
        c = rng.randint(1, 99)
        parle = "%s %s et %s centimes" % (mot(n), devise, mot(c))
        ecrit = "%s,%02d %s" % (espace_milliers(n), c, devise)
    else:
        parle = "%s %s" % (mot(n), devise)
        ecrit = "%s %s" % (espace_milliers(n), devise)
    porteuse = rng.choice(PORTEUSES)
    return porteuse.format(parle), porteuse.format(ecrit)


def gen_date(rng):
    jour = rng.randint(1, 28)
    m = rng.randrange(12)
    annee = rng.choice([rng.randint(1950, 2010), rng.randint(2020, 2035)])
    jour_parle = "premier" if jour == 1 else mot(jour)
    forme = rng.choices(["complete", "sans_annee", "annee_seule"], weights=[65, 25, 10])[0]
    if forme == "complete":
        parle = "%s %s %s" % (jour_parle, MOIS[m], mot(annee))
        ecrit = "%d %s %d" % (jour, MOIS_ACC[m], annee)
    elif forme == "sans_annee":
        parle = "%s %s" % (jour_parle, MOIS[m])
        ecrit = "%d %s" % (jour, MOIS_ACC[m])
    else:
        parle, ecrit = mot(annee), str(annee)
        return ("C'était en %s." % parle), ("C'était en %s." % ecrit)
    porteuse = rng.choice(PORTEUSES_DATE)
    return porteuse.format(parle), porteuse.format(ecrit)


def gen_heure(rng):
    h = rng.randint(0, 23)
    forme = rng.choices(["pile", "minutes", "demie", "quart", "moins_quart", "midi"],
                        weights=[25, 35, 15, 10, 10, 5])[0]
    if forme == "midi" and h not in (0, 12):
        forme = "pile"
    if forme == "pile":
        parle, ecrit = "%s heures" % mot(h), "%dh" % h
    elif forme == "minutes":
        mn = rng.choice([5, 10, 20, 25, 35, 40, 50, 55, rng.randint(1, 59)])
        parle, ecrit = "%s heures %s" % (mot(h), mot(mn)), "%dh%02d" % (h, mn)
    elif forme == "demie":
        parle, ecrit = "%s heures et demie" % mot(h), "%dh30" % h
    elif forme == "quart":
        parle, ecrit = "%s heures et quart" % mot(h), "%dh15" % h
    elif forme == "moins_quart":
        parle, ecrit = "%s heures moins le quart" % mot(h), "%dh45" % ((h - 1) % 24)
    else:
        parle, ecrit = ("midi", "12h") if h == 12 else ("minuit", "0h")
    if h == 1 and forme in ("pile", "minutes", "demie", "quart"):
        parle = parle.replace("un heures", "une heure")
    porteuse = rng.choice(PORTEUSES_HEURE)
    return porteuse.format(parle), porteuse.format(ecrit)


def gen_pourcent(rng):
    n = rng.choice([rng.randint(1, 99), rng.choice([5, 10, 15, 20, 25, 30, 50, 75])])
    porteuse = rng.choice(PORTEUSES_PCT)
    return porteuse.format("%s pour cent" % mot(n)), porteuse.format("%d %%" % n)


def gen_telephone(rng):
    paires = [rng.randint(0, 99) for _ in range(4)]
    tete = rng.choice(["06", "07", "01", "02"])
    parle = "zéro %s %s" % (mot(int(tete[1])), " ".join(mot(p) for p in paires))
    ecrit = "%s %s" % (tete, " ".join("%02d" % p for p in paires))
    return "Tu peux me joindre au %s." % parle, "Tu peux me joindre au %s." % ecrit


def gen_email(rng):
    prenoms = ["alex", "marie", "thomas", "julie", "paul", "sophie", "lucas", "emma"]
    noms = ["dupont", "durand", "martin", "bernard", "petit", "moreau"]
    doms = [("gmail", "com"), ("outlook", "fr"), ("budgie", "app"), ("free", "fr")]
    p, n = rng.choice(prenoms), rng.choice(noms)
    dom, tld = rng.choice(doms)
    sep_parle, sep_ecrit = rng.choice([("point", "."), ("tiret", "-"), ("", "")])
    local_parle = "%s %s %s" % (p, sep_parle, n) if sep_parle else "%s%s" % (p, n)
    local_ecrit = "%s%s%s" % (p, sep_ecrit, n)
    parle = "%s arobase %s point %s" % (local_parle, dom, tld)
    ecrit = "%s@%s.%s" % (local_ecrit, dom, tld)
    porteuse = rng.choice(["Envoie ça à {}.", "Son adresse c'est {}.",
                           "Tu peux écrire à {}.", "Mets {} en copie."])
    return porteuse.format(parle), porteuse.format(ecrit)


# ── Contre-exemples : ce qui ne doit PAS bouger ──────────────────────────────

def gen_deja_chiffres(rng):
    """Un nombre deja ecrit en chiffres reste tel quel. Sans ce bloc, le modele
    apprendrait a « reformater » ce qui est deja bon — c'est exactement ce que
    faisait le modele a 4 510 paires en transformant « 2500 » en « 2 500 »."""
    n = rng.randint(10, 99999)
    porteuse = rng.choice(PORTEUSES_NB + PORTEUSES)
    s = porteuse.format(str(n))
    return s, s


# Fragments combinables : dix phrases figees etaient toutes dedupliquees et le
# bloc tombait a 0,1 % du corpus. Combinees, elles donnent des milliers de
# phrases distinctes — et ce bloc est celui qui empeche le modele d'inventer
# des chiffres, donc il doit peser son vrai poids.
SN_SUJET = ["Je", "On", "Il", "Elle", "Le client", "Le fournisseur", "Mon associé",
            "La cheffe de projet", "L'équipe", "Le prestataire"]
SN_VERBE = ["a relu", "a validé", "a renvoyé", "veut revoir", "attend", "a signé",
            "a commenté", "doit relancer", "va préparer", "a oublié"]
SN_OBJET = ["le contrat", "la maquette", "le devis", "la proposition", "le dossier",
            "la présentation", "le compte rendu", "la facture", "le brief", "l'annexe"]
SN_QUEUE = ["avant la réunion", "dès que possible", "en fin de semaine", "ce matin",
            "sans me prévenir", "après relecture", "hier soir", "de son côté",
            "une deuxième fois", ""]


def gen_sans_nombre(rng):
    """Aucune conversion possible : la sortie est l'entree, mot pour mot.

    C'est le contre-exemple le plus important du jeu. Sans lui, un modele
    entraine uniquement sur des conversions apprend que « produire un chiffre »
    est toujours la bonne reponse, et en fabrique sur du texte qui n'en contient
    aucun — exactement le mode d'echec qu'on cherche a eliminer.
    """
    s = "%s %s %s%s." % (rng.choice(SN_SUJET), rng.choice(SN_VERBE),
                         rng.choice(SN_OBJET),
                         (" " + rng.choice(SN_QUEUE)).rstrip())
    return s, s


FAMILLES = [
    ("entier", gen_entier, 18),
    ("montant", gen_montant, 20),
    ("date", gen_date, 16),
    ("heure", gen_heure, 16),
    ("pourcent", gen_pourcent, 6),
    ("telephone", gen_telephone, 4),
    ("email", gen_email, 6),
    ("deja_chiffres", gen_deja_chiffres, 8),      # contre-exemple
    ("sans_nombre", gen_sans_nombre, 6),          # contre-exemple
]

CONTROL = "[Styling: semi-formal] [Structure: prose] [Context: general] [Lang: fr]"


def main():
    n_total = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(SP, "pairs_itn.jsonl")
    rng = random.Random(SEED)
    noms = [f[0] for f in FAMILLES]
    poids = [f[2] for f in FAMILLES]
    fns = {f[0]: f[1] for f in FAMILLES}

    import collections
    seen, rows, stats = set(), [], collections.Counter()
    tries = 0
    while len(rows) < n_total and tries < n_total * 40:
        tries += 1
        fam = rng.choices(noms, weights=poids)[0]
        try:
            dirty, clean = fns[fam](rng)
        except Exception:
            continue
        if dirty in seen:
            continue
        seen.add(dirty)
        # Le cote sale ressemble a de l'ASR : une hesitation de temps en temps,
        # qui doit disparaitre dans la sortie comme partout ailleurs.
        if rng.random() < 0.18:
            h = rng.choice(HESITATIONS)
            if h:
                dirty = h + dirty[0].lower() + dirty[1:]
        stats[fam] += 1
        rows.append({"id": "itn-%05d" % len(rows), "file": "itn-%s" % fam,
                     "source": "itn", "lang": "fr", "held_out": False,
                     "styling": "semi-formal", "structure": "prose", "context": "general",
                     "control": CONTROL, "dirty": dirty, "clean": clean})

    # 8 % tenus a l'ecart, par FAMILLE, pour pouvoir mesurer chaque bloc a part.
    par_fam = collections.defaultdict(list)
    for r in rows:
        par_fam[r["file"]].append(r)
    for fam, group in par_fam.items():
        for r in rng.sample(group, max(1, int(len(group) * 0.08))):
            r["held_out"] = True

    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print("paires ITN : %d  (%d tentatives, %d doublons ecartes)"
          % (len(rows), tries, tries - len(rows)))
    print("%-16s %6s %6s" % ("famille", "n", "%"))
    for fam, _, _ in FAMILLES:
        print("%-16s %6d %5.1f%%" % (fam, stats[fam], 100.0 * stats[fam] / max(1, len(rows))))
    print("tenues a l'ecart : %d" % sum(1 for r in rows if r["held_out"]))
    print("-> %s" % out)
    print()
    print("=== echantillon ===")
    for r in rng.sample(rows, 8):
        print("  [%-13s] %s" % (r["file"][4:], r["dirty"]))
        print("  %-16s %s" % ("", r["clean"]))


if __name__ == "__main__":
    main()
