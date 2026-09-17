# -*- coding: utf-8 -*-
"""Auto-corrections du locuteur, VERSION ANGLAISE — jumeau de gen_correction.py.

LE PROBLEME (identique en anglais, mesure sur un normaliseur de reference)
La spec du format donne l'exemple de reference :

    SALE    ... friday no wait thursday we have a meeting ...
    ATTENDU ... Thursday, we have a meeting ...
    OBTENU  ... Friday, no wait, Thursday, we have a meeting ...  (invente)

Meme defaut qu'en francais : le modele ponctue l'hesitation au lieu de la
resoudre. Meme remede : un generateur synthetique deterministe, parce que le
corpus reel ne porte quasiment aucune auto-correction (§0.8 des notes d'entrainement,
mesure faite sur le francais, mais la rarete du phenomene dans la parole
spontanee ne depend pas de la langue).

LE PIEGE, ET POURQUOI LES CONTRE-EXEMPLES PESENT 25-45 %
« no », « actually » et « rather » sont, en anglais parle, bien plus souvent
des marqueurs de discours que des marqueurs de correction :

    « no, that's true that... »        -> « no » repond, il ne corrige rien
    « anyway, we'll see thursday »      -> « anyway » ponctue, il ne corrige rien
    « it's rather expensive »           -> « rather » compare, il ne corrige rien
    « thursday and friday »             -> deux valeurs, toutes deux gardees

Un modele entraine uniquement sur des corrections apprendrait a supprimer tout
ce qui precede ces mots et couperait du contenu valide — le meme biais que les
familles `deja_chiffres`/`sans_nombre` evitent pour l'ITN.

LES NOMS DE FAMILLE SONT IDENTIQUES AU FRANCAIS, A DESSEIN
`valider_paires.py` connait la liste des familles contre-exemple par leur NOM
(« non_reponse », « enfin_discursif », « double_valeur », « plutot_comparatif »)
et ce nom est le meme dans les deux langues — c'est une regle du chantier
(voir chemins.py). Seuls les GABARITS sont anglais ; le champ `file` reste
« cor-<famille> » (jamais « cor-en-<famille> », sinon le validateur ne
reconnaitrait plus la famille via son decoupage `file.split("-", 1)[-1]`).

CONVENTION DE CASSE POUR LES JOURS
`JOURS` stocke les jours CAPITALISES (« Monday »), parce que c'est la forme
anglaise correcte cote propre. Cote sale, un jour est toujours inscrit en
minuscules (`.lower()`) : c'est ce qu'une transcription ASR brute produit
reellement, et c'est la seule categorie ou les deux cotes divergent en casse
(PRENOMS et VILLES restent capitalises des deux cotes, comme en francais).

LE PRONOM "I" EST TOUJOURS MAJUSCULE
`maj()` ne capitalise que le premier caractere. Une debut de phrase comme
« if i remember right » a son « i » interne qui doit RESTER majuscule en
anglais correct, meme au milieu d'une phrase. `_fix_i()` corrige ce point une
fois pour toutes cote propre, plutot que d'obliger chaque gabarit a y penser.

Usage : gen_correction_en.py [n] [sortie.jsonl]
"""
import collections, json, os, random, re, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd
SEED = 20260905
CONTROL = "[Styling: semi-formal] [Structure: prose] [Context: general] [Lang: en]"
# Hesitations de tete, comme en francais : une entree sur cinq en recoit une,
# et la chaine vide dans la liste garde une part d'entrees sans hesitation
# meme quand le tirage "avec hesitation" a lieu.
HESITATIONS = ["um ", "uh ", "so um ", "er ", "hmm ", ""]

try:
    from num2words import num2words
except ImportError:                                      # pragma: no cover
    num2words = None


def dicte(n):
    """Nombre en toutes lettres anglaises, sans virgule ni tiret : mesure sur
    ce venv, num2words(53, lang='en') = "fifty-three" et num2words(23450,
    lang='en') = "twenty-three thousand, four hundred and fifty" — l'ASR ne
    dicte jamais la ponctuation de sa propre sortie. "and" est CONSERVE :
    c'est la spec du format elle-meme qui l'ecrit ainsi dans ses exemples."""
    return num2words(n, lang="en").replace(",", "").replace("-", " ")


