# -*- coding: utf-8 -*-
"""Composition CORRECTION x ITN — trancher ET normaliser dans la MEME phrase.

LE TROU QUE CE FICHIER BOUCHE
Le modele sait trancher une auto-correction (476/476 sur les cas tenus a
l'ecart de gen_correction.py). Il sait convertir une heure (796/797 sur ceux de
gen_itn.py). Il echoue des que les deux tombent dans la MEME phrase :

    SALE    alors euh vendredi non pardon jeudi on a rendez-vous a quatorze
            heures trente pour deux cent cinquante euros
    ATTENDU Jeudi, on a rendez-vous a 14h30 pour 250 euros.
    OBTENU  Vendredi, pardon jeudi, on a rendez-vous a 14h30 pour 250 euros.

L'ITN passe, la correction ne passe plus : le modele ponctue l'hesitation au
lieu de la resoudre, exactement comme avant gen_correction.py. La cause est
mecanique, pas cognitive — gen_compo.py compose ITN x ITN, gen_correction.py ne
compose rien, et AUCUNE paire du corpus ne montre une auto-correction et une
expression numerique cote a cote. Quatrieme occurrence du meme principe dans ce
projet : ce qu'on ne montre jamais, le modele ne le produit jamais.

Chaque paire produite ici porte donc AU MOINS une auto-correction ET au moins
une expression numerique, dans la meme phrase.

POURQUOI LES CONTRE-EXEMPLES PESENT 25 %
La lecon est verifiee trois fois dans ce projet (ITN, correction, forme) : un
jeu qui ne montre que des suppressions apprend a supprimer. Ici le risque est
precis — « une valeur, un marqueur, une autre valeur » deviendrait le patron de
declenchement, et « jeudi et vendredi a 14h30 » perdrait un jour. Deux familles
l'interdisent :
    non_non_correctif  « non »/« enfin »/« plutot » qui ne corrigent RIEN,
                       avec une expression numerique dans la phrase
    deux_valeurs       deux valeurs numeriques ou nominales coordonnees,
                       toutes deux legitimes, toutes deux gardees

UN DETAIL QUI N'EN EST PAS UN : LES HEURES DES CONTRE-EXEMPLES
Une heure DICTEE fait disparaitre le mot « heures » du cote propre
(« quatorze heures trente » -> « 14h30 »). C'est une perte legitime, mais dans
une famille contre-exemple elle est indistinguable d'une suppression abusive :
valider_paires.py exige justement qu'un contre-exemple ne perde AUCUN mot de
contenu. Les contre-exemples portent donc l'heure DEJA chiffree — la forme que
l'ASR ecrit reellement, et celle de la famille `deja_chiffres` de gen_itn.py.
Ce que le contre-exemple teste est la coordination, pas l'ITN ; les familles
« trancher », elles, dictent leurs heures en toutes lettres.

Usage : gen_cor_itn.py [n] [sortie.jsonl]
"""
import collections, json, os, random, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd

# REUTILISER AVANT DE CREER. Les fragments ITN (dicte, ecrit) viennent de
# gen_compo.py, le lexique et les marqueurs de correction de gen_correction.py.
# Recopier ces listes les ferait diverger au premier ajout de vocabulaire, et
# le modele verrait deux lexiques la ou il doit en voir un. Aucun des deux
# fichiers n'est modifie.
from gen_compo import (f_heure, f_montant, f_date, f_pourcent, f_entier,
                       f_tel, f_email, mot, esp)
from gen_correction import (JOURS, PRENOMS, VILLES, LIEUX, OBJETS, GENRE,
                            VERBES_ACTION, M_PARDON, M_ENFIN, M_PLUTOT,
                            M_VEUX_DIRE, M_NON_SEC, maj, _remplace)

SEED = 20260905
CONTROL = "[Styling: semi-formal] [Structure: prose] [Context: general] [Lang: fr]"
HESITATIONS = ["euh ", "bah ", "ben ", "alors euh ", "hum ", "", "", ""]

# Les cinq familles de marqueurs sont melangees : « non pardon », « enfin »,
# « ou plutot », « je veux dire », « non », « excuse-moi » doivent tous
# declencher la meme decision, sinon le modele n'en apprend qu'un.
MARQUEURS = M_PARDON + M_ENFIN + M_PLUTOT + M_VEUX_DIRE + M_NON_SEC

