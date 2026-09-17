# -*- coding: utf-8 -*-
"""Generateur synthetique d'ITN ANGLAIS -- jumeau de gen_itn.py, memes familles.

POURQUOI IL EXISTE. Decision du 2026-09-05 : un modele par langue. Le francais
avait deja mesure (2026-09-02) que l'ITN ne s'apprend pas du reel -- il n'y a
presque aucune expression numerique de dictee dans VoxPopuli EN non plus (voir
spec_en.py, section VoxPopuli) -- et qu'un generateur synthetique deterministe
suffit : on tire une valeur, num2words en donne la forme parlee, la forme
ecrite est celle qu'on a tiree. Les deux cotes sont exacts PAR CONSTRUCTION.

CE QUI CHANGE PAR RAPPORT AU FRANCAIS, ET POURQUOI.
  - num2words(lang="en") ecrit avec des virgules et des tirets ("twenty-three
    thousand, four hundred and fifty") : un ASR n'ecrit ni l'un ni l'autre.
    dicte() retire les virgules et remplace les tirets par des espaces ; le
    "and" reste, les anglophones le disent.
  - Les dates ont DEUX ordres possibles en anglais et ne se reordonnent jamais
    (spec_en.ITN_RULES) : "march third twenty twenty six" -> "March 3, 2026"
    (ordre americain) contre "the third of march twenty twenty six" ->
    "3 March 2026" (ordre europeen). On tire l'ordre, jamais on ne le change.
  - Les annees se disent par paires de deux chiffres ("twenty twenty-six")
    sauf la decennie 2000-2009 ("two thousand and five") : num2words ne fait
    pas ce decoupage seul, annee_mots() le fait a la main.
  - "noon" et "midnight" ne se convertissent PAS en chiffres (spec_en.ITN_RULES
    ne le dit pas explicitement mais aucun exemple ne les convertit, et la
    spec du format ne montre que des heures chiffrees). Les mettre dans la
    famille heure les rendrait indiscernables d'une paire non transformee une
    fois les deux cotes mis en minuscules -- exactement ce que
    valider_paires.py appelle "identique", et heure n'est pas une famille
    contre-exemple. On les place donc dans sans_nombre, qui EST une famille
    contre-exemple : le sens (rester un mot) est identique, la place dans le
    jeu est correcte au regard du validateur.
  - Le cote sale est TOUJOURS entierement minuscule et sans ponctuation finale
    -- pas seulement le chiffre. C'est ce que montrent tous les exemples bruts
    de la spec du format reproduits dans spec_en.py ("twenty three thousand
    four hundred and fifty dollars ... march third twenty twenty six", sans
    aucune majuscule ni point). Chaque phrase porteuse est donc ecrite une
    seule fois, bien formee ("We're meeting on {}."), et par() en derive le
    cote sale en abaissant la casse et en coupant le point final -- jamais
    l'inverse (pas de fabrication a la main d'une version minuscule a cote).

CONTRE-EXEMPLES A 25-45 %, PAS 14 %. Le francais pese deja_chiffres et
sans_nombre a 14 % du total ; la consigne de ce chantier fixe la fourchette a
25-45 % pour ce jeu-ci. Les poids ci-dessous leur donnent 35 %, en reduisant
les autres familles d'autant -- rien dans la combinatoire ne les limitait,
c'est un choix de repartition, pas une contrainte technique.

Comme en francais : aucun fragment n'est tire deux fois (un seul dirty/clean
par valeur), 8 % tenus a l'ecart PAR FAMILLE, et les NOMS DE FAMILLE ainsi que
le prefixe du champ file sont IDENTIQUES au francais -- c'est valider_paires.py
qui l'exige (voir sa liste `contre` codee en dur).
"""
import collections, json, os, random, sys
from num2words import num2words

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL -- voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd
SEED = 20260905

MOIS = ["January", "February", "March", "April", "May", "June", "July",
        "August", "September", "October", "November", "December"]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def mot(n):
    return num2words(n, lang="en")


def mot_ordinal(n):
    return num2words(n, lang="en", to="ordinal")


def dicte(s):
    """Ce qu'un ASR ecrirait pour un nombre en toutes lettres : num2words met
    des virgules ("twenty-three thousand, four hundred") et des tirets
    ("forty-two") qu'aucun ASR ne produit. Le "and" reste : les anglophones le
    disent ("four hundred and fifty")."""
    return s.replace(",", "").replace("-", " ")


def virgule_milliers(n):
    """Format anglais : virgule tous les trois chiffres. 23450 -> "23,450"."""
    s = str(abs(int(n)))
    out = ""
    while len(s) > 3:
        out = "," + s[-3:] + out
        s = s[:-3]
    return ("-" if n < 0 else "") + s + out


def annee_mots(y):
    """Les annees se disent par paires de deux chiffres en anglais courant
    ("twenty twenty-six" pour 2026), sauf 2000-2009 ("two thousand and five")
    -- num2words ne connait pas ce decoupage, il faut le faire a la main."""
    if 2000 <= y <= 2009:
        reste = y - 2000
        if reste == 0:
            return "two thousand"
        return "two thousand and " + mot(reste)
    siecle, reste = y // 100, y % 100
    mot_siecle = mot(siecle)
    if reste == 0:
        return "%s hundred" % mot_siecle
    if reste < 10:
        return "%s oh %s" % (mot_siecle, mot(reste))
    return "%s %s" % (mot_siecle, mot(reste))


