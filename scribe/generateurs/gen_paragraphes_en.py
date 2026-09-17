# -*- coding: utf-8 -*-
"""Paragraphes — apprendre a couper une dictee longue, et a NE PAS la couper.

LE TROU, RELEVE PAR ALEX LE 2026-09-06
Une dictee de plusieurs minutes ressortait en un seul bloc. La cause est
mecanique, comme les cinq precedentes : AUCUNE paire d'entrainement ne portait
de saut de paragraphe. Les paires synthetiques sont des phrases isolees ; les
unites reelles font 40 mots de mediane et sortent du decoupage en une seule
coulee. Ce que le modele ne voit jamais, il ne le produit jamais — sixieme
occurrence dans ce projet, et la seule qui portait sur la FORME du document
plutot que sur le contenu d'une phrase.

La regle est ecrite dans spec_en.STRUCTURE_RULES["prose"] ; ce fichier la
MONTRE. Les listes restent derriere `[Structure: lists]`, decision d'Alex :
le produit enverra `prose` presque toujours, et `prose` doit rendre du texte
propre — donc des paragraphes.

DEUX FAMILLES, ET LA SECONDE COMPTE AUTANT QUE LA PREMIERE

  sujets       2 a 4 unites de DISCOURS DIFFERENTS, collees bout a bout du
               cote sale (avec parfois une transition parlee), separees par
               une LIGNE VIDE du cote propre.
  meme_sujet   contre-exemple : ce qui ne doit PAS etre coupe. Deux formes,
               parce que le risque a deux faces :
                 - une unite LONGUE a sujet unique (>= 45 mots) : couper sur
                   la longueur est precisement la faute a eviter ;
                 - 2 ou 3 unites CONSECUTIVES d'un meme discours : le sujet
                   continue, la ligne vide n'a rien a faire la.

LA COMBINATOIRE, PAS LE POIDS (lecon du 2026-09-03, quatrieme rappel)
Le corpus ne porte que 138 fenetres d'unites consecutives : `voxpopuli.py` a
DEJA recolle les enonces voisins en unites de 35-100 mots, donc deux unites
consecutives d'un meme discours sont rares par construction. La famille
contre-exemple serait restee sous le plancher de 200 avec cette seule forme.
L'unite longue seule la complete — et c'est la forme la plus proche du risque
reel, pas un bouche-trou.

AUCUNE FUITE : une paire tenue a l'ecart est construite EXCLUSIVEMENT a partir
d'unites elles-memes tenues a l'ecart. Melanger les deux pools mettrait du
contenu d'evaluation dans l'entrainement par la bande — le piege de §0.13,
qui se referme ici d'une facon inedite puisqu'une paire porte plusieurs
unites.

Usage : gen_paragraphes_en.py [n] [sortie.jsonl]
"""
import collections, json, os, random, re, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd
SEED = 20260906
CONTROL = "[Styling: semi-formal] [Structure: prose] [Context: general] [Lang: en]"
SOURCE = os.path.join(SP, "pairs_vox_en.jsonl")
MAX_MOTS = 260                 # au-dela, on retire une unite
LONG_MIN = 35                  # une unite « longue », pour le contre-exemple
PLANCHER = 200

# Transitions PURES : des marqueurs de discours, qui disparaissent comme une
# hesitation. Elles signalent le changement de sujet sans rien affirmer.
TRANSITIONS_PURES = ["okay", "okay so", "um so", "right so", "so", "alright",
                     "um", "uh so", "well so"]

# Transitions PORTEUSES : elles restent, en tete du nouveau paragraphe, parce
# qu'elles portent du sens (« aussi », « ensuite »). La forme ecrite est
# imposee ici, pas devinee par le modele.
TRANSITIONS_PORTEUSES = {
    "also": "Also,",
    "another thing": "Another thing:",
    "anyway": "Anyway,",
    "oh and": "And",
    "next thing": "Next,",
    "moving on": "Moving on,",
    "one more thing": "One more thing:",
    "and then": "Then,",
}


def _mots(s):
    return len(s.split())