# Plus large que la liste de gen_compo.py : c'est la COMBINATOIRE, pas le
# poids, qui fixe le plafond d'une famille — la deduplication rejette les
# familles saturees.
MONTANTS = [80, 100, 120, 150, 180, 200, 250, 300, 350, 400, 450, 500, 600,
            750, 800, 900, 1000, 1200, 1500, 1800, 2000, 2500, 3000, 3500,
            4500, 6000, 8000, 12000]
POURCENTS = [5, 10, 15, 20, 25, 30, 35, 40, 50, 60, 70, 75]


# ── Fragments propres a ce jeu ──────────────────────────────────────────────
# Montants utilisables dans un CONTRE-EXEMPLE. « quatre-vingts euros » ->
# « 80 euros » fait disparaitre le mot « vingts », que valider_paires.py compte
# comme une perte de contenu : sa liste de nombres connait « quatre-vingts »
# entier, pas le morceau que la coupure sur le trait d'union laisse. La perte
# est legitime, mais dans une famille contre-exemple elle est indistinguable
# d'une suppression abusive. Les familles « trancher », elles, gardent la liste
# complete — le modele continue d'y voir « quatre-vingts » -> « 80 ».
MONTANTS_CE = [n for n in MONTANTS if "vingts" not in mot(n)]


def f_euros(rng):
    """Montant en euros seulement, sans perte de mot une fois chiffre.

    f_montant tire la devise a chaque appel : deux montants coordonnes dans
    une meme phrase sortaient « de 250 euros a 350 dollars ». Un fragment tire
    une seule fois n'y suffit pas quand la phrase en demande deux."""
    n = rng.choice(MONTANTS_CE)
    return "%s euros" % mot(n), "%s euros" % esp(n)


def f_heure_ecrite(rng):
    """Heure deja normalisee des la dictee — voir l'entete du fichier."""
    h = rng.randint(7, 20)
    mn = rng.choice([0, 0, 15, 30, 45])
    s = "%dh" % h if not mn else "%dh%02d" % (h, mn)
    return s, s


def f_plage_ecrite(rng):
    """« de 9h a 18h » — deja chiffree, meme raison."""
    s = "%dh a %dh" % (rng.randint(7, 12), rng.randint(14, 20))
    s = s.replace(" a ", " à ")
    return s, s


def f_creneau(rng):
    """« de neuf heures a quatorze heures trente » -> « de 9h a 14h30 ».

    Un SEUL fragment pour les deux bornes : deux appels a f_heure produisaient
    « de 18h a 9h », un creneau qui n'existe pas. Le contenu doit rester vrai,
    pas seulement bien forme."""
    h1, h2 = rng.randint(7, 12), rng.randint(14, 20)
    m1, m2 = rng.choice([0, 0, 30]), rng.choice([0, 0, 30])
    dit = "%s heures%s à %s heures%s" % (mot(h1), " trente" if m1 else "",
                                         mot(h2), " trente" if m2 else "")
    ecrit = "%dh%s à %dh%s" % (h1, "30" if m1 else "", h2, "30" if m2 else "")
    return dit, ecrit


# ── Paires corrigees : la valeur abandonnee et la valeur retenue ────────────
# Chaque paire est tiree UNE fois ; le cote sale prend les deux formes dictees,
# le cote propre la seule forme ecrite de la valeur retenue. Tirer deux fois
# faisait changer le verbe entre l'entree et la sortie dans gen_correction.py —
# des paires qui enseignaient litteralement l'invention.
def _paire_montant(rng):
    a = rng.choice(MONTANTS)
    b = _remplace(rng, MONTANTS, a)
    dev = rng.choices(["euros", "dollars"], weights=[9, 1])[0]
    forme = lambda n: ("%s %s" % (mot(n), dev), "%s %s" % (esp(n), dev))
    return forme(a), forme(b)


def _paire_entier(rng):
    vals = list(range(2, 61))
    a = rng.choice(vals)
    b = _remplace(rng, vals, a)
    return (mot(a), str(a)), (mot(b), str(b))