def sale(s):
    """Derive le cote sale d'une phrase bien formee : tout en minuscules, sans
    le point final. JAMAIS l'inverse -- une phrase sale n'est pas ecrite a la
    main a cote de sa version propre, ce qui garantirait leur divergence."""
    d = s.lower()
    return d[:-1] if d.endswith(".") else d


def par(rng, porteuses, parle_val, ecrit_val):
    """Tire UNE porteuse, l'applique aux deux valeurs deja tirees. La porteuse
    elle-meme n'est jamais tiree deux fois : c'est le meme tirage qui sert aux
    deux cotes, comme dans gen_itn.py."""
    t = rng.choice(porteuses)
    clean = t.format(ecrit_val)
    dirty = sale(t.format(parle_val))
    return dirty, clean


def par2(rng, porteuses, parle_vals, ecrit_vals):
    """Comme par(), pour une porteuse a DEUX trous ("{} ... {}") : les deux
    valeurs de chaque cote sont deja tirees, seule la porteuse elle-meme est
    tiree ici -- meme regle qu'en un trou, un seul tirage sert aux deux cotes."""
    t = rng.choice(porteuses)
    clean = t.format(*ecrit_vals)
    dirty = sale(t.format(*parle_vals))
    return dirty, clean


# ── Phrases porteuses, par famille ───────────────────────────────────────────

PORTEUSES_NB = [
    "There are {} people in the room.", "We received {} sign-ups.",
    "I have {} unread messages.", "The file has {} lines.",
    "She has {} followers now.", "That's {} hours of work.",
    "We're at {} open tickets.", "The folder has {} pages.",
    "There are {} seats left.", "I walked {} kilometres today.",
    "The warehouse in Bristol shipped {} units.", "Denver reported {} new cases.",
]
# Decimales : les compteurs (personnes, pages, tickets...) n'en ont pas dans la
# vraie vie ("930.7 lignes" ne se dit pas) ; les mesures et notes, si.
PORTEUSES_NB_DECIMAL = [
    "I walked {} kilometres today.", "That's {} hours of work.",
    "The rating came out to {}.", "The distance is {} miles.",
    "It weighs about {} kilos.", "The score was {}.",
]
PORTEUSES = [
    "The quote comes to {}.", "That's {} in total.", "I have {} left in the account.",
    "I owe you {}.", "The budget is {}.", "We spent {} this month.",
    "The transfer of {} went through.", "Bill {} for the service.",
    "We need at least {}.", "The invoice comes to {}.",
]
PORTEUSES_IMPLICIT = {
    "$": ["The total in dollars comes to {}.", "In US dollars that's about {}.",
          "Converted to dollars it's {}."],
    "£": ["The total in pounds comes to {}.", "In sterling that's about {}.",
          "Converted to pounds it's {}."],
    "€": ["The total in euros comes to {}.", "In euros that's about {}.",
          "Converted to euros it's {}."],
}
PORTEUSES_CENTS = [
    "That will be {}.", "It only costs {}.", "The fee comes to {}.",
    "The difference is just {}.", "That's {} short.",
]
PORTEUSES_DATE = [
    "We're meeting on {}.", "The deadline is on {}.", "The contract starts on {}.",
    "She was born on {}.", "The meeting was moved to {}.",
    "It needs to be done by {}.", "Payment is due on {}.",
    "We signed on {}.", "Delivery is expected on {}.", "The trip is planned for {}.",
]
PORTEUSES_ANNEE = [
    "That was back in {}.", "The building was built in {}.",
    "She graduated in {}.", "The company was founded in {}.",
    "That policy dates back to {}.",
]
# Trou releve (bench scribe-en-v1) : le jeu n'avait aucun gabarit ou la date
# OUVRE la phrase ("the third of march twenty twenty six is the deadline") --
# le modele n'a jamais vu une date en position sujet et se contente de la
# capitaliser au lieu de la convertir. Deux ordres, avec et sans annee, avec
# et sans heure -- voir gen_date_tete().
PORTEUSES_DATE_TETE = [
    "{} is the deadline.", "{} works for me.", "{} is when we start.",
    "{} is the target date.", "{} we ship.", "{} we go live.",
    "{} is confirmed.", "{} is fine by me.",
]
PORTEUSES_DATE_TETE_HEURE = [
    "On {} at {} we meet.", "On {} at {} we start.", "{} at {} works for me.",
    "On {} at {} the doors open.", "{} at {} is when we begin.",
    "{} at {}.",
]
PORTEUSES_HEURE = [
    "We're meeting at {}.", "The train leaves at {}.", "Let's call at {}.",
    "The store closes at {}.", "I'll be there around {}.",
    "She called me at {}.", "The flight from Manchester departs at {}.",
    "Doors open at {}.", "The office in Austin opens at {}.",
]
# Trou releve (bench scribe-en-v2) : une heure NUE -- sans o'clock, sans
# am/pm, sans minutes ("at nine", "around eight") -- n'avait aucune forme.
# "the meeting is at nine for three hundred dollars" devenait "at $9 for
# $300" : le modele inventait un symbole monetaire sur l'heure par contagion
# du montant qui suit. Ecrite en chiffres SANS deux-points ni symbole -- voir
# gen_heure_nue().
PORTEUSES_HEURE_NUE = [
    "We're meeting at {}.", "Let's call around {}.", "I'll see you by {}.",
    "The train leaves around {}.", "Doors open at {} tomorrow.",
    "She'll call by {}.", "Let's meet at {} tomorrow.", "The store opens around {}.",
    "I'll be there by {}.", "We start at {} sharp.", "Call me around {}.",
    "The shop closes by {}.",
]
# Porteuses a deux trous : l'heure nue precede ou suit un montant, un entier
# dicte ou un pourcentage dans la MEME phrase -- exactement le contexte qui
# faisait inventer le symbole monetaire. Un seul tirage sert aux deux cotes,
# comme partout ailleurs dans ce fichier (voir par2()).
PORTEUSES_HEURE_NUE_MONT = [
    "The meeting is at {} for {}.", "Doors open at {} for {}.",
    "We're closing at {} after making {}.", "The call is at {} to discuss {}.",
]
PORTEUSES_HEURE_NUE_ENTIER = [
    "We open at {} with {} people.", "We start at {} with {} guests.",
    "The show starts at {} with {} tickets left.", "We begin at {} with {} on the list.",
]
PORTEUSES_HEURE_NUE_PCT = [
    "We start at {} with {} already booked.", "The sale opens at {} with {} sold already.",
    "We begin at {} with {} of seats filled.",
]
PORTEUSES_PCT = [
    "We're at a {} margin.", "That's {} of the total.", "We're {} short of the goal.",
    "The rate went up to {}.", "We gained {} this year.",
    "Discounts are capped at {}.", "Turnout was around {}.",
]
PORTEUSES_TEL = [
    "You can reach me at {}.", "Call me at {}.", "Her number is {}.",
    "Text him at {}.", "The office line is {}.", "Ring the front desk at {}.",
    "My cell is {}.", "You can text me on {}.",
]
PORTEUSES_EMAIL = [
    "Send that to {}.", "Her email is {}.", "You can write to {}.",
    "Copy {} on this.", "Reach out to {} directly.", "His address is {}.",
]
TOUTES_PORTEUSES = [
    "It says {} on the screen.", "The number on the invoice is {}.",
    "That's what it shows: {}.", "The reading was {}.",
    "It's marked as {} on the form.", "The counter shows {}.",
    "That figure was {}.", "The label reads {}.",
    "The ticket number is {}.", "It came up as {}.",
]
# Trou releve : "we had 2500 people at 3pm and it went well" -> le modele
# ajoutait une virgule a un nombre DEJA en chiffres. TOUTES_PORTEUSES ne
# montre qu'UNE valeur deja-chiffree isolee dans un gabarit generique ; il
# manquait des phrases ordinaires avec un nombre brut a 4-7 chiffres, seul ou
# combine a une heure/un montant/un pourcentage deja chiffres eux aussi --
# voir gen_deja_chiffres() et valeur_num_brute().
PORTEUSES_DEJA_SEUL = [
    "We had {} people at the event.", "The warehouse holds {} units.",
    "There are {} records in the system.", "Attendance hit {} this year.",
    "The population is close to {}.", "We shipped {} orders last quarter.",
    "The article got {} views overnight.", "Enrollment reached {} students.",
    "The stadium seats {}.", "Sales reached {} units this month.",
]
PORTEUSES_DEJA_COMBO_HEURE = [
    "We had {} people at {} and it went well.", "There were {} attendees by {}.",
    "The venue had {} guests checked in by {}.", "We counted {} entries before {}.",
    "Sales hit {} units by {} sharp.",
]
PORTEUSES_DEJA_COMBO_MONT = [
    "We had {} sign-ups for {}.", "There were {} tickets sold at {} each.",
    "The order had {} items totalling {}.", "We logged {} calls costing {}.",
]
PORTEUSES_DEJA_COMBO_PCT = [
    "We had {} responses with {} approval.", "There were {} votes at {} turnout.",
    "The batch had {} units with {} defects.",
]