def _fix_i(s):
    """Le pronom "I" est toujours majuscule en anglais, y compris au milieu
    d'une phrase et dans une contraction ("I'll", "I'd") — ce que maj(), qui
    ne touche que le premier caractere, ne peut pas garantir seul. `\\bi\\b`
    trouve le "i" de "i'll" : `'` est un caractere non-mot, donc la frontiere
    existe juste apres le "i" comme juste avant."""
    return re.sub(r"\bi\b", "I", s)


# ── Vocabulaire, pour la variete combinatoire ───────────────────────────────
# Capitalises : forme correcte cote propre. Cote sale, toujours `.lower()`.
JOURS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
         "Sunday"]
PRENOMS = ["Sarah", "Tom", "James", "Emma", "Michael", "Laura", "David",
           "Sophie", "Daniel", "Emily", "Chris", "Rachel", "Matthew",
           "Olivia", "Andrew", "Hannah", "Ryan", "Jessica", "Kevin",
           "Amanda"]
VILLES = ["Leeds", "Manchester", "Bristol", "Austin", "Denver", "Chicago",
          "Seattle", "Boston", "Phoenix", "Portland", "Nashville", "Dallas",
          "Atlanta", "Miami", "Glasgow", "Liverpool", "Birmingham", "Cardiff"]
LIEUX = ["at the office", "at home", "in room two", "on the second floor",
         "at the station", "on a call", "at the restaurant", "at your place",
         "at my place", "in the lobby", "in the meeting room",
         "on a video call"]

# Pas d'accord de genre en anglais : GENRE reste un dict vide, exporte quand
# meme pour que gen_cor_itn_en.py puisse l'importer sans branche `if lang`.
OBJETS = ["the report", "the invoice", "the contract", "the quote",
          "the deck", "the mockup", "the schedule", "the order", "the brief",
          "the memo", "the presentation", "the summary"]
GENRE = {}

# Adjectifs simples, sans accord : adj() les renvoie tels quels.
ADJECTIFS = ["expensive", "long", "complicated", "urgent", "clear", "heavy",
             "simple", "fast", "ready", "complete"]


def adj(rng, objet=None):
    """L'adjectif, invariable en anglais — `objet` n'est garde que pour la
    meme signature qu'un futur accord, comme le veut la consigne."""
    return rng.choice(ADJECTIFS)


VERBES_ENVOI = ["send", "forward", "share", "resend", "pass along"]

# Verbes transitifs, pour composer des groupes verbaux varies avec OBJETS :
# c'est la combinatoire VERBES x OBJETS x gabarits qui fixe le nombre de
# paires distinctes qu'une famille peut produire, pas le poids.
VERBES_ACTION = ["review", "approve", "finish", "revise", "correct", "send",
                  "quote", "file", "sign", "archive", "check", "prepare"]

DEBUTS = ["i can confirm that", "i think", "we said that",
          "if i remember right", "i noted that", "we agreed that",
          "i was telling you that", "from what i recall"]

# ── Marqueurs de correction, par famille (mesure sur un normaliseur de reference + spec du contrat) ─
M_PARDON = ["no wait", "no sorry", "sorry", "no wait make that", "my mistake",
            "correction"]
M_ENFIN = ["actually", "no actually", "well actually", "I mean actually"]
M_PLUTOT = ["or rather", "make that", "rather", "or actually"]
M_VEUX_DIRE = ["I mean", "I meant", "that is", "I mean to say"]
M_NON_SEC = ["no", "no no"]

# ── Complement de contenu intercale, pour le trou mesure sur scribe-en-v1 ────
# Tous les gabarits « trancher » avaient la forme « <valeur A> <marqueur>
# <valeur B> » : la valeur abandonnee est immediatement suivie du marqueur.
# scribe-en-v1 (475/475 + 238/238 sur l'axe tenu a l'ecart) SUPPRIME du
# contenu des que ce n'est plus vrai :
#     IN  "let's meet at half past two tomorrow uh actually make it three
#          fifteen p m"
#     ATTENDU "Let's meet at 3:15pm tomorrow."
#     OBTENU  "Let's meet at 3:15pm."               <- "tomorrow" a disparu
# Le modele apprend a jeter tout ce qui touche la valeur abandonnee — y
# compris un complement qui n'a rien a voir avec la correction. COMPLEMENTS
# fournit ce complement ; `_complement()` le tire UNE fois par paire et
# l'appelant le reutilise cote sale (colle a la valeur abandonnee, avant le
# marqueur) ET cote propre (recolle a la valeur retenue) — jamais deux tirages
# separes, sinon le cote propre pourrait garder un complement qui n'existait
# pas cote sale (une invention).
COMPLEMENTS = ["tomorrow", "with Sarah", "at the office", "for the demo",
               "by email", "before lunch"]