def _paire_pourcent(rng):
    a = rng.choice(POURCENTS)
    b = _remplace(rng, POURCENTS, a)
    forme = lambda n: ("%s pour cent" % mot(n), "%d %%" % n)
    return forme(a), forme(b)


def _paire_heure(rng):
    a = f_heure(rng)
    b = f_heure(rng)
    for _ in range(25):
        if b[1] != a[1]:
            break
        b = f_heure(rng)
    return a, b


CORRECTEURS = {"montant": _paire_montant, "entier": _paire_entier,
               "pourcent": _paire_pourcent, "heure": _paire_heure}


# ── Rendu ───────────────────────────────────────────────────────────────────
def _rendu(rng, d_tpl, c_tpl, frags, extra_d, extra_c=None):
    """Remplit {f1}, {f2}... avec des fragments tires UNE fois.

    `extra_d` / `extra_c` portent les fentes non numeriques (jour, prenom,
    marqueur...). Elles sont identiques sauf pour les familles ou la valeur
    corrigee est elle-meme une expression numerique : la, le cote sale porte
    la forme dictee et le cote propre la forme ecrite."""
    sd = dict(extra_d)
    sc = dict(extra_c if extra_c is not None else extra_d)
    vus = set()
    for i, f in enumerate(frags, 1):
        dit, ecrit = f(rng)
        for _ in range(25):
            if ecrit not in vus:
                break
            dit, ecrit = f(rng)
        vus.add(ecrit)
        sd["f%d" % i] = dit
        sc["f%d" % i] = ecrit
    return d_tpl.format(**sd), c_tpl.format(**sc)


def _fentes(rng):
    """Fentes communes a tous les gabarits — fournies meme si inutilisees.

    `il` reprend l'objet tire, et il ACCORDE. gen_correction.py tient la table
    GENRE pour une raison qui vaut ici mot pour mot : « le GENRE voyage avec le
    nom ». Sans cette fente, le seul gabarit qui reprend l'objet par un pronom
    ecrivait « je te dépose la maquette [...], IL est à 300 euros » — du
    francais fautif, des DEUX cotes de la paire, donc appris comme la bonne
    reponse. 16 paires sur 3 000 ; le prix d'un mot mal accorde n'est pas dans
    son compte, il est dans le fait qu'on l'enseigne."""
    o = rng.choice(OBJETS)
    return {"m": rng.choice(MARQUEURS), "o": o, "p": rng.choice(PRENOMS),
            "v": "%s %s" % (rng.choice(VERBES_ACTION), o),
            "j": rng.choice(JOURS),
            "il": "elle" if GENRE.get(o) == "f" else "il"}


# ═══ TRANCHER : une correction ET une expression numerique ═════════════════

# --- 1. correction sur un JOUR + une heure ---------------------------------
T_JOUR_HEURE = [
    ("{a} {m} {b} on a rendez-vous à {f1}",
     "{B}, on a rendez-vous à {f1}.", (f_heure,)),
    ("{a} {m} {b} on a rendez-vous à {f1} pour {f2}",
     "{B}, on a rendez-vous à {f1} pour {f2}.", (f_heure, f_montant)),
    ("on se voit {a} {m} {b} à {f1}",
     "On se voit {b} à {f1}.", (f_heure,)),
    ("la réunion est {a} {m} {b} à {f1}",
     "La réunion est {b} à {f1}.", (f_heure,)),
    ("je passe {a} {m} {b} vers {f1} pour {f2}",
     "Je passe {b} vers {f1} pour {f2}.", (f_heure, f_montant)),
    ("on démarre {a} {m} {b} à {f1} avec {f2} personnes",
     "On démarre {b} à {f1} avec {f2} personnes.", (f_heure, f_entier)),
    ("le point sur {o} est calé {a} {m} {b} à {f1}",
     "Le point sur {o} est calé {b} à {f1}.", (f_heure,)),
    ("{p} arrive {a} {m} {b} à {f1} et repart le {f2}",
     "{p} arrive {b} à {f1} et repart le {f2}.", (f_heure, f_date)),
    ("on livre {o} {a} {m} {b} à {f1} pour {f2}",
     "On livre {o} {b} à {f1} pour {f2}.", (f_heure, f_montant)),
    ("est-ce qu'on peut se voir {a} {m} {b} à {f1}",
     "Est-ce qu'on peut se voir {b} à {f1} ?", (f_heure,)),
    ("appelle-moi {a} {m} {b} avant {f1} au {f2}",
     "Appelle-moi {b} avant {f1} au {f2}.", (f_heure, f_tel)),
    ("il faut boucler {o} {a} {m} {b} avant {f1}",
     "Il faut boucler {o} {b} avant {f1}.", (f_heure,)),
    ("le créneau est {a} {m} {b} de {f1}",
     "Le créneau est {b} de {f1}.", (f_creneau,)),
]