# Decoys : "at", "dot", "point", "one" en usage ORDINAIRE, pour que le modele
# n'y voie pas une adresse ou un nombre. Releves dans la consigne du chantier.
FIXED_DECOYS = [
    "We met at the station.", "Let's get to the point.", "One of us has to go.",
    "That's a good point.", "She stared at the screen for a while.",
    "He's really good at this.", "Stop beating around the point.",
    "One more thing before we start.", "I'll be at the office all day.",
    "Try to get straight to the point.", "He looked at her and smiled.",
    "One never knows what to expect.",
]
# "noon" et "midnight" restent des mots -- voir la note en tete de fichier sur
# pourquoi ils vivent ici et pas dans la famille heure.
NOON_MIDNIGHT = [
    "We can meet at noon.", "Let's talk before midnight.",
    "The office closes at noon.", "It happened around midnight.",
    "She usually calls around noon.", "The deadline is midnight.",
    "Lunch is at noon sharp.", "The shift ends at midnight.",
]
# Fragments combinables : la combinatoire, pas le poids, fixe le plafond d'une
# famille (lecon de gen_cor_itn.py).
SN_SUJET = ["I", "We", "He", "She", "The client", "The team", "My colleague",
            "The manager", "The vendor", "Our supplier"]
# Simple past uniquement : invariable quel que soit le sujet ("I"/"We" cassent
# l'accord d'un present a la 3e personne -- "we is preparing" -- une lecture
# de l'echantillon l'a montre sur pairs_itn_en.jsonl.
SN_VERBE = ["reviewed", "approved", "sent back", "wanted to revisit", "waited on",
            "signed off on", "commented on", "needed to follow up on",
            "prepared", "forgot about"]
SN_OBJET = ["the contract", "the mockup", "the quote", "the proposal", "the file",
            "the presentation", "the report", "the invoice", "the brief", "the appendix"]