def _complement(rng, p=0.28, exclude=()):
    """Un complement de contenu, ou None (72 % du temps) — voir le commentaire
    ci-dessus. `exclude` retire les complements qui doublonneraient le
    vocabulaire deja tire pour la valeur corrigee elle-meme (un prenom ne
    doit pas recevoir "with Sarah" si Sarah peut aussi etre la valeur A/B ;
    un lieu ne doit pas recevoir "at the office" si LIEUX contient deja cette
    entree)."""
    if rng.random() >= p:
        return None
    pool = [c for c in COMPLEMENTS if c not in exclude]
    return rng.choice(pool)


def maj(s):
    return s[0].upper() + s[1:] if s else s


def _remplace(rng, liste, sauf):
    """Un element different de `sauf` — sinon la correction ne corrige rien."""
    autres = [x for x in liste if x != sauf]
    return rng.choice(autres)


# ═══ FAMILLES DE CORRECTION : le modele doit TRANCHER ══════════════════════
# Correspondance des noms de famille (identiques au francais) :
#   pardon = "no wait" / "sorry" ; enfin = "actually" ; plutot = "or rather" /
#   "make that" ; veux_dire = "I mean" / "I meant" ; non_sec = "no" tout seul ;
#   nombre = auto-correction chiffree ; faux_depart = reprise sans marqueur.

def gen_pardon(rng):
    """"friday no wait thursday" -> "Thursday."

    Un quart environ intercale un complement de contenu entre la valeur
    abandonnee et le marqueur ("... TOMORROW no wait ...") : le modele doit
    le garder a sa place, pas le perdre avec la valeur abandonnee — voir
    COMPLEMENTS en tete de fichier."""
    forme = rng.choice(["jour", "prenom", "ville", "lieu", "objet"])
    m = rng.choice(M_PARDON)
    debut = rng.choice(DEBUTS)
    if forme == "jour":
        a = rng.choice(JOURS); b = _remplace(rng, JOURS, a)
        k = _complement(rng)
        if k:
            d = "%s we meet %s %s %s %s" % (debut, a.lower(), k, m, b.lower())
            c = "%s we meet %s %s." % (maj(debut), b, k)
        else:
            d = "%s we meet %s %s %s" % (debut, a.lower(), m, b.lower())
            c = "%s we meet %s." % (maj(debut), b)
    elif forme == "prenom":
        a = rng.choice(PRENOMS); b = _remplace(rng, PRENOMS, a)
        k = _complement(rng, exclude=("with Sarah",))
        if k:
            # le complement suit "who's handling it" (le marqueur, pas la
            # valeur, doit rester colle a ce groupe) : "it's Sarah who's
            # handling it FOR THE DEMO no wait Tom" -> "It's Tom who's
            # handling it for the demo."
            d = "%s it's %s who's handling it %s %s %s" % (debut, a, k, m, b)
            c = "%s it's %s who's handling it %s." % (maj(debut), b, k)
        else:
            d = "%s it's %s who's handling it %s %s" % (debut, a, m, b)
            c = "%s it's %s who's handling it." % (maj(debut), b)
    elif forme == "ville":
        a = rng.choice(VILLES); b = _remplace(rng, VILLES, a)
        k = _complement(rng)
        if k:
            d = "the meeting is in %s %s %s in %s" % (a, k, m, b)
            c = "The meeting is in %s %s." % (b, k)
        else:
            d = "the meeting is in %s %s in %s" % (a, m, b)
            c = "The meeting is in %s." % b
    elif forme == "lieu":
        a = rng.choice(LIEUX); b = _remplace(rng, LIEUX, a)
        k = _complement(rng, exclude=("at the office",))
        if k:
            d = "we're meeting %s %s %s %s" % (a, k, m, b)
            c = "We're meeting %s %s." % (b, k)
        else:
            d = "we're meeting %s %s %s" % (a, m, b)
            c = "We're meeting %s." % b
    else:
        a = rng.choice(OBJETS); b = _remplace(rng, OBJETS, a)
        # UN SEUL tirage de verbe, reutilise des deux cotes : c'est le bug
        # qui a empoisonne 1 100 paires francaises (verbe interverti entre
        # entree et sortie), voir gen_correction.py.
        v = rng.choice(VERBES_ENVOI)
        k = _complement(rng)
        if k:
            d = "i need to %s %s %s %s %s" % (v, a, k, m, b)
            c = "I need to %s %s %s." % (v, b, k)
        else:
            d = "i need to %s %s %s %s" % (v, a, m, b)
            c = "I need to %s %s." % (v, b)
    return d, c