def gen_jour_heure(rng):
    d, c, frags = rng.choice(T_JOUR_HEURE)
    a = rng.choice(JOURS)
    b = _remplace(rng, JOURS, a)
    ex = _fentes(rng)
    ex.update({"a": a, "b": b, "B": maj(b)})
    return _rendu(rng, d, c, frags, ex)


# --- 2. correction sur un LIEU + un montant --------------------------------
# `pool` garde les gabarits grammaticaux : « on ouvre l'agence en visio » est
# du francais fautif, et six cents paires de francais fautif s'apprennent.
T_LIEU_MONTANT = [
    ("both", "on signe {a} {m} {b} pour {f1}",
     "On signe {b} pour {f1}.", (f_montant,)),
    ("both", "la formation se fait {a} {m} {b} pour {f1}",
     "La formation se fait {b} pour {f1}.", (f_montant,)),
    ("both", "l'intervention est {a} {m} {b} et ça coûte {f1}",
     "L'intervention est {b} et ça coûte {f1}.", (f_montant,)),
    ("both", "le stand sera {a} {m} {b} et ça nous coûte {f1} par jour",
     "Le stand sera {b} et ça nous coûte {f1} par jour.", (f_montant,)),
    ("both", "il faut livrer {o} {a} {m} {b} pour {f1}",
     "Il faut livrer {o} {b} pour {f1}.", (f_montant,)),
    ("both", "on se retrouve {a} {m} {b} à {f1} pour {f2}",
     "On se retrouve {b} à {f1} pour {f2}.", (f_heure, f_montant)),
    ("both", "le rendez-vous est {a} {m} {b} à {f1} pour {f2}",
     "Le rendez-vous est {b} à {f1} pour {f2}.", (f_heure, f_montant)),
    ("both", "{p} nous attend {a} {m} {b} avec un devis de {f1}",
     "{p} nous attend {b} avec un devis de {f1}.", (f_montant,)),
    ("ville", "on ouvre l'agence {a} {m} {b} avec un budget de {f1}",
     "On ouvre l'agence {b} avec un budget de {f1}.", (f_montant,)),
    ("ville", "j'ai réservé une salle {a} {m} {b} pour {f1}",
     "J'ai réservé une salle {b} pour {f1}.", (f_montant,)),
    ("ville", "on déménage {a} {m} {b} le {f1} pour {f2}",
     "On déménage {b} le {f1} pour {f2}.", (f_date, f_montant)),
    ("ville", "le chantier est {a} {m} {b} et il est chiffré à {f1}",
     "Le chantier est {b} et il est chiffré à {f1}.", (f_montant,)),
    ("lieu", "on fait le point {a} {m} {b} sur {o} de {f1}",
     "On fait le point {b} sur {o} de {f1}.", (f_montant,)),
    ("lieu", "je te dépose {o} {a} {m} {b}, {il} est à {f1}",
     "Je te dépose {o} {b}, {il} est à {f1}.", (f_montant,)),
]


def gen_lieu_montant(rng):
    pool, d, c, frags = rng.choice(T_LIEU_MONTANT)
    if pool == "ville" or (pool == "both" and rng.random() < 0.5):
        va = rng.choice(VILLES)
        vb = _remplace(rng, VILLES, va)
        a, b = "à %s" % va, "à %s" % vb
    else:
        a = rng.choice(LIEUX)
        b = _remplace(rng, LIEUX, a)
    ex = _fentes(rng)
    ex.update({"a": a, "b": b})
    return _rendu(rng, d, c, frags, ex)