SN_QUEUE = ["before the meeting", "as soon as possible", "by the end of the week",
            "this morning", "without telling me", "after review", "last night",
            "on their end", "a second time", ""]

HESITATIONS = ["um ", "uh ", "er ", "so um "]

CURRENCIES = [("dollars", "$"), ("pounds", "£"), ("euros", "€")]
CUR_WEIGHTS = [45, 30, 25]


# ── Un generateur par famille ────────────────────────────────────────────────

def valeur_multi_echelle(rng):
    """Nombres a deux ou trois echelles (million+thousand+unites,
    thousand+hundred+dizaines), avec des zeros intermediaires par endroits
    ("two million and forty" = 2 000 040, "three thousand and seven" = 3 007).
    Trou releve : "fourteen million eight hundred thousand and thirty two"
    -> 14 832 au lieu de 14 800 032. num2words rend ce gabarit correctement
    (verifie) ; c'est le tirage uniforme sur une plage large qui le sous-
    representait -- ce generateur le construit explicitement."""
    mode = rng.choices(["million_plein", "million_trou", "mille_plein", "mille_trou"],
                       weights=[35, 25, 25, 15])[0]
    if mode == "million_plein":
        return rng.randint(1, 20) * 10 ** 6 + rng.randint(1, 999) * 1000 + rng.randint(1, 999)
    if mode == "million_trou":
        return rng.randint(1, 20) * 10 ** 6 + rng.randint(1, 999)
    if mode == "mille_plein":
        return rng.randint(1, 20) * 1000 + rng.randint(1, 9) * 100 + rng.randint(1, 99)
    return rng.randint(1, 20) * 1000 + rng.randint(1, 99)


def gen_entier(rng):
    forme = rng.choices(["plain", "a_hundred", "round_hundred", "decimal", "multi_echelle"],
                        weights=[40, 8, 12, 15, 25])[0]
    if forme == "multi_echelle":
        n = valeur_multi_echelle(rng)
        parle, ecrit = dicte(mot(n)), virgule_milliers(n)
        return par(rng, PORTEUSES_NB, parle, ecrit)
    if forme == "a_hundred":
        n, parle, ecrit = 100, "a hundred", "100"
    elif forme == "round_hundred":
        # "twelve hundred" -> 1200 : une facon courante de dire les centaines
        # rondes que num2words ne produit pas seul ("one thousand, two hundred").
        k = rng.randint(11, 99)
        while k % 10 == 0:
            k = rng.randint(11, 99)
        n = k * 100
        parle, ecrit = "%s hundred" % dicte(mot(k)), virgule_milliers(n)
    elif forme == "decimal":
        intpart, dec = rng.randint(0, 999), rng.randint(1, 9)
        parle = "%s point %s" % (dicte(mot(intpart)), dicte(mot(dec)))
        ecrit = "%d.%d" % (intpart, dec)
        return par(rng, PORTEUSES_NB_DECIMAL, parle, ecrit)
    else:
        bucket = rng.choices(["petit", "moyen", "grand", "tres_grand"],
                             weights=[45, 30, 20, 5])[0]
        n = {"petit": lambda: rng.randint(1, 99),
             "moyen": lambda: rng.randint(100, 9999),
             "grand": lambda: rng.randint(10000, 999999),
             "tres_grand": lambda: rng.randint(10 ** 6, 50 * 10 ** 6)}[bucket]()
        parle, ecrit = dicte(mot(n)), virgule_milliers(n)
    return par(rng, PORTEUSES_NB, parle, ecrit)


def gen_montant(rng):
    devise, sym = rng.choices(CURRENCIES, weights=CUR_WEIGHTS)[0]
    n = rng.choice([rng.randint(1, 999), rng.randint(1, 99) * 10,
                    rng.randint(1, 500) * 100, rng.randint(1000, 99999)])
    forme = rng.choices(["simple", "word_cents", "inline_cents", "implicit_cents",
                        "cents_only", "half_thousand", "round_hundred"],
                       weights=[25, 15, 12, 8, 8, 12, 20])[0]
    if forme == "round_hundred":
        # "twelve hundred dollars" -> $1,200 ; "fifteen hundred euros" ->
        # €1,500. Trou releve : le separateur de milliers manquait pour les
        # montants dictes en "hundred" -- virgule_milliers() le fournit deja,
        # il manquait juste ce mode de tirage cote montant.
        k = rng.randint(11, 99)
        while k % 10 == 0:
            k = rng.randint(11, 99)
        n = k * 100
        parle = "%s hundred %s" % (dicte(mot(k)), devise)
        ecrit = "%s%s" % (sym, virgule_milliers(n))
        return par(rng, PORTEUSES, parle, ecrit)
    if forme == "simple":
        parle = "%s %s" % (dicte(mot(n)), devise)
        ecrit = "%s%s" % (sym, virgule_milliers(n))
        return par(rng, PORTEUSES, parle, ecrit)
    if forme == "word_cents":
        c = rng.randint(1, 99)
        parle = "%s %s and %s cents" % (dicte(mot(n)), devise, dicte(mot(c)))
        ecrit = "%s%s.%02d" % (sym, virgule_milliers(n), c)
        return par(rng, PORTEUSES, parle, ecrit)
    if forme == "inline_cents":
        c = rng.randint(1, 99)
        parle = "%s %s %s" % (dicte(mot(n)), devise, dicte(mot(c)))
        ecrit = "%s%s.%02d" % (sym, virgule_milliers(n), c)
        return par(rng, PORTEUSES, parle, ecrit)
    if forme == "implicit_cents":
        # "forty two fifty" -> le contexte (la porteuse) porte la devise, pas
        # le nombre lui-meme -- voir la note du chantier sur cet exemple.
        c = rng.randint(1, 99)
        parle = "%s %s" % (dicte(mot(n)), dicte(mot(c)))
        ecrit = "%s%s.%02d" % (sym, virgule_milliers(n), c)
        return par(rng, PORTEUSES_IMPLICIT[sym], parle, ecrit)
    if forme == "cents_only":
        c = rng.randint(1, 99)
        return par(rng, PORTEUSES_CENTS, "%s cents" % dicte(mot(c)), "%d cents" % c)
    # half_thousand : "two and a half thousand dollars" -> 2500
    k = rng.randint(1, 20)
    n2 = k * 1000 + 500
    parle = "%s and a half thousand %s" % (dicte(mot(k)), devise)
    ecrit = "%s%s" % (sym, virgule_milliers(n2))
    return par(rng, PORTEUSES, parle, ecrit)