def gen_enfin(rng):
    """"in Leeds actually in Manchester" -> "In Manchester." Un complement
    intercale un quart du temps environ (voir COMPLEMENTS)."""
    m = rng.choice(M_ENFIN)
    if rng.random() < 0.5:
        a = rng.choice(VILLES); b = _remplace(rng, VILLES, a)
        k = _complement(rng)
        if k:
            d = "it's in %s %s %s in %s" % (a, k, m, b)
            c = "It's in %s %s." % (b, k)
        else:
            d = "it's in %s %s in %s" % (a, m, b)
            c = "It's in %s." % b
    else:
        a = rng.choice(OBJETS); b = _remplace(rng, OBJETS, a)
        k = _complement(rng)
        if k:
            d = "i read through %s %s %s %s" % (a, k, m, b)
            c = "I read through %s %s." % (b, k)
        else:
            d = "i read through %s %s %s" % (a, m, b)
            c = "I read through %s." % b
    return d, c


def gen_plutot(rng):
    """"tuesday or rather wednesday" -> "Wednesday." Un complement intercale
    un quart du temps environ (voir COMPLEMENTS)."""
    m = rng.choice(M_PLUTOT)
    if rng.random() < 0.5:
        a = rng.choice(JOURS); b = _remplace(rng, JOURS, a)
        k = _complement(rng)
        if k:
            d = "let's set that for %s %s %s %s" % (a.lower(), k, m, b.lower())
            c = "Let's set that for %s %s." % (b, k)
        else:
            d = "let's set that for %s %s %s" % (a.lower(), m, b.lower())
            c = "Let's set that for %s." % b
    else:
        a = rng.choice(LIEUX); b = _remplace(rng, LIEUX, a)
        k = _complement(rng, exclude=("at the office",))
        if k:
            d = "i suggest %s %s %s %s" % (a, k, m, b)
            c = "I suggest %s %s." % (b, k)
        else:
            d = "i suggest %s %s %s" % (a, m, b)
            c = "I suggest %s." % b
    return d, c


def gen_veux_dire(rng):
    """"Sarah I mean Tom" -> "Tom." Un complement intercale un quart du temps
    environ, colle apres la queue fixe du gabarit ("know" / "who has the
    file") et non apres le prenom : voir COMPLEMENTS."""
    m = rng.choice(M_VEUX_DIRE)
    a = rng.choice(PRENOMS); b = _remplace(rng, PRENOMS, a)
    k = _complement(rng, exclude=("with Sarah",))
    i = rng.randrange(3)
    if i == 0:
        if k:
            d = "we need to let %s know %s %s %s" % (a, k, m, b)
            c = "We need to let %s know %s." % (b, k)
        else:
            d = "we need to let %s know %s %s" % (a, m, b)
            c = "We need to let %s know." % b
    elif i == 1:
        if k:
            d = "it's %s who has the file %s %s %s" % (a, k, m, b)
            c = "It's %s who has the file %s." % (b, k)
        else:
            d = "it's %s who has the file %s %s" % (a, m, b)
            c = "It's %s who has the file." % b
    else:
        if k:
            d = "i mentioned it to %s %s %s %s" % (a, k, m, b)
            c = "I mentioned it to %s %s." % (b, k)
        else:
            d = "i mentioned it to %s %s %s" % (a, m, b)
            c = "I mentioned it to %s." % b
    return d, c