# --- 3. correction sur un PRENOM + une date --------------------------------
T_PRENOM_DATE = [
    ("c'est {a} {m} {b} qui envoie {o} avant le {f1}",
     "C'est {b} qui envoie {o} avant le {f1}.", (f_date,)),
    ("{a} {m} {b} revient le {f1}",
     "{B} revient le {f1}.", (f_date,)),
    ("il faut prévenir {a} {m} {b} avant le {f1}",
     "Il faut prévenir {b} avant le {f1}.", (f_date,)),
    ("{a} {m} {b} signe le contrat le {f1} pour {f2}",
     "{B} signe le contrat le {f1} pour {f2}.", (f_date, f_montant)),
    ("j'ai vu {a} {m} {b} le {f1}",
     "J'ai vu {b} le {f1}.", (f_date,)),
    ("{o} de {a} {m} {b} part le {f1}",
     "{O} de {b} part le {f1}.", (f_date,)),
    ("demande à {a} {m} à {b} de rappeler avant le {f1} au {f2}",
     "Demande à {b} de rappeler avant le {f1} au {f2}.", (f_date, f_tel)),
    ("écris à {a} {m} à {b} le {f1} sur {f2}",
     "Écris à {b} le {f1} sur {f2}.", (f_date, f_email)),
    ("{a} {m} {b} facture {f1} le {f2}",
     "{B} facture {f1} le {f2}.", (f_montant, f_date)),
    ("on attend {a} {m} {b} le {f1} à {f2}",
     "On attend {b} le {f1} à {f2}.", (f_date, f_heure)),
    ("le dossier passe à {a} {m} {b} le {f1}",
     "Le dossier passe à {b} le {f1}.", (f_date,)),
    ("est-ce que {a} {m} {b} est dispo le {f1} ?",
     "Est-ce que {b} est dispo le {f1} ?", (f_date,)),
]


def gen_prenom_date(rng):
    d, c, frags = rng.choice(T_PRENOM_DATE)
    a = rng.choice(PRENOMS)
    b = _remplace(rng, PRENOMS, a)
    ex = _fentes(rng)
    ex.update({"a": a, "b": b, "B": maj(b), "O": maj(ex["o"])})
    return _rendu(rng, d, c, frags, ex)


# --- 4. correction sur un NOMBRE + une autre expression numerique ----------
# La famille la plus proche du defaut mesure : les DEUX competences tirent en
# meme temps sur la meme phrase, et sur des chiffres des deux cotes.
T_NOMBRE_X = [
    ("montant", "le devis est à {a} {m} {b} avant le {f1}",
     "Le devis est à {b} avant le {f1}.", (f_date,)),
    ("montant", "l'acompte est de {a} {m} {b} à verser le {f1}",
     "L'acompte est de {b} à verser le {f1}.", (f_date,)),
    ("montant", "le budget passe à {a} {m} {b} avant {f1}",
     "Le budget passe à {b} avant {f1}.", (f_heure,)),
    ("montant", "ça fait {a} {m} {b} en tout pour {f1} jours",
     "Ça fait {b} en tout pour {f1} jours.", (f_entier,)),
    ("montant", "on part sur {a} {m} {b} par personne pour {f1} personnes",
     "On part sur {b} par personne pour {f1} personnes.", (f_entier,)),
    ("montant", "la facture est à {a} {m} {b} et elle part le {f1}",
     "La facture est à {b} et elle part le {f1}.", (f_date,)),
    ("montant", "il faut régler {a} {m} {b} avant le {f1}",
     "Il faut régler {b} avant le {f1}.", (f_date,)),
    ("entier", "il en faut {a} {m} {b} pour {f1}",
     "Il en faut {b} pour {f1}.", (f_montant,)),
    ("entier", "on sera {a} {m} {b} à la réunion de {f1}",
     "On sera {b} à la réunion de {f1}.", (f_heure,)),
    ("entier", "j'ai commandé {a} {m} {b} unités pour {f1}",
     "J'ai commandé {b} unités pour {f1}.", (f_montant,)),
    ("entier", "il reste {a} {m} {b} places pour le {f1}",
     "Il reste {b} places pour le {f1}.", (f_date,)),
    ("pourcent", "on est à {a} {m} {b} de remise sur {f1}",
     "On est à {b} de remise sur {f1}.", (f_montant,)),
    ("pourcent", "il reste {a} {m} {b} de marge sur {f1}",
     "Il reste {b} de marge sur {f1}.", (f_montant,)),
    ("heure", "le rendez-vous est à {a} {m} {b} le {f1}",
     "Le rendez-vous est à {b} le {f1}.", (f_date,)),
    ("heure", "on se cale à {a} {m} {b} pour {f1}",
     "On se cale à {b} pour {f1}.", (f_montant,)),
    ("heure", "{p} passe à {a} {m} {b} avec {f1} dossiers",
     "{p} passe à {b} avec {f1} dossiers.", (f_entier,)),
]