# UN COTE SALE SANS PONCTUATION, PARCE QUE C'EST UN REGIME REEL
# Cohere tourne avec `punctuation: true`, donc le cote sale du corpus est
# ponctue et capitalise. Le modele apprenait alors a couper AUX POINTS deja
# presents, et non a entendre un changement de sujet : sur une dictee brute
# sans ponctuation (Cohere ponctuation coupee, ou un autre moteur), il rendait
# un seul bloc. Mesure sur scribe-en-v4, cas « 15-paragraphes » : trois sujets
# fondus en un. On montre donc les DEUX regimes.
# La virgule des MILLIERS est preservee (« 1,200 » ne devient pas « 1200 ») :
# c'est un chiffre, pas une ponctuation, et valider_paires compte les chiffres.
def _sans_ponctuation(s):
    # UNIQUEMENT la ponctuation de FIN DE PHRASE : un signe suivi d'une espace
    # ou d'une fin de chaine. Retirer tous les points aveuglement transformait
    # « i.e. » en « ie », un mot de contenu apparu de nulle part que
    # valider_paires signalait a juste titre — et aurait casse « 3:15pm » et
    # « github.com » de la meme facon. Un ASR sans ponctuation n'invente pas
    # « ie » non plus : il ecrit les abreviations telles qu'il les entend.
    s = re.sub(r"[.?!;:,](?=\s|$)", "", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def _minuscule_debut(s):
    """La transition porteuse prend la tete du paragraphe : la phrase qui
    suivait perd sa majuscule SAUF si son premier mot est un nom propre ou
    « I ». Test grossier mais sur : un mot entierement minuscule apres
    abaissement n'etait pas un nom propre s'il figure dans la liste des mots
    ordinaires les plus frequents. On ne prend donc AUCUN risque — on
    n'abaisse que les mots-outils les plus courants."""
    ORDINAIRES = {"the", "we", "they", "it", "this", "that", "there", "you",
                  "he", "she", "our", "my", "his", "her", "their", "a", "an",
                  "in", "on", "for", "about", "as", "at", "if", "when", "what",
                  "and", "but", "so", "one", "two", "three", "all", "some"}
    premier = s.split(" ", 1)[0]
    if premier.lower().strip(",.") in ORDINAIRES:
        return premier[0].lower() + s[1:]
    return s


def charger():
    """Les unites reelles utilisables : semi-formal / prose / general.

    Les autres portent des listes ou une mise en page d'e-mail du cote propre ;
    les coller bout a bout produirait un document dont la structure ne suit
    plus la ligne de controle."""
    rows = [json.loads(l) for l in open(SOURCE, encoding="utf-8")]
    return [r for r in rows
            if r.get("styling") == "semi-formal"
            and r.get("structure") == "prose"
            and r.get("context") == "general"
            and r.get("clean", "").strip() and r.get("dirty", "").strip()]


def sans_perte(u):
    """L'unite perd-elle un mot de contenu, ou un chiffre, entre le sale et le
    propre ?

    Le professeur reecrit legitimement (registre, negation restituee), mais la
    famille contre-exemple exige que RIEN ne disparaisse : valider_paires.py
    le verifie sur la paire ASSEMBLEE, donc on ecarte en amont les unites qui
    le feraient echouer. On reutilise ses propres fonctions plutot que d'en
    reecrire une variante qui deriverait.

    Le decompte de CHIFFRES compte autant que les mots : quatre unites du
    corpus voyaient le professeur ecrire « 2006 » la ou le sale portait
    « 2000 6 », ou perdre un numero d'article. Sur une famille qui promet de
    ne rien changer, c'est eliminatoire."""
    from valider_paires import TABLES, _mots as vmots, _racine, chiffres
    T = TABLES["en"]
    md, mc = set(vmots(u["dirty"], T["outils"])), set(vmots(u["clean"], T["outils"]))
    rc = {_racine(x, T["suffixes"]) for x in mc}
    perdus = {x for x in (md - mc) - T["hesitations"] - T["nombres_mots"]
              if _racine(x, T["suffixes"]) not in rc
              and T["synonymes"].get(x) not in mc}
    if perdus:
        return False
    # meme regle que valider_paires : le decompte ne vaut que si l'entree ne
    # dicte aucun nombre en lettres, sinon l'ITN cree legitimement un chiffre.
    if not (set(vmots(u["dirty"], T["outils"])) & T["nombres_mots"]):
        return chiffres(u["dirty"]) == chiffres(u["clean"])
    return True


def discours(units):
    """Les unites groupees par DISCOURS (`<session>_<horodatage>`), triees par
    rang. Deux unites du meme groupe sont deux tranches consecutives d'une
    meme prise de parole : meme locuteur, meme sujet."""
    g = collections.defaultdict(list)
    for u in units:
        g[u["id"].rsplit("#", 1)[0]].append(u)
    for k in g:
        g[k].sort(key=lambda r: int(r["id"].rsplit("#", 1)[1]))
    return g


def gen_sujets(rng, pool_par_session):
    """2 a 4 unites de SESSIONS differentes -> autant de paragraphes."""
    sessions = rng.sample(list(pool_par_session), rng.choice([2, 2, 3, 3, 4]))
    unites = [rng.choice(pool_par_session[s]) for s in sessions]
    while len(unites) > 2 and sum(_mots(u["dirty"]) for u in unites) > MAX_MOTS:
        unites.pop()
    sales, propres = [unites[0]["dirty"]], [unites[0]["clean"]]
    for u in unites[1:]:
        t = rng.random()
        if t < 0.30:                                   # transition pure
            m = rng.choice(TRANSITIONS_PURES)
            sales.append(m + " " + u["dirty"][0].lower() + u["dirty"][1:])
            propres.append(u["clean"])
        elif t < 0.60:                                 # transition porteuse
            m = rng.choice(list(TRANSITIONS_PORTEUSES))
            sales.append(m + " " + u["dirty"][0].lower() + u["dirty"][1:])
            propres.append("%s %s" % (TRANSITIONS_PORTEUSES[m],
                                      _minuscule_debut(u["clean"])))
        else:                                          # aucune transition
            sales.append(u["dirty"])
            propres.append(u["clean"])
    return " ".join(sales), "\n\n".join(propres)


def gen_meme_sujet(rng, longues, fenetres):
    """Ce qui ne doit PAS etre coupe : une unite longue, ou deux tranches
    consecutives d'un meme discours. Un seul paragraphe des deux cotes."""
    if fenetres and rng.random() < 0.55:
        f = rng.choice(fenetres)
        return " ".join(u["dirty"] for u in f), " ".join(u["clean"] for u in f)
    u = rng.choice(longues)
    return u["dirty"], u["clean"]


FAMILLES = [("sujets", 65), ("meme_sujet", 35)]
CONTRE = {"meme_sujet"}


def _fenetres(g):
    """Fenetres de 2 et 3 unites REELLEMENT consecutives (rangs qui se
    suivent) : un trou de rang veut dire qu'une unite a ete rejetee par le QC
    entre les deux, donc du contenu manque et la continuite n'est plus sure."""
    out = []
    for v in g.values():
        rangs = [int(u["id"].rsplit("#", 1)[1]) for u in v]
        for n in (2, 3):
            for i in range(len(v) - n + 1):
                if rangs[i + n - 1] - rangs[i] == n - 1 and \
                        sum(_mots(x["dirty"]) for x in v[i:i + n]) <= MAX_MOTS:
                    out.append(v[i:i + n])
    return out


def _pools(units):
    par_session = collections.defaultdict(list)
    for u in units:
        par_session[u["file"]].append(u)
    g = discours(units)
    longues = [u for u in units if _mots(u["dirty"]) >= LONG_MIN]
    return dict(par_session), _fenetres(g), longues


def main():
    n_total = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(SP, "pairs_paragraphes_en.jsonl")
    rng = random.Random(SEED)

    toutes = charger()
    propres = [u for u in toutes if sans_perte(u)]
    ecartees = len(toutes) - len(propres)

    # Deux mondes etanches : une paire tenue a l'ecart ne voit que des unites
    # tenues a l'ecart. C'est la seule facon de garder le jeu d'evaluation
    # honnete quand une paire porte plusieurs unites.
    mondes = {
        False: _pools([u for u in propres if not u.get("held_out")]),
        True: _pools([u for u in propres if u.get("held_out")]),
    }

    rows, seen, stats = [], set(), collections.Counter()

    def produire(fam, tenu, part):
        """Tire jusqu'a `part` paires distinctes, ou jusqu'a epuisement de la
        combinatoire. Rend le nombre reellement produit."""
        par_session, fenetres, longues = mondes[tenu]
        if fam == "sujets" and len(par_session) < 2:
            return 0
        if fam == "meme_sujet" and not (fenetres or longues):
            return 0
        essais, faits = 0, 0
        while faits < part and essais < max(400, part * 120):
            essais += 1
            d, c = (gen_sujets(rng, par_session) if fam == "sujets"
                    else gen_meme_sujet(rng, longues, fenetres))
            if rng.random() < 0.40:
                d = _sans_ponctuation(d)
            if d in seen:
                continue
            seen.add(d)
            faits += 1
            stats[fam] += 1
            rows.append({"id": "par-en-%05d" % len(rows), "file": "par-%s" % fam,
                         "source": "paragraphes", "lang": "en", "held_out": tenu,
                         "styling": "semi-formal", "structure": "prose",
                         "context": "general", "control": CONTROL,
                         "dirty": d, "clean": c})
        return faits

    # LE CONTRE-EXEMPLE D'ABORD, ET C'EST LUI QUI FIXE LA TAILLE DU JEU.
    # `meme_sujet` est plafonne par la combinatoire du corpus (138 fenetres
    # consecutives, quelques centaines d'unites longues) ; `sujets` ne l'est
    # pas du tout — 411 sessions se combinent librement. Demander 65/35 en
    # poids donnerait donc 82/18 en sortie, et un contre-exemple famelique
    # est exactement ce que §0.19 a appris a ne pas faire. On produit le
    # contre-exemple jusqu'a epuisement, puis on cale l'autre famille sur lui.
    part_contre = dict(FAMILLES)["meme_sujet"]
    part_regle = dict(FAMILLES)["sujets"]
    obtenu = {}
    for tenu in (False, True):
        cible = int(n_total * part_contre / 100.0)
        part = int(cible * 0.08) if tenu else cible - int(cible * 0.08)
        obtenu[tenu] = produire("meme_sujet", tenu, part)
    for tenu in (False, True):
        produire("sujets", tenu, int(obtenu[tenu] * part_regle / float(part_contre)))

    rng.shuffle(rows)
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    n = max(1, len(rows))
    print("paires de paragraphes : %d  (%d unites reelles, %d ecartees pour perte)"
          % (len(rows), len(propres), ecartees))
    print("%-14s %6s %6s %8s" % ("famille", "n", "%", "held_out"))
    for fam, _ in FAMILLES:
        k = stats[fam]
        h = sum(1 for r in rows if r["file"] == "par-" + fam and r["held_out"])
        marque = "   <- contre-exemple" if fam in CONTRE else ""
        print("%-14s %6d %5.1f%% %8d%s" % (fam, k, 100.0 * k / n, h, marque))
    avec = sum(1 for r in rows if "\n\n" in r["clean"])
    print("\nparagraphes multiples : %d (%.0f %%)  |  bloc unique : %d"
          % (avec, 100.0 * avec / n, len(rows) - avec))
    print("mots par paire (sale) : mediane %d, max %d"
          % (sorted(_mots(r["dirty"]) for r in rows)[len(rows) // 2],
             max(_mots(r["dirty"]) for r in rows)))
    print("tenues a l'ecart : %d" % sum(1 for r in rows if r["held_out"]))
    for fam, _ in FAMILLES:
        if stats[fam] < PLANCHER:
            print("ATTENTION : %s sous le plancher de %d — elargir la matiere"
                  % (fam, PLANCHER))
    print("familles contre-exemple pour valider_paires.py : %s" % " ".join(sorted(CONTRE)))
    print("-> %s" % out)


if __name__ == "__main__":
    main()
