# -*- coding: utf-8 -*-
"""Compositions ITN, en ANGLAIS — jumeau de gen_compo.py pour SCRIBE_LANG=en.

LE TROU QUE CE FICHIER BOUCHE
Meme constat qu'en francais (voir gen_compo.py) : aucun generateur anglais
n'existe encore, donc aucun ne produit deux expressions numeriques dans la
meme phrase. Sans ce fichier, le modele anglais apprendrait « un nombre par
sortie » et fusionnerait le reste :

    "at nine for three hundred dollars" -> "at 9:03" au lieu de
                                            "at 9:00 for $300"

Un fichier separe, pas un `if lang` dans gen_compo.py : les deux langues
n'ont ni le meme alphabet numerique (heures 12h vs 24h, "and" dans les
montants, ordre jour/mois qui NE SE REORDONNE JAMAIS), ni le meme lexique de
gabarits. spec_en.py ITN_RULES fait foi sur chaque forme ci-dessous ; le
francais n'est pas touche par ce fichier.

Usage : gen_compo_en.py [n] [sortie.jsonl]
"""
import collections, json, os, random, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd
SEED = 20260905
CONTROL = "[Styling: semi-formal] [Structure: prose] [Context: general] [Lang: en]"
HESITATIONS = ["um ", "uh ", "well ", "so um ", "erm ", "", "", ""]

from num2words import num2words

JOURS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MOIS = ["january", "february", "march", "april", "may", "june", "july",
        "august", "september", "october", "november", "december"]
PRENOMS = ["Sarah", "John", "Michael", "Emma", "David", "Laura", "James",
           "Olivia", "Daniel", "Sophie", "Ryan", "Grace", "Ethan", "Chloe"]
OBJETS = ["the quote", "the invoice", "the contract", "the order",
          "the report", "the deposit", "the deal", "the shipment"]
DOMAINES = ["google", "github", "gobudgie", "anthropic", "microsoft",
            "openai", "amazon"]


def dicte(s):
    """La forme dictee de num2words porte des virgules et des tirets qu'aucun
    locuteur ne prononce : « twenty-three thousand, four hundred and fifty ».
    On les retire, on garde « and » — lui, il se dit."""
    return s.replace(",", "").replace("-", " ")


def mot(n):
    return dicte(num2words(n, lang="en"))


def mot_ordinal(n):
    """« third », « twenty first »… — sert aux dates : le jour se dicte en
    ordinal, jamais en cardinal (« march third », pas « march three »)."""
    return dicte(num2words(n, to="ordinal", lang="en"))


def esp(n):
    """Separateur de milliers anglo-saxon, la virgule : « 23,450 »."""
    return "{:,}".format(n)