def gen_non_sec(rng):
    """"the meeting is at eleven no at ten" -> "The meeting is at 10am."
    ("no" tout seul, sans "wait" ni "sorry", tranche aussi). Un complement
    intercale un quart du temps environ (voir COMPLEMENTS)."""
    m = rng.choice(M_NON_SEC)
    forme = rng.choice(["heure", "jour", "lieu", "prenom", "objet"])
    if forme == "heure" and num2words:
        ha = rng.randint(1, 11); hb = _remplace(rng, list(range(1, 12)), ha)
        k = _complement(rng)
        if rng.random() < 0.5:
            # "11am" : heure seule, marqueur am/pm dicte comme un seul mot
            # colle (forme deja normalisee par l'ASR, pas "a m" epelle) —
            # sinon "am"/"pm" apparaitrait cote propre sans jamais avoir
            # existe comme token cote sale, et serait accuse d'invention.
            ampm = rng.choice(["am", "pm"])
            if k:
                d = "the meeting is at %s %s %s %s %s %s" % (
                    dicte(ha), ampm, k, m, dicte(hb), ampm)
                c = "The meeting is at %d%s %s." % (hb, ampm, k)
            else:
                d = "the meeting is at %s %s %s %s %s" % (
                    dicte(ha), ampm, m, dicte(hb), ampm)
                c = "The meeting is at %d%s." % (hb, ampm)
        else:
            # "11:30" : heure et minutes, sans marqueur a m / p m.
            mn = rng.choice([15, 30, 45])
            if k:
                d = "the meeting is at %s %s %s %s %s %s" % (
                    dicte(ha), dicte(mn), k, m, dicte(hb), dicte(mn))
                c = "The meeting is at %d:%02d %s." % (hb, mn, k)
            else:
                d = "the meeting is at %s %s %s %s %s" % (
                    dicte(ha), dicte(mn), m, dicte(hb), dicte(mn))
                c = "The meeting is at %d:%02d." % (hb, mn)
    elif forme == "jour":
        a = rng.choice(JOURS); b = _remplace(rng, JOURS, a)
        v = rng.choice(["i'll drop by", "we deliver", "i'll call back",
                        "he's coming", "we're starting",
                        "i'm returning %s" % rng.choice(OBJETS)])
        k = _complement(rng)
        if k:
            d = "%s %s %s %s %s" % (v, a.lower(), k, m, b.lower())
            c = "%s %s %s." % (maj(v), b, k)
        else:
            d = "%s %s %s %s" % (v, a.lower(), m, b.lower())
            c = "%s %s." % (maj(v), b)
    elif forme == "lieu":
        a = rng.choice(LIEUX); b = _remplace(rng, LIEUX, a)
        k = _complement(rng, exclude=("at the office",))
        if k:
            d = "it's %s %s %s %s" % (a, k, m, b); c = "It's %s %s." % (b, k)
        else:
            d = "it's %s %s %s" % (a, m, b); c = "It's %s." % b
    elif forme == "prenom":
        a = rng.choice(PRENOMS); b = _remplace(rng, PRENOMS, a)
        k = _complement(rng, exclude=("with Sarah",))
        if k:
            d = "ask %s %s %s %s" % (a, k, m, b); c = "Ask %s %s." % (b, k)
        else:
            d = "ask %s %s %s" % (a, m, b); c = "Ask %s." % b
    else:
        a = rng.choice(OBJETS); b = _remplace(rng, OBJETS, a)
        k = _complement(rng)
        if k:
            d = "i need %s %s %s %s" % (a, k, m, b); c = "I need %s %s." % (b, k)
        else:
            d = "i need %s %s %s" % (a, m, b); c = "I need %s." % b
    return d, c