def gen_nombre_x(rng):
    corr, d, c, frags = rng.choice(T_NOMBRE_X)
    (a_dit, _), (b_dit, b_ecrit) = CORRECTEURS[corr](rng)
    ex = _fentes(rng)
    ed = dict(ex); ed.update({"a": a_dit, "b": b_dit})
    ec = dict(ex); ec.update({"a": a_dit, "b": b_ecrit})
    return _rendu(rng, d, c, frags, ed, ec)


# --- 5. faux depart + expression numerique ---------------------------------
# Aucun marqueur : c'est la reprise seule qui signale l'abandon. Le modele doit
# couper l'amorce et normaliser le nombre dans le meme mouvement.
T_FAUX = [
    ("je vais je vais pas {v} avant {f1}",
     "Je ne vais pas {v} avant {f1}.", (f_heure,)),
    ("on peut on doit livrer {o} avant le {f1}",
     "On doit livrer {o} avant le {f1}.", (f_date,)),
    ("il faut il faudrait {v} pour {f1}",
     "Il faudrait {v} pour {f1}.", (f_montant,)),
    ("je te je t'envoie {o} avant {f1}",
     "Je t'envoie {o} avant {f1}.", (f_heure,)),
    ("faut que je faut qu'on {v} avant le {f1}",
     "Il faut qu'on {v} avant le {f1}.", (f_date,)),
    ("j'ai commencé à j'ai fini de {v} le {f1}",
     "J'ai fini de {v} le {f1}.", (f_date,)),
    ("on avait on s'était dit {f1} pour {o}",
     "On s'était dit {f1} pour {o}.", (f_montant,)),
    ("le budget c'est le budget est de {f1} pour {f2} personnes",
     "Le budget est de {f1} pour {f2} personnes.", (f_montant, f_entier)),
    ("on se voit on se retrouve à {f1} le {f2}",
     "On se retrouve à {f1} le {f2}.", (f_heure, f_date)),
    ("je pense que je crois qu'on aura {f1} de remise sur {f2}",
     "Je crois qu'on aura {f1} de remise sur {f2}.", (f_pourcent, f_montant)),
    ("appelle appelle-moi au {f1} avant {f2}",
     "Appelle-moi au {f1} avant {f2}.", (f_tel, f_heure)),
    ("il me faut il nous faut {f1} avant le {f2}",
     "Il nous faut {f1} avant le {f2}.", (f_montant, f_date)),
    ("{p} arrive {p} passe plutôt à {f1} le {f2}",
     "{p} passe plutôt à {f1} le {f2}.", (f_heure, f_date)),
    ("on a on avait chiffré {o} à {f1} le {f2}",
     "On avait chiffré {o} à {f1} le {f2}.", (f_montant, f_date)),
    ("je dois je devais {v} avant {f1}",
     "Je devais {v} avant {f1}.", (f_heure,)),
]


def gen_faux_depart(rng):
    d, c, frags = rng.choice(T_FAUX)
    return _rendu(rng, d, c, frags, _fentes(rng))


# ═══ CONTRE-EXEMPLES : le modele ne doit RIEN supprimer ════════════════════

# --- 6. « non »/« enfin »/« plutot » NON correctifs + un nombre ------------
# (dit, ecrit, virgule). « non mais » ne prend pas de virgule : « Non mais, »
# n'existe pas.
PREFIXES = [("non", "Non", True), ("non non", "Non non", True),
            ("non mais", "Non mais", False), ("ah non", "Ah non", True),
            ("enfin bref", "Enfin bref", True),
            ("enfin voilà", "Enfin voilà", True),
            ("enfin bon", "Enfin bon", True)]