def construire_date(rng, avec_annee):
    """Construit (parle, ecrit) pour une date complete ou sans annee, dans
    l'un des deux ordres -- extrait de gen_date() pour etre reutilise par
    gen_date_tete() sans dupliquer la regle de non-reordonnancement."""
    jour = rng.randint(1, 28)
    m = rng.randrange(12)
    annee = rng.choice([rng.randint(1950, 2010), rng.randint(2020, 2035)])
    ordre = rng.choice(["us", "uk"])
    jour_ord = dicte(mot_ordinal(jour))
    if ordre == "us":
        # "march third twenty twenty six" -> "March 3, 2026" : jamais reordonne.
        if avec_annee:
            parle = "%s %s %s" % (MOIS[m], jour_ord, dicte(annee_mots(annee)))
            ecrit = "%s %d, %d" % (MOIS[m], jour, annee)
        else:
            parle, ecrit = "%s %s" % (MOIS[m], jour_ord), "%s %d" % (MOIS[m], jour)
    else:
        # "the third of march twenty twenty six" -> "3 March 2026".
        if avec_annee:
            parle = "the %s of %s %s" % (jour_ord, MOIS[m], dicte(annee_mots(annee)))
            ecrit = "%d %s %d" % (jour, MOIS[m], annee)
        else:
            parle, ecrit = "the %s of %s" % (jour_ord, MOIS[m]), "%d %s" % (jour, MOIS[m])
    return parle, ecrit


def gen_date_tete(rng):
    """La date OUVRE la phrase ("the third of march twenty twenty six is the
    deadline", "on the fifth of june at ten am we meet") : trou releve sur
    scribe-en-v1, le jeu n'avait aucun exemple de date en position sujet et
    le modele se contentait de la capitaliser au lieu de la convertir. Les
    deux ordres, avec et sans annee, avec et sans heure -- meme regle de
    non-reordonnancement que gen_date()."""
    date_parle, date_ecrit = construire_date(rng, avec_annee=rng.random() < 0.55)
    if rng.random() < 0.45:
        h = rng.randint(1, 12)
        ampm, ampm_mot = choix_ampm(rng)
        heure_parle, heure_ecrit = "%s %s" % (dicte(mot(h)), ampm_mot), "%d%s" % (h, ampm)
        return par2(rng, PORTEUSES_DATE_TETE_HEURE,
                    (date_parle, heure_parle), (date_ecrit, heure_ecrit))
    return par(rng, PORTEUSES_DATE_TETE, date_parle, date_ecrit)


def gen_date(rng):
    forme = rng.choices(["complete", "sans_annee", "annee_seule", "tete"],
                        weights=[40, 18, 15, 27])[0]
    if forme == "annee_seule":
        annee = rng.choice([rng.randint(1950, 2010), rng.randint(2020, 2035)])
        parle, ecrit = dicte(annee_mots(annee)), str(annee)
        return par(rng, PORTEUSES_ANNEE, parle, ecrit)
    if forme == "tete":
        return gen_date_tete(rng)

    parle, ecrit = construire_date(rng, avec_annee=(forme == "complete"))
    if rng.random() < 0.3:
        wd = rng.choice(WEEKDAYS)
        # virgule cote ecrit seulement ("Sunday, 3 March 1990") : le cote sale
        # n'a pas de ponctuation interne, l'ecrit en a besoin pour se lire.
        parle, ecrit = "%s %s" % (wd, parle), "%s, %s" % (wd, ecrit)
    return par(rng, PORTEUSES_DATE, parle, ecrit)


def minute_mot(mm):
    return "oh %s" % dicte(mot(mm)) if mm < 10 else dicte(mot(mm))


def choix_ampm(rng):
    # "am"/"pm" dictes en un seul mot (pas "a m" en deux lettres separees) :
    # sinon le mot de deux lettres du cote propre ("10:58am" -> token "am")
    # n'a aucune source cote sale (les lettres isolees "a" et "m" sont trop
    # courtes pour compter comme des mots) et valider_paires.py le signale a
    # tort comme une invention -- decision de generation, pas du validateur.
    return ("am", "am") if rng.choice([True, False]) else ("pm", "pm")