def gen_nombre(rng):
    """"three hundred no three hundred and fifty dollars" -> "$350."

    Cette famille fait travailler DEUX competences a la fois : trancher la
    correction et normaliser le nombre (ITN). Elle renforce l'ITN au lieu de
    lui faire concurrence — meme raisonnement que gen_correction.py. Un
    complement intercale un quart du temps environ, colle apres le mot-outil
    fixe ("dollars" / "percent") et non apres le chiffre : voir COMPLEMENTS,
    exemple mesure de la spec du format : "three hundred dollars for the demo
    sorry three hundred and fifty" -> "$350 for the demo.\""""
    if not num2words:
        raise RuntimeError("num2words requis")
    m = rng.choice(M_NON_SEC + M_PARDON[:2])
    forme = rng.choice(["montant", "quantite", "pourcent"])
    k = _complement(rng)
    if forme == "montant":
        a = rng.choice([100, 150, 200, 250, 300, 500, 800, 1200, 1500, 2000])
        b = a + rng.choice([50, 100, 150, 200, 500])
        if k:
            d = "the quote is %s dollars %s %s %s dollars" % (dicte(a), k, m, dicte(b))
            c = "The quote is $%s %s." % ("{:,}".format(b), k)
        else:
            d = "the quote is %s dollars %s %s dollars" % (dicte(a), m, dicte(b))
            c = "The quote is $%s." % ("{:,}".format(b))
    elif forme == "quantite":
        a = rng.randint(2, 40); b = _remplace(rng, list(range(2, 41)), a)
        if k:
            d = "we need %s %s %s %s" % (dicte(a), k, m, dicte(b))
            c = "We need %d %s." % (b, k)
        else:
            d = "we need %s %s %s" % (dicte(a), m, dicte(b))
            c = "We need %d." % b
    else:
        a = rng.choice([10, 15, 20, 25, 30, 40, 50])
        b = _remplace(rng, [10, 15, 20, 25, 30, 40, 50, 60, 70], a)
        if k:
            d = "we're at %s percent %s %s %s percent" % (dicte(a), k, m, dicte(b))
            c = "We're at %d%% %s." % (b, k)
        else:
            d = "we're at %s percent %s %s percent" % (dicte(a), m, dicte(b))
            c = "We're at %d%%." % b
    return d, c


def gen_faux_depart(rng):
    """"i'm gonna i'm going to send the report" -> "I'm going to send the report."

    Pas de marqueur : c'est la reprise seule qui signale l'abandon. Le modele
    doit couper l'amorce, pas la ponctuer."""
    v = "%s %s" % (rng.choice(VERBES_ACTION), rng.choice(OBJETS))
    tpl = rng.choice([
        ("i'm gonna i'm going to %s", "I'm going to %s."),
        ("we should we could %s", "We could %s."),
        ("we need to we have to %s", "We have to %s."),
        ("i'll i'll try to %s", "I'll try to %s."),
        ("let's let's just %s", "Let's just %s."),
        ("you should you could %s", "You could %s."),
        ("i was going to i think i'll %s", "I think I'll %s."),
    ])
    return tpl[0] % v, tpl[1] % v


# ═══ CONTRE-EXEMPLES : le modele ne doit RIEN supprimer ════════════════════
# Correspondance des noms de famille (identiques au francais) :
#   non_reponse = "no" qui repond ; enfin_discursif = "well"/"so"/"anyway"/
#   "I mean" comme ponctuation de discours ; double_valeur = deux valeurs
#   gardees ("X and Y") ; plutot_comparatif = "rather"/"actually"/"quite"
#   comparatifs.

def gen_non_reponse(rng):
    """"no that's true that the invoice is a bit high" -> "No, that's true
    that the invoice is a bit high." — "no" repond, il ne corrige pas.

    Chaque gabarit tire ses PROPRES fentes (comme en francais) : la
    combinatoire, pas le poids, fixe le plafond d'une famille."""
    i = rng.randrange(12)
    if i == 0:
        o = rng.choice(OBJETS)
        suite = suite_c = "that's true that %s is a bit %s" % (o, adj(rng, o))
    elif i == 1:
        suite = suite_c = "i don't think that's possible %s" % rng.choice(LIEUX)
    elif i == 2:
        suite = suite_c = "we haven't received %s yet" % rng.choice(OBJETS)
    elif i == 3:
        j = rng.choice(JOURS)
        suite = "that's not what we agreed %s" % j.lower()
        suite_c = "that's not what we agreed %s" % j
    elif i == 4:
        j = rng.choice(JOURS)
        suite = "i'd rather we talk about it again %s" % j.lower()
        suite_c = "i'd rather we talk about it again %s" % j
    elif i == 5:
        o = rng.choice(OBJETS)
        suite = suite_c = "%s isn't %s yet" % (o, adj(rng, o))
    elif i == 6:
        lieu, j = rng.choice(LIEUX), rng.choice(JOURS)
        suite = "we won't be %s %s" % (lieu, j.lower())
        suite_c = "we won't be %s %s" % (lieu, j)
    elif i == 7:
        suite = suite_c = "i haven't gotten %s from %s" % (
            rng.choice(OBJETS), rng.choice(PRENOMS))
    elif i == 8:
        suite = suite_c = "%s isn't the one handling it" % rng.choice(PRENOMS)
    elif i == 9:
        v, o, j = rng.choice(VERBES_ACTION), rng.choice(OBJETS), rng.choice(JOURS)
        suite = "we can't %s %s before %s" % (v, o, j.lower())
        suite_c = "we can't %s %s before %s" % (v, o, j)
    elif i == 10:
        suite = suite_c = "%s doesn't want to %s %s" % (
            rng.choice(PRENOMS), rng.choice(VERBES_ACTION), rng.choice(OBJETS))
    else:
        ville, j = rng.choice(VILLES), rng.choice(JOURS)
        suite = "i won't be in %s %s" % (ville, j.lower())
        suite_c = "i won't be in %s %s" % (ville, j)
    d = "no %s" % suite
    c = "No, %s." % suite_c
    return d, c