SUFFIXES = ["enfin bref", "enfin voilà", "enfin bon"]

# Un seul gabarit par entree : les deux cotes sont le MEME texte, seuls les
# fragments changent de forme. C'est ce qui garantit qu'un contre-exemple ne
# perd rien — l'invariant est structurel, pas declaratif.
CORPS_NON = [
    ("c'est vrai qu'il faut {f1} avant {j}", (f_euros,)),
    ("on n'a pas encore reçu {o} de {f1}", (f_euros,)),
    ("je ne crois pas qu'on puisse finir avant le {f1}", (f_date,)),
    ("il reste {f1} de marge sur {f2}", (f_pourcent, f_euros)),
    ("on est {f1} dans l'équipe et ça suffit", (f_entier,)),
    ("le rendez-vous de {f1} tient toujours", (f_heure_ecrite,)),
    ("ça fait {f1} jours que j'attends {o}", (f_entier,)),
    ("il faut compter {f1} de plus", (f_euros,)),
    ("je préfère qu'on reparle du budget de {f1} {j}", (f_euros,)),
    ("on a {f1} dossiers à traiter avant le {f2}", (f_entier, f_date)),
    ("{p} passe {j} à {f1} avec {o}", (f_heure_ecrite,)),
    ("la remise de {f1} court jusqu'au {f2}", (f_pourcent, f_date)),
    ("c'est plutôt {f1} qu'il faut prévoir pour {o}", (f_euros,)),
    ("on est plutôt à {f1} de marge sur {o}", (f_pourcent,)),
    ("{o} de {f1} part {j} et c'est très bien", (f_euros,)),
    ("j'ai relu {o} et il manque {f1} au total", (f_euros,)),
    ("{p} facture {f1} et tout le monde est d'accord", (f_euros,)),
    ("on garde {f1} de côté pour {j}", (f_euros,)),
]


def gen_non_non_correctif(rng):
    tpl, frags = rng.choice(CORPS_NON)
    ex = _fentes(rng)
    corps_d, corps_c = _rendu(rng, tpl, tpl, frags, ex)
    if rng.random() < 0.28:
        s = rng.choice(SUFFIXES)
        return "%s %s" % (corps_d, s), "%s, %s." % (maj(corps_c), s)
    dit, ecrit, virgule = rng.choice(PREFIXES)
    return "%s %s" % (dit, corps_d), "%s%s %s." % (ecrit, "," if virgule else "",
                                                   corps_c)


# --- 7. deux valeurs coordonnees, toutes deux gardees ----------------------
T_DEUX = [
    ("jours", "on a rendez-vous {a} et {b} à {f1}", (f_heure_ecrite,)),
    ("jours", "je suis dispo {a} et {b} pour {f1}", (f_euros,)),
    ("jours", "on est là de {f1} {a} et {b}", (f_plage_ecrite,)),
    ("jours", "on livre {a} et {b} pour {f1} au total", (f_euros,)),
    ("jours", "le point de {f1} tient {a} et {b}", (f_heure_ecrite,)),
    ("prenoms", "{a} et {b} s'occupent du dossier de {f1}", (f_euros,)),
    ("prenoms", "{a} et {b} arrivent à {f1} le {f2}", (f_heure_ecrite, f_date)),
    ("prenoms", "{a} et {b} ont chacun {f1} dossiers", (f_entier,)),
    ("villes", "on a des bureaux à {a} et à {b} pour {f1} par mois", (f_euros,)),
    ("villes", "il en faut {f1} pour {a} et {f2} pour {b}", (f_entier, f_entier)),
    ("villes", "le stand est à {a} et à {b} le {f1}", (f_date,)),
    ("objets", "il me faut {a} et {b} avant le {f1}", (f_date,)),
    ("objets", "{a} et {b} sont à {f1} au total", (f_euros,)),
    ("aucun", "le devis passe de {f1} à {f2}", (f_euros, f_euros)),
    ("aucun", "il faut {f1} dossiers le {f2} et {f3} le {f4}",
     (f_entier, f_date, f_entier, f_date)),
    ("aucun", "compte {f1} de remise et {f2} de frais", (f_pourcent, f_euros)),
    ("aucun", "on facture {f1} en mars et {f2} en avril", (f_euros, f_euros)),
    ("aucun", "le rendez-vous est le {f1} et le {f2}", (f_date, f_date)),
    ("aucun", "on demande {f1} d'acompte et {f2} à la livraison",
     (f_euros, f_euros)),
]