def gen_heure_nue(rng):
    """Heure nue : "at nine", "around eight", "by seven" -- en chiffres SANS
    deux-points ni symbole ("at 9"). ~20 % de la famille heure (voir le poids
    du mode "nue" dans gen_heure). La majorite est une porteuse simple ; le
    reste combine l'heure nue a un montant, un entier dicte ou un pourcentage
    dans la meme phrase, pour que le modele n'invente pas un symbole sur
    l'heure par contagion de la valeur voisine."""
    h = rng.randint(1, 12)
    parle, ecrit = dicte(mot(h)), str(h)
    r = rng.random()
    if r < 0.6:
        return par(rng, PORTEUSES_HEURE_NUE, parle, ecrit)
    if r < 0.75:
        n = rng.choice([rng.randint(1, 999), rng.randint(1, 99) * 10, rng.randint(1, 500) * 100])
        sym, devise = rng.choice([("$", "dollars"), ("£", "pounds"), ("€", "euros")])
        autre_parle = "%s %s" % (dicte(mot(n)), devise)
        autre_ecrit = "%s%s" % (sym, virgule_milliers(n))
        return par2(rng, PORTEUSES_HEURE_NUE_MONT, (parle, autre_parle), (ecrit, autre_ecrit))
    if r < 0.9:
        n = rng.randint(2, 999)
        autre_parle, autre_ecrit = dicte(mot(n)), virgule_milliers(n)
        return par2(rng, PORTEUSES_HEURE_NUE_ENTIER, (parle, autre_parle), (ecrit, autre_ecrit))
    n = rng.choice([rng.randint(1, 99), rng.choice([5, 10, 15, 20, 25, 30, 50, 75, 90])])
    autre_parle, autre_ecrit = "%s percent" % dicte(mot(n)), "%d%%" % n
    return par2(rng, PORTEUSES_HEURE_NUE_PCT, (parle, autre_parle), (ecrit, autre_ecrit))


def gen_heure(rng):
    forme = rng.choices(["hm_ampm", "h_ampm", "o_clock", "half_past", "quarter_to",
                        "quarter_past", "h24", "nue"],
                       weights=[22, 15, 13, 10, 10, 10, 20, 25])[0]
    if forme == "nue":
        return gen_heure_nue(rng)
    if forme == "h24":
        h = rng.randint(13, 23)
        mm = rng.choice([0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, rng.randint(1, 59)])
        mn_mot = "hundred" if mm == 0 else minute_mot(mm)
        parle, ecrit = "%s %s" % (dicte(mot(h)), mn_mot), "%d:%02d" % (h, mm)
        return par(rng, PORTEUSES_HEURE, parle, ecrit)

    h = rng.randint(1, 12)
    if forme == "hm_ampm":
        mm = rng.choice([5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, rng.randint(1, 59)])
        ampm, ampm_mot = choix_ampm(rng)
        parle = "%s %s %s" % (dicte(mot(h)), minute_mot(mm), ampm_mot)
        ecrit = "%d:%02d%s" % (h, mm, ampm)
    elif forme == "h_ampm":
        ampm, ampm_mot = choix_ampm(rng)
        parle, ecrit = "%s %s" % (dicte(mot(h)), ampm_mot), "%d%s" % (h, ampm)
    elif forme == "o_clock":
        parle, ecrit = "%s o'clock" % dicte(mot(h)), "%d:00" % h
    elif forme == "half_past":
        parle, ecrit = "half past %s" % dicte(mot(h)), "%d:30" % h
    elif forme == "quarter_to":
        h_prev = 12 if h == 1 else h - 1
        parle, ecrit = "quarter to %s" % dicte(mot(h)), "%d:45" % h_prev
    else:
        parle, ecrit = "quarter past %s" % dicte(mot(h)), "%d:15" % h
    return par(rng, PORTEUSES_HEURE, parle, ecrit)


def gen_pourcent(rng):
    if rng.random() < 0.15:
        intpart, dec = rng.randint(0, 99), rng.randint(1, 9)
        parle = "%s point %s percent" % (dicte(mot(intpart)), dicte(mot(dec)))
        ecrit = "%d.%d%%" % (intpart, dec)
    else:
        n = rng.choice([rng.randint(1, 99), rng.choice([5, 10, 15, 20, 25, 30, 50, 75, 90])])
        parle, ecrit = "%s percent" % dicte(mot(n)), "%d%%" % n
    return par(rng, PORTEUSES_PCT, parle, ecrit)


DIGIT_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]


def dire_chiffres(chiffres, oh_premier=False):
    """"double trois" / "oh" sont dictes : cf. spec_en. Le premier chiffre
    d'un mobile britannique (le 0 initial) se dit toujours "oh", pas "zero"."""
    mots, i, n, premier = [], 0, len(chiffres), True
    while i < n:
        d = chiffres[i]
        j = i
        while j + 1 < n and chiffres[j + 1] == d:
            j += 1
        run = j - i + 1
        w = "oh" if (premier and oh_premier and d == 0) else DIGIT_WORDS[d]
        mots.append(("triple %s" if run >= 3 else "double %s" if run == 2 else "%s") % w)
        i, premier = j + 1, False
    return " ".join(mots)


def tirer_chiffres(rng, n):
    """Tire n chiffres en forcant des repetitions adjacentes ("double
    trois", "triple deux") plus souvent qu'un tirage uniforme ne le ferait --
    trou releve : "double"/"triple" etaient trop rares a l'entrainement pour
    que le modele apprenne fiablement a les redecouper en chiffres."""
    out = []
    while len(out) < n:
        d = rng.randint(0, 9)
        r = rng.random()
        if r < 0.15 and len(out) + 3 <= n:
            out += [d, d, d]
        elif r < 0.45 and len(out) + 2 <= n:
            out += [d, d]
        else:
            out.append(d)
    return out[:n]