def gen_enfin_discursif(rng):
    """"anyway we'll see thursday" -> "Anyway, we'll see Thursday." —
    ponctuation de discours, pas une correction."""
    forme = rng.choice(["well", "so", "anyway", "i mean"])
    forme_c = "I mean" if forme == "i mean" else forme.capitalize()
    i = rng.randrange(4)
    if i == 0:
        j = rng.choice(JOURS)
        corps, corps_c = "we'll see %s" % j.lower(), "we'll see %s" % j
    elif i == 1:
        o = rng.choice(OBJETS)
        corps = corps_c = "%s is almost ready" % o
    elif i == 2:
        o = rng.choice(OBJETS)
        corps = corps_c = "we need to move forward on %s" % o
    else:
        lieu = rng.choice(LIEUX)
        corps = corps_c = "we're meeting %s" % lieu
    if rng.random() < 0.5:
        # marqueur en fin de phrase : reste en minuscules, comme le francais
        # garde "enfin bref" en minuscules en position finale.
        d, c = "%s %s" % (corps, forme), "%s, %s." % (maj(corps_c), forme)
    else:
        d, c = "%s %s" % (forme, corps), "%s, %s." % (forme_c, corps_c)
    return d, c


def gen_double_valeur(rng):
    """"thursday and friday" — deux valeurs legitimes, toutes deux gardees."""
    forme = rng.choice(["jours", "prenoms", "villes", "objets"])
    if forme == "jours":
        a = rng.choice(JOURS); b = _remplace(rng, JOURS, a)
        d = "i'm available %s and %s" % (a.lower(), b.lower())
        c = "I'm available %s and %s." % (a, b)
    elif forme == "prenoms":
        a = rng.choice(PRENOMS); b = _remplace(rng, PRENOMS, a)
        d = "%s and %s are handling it" % (a, b)
        c = "%s and %s are handling it." % (a, b)
    elif forme == "villes":
        a = rng.choice(VILLES); b = _remplace(rng, VILLES, a)
        d = "we have offices in %s and in %s" % (a, b)
        c = "We have offices in %s and in %s." % (a, b)
    else:
        a = rng.choice(OBJETS); b = _remplace(rng, OBJETS, a)
        d = "i need %s and %s" % (a, b)
        c = "I need %s and %s." % (a, b)
    return d, c


def gen_plutot_comparatif(rng):
    """"it's rather expensive" — "rather"/"actually"/"quite" comparent, ils
    ne corrigent pas."""
    i = rng.randrange(10)
    if i == 0:
        o = rng.choice(OBJETS)
        corps = corps_c = "%s is rather %s" % (o, adj(rng, o))
    elif i == 1:
        corps = corps_c = "actually it's quite %s" % adj(rng)
    elif i == 2:
        corps = corps_c = "i'd rather meet %s than %s" % (
            rng.choice(LIEUX), rng.choice(LIEUX))
    elif i == 3:
        prenom, j = rng.choice(PRENOMS), rng.choice(JOURS)
        corps = "%s is more likely to be free on %s" % (prenom, j.lower())
        corps_c = "%s is more likely to be free on %s" % (prenom, j)
    elif i == 4:
        corps = corps_c = "it's rather %s as a solution" % adj(rng)
    elif i == 5:
        corps = corps_c = "i'm rather %s about %s" % (
            rng.choice(["in favor", "reserved", "confident"]),
            rng.choice(OBJETS))
    elif i == 6:
        corps = corps_c = "we're rather %s on the schedule" % rng.choice(
            ["ahead", "behind", "on time"])
    elif i == 7:
        corps = corps_c = "%s is rather the type to %s %s" % (
            rng.choice(PRENOMS), rng.choice(VERBES_ACTION), rng.choice(OBJETS))
    elif i == 8:
        corps = corps_c = "we'd rather go to %s than %s" % (
            rng.choice(VILLES), rng.choice(VILLES))
    else:
        v, o, j = rng.choice(VERBES_ACTION), rng.choice(OBJETS), rng.choice(JOURS)
        corps = "it's rather better to %s %s %s" % (v, o, j.lower())
        corps_c = "it's rather better to %s %s %s" % (v, o, j)
    return corps, maj(corps_c) + "."