def gen_deux_valeurs(rng):
    pool, tpl, frags = rng.choice(T_DEUX)
    src = {"jours": JOURS, "prenoms": PRENOMS, "villes": VILLES,
           "objets": OBJETS}.get(pool)
    ex = _fentes(rng)
    if src:
        a = rng.choice(src)
        ex.update({"a": a, "b": _remplace(rng, src, a)})
    d, c = _rendu(rng, tpl, tpl, frags, ex)
    return d, maj(c) + "."


FAMILLES = [
    # trancher — 75 %
    ("jour_heure", gen_jour_heure, 17),
    ("lieu_montant", gen_lieu_montant, 15),
    ("prenom_date", gen_prenom_date, 14),
    ("nombre_x", gen_nombre_x, 16),
    ("faux_depart", gen_faux_depart, 13),
    # ne rien supprimer — 25 %, et c'est delibere
    ("non_non_correctif", gen_non_non_correctif, 14),
    ("deux_valeurs", gen_deux_valeurs, 11),
]
CONTRE = {"non_non_correctif", "deux_valeurs"}
PLANCHER = 200


def main():
    n_total = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(SP, "pairs_cor_itn.jsonl")
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
            dirty, clean = fns[fam](rng)
        except Exception:
            continue
        if dirty in seen:
            continue
        seen.add(dirty)
        # Le cote sale doit ressembler a de l'ASR. Les hesitations disparaissent
        # partout, contre-exemples compris : c'est la premiere regle de la spec.
        if rng.random() < 0.22:
            h = rng.choice(HESITATIONS)
            if h:
                dirty = h + dirty
        stats[fam] += 1
        rows.append({"id": "cri-%05d" % len(rows), "file": "cri-%s" % fam,
                     "source": "coritn", "lang": "fr", "held_out": False,
                     "styling": "semi-formal", "structure": "prose",
                     "context": "general", "control": CONTROL,
                     "dirty": dirty, "clean": clean})

    # 8 % tenus a l'ecart PAR FAMILLE. Ce jeu n'a que sept valeurs de `file` :
    # un decoupage par fichier emporterait des familles entieres.
    par_fam = collections.defaultdict(list)
    for r in rows:
        par_fam[r["file"].split("-", 1)[-1]].append(r)
    for fam, group in par_fam.items():
        for r in rng.sample(group, max(1, int(len(group) * 0.08))):
            r["held_out"] = True

    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    n = len(rows)
    tranche = sum(stats[f] for f in noms if f not in CONTRE)
    print("composition correction x ITN : %d paires  (%d tentatives, %d doublons ecartes)"
          % (n, tries, tries - n))
    print("%-20s %6s %6s %8s" % ("famille", "n", "%", "ecart"))
    sous = []
    for fam, _, _ in FAMILLES:
        marque = "   <- contre-exemple" if fam in CONTRE else ""
        ho = sum(1 for r in par_fam[fam] if r["held_out"])
        print("%-20s %6d %5.1f%% %8d%s"
              % (fam, stats[fam], 100.0 * stats[fam] / max(1, n), ho, marque))
        if stats[fam] < PLANCHER:
            sous.append(fam)
    print("\ntrancher : %d (%.0f %%) | ne rien supprimer : %d (%.0f %%)"
          % (tranche, 100.0 * tranche / max(1, n),
             n - tranche, 100.0 * (n - tranche) / max(1, n)))
    print("tenues a l'ecart : %d (%.1f %%)"
          % (sum(1 for r in rows if r["held_out"]),
             100.0 * sum(1 for r in rows if r["held_out"]) / max(1, n)))
    print("-> %s" % out)
    if sous:
        print("\nATTENTION : famille(s) sous le plancher de %d — elargir les "
              "gabarits ou le vocabulaire : %s" % (PLANCHER, ", ".join(sous)))
        return 1
    print("familles contre-exemple pour valider_paires.py : %s"
          % " ".join(sorted(CONTRE)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