def gen_telephone(rng):
    if rng.random() < 0.5:
        # Royaume-Uni : "0" + 4 chiffres, espace, 6 chiffres -> "07912 345678".
        reste = tirer_chiffres(rng, 10)
        parle = dire_chiffres([0] + reste, oh_premier=True)
        ecrit = "0%d%d%d%d %d%d%d%d%d%d" % tuple(reste)
    else:
        # Etats-Unis : NNN-NNN-NNNN.
        chiffres = [rng.randint(1, 9)] + tirer_chiffres(rng, 9)
        parle = dire_chiffres(chiffres)
        ecrit = "%d%d%d-%d%d%d-%d%d%d%d" % tuple(chiffres)
    return par(rng, PORTEUSES_TEL, parle, ecrit)


FIRST_NAMES = ["alex", "john", "sarah", "emma", "james", "olivia", "liam", "sophie",
               "noah", "grace", "daniel", "chloe", "ryan", "megan"]
LAST_NAMES = ["smith", "johnson", "brown", "taylor", "clark", "walker", "hughes",
              "murray", "bennett", "coleman"]
DOMAINS = [("gmail", "com"), ("outlook", "com"), ("yahoo", "com"), ("gobudgie", "com"),
           ("budgie", "app"), ("hotmail", "co.uk"), ("example", "co.uk"), ("company", "org")]


def gen_email(rng):
    p, n = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
    dom, tld = rng.choice(DOMAINS)
    sep_mot, sep_ecrit = rng.choice([("dot", "."), ("dash", "-"), ("underscore", "_"), ("", "")])
    local_parle = "%s %s %s" % (p, sep_mot, n) if sep_mot else "%s%s" % (p, n)
    local_ecrit = "%s%s%s" % (p, sep_ecrit, n)
    tld_parle = " dot ".join(tld.split("."))
    parle = "%s at %s dot %s" % (local_parle, dom, tld_parle)
    ecrit = "%s@%s.%s" % (local_ecrit, dom, tld)
    return par(rng, PORTEUSES_EMAIL, parle, ecrit)


# ── Contre-exemples : ce qui ne doit PAS bouger ──────────────────────────────

def valeur_dejachiffree(rng):
    """Une valeur DEJA ecrite en chiffres, telle qu'un ASR l'ecrirait -- sans
    virgule de milliers ajoutee : c'est precisement ce que le modele ne doit
    pas "corriger"."""
    genre = rng.choice(["entier", "argent", "heure", "pourcent", "annee"])
    if genre == "entier":
        return str(rng.randint(2, 99999))
    if genre == "argent":
        sym = rng.choice(["$", "€", "£"])
        n = rng.randint(1, 99999)
        if rng.random() < 0.3:
            return "%s%d.%02d" % (sym, n, rng.randint(0, 99))
        return "%s%d" % (sym, n)
    if genre == "heure":
        if rng.random() < 0.5:
            h, ampm = rng.randint(1, 12), rng.choice(["am", "pm"])
            if rng.random() < 0.5:
                return "%d%s" % (h, ampm)
            return "%d:%02d%s" % (h, rng.choice([0, 15, 30, 45]), ampm)
        return "%d:%02d" % (rng.randint(0, 23), rng.choice([0, 15, 30, 45]))
    if genre == "pourcent":
        return "%d%%" % rng.randint(1, 99)
    return str(rng.randint(1950, 2035))


def valeur_num_brute(rng):
    """Nombre a 4-7 chiffres deja ecrit tel quel : avec ou sans virgule de
    milliers, choisi au hasard -- les DEUX doivent rester inchanges. Trou
    releve : "we had 2500 people" devenait "2,500 people" ; il manquait des
    exemples de nombres bruts SANS separateur, seuls ou combines a une heure/
    un montant/un pourcentage deja chiffres, dans des phrases ordinaires."""
    n = rng.randint(1000, 9999999)
    return virgule_milliers(n) if rng.random() < 0.5 else str(n)


def valeur_num_brute_45(rng):
    """Nombre a 4 OU 5 chiffres, JAMAIS de virgule -- exactement la forme du
    trou releve ("we had 2500 people at 3pm"). Deuxieme tour de correction :
    le premier tour avait ajoute des cas 4-7 chiffres sans separateur, mais
    ils ne pesaient pas assez face aux 1 451 paires de la famille entier qui
    ajoutent des virgules. Tire a part, avec un poids dedie dans
    gen_deja_chiffres(), pour garantir la part mesuree plutot que l'esperer
    d'un tirage large sur valeur_num_brute()."""
    return str(rng.randint(1000, 99999))


# Trou releve : "we had 2500 people at 3pm and it went well" reste inchange.
# Contextes au plus pres de l'echec -- "<N> people/units/euros" deja chiffre,
# combine a "at 3pm", "at 10am", "on March 3" ou "25%" deja chiffres eux
# aussi. Le principe a faire apprendre : un chiffre deja ecrit ne bouge
# JAMAIS, separateur compris.
PORTEUSES_DEJA_45 = [
    "We had {} people at 3pm and it went well.", "We had {} people at 3pm.",
    "We had {} people at 10am.", "We had {} units at 3pm.",
    "We had {} units at 10am.", "We had {} euros at 3pm.",
    "We had {} euros at 10am.", "There were {} people on March 3.",
    "We shipped {} units on March 3.", "We collected {} euros on March 3.",
    "We had {} people with 25% already checked in.",
    "We shipped {} units with 25% still pending.",
    "We collected {} euros with 25% already spent.",
    "We had {} people and it went well.", "We shipped {} units and it went well.",
]