def annee_dicte(a):
    """Une annee se dicte par groupes de deux chiffres : 2026 -> « twenty
    twenty six ». Comme en francais, mais la coupure est fixe a la centaine,
    jamais un nombre entier d'un bloc."""
    return "%s %s" % (mot(a // 100), mot(a % 100))


# ── Fragments : (dicte, ecrit). Aucune phrase porteuse ici — c'est justement
#    ce qui manque pour pouvoir les COMBINER dans le meme gabarit.
MOT_MINUTE = {5: "five", 10: "ten", 20: "twenty", 25: "twenty five"}


def f_heure(rng):
    """Formes relatives : « quarter »/« half » (1 seul tirage par appel,
    fragment complet) plus « five/ten/twenty/twenty five past/to » — memes
    conventions (heure suivante dictee pour « to », heure courante ecrite).
    Enrichi le 2026-09-05 : deux heures relatives adjacentes dans une meme
    phrase (« half past two and quarter to five ») n'existaient dans aucun
    gabarit, et le modele les fusionnait plutot que de les garder distinctes.
    Enrichi a nouveau le 2026-09-05 (trou A) : une heure NUE dictee seule
    apres « at/around/by » (« nine ») s'ecrit en chiffres SANS deux-points ni
    symbole (« 9 ») — meme convention que gen_itn_en.py. Sans cette forme,
    une heure nue suivie d'un montant se faisait happer le symbole monetaire
    par le modele (« at nine for three hundred dollars » -> « at $9 for
    $300 »)."""
    forme = rng.choices(
        ["oclock", "half", "quart_apres", "quart_avant", "rel_apres",
         "rel_avant", "ampm", "h24", "nue"],
        weights=[8, 14, 12, 12, 14, 14, 16, 10, 18])[0]
    if forme == "nue":
        h = rng.randint(1, 12)
        return mot(h), str(h)
    if forme == "oclock":
        h = rng.randint(1, 12)
        return "%s o'clock" % mot(h), "%d:00" % h
    if forme == "half":
        h = rng.randint(1, 12)
        return "half past %s" % mot(h), "%d:30" % h
    if forme == "quart_apres":
        h = rng.randint(1, 12)
        return "quarter past %s" % mot(h), "%d:15" % h
    if forme == "quart_avant":
        h = rng.randint(1, 12)
        nh = h + 1 if h < 12 else 1
        return "quarter to %s" % mot(nh), "%d:45" % h
    if forme == "rel_apres":
        h = rng.randint(1, 12)
        mn = rng.choice([5, 10, 20, 25])
        return "%s past %s" % (MOT_MINUTE[mn], mot(h)), "%d:%02d" % (h, mn)
    if forme == "rel_avant":
        h = rng.randint(1, 12)
        mn = rng.choice([5, 10, 20, 25])
        nh = h + 1 if h < 12 else 1
        return "%s to %s" % (MOT_MINUTE[mn], mot(nh)), "%d:%02d" % (h, 60 - mn)
    if forme == "ampm":
        h = rng.randint(1, 12)
        mn = rng.choice([0, 5, 10, 15, 20, 30, 40, 45, 50])
        suf = rng.choice(["a m", "p m"])
        suf_ecrit = suf.replace(" ", "")
        if mn == 0:
            return "%s %s" % (mot(h), suf), "%d%s" % (h, suf_ecrit)
        return "%s %s %s" % (mot(h), mot(mn), suf), "%d:%02d%s" % (h, mn, suf_ecrit)
    # 24h : « fourteen thirty » -> « 14:30 ». Pas de forme a zero minute ici,
    # ITN_RULES n'atteste que la forme composee, pas « fourteen hundred ».
    h = rng.randint(13, 23)
    mn = rng.choice([15, 30, 45])
    return "%s %s" % (mot(h), mot(mn)), "%d:%02d" % (h, mn)


def f_montant(rng):
    n = rng.choice([50, 80, 120, 150, 250, 300, 450, 800, 1200, 2500, 4800,
                    12000, 23450, 35000])
    dev = rng.choices(["dollars", "euros", "pounds"], weights=[5, 3, 2])[0]
    sym = {"dollars": "$", "euros": "€", "pounds": "£"}[dev]
    if rng.random() < 0.25:
        cents = rng.choice([25, 50, 75])
        return "%s %s %s" % (mot(n), dev, mot(cents)), \
               "%s%s.%02d" % (sym, esp(n), cents)
    # « twelve hundred dollars » plutot que « one thousand two hundred » :
    # c'est la forme que num2words ne produit JAMAIS et que tout anglophone
    # dicte. Elle existait dans gen_itn_en, seule dans sa phrase ; le modele
    # sortait alors « 1,200 dollars on March 3 » des qu'une date la suivait —
    # le symbole se perdait a l'adjacence, exactement comme l'heure nue prenait
    # un « $ » de son voisin. Mesure sur scribe-en-v4, cas r6.
    if 1100 <= n <= 9900 and n % 100 == 0 and rng.random() < 0.55:
        return "%s hundred %s" % (mot(n // 100), dev), "%s%s" % (sym, esp(n))
    return "%s %s" % (mot(n), dev), "%s%s" % (sym, esp(n))


def f_date(rng):
    """Deux ordres, jamais reordonnes — ITN_RULES le repete deux fois :
    « march third » -> « March 3 » (ordre americain, mois d'abord),
    « the third of march » -> « 3 March » (ordre europeen, jour d'abord)."""
    j = rng.randint(1, 28)
    idx = rng.randint(0, 11)
    m_dit, m_ecrit = MOIS[idx], MOIS[idx].capitalize()
    jo = mot_ordinal(j)
    avec_annee = rng.random() < 0.5
    a = rng.randint(2024, 2027)
    if rng.random() < 0.5:
        dit, ecrit = "%s %s" % (m_dit, jo), "%s %d" % (m_ecrit, j)
        if avec_annee:
            dit += " %s" % annee_dicte(a)
            ecrit += ", %d" % a
    else:
        dit, ecrit = "the %s of %s" % (jo, m_dit), "%d %s" % (j, m_ecrit)
        if avec_annee:
            dit += " %s" % annee_dicte(a)
            ecrit += " %d" % a
    return dit, ecrit


def f_pourcent(rng):
    n = rng.choice([5, 10, 15, 20, 25, 30, 40, 50, 60, 75])
    return "%s percent" % mot(n), "%d%%" % n


def f_entier(rng):
    if rng.random() < 0.3:
        n = rng.choice([200, 300, 400, 500, 600, 700, 800, 900, 1100, 1200,
                         1300, 1500, 1800])
        return "%s hundred" % mot(n // 100), esp(n)
    n = rng.randint(2, 60)
    return mot(n), str(n)


DEJA_VALEURS = [1200, 1500, 2500, 3300, 4200, 8000, 15000, 27000]


def f_deja(rng):
    """Trou B : un nombre DEJA ecrit en chiffres cote dicte — pas une forme
    parlee a convertir. ITN_RULES le dit deux fois : « What is ALREADY in
    digits stays as it is ». Dans une composition, ce qui est dicte se
    convertit ; ce qui est deja en chiffres ne bouge pas, separateur compris.
    Renvoie (s, s) — la MEME chaine des deux cotes — parfois avec la virgule
    de milliers deja posee (« 2,500 »), parfois sans (« 2500 »)."""
    n = rng.choice(DEJA_VALEURS)
    s = esp(n) if rng.random() < 0.3 else str(n)
    return s, s


def f_email(rng):
    u = rng.choice(["contact", "support", "sales", "info", "hello", "admin"])
    d = rng.choice(DOMAINES)
    t = rng.choice(["com", "org", "net"])
    return "%s at %s dot %s" % (u, d, t), "%s@%s.%s" % (u, d, t)


def f_url(rng):
    d = rng.choice(DOMAINES)
    t = rng.choice(["com", "org", "net"])
    tirage = rng.random()
    if tirage < 0.3:
        page = rng.choice(["docs", "support", "pricing", "blog", "help"])
        return "%s dot %s slash %s" % (d, t, page), "%s.%s/%s" % (d, t, page)
    if tirage < 0.5:
        return "double u double u double u dot %s dot %s" % (d, t), \
               "www.%s.%s" % (d, t)
    return "%s dot %s" % (d, t), "%s.%s" % (d, t)


def f_tel(rng):
    """Deux conventions, comme le corpus les distingue : le Royaume-Uni
    dicte son zero initial « oh » (« oh seven nine one two... »), les
    Etats-Unis dictent chiffre par chiffre sans « oh » particulier."""
    if rng.random() < 0.5:
        chiffres = [0, rng.choice([7, 8])] + [rng.randint(0, 9) for _ in range(9)]
        dit = " ".join("oh" if d == 0 else mot(d) for d in chiffres)
        ecrit = "%d%d%d%d%d %d%d%d%d%d%d" % tuple(chiffres)
        return dit, ecrit
    chiffres = [5, 5, 5] + [rng.randint(0, 9) for _ in range(7)]
    dit = " ".join("zero" if d == 0 else mot(d) for d in chiffres)
    ecrit = "%d%d%d-%d%d%d-%d%d%d%d" % tuple(chiffres)
    return dit, ecrit


# ── Gabarits. Chaque %s consomme UN fragment, dans l'ordre donne. ───────────
GABARITS_2 = [
    ("the meeting is at %s and the quote is %s",
     "The meeting is at %s and the quote is %s.", (f_heure, f_montant)),
    ("{O} of %s is due on %s", "{O} of %s is due on %s.", (f_montant, f_date)),
    ("meet me on %s at %s", "Meet me on %s at %s.", (f_date, f_heure)),
    ("we need to settle %s before %s", "We need to settle %s before %s.",
     (f_montant, f_date)),
    ("call me on %s before %s", "Call me on %s before %s.", (f_tel, f_heure)),
    ("we get %s off on %s", "We get %s off on %s.", (f_pourcent, f_montant)),
    ("send {O} to %s before %s", "Send {O} to %s before %s.", (f_email, f_date)),
    ("there were %s of us and it cost %s", "There were %s of us and it cost %s.",
     (f_entier, f_montant)),
    ("{P} lands at %s on %s", "{P} lands at %s on %s.", (f_heure, f_date)),
    ("the quote went from %s to %s", "The quote went from %s to %s.",
     (f_montant, f_montant)),
    ("everything's on %s, reply before %s", "Everything's on %s, reply before %s.",
     (f_url, f_date)),
    ("{P} billed %s for %s hours", "{P} billed %s for %s hours.",
     (f_montant, f_entier)),
    # Deux heures dans la meme phrase, au moins une relative la plupart du
    # temps (poids f_heure ci-dessus) : c'est le trou du 2026-09-05, deux
    # tirages DISTINCTS de f_heure, chacun sa propre chaine des deux cotes.
    ("between %s and %s works for the call", "Between %s and %s works for the call.",
     (f_heure, f_heure)),
    ("from %s to %s is fine with me", "From %s to %s is fine with me.",
     (f_heure, f_heure)),
    ("%s and %s both work for me", "%s and %s both work for me.",
     (f_heure, f_heure)),
    ("either at %s or at %s", "Either at %s or at %s.", (f_heure, f_heure)),
    ("the call runs from %s until %s", "The call runs from %s until %s.",
     (f_heure, f_heure)),
    ("we could meet at %s or push it to %s",
     "We could meet at %s or push it to %s.", (f_heure, f_heure)),
    ("{P} suggested either %s or %s", "{P} suggested either %s or %s.",
     (f_heure, f_heure)),
    # Trou A (2026-09-05) : heure NUE immediatement devant un montant, un
    # pourcentage ou un entier — c'est l'adjacence qui faisait inventer un
    # symbole monetaire sur l'heure (voir f_heure, forme "nue").
    ("the meeting is at %s for %s", "The meeting is at %s for %s.",
     (f_heure, f_montant)),
    ("we start at %s with %s people", "We start at %s with %s people.",
     (f_heure, f_entier)),
    ("be there by %s it's %s a head", "Be there by %s, it's %s a head.",
     (f_heure, f_montant)),
    ("call around %s about %s off", "Call around %s about %s off.",
     (f_heure, f_pourcent)),
    # Trou B (2026-09-05) : un nombre DEJA en chiffres (f_deja) a cote d'une
    # expression dictee dans la meme phrase — l'un se convertit, l'autre ne
    # bouge pas, separateur compris (voir f_deja).
    ("we had %s people at %s", "We had %s people at %s.",
     (f_deja, f_heure)),
    ("%s units for %s", "%s units for %s.", (f_deja, f_montant)),
    ("the %s attendees paid %s", "The %s attendees paid %s.",
     (f_deja, f_montant)),
    ("%s guests got %s off", "%s guests got %s off.", (f_deja, f_pourcent)),
]
GABARITS_3 = [
    ("on %s at %s we're signing for %s", "On %s at %s, we're signing for %s.",
     (f_date, f_heure, f_montant)),
    ("meet me on %s at %s with %s people",
     "Meet me on %s at %s with %s people.", (f_date, f_heure, f_entier)),
    ("%s off on %s, valid until %s", "%s off on %s, valid until %s.",
     (f_pourcent, f_montant, f_date)),
    ("call %s before %s for {O} of %s", "Call %s before %s for {O} of %s.",
     (f_tel, f_heure, f_montant)),
    ("send to %s on %s the amount of %s", "Send to %s on %s the amount of %s.",
     (f_email, f_date, f_montant)),
    ("we're at %s of the budget which is %s as of %s",
     "We're at %s of the budget which is %s as of %s.",
     (f_pourcent, f_montant, f_date)),
    ("on %s we're free from %s to %s", "On %s we're free from %s to %s.",
     (f_date, f_heure, f_heure)),
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
PLANCHER = 200


def main():
    n_total = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(SP, "pairs_compo_en.jsonl")
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
        if rng.random() < 0.20:
            h = rng.choice(HESITATIONS)
            if h:
                d = h + d
        stats[fam] += 1
        rows.append({"id": "cmp-en-%05d" % len(rows), "file": "cmp-%s" % fam,
                     "source": "compo", "lang": "en", "held_out": False,
                     "styling": "semi-formal", "structure": "prose",
                     "context": "general", "control": CONTROL,
                     "dirty": d, "clean": c})

    # 8 % tenus a l'ecart PAR FAMILLE, comme en francais.
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
    print("compositions ITN anglais : %d  (%d tentatives, %d doublons ecartes)"
          % (n, tries, tries - n))
    sous = []
    for fam, _, _ in FAMILLES:
        print("  %-10s %6d  %5.1f %%" % (fam, stats[fam], 100.0 * stats[fam] / max(1, n)))
        if stats[fam] < PLANCHER:
            sous.append(fam)
    # compo3 est la SEULE famille dont les trois fragments viennent de trois
    # f_* distincts a chaque tirage (voir GABARITS_3) : son taux EST le taux
    # de sorties a 3 expressions numeriques distinctes ou plus.
    print("  3+ familles distinctes : %d  (%5.1f %%)"
          % (stats["compo3"], 100.0 * stats["compo3"] / max(1, n)))
    print("  tenues a l'ecart : %d" % sum(1 for r in rows if r["held_out"]))
    print("-> %s" % out)
    if sous:
        print("\nATTENTION : famille(s) sous le plancher de %d — elargir les "
              "gabarits ou le vocabulaire : %s" % (PLANCHER, ", ".join(sous)))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