FAMILLES = [
    # trancher — correspondance francaise entre parentheses
    ("pardon", gen_pardon, 15),                      # no wait / sorry
    ("enfin", gen_enfin, 11),                        # actually
    ("plutot", gen_plutot, 9),                       # or rather / make that
    ("veux_dire", gen_veux_dire, 8),                 # I mean / I meant
    ("non_sec", gen_non_sec, 10),                    # "no" tout seul
    ("nombre", gen_nombre, 12),                      # auto-correction chiffree
    ("faux_depart", gen_faux_depart, 8),             # reprise sans marqueur
    # ne rien supprimer — ~32 % du jeu, et c'est deliberé
    ("non_reponse", gen_non_reponse, 13),            # "no" qui repond
    ("enfin_discursif", gen_enfin_discursif, 7),     # well / so / anyway / I mean
    ("double_valeur", gen_double_valeur, 7),         # "X and Y" gardes
    ("plutot_comparatif", gen_plutot_comparatif, 8), # rather / actually / quite
]
CONTRE = {"non_reponse", "enfin_discursif", "double_valeur", "plutot_comparatif"}
# Plancher impose par gen_cor_itn.py (voir son main()) : sous ce seuil, une
# famille n'a pas assez de gabarits/vocabulaire pour generaliser.
PLANCHER = 200


def main():
    n_total = int(sys.argv[1]) if len(sys.argv) > 1 else 6000
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        SP, "pairs_correction_en.jsonl")
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
        clean = _fix_i(clean)
        # Le cote sale doit ressembler a de l'ASR : une hesitation de temps en
        # temps, qui disparait en sortie comme partout ailleurs.
        if rng.random() < 0.20:
            h = rng.choice(HESITATIONS)
            if h:
                dirty = h + dirty
        stats[fam] += 1
        rows.append({"id": "cor-en-%05d" % len(rows), "file": "cor-%s" % fam,
                     "source": "correction", "lang": "en", "held_out": False,
                     "styling": "semi-formal", "structure": "prose",
                     "context": "general", "control": CONTROL,
                     "dirty": dirty, "clean": clean})

    # 8 % tenus a l'ecart PAR FAMILLE. Un decoupage par fichier emporterait des
    # familles entieres : elles n'ont que onze valeurs de `file` distinctes.
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
    tranche = sum(stats[f] for f in noms if f not in CONTRE)
    print("paires d'auto-correction (anglais) : %d  (%d tentatives, %d doublons ecartes)"
          % (n, tries, tries - n))
    print("%-20s %6s %6s" % ("famille", "n", "%"))
    sous = []
    for fam, _, _ in FAMILLES:
        marque = "   <- contre-exemple" if fam in CONTRE else ""
        print("%-20s %6d %5.1f%%%s" % (fam, stats[fam],
                                       100.0 * stats[fam] / max(1, n), marque))
        if stats[fam] < PLANCHER:
            sous.append(fam)
    print("\ntrancher : %d (%.0f %%) | ne rien supprimer : %d (%.0f %%)"
          % (tranche, 100.0 * tranche / max(1, n),
             n - tranche, 100.0 * (n - tranche) / max(1, n)))
    print("tenues a l'ecart : %d" % sum(1 for r in rows if r["held_out"]))
    print("-> %s" % out)
    if sous:
        print("\nATTENTION : famille(s) sous le plancher de %d — elargir les "
              "gabarits ou le vocabulaire : %s" % (PLANCHER, ", ".join(sous)))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