def gen_deja_chiffres(rng):
    # "brut_45" pese 45 % expres : c'est le genre qui garantit la part
    # mesuree de nombres a 4-5 chiffres SANS separateur (>= 40 % vise pour la
    # famille) -- le reste de la combinatoire (brut_seul va jusqu'a 7
    # chiffres, 50 % avec virgule) n'y contribue qu'a la marge.
    genre = rng.choices(["simple", "brut_seul", "brut_45", "brut_heure", "brut_montant",
                        "brut_pourcent"], weights=[18, 15, 45, 8, 7, 7])[0]
    if genre == "simple":
        val = valeur_dejachiffree(rng)
        return par(rng, TOUTES_PORTEUSES, val, val)
    if genre == "brut_seul":
        val = valeur_num_brute(rng)
        return par(rng, PORTEUSES_DEJA_SEUL, val, val)
    if genre == "brut_45":
        val = valeur_num_brute_45(rng)
        return par(rng, PORTEUSES_DEJA_45, val, val)
    n = valeur_num_brute(rng)
    if genre == "brut_heure":
        h, ampm = rng.randint(1, 12), rng.choice(["am", "pm"])
        autre, porteuses = "%d%s" % (h, ampm), PORTEUSES_DEJA_COMBO_HEURE
    elif genre == "brut_montant":
        sym = rng.choice(["$", "€", "£"])
        autre, porteuses = "%s%d" % (sym, rng.randint(1, 99999)), PORTEUSES_DEJA_COMBO_MONT
    else:
        autre, porteuses = "%d%%" % rng.randint(1, 99), PORTEUSES_DEJA_COMBO_PCT
    return par2(rng, porteuses, (n, autre), (n, autre))


def gen_sans_nombre(rng):
    """Aucune conversion possible : la sortie est l'entree, mot pour mot (une
    fois mise en forme). Inclut les decoys "at"/"dot"/"point"/"one" en usage
    ordinaire, et "noon"/"midnight" qui restent des mots -- voir la note en
    tete de fichier sur pourquoi ils vivent ici plutot que dans heure."""
    r = rng.random()
    if r < 0.12:
        s = rng.choice(FIXED_DECOYS)
    elif r < 0.22:
        s = rng.choice(NOON_MIDNIGHT)
    else:
        s = "%s %s %s%s." % (rng.choice(SN_SUJET), rng.choice(SN_VERBE),
                             rng.choice(SN_OBJET),
                             (" " + rng.choice(SN_QUEUE)).rstrip())
    return sale(s), s


FAMILLES = [
    ("entier", gen_entier, 14),
    ("montant", gen_montant, 15),
    ("date", gen_date, 12),
    ("heure", gen_heure, 12),
    ("pourcent", gen_pourcent, 5),
    ("telephone", gen_telephone, 4),
    ("email", gen_email, 3),
    ("deja_chiffres", gen_deja_chiffres, 18),      # contre-exemple
    ("sans_nombre", gen_sans_nombre, 17),          # contre-exemple
]
CONTRE = {"deja_chiffres", "sans_nombre"}
CONTROL = "[Styling: semi-formal] [Structure: prose] [Context: general] [Lang: en]"
PLANCHER = 200


def main():
    n_total = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(SP, "pairs_itn_en.jsonl")
    rng = random.Random(SEED)
    noms = [f[0] for f in FAMILLES]
    poids = [f[2] for f in FAMILLES]
    fns = {f[0]: f[1] for f in FAMILLES}

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
        # sur ~20 % des entrees, qui doit disparaitre dans la sortie.
        if rng.random() < 0.20:
            dirty = rng.choice(HESITATIONS) + dirty
        stats[fam] += 1
        rows.append({"id": "itn-en-%05d" % len(rows), "file": "itn-%s" % fam,
                     "source": "itn", "lang": "en", "held_out": False,
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

    n = len(rows)
    contre_n = sum(stats[f] for f in noms if f in CONTRE)
    print("paires ITN anglais : %d  (%d tentatives, %d doublons ecartes)"
          % (n, tries, tries - n))
    print("%-16s %6s %6s" % ("famille", "n", "%"))
    sous = []
    for fam, _, _ in FAMILLES:
        marque = "   <- contre-exemple" if fam in CONTRE else ""
        print("%-16s %6d %5.1f%%%s" % (fam, stats[fam], 100.0 * stats[fam] / max(1, n), marque))
        if stats[fam] < PLANCHER:
            sous.append(fam)
    print("\ncontre-exemples : %d (%.1f %%)" % (contre_n, 100.0 * contre_n / max(1, n)))
    print("tenues a l'ecart : %d" % sum(1 for r in rows if r["held_out"]))
    print("-> %s" % out)
    if sous:
        print("\nATTENTION : famille(s) sous le plancher de %d -- elargir les "
              "gabarits ou le vocabulaire : %s" % (PLANCHER, ", ".join(sous)))
    print()
    print("=== echantillon ===")
    for r in rng.sample(rows, 8):
        print("  [%-13s] %s" % (r["file"][4:], r["dirty"]))
        print("  %-16s %s" % ("", r["clean"]))
    return 1 if sous else 0


if __name__ == "__main__":
    sys.exit(main())
