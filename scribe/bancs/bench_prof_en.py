# -*- coding: utf-8 -*-
"""Banc du PROFESSEUR ANGLAIS — deux candidats locaux, double arbitrage, zero
appel payant.

POURQUOI UN BANC SEPARE DE bench_prof.py
`bench_prof.py` a tranche gemma-12b-qat contre DeepSeek EN FRANCAIS (notes d'entrainement
§0.21). Ce resultat ne se transpose pas : la spec anglaise est un fichier a
part (`spec_en.py`), le corpus sale vient d'un autre moteur (Cohere, ITN
desactivee), et la decision d'Alex pour l'anglais est differente au depart —
zero appel payant, DEUX candidats locaux (`gemma-12b-qat` et `gemma-31b-qat`),
et un DOUBLE arbitrage plutot qu'un arbitre unique.

DEUX PIEGES DEJA CONNUS DU BANC FRANCAIS (§0.21), A NE PAS REPRODUIRE ICI
  1. L'arbitre ne doit JAMAIS etre un des deux candidats : un modele qui juge
     sa propre production se prefere. `arbitrer` prend donc un <arbitre> qui
     doit etre un TROISIEME modele (ex. qwen3.8-27b, gemma-26b-a4b-qat) — rien
     dans le code ne l'empeche de valoir gemma-12b-qat ou gemma-31b-qat, mais
     rien ne l'exige non plus : c'est un choix d'operateur, documente ici.
     Le "double arbitrage" voulu par Alex consiste a lancer `arbitrer` deux
     fois, avec deux arbitres differents, et a les croiser dans `synthese`.
  2. Le confond de spec sur les nombres : un modele qui convertit correctement
     "six mois" en "6 mois" n'invente pas une valeur, il applique l'ITN. Pour
     l'A/B, le probleme est pire qu'en francais : deux professeurs peuvent
     rendre le MEME nombre dicte de deux formes egalement correctes ("3:15pm"
     contre "15:15" n'existe pas ici, mais "March 3, 2026" contre "3 March
     2026" existe bel et bien — l'ordre dicte, pas une regle universelle,
     cf. spec_en.py). Plutot que d'apprendre a l'arbitre cette subtilite,
     `arbitrer` ELIMINE purement et simplement tout cas dont l'entree porte un
     nombre, en lettres ou en chiffres (voir `contient_nombre`).

TROIS SOUS-COMMANDES, CHACUNE IDEMPOTENTE
  enseigner   ecrit prof_en_<candidat>.jsonl ; relit les ids deja presents et
              ne relance que ce qui manque.
  arbitrer    ecrit ab_prof_en_<arbitre>.jsonl ; meme reprise sur (id, miroir).
  synthese    ne fait AUCUN appel reseau — elle relit ce que les deux
              commandes precedentes ont deja ecrit. C'est le mode qui permet
              de tester toute la logique deterministe sans serveur.

LE MIROIR, PARCE QU'UN SEUL TIRAGE A/B NE PROUVE RIEN
Poser le cas UNE fois avec un ordre A/B tire au sort mesure une preference,
pas une coherence : un arbitre qui prefererait toujours "la colonne A" gagnerait
la moitie du temps par hasard de tirage. On pose donc CHAQUE cas retenu DEUX
fois, avec les colonnes exactement inversees la seconde fois. Un arbitre
coherent doit alors rendre un verdict de lettre DIFFERENTE (A la premiere
fois, B la seconde, ou l'inverse) puisque le meme modele change de colonne :
c'est la seule facon de "trancher" un cas. Une lettre identique aux deux
poses trahit un biais de position et compte comme instable — assimile a une
egalite, jamais a une victoire (voir `trancher`).

Usage :
  bench_prof_en.py enseigner <candidat> <entrees.jsonl> [n=120] [port=8899]
  bench_prof_en.py arbitrer <arbitre> [port=8899]
  bench_prof_en.py synthese
"""
import collections, glob, json, math, os, queue, random, re, sys, threading, time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd
import spec_en                 # deja sur sys.path via chemins ; NE PAS passer par chemins.spec()

# `valeurs()` et `controle()` sont RECOPIEES depuis bench_prof.py, pas
# importees : ce sont deux fonctions de pure regex, indifferentes a la
# langue, mais bench_prof.py les fait suivre d'un `from valider_paires import
# mots, racine, HESITATIONS, NOMBRES_MOTS, SYNONYMES` AU NIVEAU MODULE — donc
# importer bench_prof.py pour ces deux fonctions importerait aussi toute la
# mecanique francaise de valider_paires.py, et ferait echouer bench_prof_en.py
# a chaque fois que cette mecanique bouge (verifie en direct : valider_paires.py
# est en cours de reecriture bilingue pendant l'ecriture de ce banc, et
# bench_prof.py ne s'importe plus tel quel pour l'instant). Deux fonctions de
# quelques lignes, sans etat, valent mieux qu'un import fragile.
NUM = re.compile(r"\d[\d  ]*(?:,\d+)?")


def valeurs(s):
    """Valeurs numeriques, espaces de milliers retires."""
    out = []
    for m in NUM.finditer(s):
        v = m.group(0).replace(" ", "").replace(" ", "").rstrip(",")
        if v:
            out.append(v)
    return collections.Counter(out)


def controle(r):
    """Les trois axes de la ligne de consigne, tels qu'ils sont dans la paire."""
    m = dict(re.findall(r"\[(\w+): ([\w-]+)\]", r["control"]))
    return (m.get("Styling", "semi-formal"), m.get("Structure", "prose"),
            m.get("Context", "general"))

CANDIDATS = ("gemma-12b-qat", "gemma-31b-qat")
WORKERS = int(os.environ.get("PROF_WORKERS", "4"))    # llama-server n'ouvre que 4 slots
SEED_AB = 20260905      # ordre A/B de l'arbitrage — impose par le brief, ne pas changer


# ---------------------------------------------------------------------------
# Serveur : le coordinateur charge/decharge les modeles entre les phases.
# Ce script n'en lance aucun ; il verifie seulement que celui qui repond est
# bien celui qu'on croit, et echoue fort sinon.
# ---------------------------------------------------------------------------

def verifie_serveur(alias, port):
    """Echoue fort si /v1/models ne repond pas ou ne porte pas `alias`.

    Le champ `model` d'une requete de chat est IGNORE par llama-server (voir
    llm.py, llamacpp_ok()) : une variable d'environnement perimee, ou un
    mauvais modele charge, ne ferait jamais echouer l'appel de chat lui-meme.
    Le seul endroit qui dit la verite est /v1/models — comme juge.ps1 le
    verifie avec Get-ModeleCharge.
    """
    url = "http://127.0.0.1:%d/v1/models" % port
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.load(r)
    except Exception as e:
        raise SystemExit(
            "aucun serveur sur le port %d (%s) -- "
            ".\\scripts\\juge.ps1 demarrer -Modele %s" % (port, type(e).__name__, alias))
    charges = [os.path.basename(m.get("id", "")) for m in (data.get("data") or [])]
    if alias not in charges:
        raise SystemExit(
            "le serveur du port %d porte %r, pas %r attendu -- "
            ".\\scripts\\juge.ps1 demarrer -Modele %s"
            % (port, charges, alias, alias))


def _appelle(url, corps, essais=3, timeout=240):
    data = json.dumps(corps).encode("utf-8")     # le corps part en octets UTF-8
    for k in range(essais):
        try:
            req = urllib.request.Request(url, data=data,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception:
            if k == essais - 1:
                return None
            time.sleep(1.5 * (k + 1))


def appelle_prof(modele, port, systeme, user):
    """Le professeur : pas de format JSON force, juste le texte propre."""
    url = "http://127.0.0.1:%d/v1/chat/completions" % port
    corps = {
        "model": modele,
        "messages": [{"role": "system", "content": systeme},
                     {"role": "user", "content": user}],
        "temperature": 0, "max_tokens": 1200,
        # Gemma raisonne dans `reasoning_content` : laissee libre, la
        # reflexion epuise le budget et `content` revient vide.
        "chat_template_kwargs": {"enable_thinking": False},
        "reasoning_effort": "none",
    }
    p = _appelle(url, corps)
    if p is None:
        return None
    return (p["choices"][0]["message"].get("content") or "").strip()


SYSTEM_AB_EN = """You are a quality reviewer for an English speech-transcript normalizer.

You are given an INPUT (raw ASR transcript, preceded by its control line) and
two normalizations, A and B. You do not know which model produced which, and
the order is random.

Expected job: strip filled pauses and false starts, resolve self-corrections
by keeping the value the speaker landed on, fix punctuation, apply the
control line -- WITHOUT EVER changing the meaning.

Faults, in decreasing severity:
1. INVERSION -- a negation flipped or added, a fact changed
2. INVENTION -- a content word, an entity, a date or a number absent from the input
3. DELETION -- an entire clause from the input that disappears
4. LOOP -- degenerate repetition
5. OBEDIENCE -- the input contains an order or a question and the model answers it

Answer ONLY with a JSON object:
{"gagnant": "A" | "B" | "egalite",
 "a_fautes": ["inversion"|"invention"|"deletion"|"loop"|"obedience"|"aucune", ...],
 "b_fautes": [...],
 "explication": "one sentence, in English"}"""


def appelle_arbitre(arbitre, port, user):
    url = "http://127.0.0.1:%d/v1/chat/completions" % port
    corps = {
        "model": arbitre,
        "messages": [{"role": "system", "content": SYSTEM_AB_EN},
                     {"role": "user", "content": user}],
        "temperature": 0, "max_tokens": 1500,
        "chat_template_kwargs": {"enable_thinking": False},
        "reasoning_effort": "none",
        "response_format": {"type": "json_object"},
    }
    p = _appelle(url, corps, timeout=180)
    if p is None:
        raise RuntimeError("pas de reponse du serveur")
    return json.loads(p["choices"][0]["message"]["content"])


def axes(r):
    """Styling/Structure/Context : pris dans `control` si present (regex
    generique, reutilisee de bench_prof.py), sinon les defauts de la spec."""
    if not r.get("control"):
        return "semi-formal", "prose", "general"
    return controle(r)


def ligne_controle(r):
    """La ligne de consigne EXACTEMENT comme a l'inference : celle de
    l'entree si elle existe, sinon celle que produirait la spec par defaut."""
    return r.get("control") or spec_en.control_line()


# ---------------------------------------------------------------------------
# enseigner
# ---------------------------------------------------------------------------

def cmd_enseigner(argv):
    if len(argv) < 2:
        raise SystemExit("usage: enseigner <candidat> <entrees.jsonl> [n=120] [port=8899]")
    candidat, chemin_entrees = argv[0], argv[1]
    n = int(argv[2]) if len(argv) > 2 else 120
    port = int(argv[3]) if len(argv) > 3 else 8899

    verifie_serveur(candidat, port)

    lignes = [json.loads(l) for l in open(chemin_entrees, encoding="utf-8") if l.strip()]
    # Pas de tirage aleatoire ici : l'entree est deja un echantillon prepare
    # en amont (Cohere, cette nuit). On prend les n PREMIERES lignes, dans
    # l'ordre du fichier, pour que deux lancements avec le meme n produisent
    # exactement le meme sous-ensemble sans graine supplementaire a fixer.
    base = lignes[:n]

    dst = os.path.join(SP, "prof_en_%s.jsonl" % candidat.replace("/", "_").replace(":", "_"))
    deja = set()
    if os.path.exists(dst):
        for l in open(dst, encoding="utf-8"):
            if l.strip():
                deja.add(json.loads(l)["id"])
    reste = [r for r in base if r["id"] not in deja]
    print("=== enseigner %s -- %d entrees, %d deja faites, %d restantes ==="
          % (candidat, len(base), len(deja), len(reste)), flush=True)
    if not reste:
        print("rien a faire -- %s est deja complet" % dst)
        return

    q = queue.Queue()
    for r in reste:
        q.put(r)
    lock = threading.Lock()
    f = open(dst, "a", encoding="utf-8")
    compte = [0]
    erreurs = [0]

    def worker():
        while True:
            try:
                r = q.get_nowait()
            except queue.Empty:
                return
            styling, structure, context = axes(r)
            systeme = spec_en.teacher_prompt(styling, structure, context)
            ligne = ligne_controle(r)
            t0 = time.time()
            got = appelle_prof(candidat, port, systeme, "%s\n%s" % (ligne, r["dirty"]))
            dt = time.time() - t0
            with lock:
                if got is None:
                    erreurs[0] += 1
                else:
                    f.write(json.dumps({"id": r["id"], "dirty": r["dirty"],
                                        "control": ligne, "clean": got,
                                        "secondes": round(dt, 2)},
                                       ensure_ascii=False) + "\n")
                    f.flush()
                compte[0] += 1
                if compte[0] % 30 == 0:
                    print("   %d/%d" % (compte[0], len(reste)), flush=True)

    t0 = time.time()
    ts = [threading.Thread(target=worker, daemon=True) for _ in range(WORKERS)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    f.close()
    print("  duree %.1f min, %d erreurs reseau" % ((time.time() - t0) / 60, erreurs[0]))
    print("-> %s" % dst)


# ---------------------------------------------------------------------------
# arbitrer — le detecteur de mots-nombres, et le miroir
# ---------------------------------------------------------------------------

# Releve exactement le perimetre du brief : zero..ninety, hundred/thousand/
# million/billion, les ordinaux first..thirtieth (un ordinal compose comme
# "thirty-first" se decoupe en "thirty" + "first", deja couverts separement —
# inutile de lister les composes), et les fractions de dictee "half"/"quarter".
_CARDINAUX = ("zero one two three four five six seven eight nine ten eleven "
              "twelve thirteen fourteen fifteen sixteen seventeen eighteen "
              "nineteen twenty thirty forty fifty sixty seventy eighty ninety").split()
_ECHELLES = "hundred thousand million billion".split()
_ORDINAUX = ("first second third fourth fifth sixth seventh eighth ninth tenth "
             "eleventh twelfth thirteenth fourteenth fifteenth sixteenth "
             "seventeenth eighteenth nineteenth twentieth thirtieth").split()
_FRACTIONS = "half quarter".split()
NOMBRES_MOTS_EN = set(_CARDINAUX) | set(_ECHELLES) | set(_ORDINAUX) | set(_FRACTIONS)


def contient_nombre(s):
    """Un mot-nombre anglais est-il present, en lettres, dans `s` ?

    Volontairement LARGE : "one" est un mot-nombre, donc "one of us" EST
    detecte comme portant un nombre, meme si ce n'en est pas un a la lecture
    humaine. Choix assume (brief) — on prefere exclure trop de cas de l'A/B
    plutot que d'en laisser passer un qui confond la regle de conversion
    testee avec une erreur du modele (piege §0.21 : « six mois » -> « 6 mois »
    compte comme faute a tort si on ne fait pas ce genre de choix large).
    Les traits d'union sont remplaces par des espaces AVANT tokenisation :
    "twenty-third" redevient "twenty" + "third", deja dans la table — inutile
    de lister les composes.
    """
    tokens = re.findall(r"[a-z]+", s.lower().replace("-", " "))
    return bool(set(tokens) & NOMBRES_MOTS_EN)


def cmd_arbitrer(argv):
    if not argv:
        raise SystemExit("usage: arbitrer <arbitre> [port=8899]")
    arbitre = argv[0]
    port = int(argv[1]) if len(argv) > 1 else 8899

    verifie_serveur(arbitre, port)

    def charge(candidat):
        p = os.path.join(SP, "prof_en_%s.jsonl" % candidat)
        if not os.path.exists(p):
            raise SystemExit("absent : %s -- lancer d'abord 'enseigner %s ...'" % (p, candidat))
        return {json.loads(l)["id"]: json.loads(l)
                for l in open(p, encoding="utf-8") if l.strip()}

    c12, c31 = charge(CANDIDATS[0]), charge(CANDIDATS[1])
    communs = sorted(set(c12) & set(c31))
    sans_nombre = [i for i in communs if not contient_nombre(c12[i]["dirty"])]
    print("=== arbitre %s -- %d cas communs, %d retenus (sans nombre) ==="
          % (arbitre, len(communs), len(sans_nombre)), flush=True)

    rng = random.Random(SEED_AB)
    jobs = []
    for i in sans_nombre:
        swap = rng.random() < 0.5
        entree = c12[i]["control"] + "\n" + c12[i]["dirty"]
        # miroir1 : qui est en A depend du tirage. miroir2 : EXACTEMENT
        # l'inverse — le meme modele change de colonne.
        a1, b1 = (CANDIDATS[1], CANDIDATS[0]) if swap else (CANDIDATS[0], CANDIDATS[1])
        a2, b2 = b1, a1
        jobs.append((i, "miroir1", entree, a1, b1))
        jobs.append((i, "miroir2", entree, a2, b2))

    def texte(modele, i):
        return (c12 if modele == CANDIDATS[0] else c31)[i]["clean"]

    dst = os.path.join(SP, "ab_prof_en_%s.jsonl" % arbitre.replace("/", "_").replace(":", "_"))
    deja = set()
    if os.path.exists(dst):
        for l in open(dst, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                deja.add((r["id"], r["miroir"]))

    a_faire = [j for j in jobs if (j[0], j[1]) not in deja]
    print("   %d/%d poses restantes (deja %d)" % (len(a_faire), len(jobs), len(jobs) - len(a_faire)))
    if not a_faire:
        print("rien a faire -- %s est deja complet" % dst)
        return

    q = queue.Queue()
    for j in a_faire:
        q.put(j)
    lock = threading.Lock()
    f = open(dst, "a", encoding="utf-8")
    compte = [0]

    def worker():
        while True:
            try:
                i, miroir, entree, ma, mb = q.get_nowait()
            except queue.Empty:
                return
            a, b = texte(ma, i), texte(mb, i)
            try:
                v = appelle_arbitre(arbitre, port,
                                    "ENTREE:\n%s\n\nA:\n%s\n\nB:\n%s" % (entree, a, b))
            except Exception as e:
                v = {"erreur": str(e)[:150]}
            v.update({"id": i, "miroir": miroir, "modele_a": ma, "modele_b": mb})
            with lock:
                f.write(json.dumps(v, ensure_ascii=False) + "\n")
                f.flush()
                compte[0] += 1
                if compte[0] % 20 == 0:
                    print("   %d/%d" % (compte[0], len(a_faire)), flush=True)

    ts = [threading.Thread(target=worker, daemon=True) for _ in range(WORKERS)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    f.close()
    print("-> %s" % dst)


# ---------------------------------------------------------------------------
# synthese — aucun appel reseau, tout est relu depuis les fichiers deja ecrits
# ---------------------------------------------------------------------------

# Tables anglaises. Reecrites ici plutot qu'importees de valider_paires.py,
# qui est cablee sur le francais de bout en bout (accents, mots-outils
# francais, nombres francais) : rien n'y est reutilisable pour l'anglais.

# Hesitations SANS AMBIGUITE seulement : "like" et "you know" sont parfois des
# hesitations (spec_en CORE_RULES) mais aussi des mots de sens plein ("I like
# it", "you know the answer") — les exclure ferait rater des inventions
# reelles. On se limite aux marqueurs qui ne sont jamais autre chose.
HESITATIONS_EN = set("um uh er erm hmm mm mhm uhh umm".split())

# Mots-outils anglais : ce que `mots_en()` retire pour ne garder que le
# contenu, et le denominateur du test de langue plus bas. Les formes contractees
# (« i'm », « don't »...) restent des tokens entiers apres tokenisation — voir
# `mots_en` — donc elles doivent figurer ici explicitement, sans quoi une
# contraction serait comptee comme un mot de contenu invente.
OUTILS_EN = set("""
a an the and or but if then else nor so yet
with without to of in on at by for from as into onto upon
is are was were be been being am do does did doing done
have has had having will would can could should shall may might must
not no this that these those it its i you he she we they me him her us them
my your his its our their mine yours hers ours theirs
who whom whose which what where when why how
i'm i've i'll i'd you're you've you'll you'd he's he'll he'd she's she'll she'd
it's we're we've we'll we'd they're they've they'll they'd
isn't aren't wasn't weren't haven't hasn't hadn't don't doesn't didn't
won't wouldn't can't cannot couldn't shouldn't mustn't
that's there's here's what's who's let's
""".split())

# Substitutions de REGISTRE volontaires (STYLING_RULES semi-formal) :
# "gonna" -> "going to" etc. Le professeur remplace un mot familier par une
# forme standard ; ce n'est pas une invention. La table est mono-mot ->
# mono-mot (comme SYNONYMES en francais) alors que la cible reelle est une
# locution ("going to") : on ne verifie donc que le premier mot de contenu de
# la locution, ce qui suffit a couvrir le cas sans faire une vraie
# reecriture multi-mots ici.
SYNONYMES_EN = {"gonna": "going", "wanna": "want", "kinda": "kind", "yeah": "yes"}

NEG_EN = re.compile(r"\b(not|no|never|none|nothing|nobody|neither|nor|cannot)\b|n't", re.I)

# Marqueurs de bascule HORS anglais. Volontairement grossiers (des mots-outils
# tres frequents, pas une vraie detection de langue) : le but est de repérer
# un dérapage massif, pas de mesurer un taux de code-switching legitime.
FR_OUTILS = re.compile(r"\b(le|la|les|de|des|du|un|une|est|et|que|qui|pour|avec|"
                       r"dans|sur|pas|ne|vous|nous|ils|elle|c'est|je|il)\b", re.I)
ES_OUTILS = re.compile(r"\b(el|la|los|las|de|que|y|en|un|una|es|para|con|por|"
                       r"no|se|usted|nosotros)\b", re.I)
DE_OUTILS = re.compile(r"\b(der|die|das|und|ist|nicht|mit|für|ein|eine|zu|von|"
                       r"auf|sie|ich|wir|sind)\b", re.I)
EN_MARQUEURS = re.compile(r"\b(the|and|with|this|that|from|have|will|would|"
                          r"about|because|there|which|is|are|was|were)\b", re.I)


_SUFFIXE_ORDINAL = re.compile(r"(?<=\d)(st|nd|rd|th)\b", re.I)


def mots_en(s):
    """Mots de CONTENU en minuscules, mots-outils exclus.

    L'apostrophe typographique (U+2019) est normalisee EN PREMIER, avant
    toute tokenisation — meme piege qu'en francais (valider_paires.mots) :
    un professeur qui ecrit « don't » avec l'apostrophe typographique et une
    entree ASR en apostrophe ASCII produiraient deux tokens differents pour
    le meme mot, et une invention serait comptee a tort.

    Le suffixe ordinal colle a un chiffre (« 15th », « 3rd ») est retire AVANT
    la tokenisation : sinon la regex `[a-z']+`, qui ignore les chiffres, en
    extrait « th » ou « rd » comme un mot a part entiere — un mot invente qui
    n'existe pas, calibre sur un cas reel de ce banc (« the 15th » -> « th »).
    """
    s = _SUFFIXE_ORDINAL.sub("", s.lower().replace("’", "'").replace("ʼ", "'"))
    bruts = re.findall(r"[a-z']+", s)
    return [m.strip("'") for m in bruts
            if m.strip("'") and m.strip("'") not in OUTILS_EN and len(m.strip("'")) > 1]


def racine_en(m):
    """Radical grossier : suffixes s/es/ed/ing, comme demande par le brief.

    Pas de gestion des irregularites (« ran » vs « run », consonne doublee de
    « running ») : la France utilise le meme niveau de rusticite (accords
    seulement), et le but est d'attraper l'accord/la conjugaison reguliere,
    pas de faire un vrai lemmatiseur.
    """
    for suf in ("ing", "ed", "es", "s"):
        if m.endswith(suf) and len(m) - len(suf) >= 3:
            return m[:-len(suf)]
    return m


def invariants(rows):
    c = collections.Counter()
    fautes = collections.defaultdict(list)
    for r in rows:
        c["n"] += 1
        d, g = r["dirty"], r.get("clean") or ""
        if not d.strip():
            continue

        contenu_d = mots_en(d)
        if not g.strip() and len(contenu_d) >= 5:
            c["vide"] += 1
            fautes["vide"].append(r["id"])
            continue

        # VALEURS — reutilise valeurs() de bench_prof.py (pure regex sur les
        # chiffres, indifferente a la langue). Un chiffre de sortie n'est
        # legitime que si l'entree porte un chiffre OU un mot-nombre : sinon
        # c'est une invention, la faute la plus grave (piege §0.21).
        vd, vg = valeurs(d), valeurs(g)
        dicte_en_mots = bool(set(contenu_d) & NOMBRES_MOTS_EN)
        if (vg - vd) and not dicte_en_mots:
            c["valeur_inventee"] += 1
            fautes["valeur_inventee"].append((r["id"], sorted((vg - vd).elements())[:3]))

        # INVENTION lexicale
        md, mg = set(contenu_d), set(mots_en(g))
        rd = {racine_en(x) for x in md}
        inv = {x for x in (mg - md) - HESITATIONS_EN - NOMBRES_MOTS_EN
               if racine_en(x) not in rd and SYNONYMES_EN.get(x) not in md}
        if inv:
            c["invention"] += 1
            fautes["invention"].append((r["id"], sorted(inv)[:4]))

        # AMPUTATION — un professeur qui resume est disqualifie
        if d.split() and len(g.split()) < 0.6 * len(d.split()):
            c["amputation"] += 1
            fautes["amputation"].append((r["id"], "%d -> %d mots"
                                         % (len(d.split()), len(g.split()))))

        # POLARITE
        nd, ng = len(NEG_EN.findall(d)), len(NEG_EN.findall(g))
        if abs(nd - ng) > max(1, 0.4 * nd):
            c["polarite"] += 1
            fautes["polarite"].append(r["id"])

        # LANGUE — la sortie doit rester en anglais
        etranger = (len(FR_OUTILS.findall(g)) + len(ES_OUTILS.findall(g))
                    + len(DE_OUTILS.findall(g)))
        anglais = len(EN_MARQUEURS.findall(g))
        if g.strip() and etranger > anglais + 2:
            c["langue"] += 1
            fautes["langue"].append(r["id"])

        # OBEISSANCE — heuristique de bench_prof.py, non specifique au francais
        if "?" in d and len(g.split()) > 1.6 * len(d.split()):
            c["obeissance_possible"] += 1

        c["ok"] += 1 if not ((vg - vd) and not dicte_en_mots) and not inv else 0

    return c, fautes


def imprime_invariants(candidat, c, fautes):
    n_ = max(1, c["n"])
    print("\n  --- %s ---" % candidat)
    print("  entrees mesurees        %5d" % c["n"])
    for cle, libelle in (
        ("valeur_inventee", "VALEUR inventee   <-- la faute grave"),
        ("invention", "invention lexicale"),
        ("amputation", "amputation (<60% des mots)"),
        ("polarite", "polarite de negation"),
        ("langue", "bascule hors anglais"),
        ("vide", "sortie vide a tort"),
    ):
        print("  %-32s %4d  %5.1f %%" % (libelle, c[cle], 100.0 * c[cle] / n_))
    print("  %-32s %4d  %5.1f %%" % ("obeissance possible (info)",
                                     c["obeissance_possible"], 100.0 * c["obeissance_possible"] / n_))
    print("  %-32s %4d  %5.1f %%" % ("sans aucune faute grave", c["ok"], 100.0 * c["ok"] / n_))
    for cle in ("valeur_inventee", "invention", "amputation", "polarite", "langue", "vide"):
        if fautes[cle]:
            print("    exemples %s :" % cle)
            for x in fautes[cle][:2]:
                print("      %s" % (x,))


def trancher(r1, r2):
    """Un cas n'est TRANCHE que si les deux poses (colonnes inversees) se
    contredisent en LETTRE : le meme modele a change de colonne, donc un
    arbitre coherent doit rendre une lettre differente. Une lettre identique
    dans les deux poses trahit un biais de position, pas une preference de
    contenu : « instable », compte comme egalite — jamais comme victoire."""
    if not r1 or not r2 or "gagnant" not in r1 or "gagnant" not in r2:
        return "instable"
    g1, g2 = r1["gagnant"], r2["gagnant"]
    if g1 not in ("A", "B") or g2 not in ("A", "B"):
        return "egalite" if g1 == "egalite" and g2 == "egalite" else "instable"
    if g1 == g2:
        return "instable"
    m1 = r1["modele_a"] if g1 == "A" else r1["modele_b"]
    m2 = r2["modele_a"] if g2 == "A" else r2["modele_b"]
    return m1 if m1 == m2 else "instable"


def qualifie(candidat, resultats, v12c, v31c, z):
    stats = resultats.get(candidat)
    if not stats:
        return False
    n_ = max(1, stats["n"])
    if stats["valeur_inventee"] != 0:
        return False
    if 100.0 * stats["amputation"] / n_ >= 2.0:
        return False
    if stats["polarite"] != 0:
        return False
    if z is not None and abs(z) >= 1.96:
        favori = CANDIDATS[0] if v12c > v31c else CANDIDATS[1]
        if favori != candidat:
            return False
    return True


def recommande(resultats, v12c, v31c, z):
    for candidat in CANDIDATS:
        if qualifie(candidat, resultats, v12c, v31c, z):
            return candidat
    return "aucun"


def cmd_synthese(argv):
    resultats = {}
    for candidat in CANDIDATS:
        p = os.path.join(SP, "prof_en_%s.jsonl" % candidat)
        if not os.path.exists(p):
            print("absent : %s -- 'enseigner %s ...' d'abord" % (p, candidat))
            continue
        rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
        c, fautes = invariants(rows)
        resultats[candidat] = c
        imprime_invariants(candidat, c, fautes)

    ab_paths = sorted(glob.glob(os.path.join(SP, "ab_prof_en_*.jsonl")))
    ab_stats = {}
    par_id = collections.defaultdict(dict)      # id -> {arbitre: gagnant|"egalite"|"instable"}
    for path in ab_paths:
        arbitre = os.path.basename(path)[len("ab_prof_en_"):-len(".jsonl")]
        rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
        par_paire = collections.defaultdict(dict)
        for r in rows:
            par_paire[r["id"]][r.get("miroir")] = r
        v = collections.Counter()
        for i, m in par_paire.items():
            g = trancher(m.get("miroir1"), m.get("miroir2"))
            v[g] += 1
            par_id[i][arbitre] = g
        ab_stats[arbitre] = {"cas": len(par_paire),
                             "victoires_%s" % CANDIDATS[0]: v[CANDIDATS[0]],
                             "victoires_%s" % CANDIDATS[1]: v[CANDIDATS[1]],
                             "egalites": v["egalite"], "instables": v["instable"]}
        print("\n  --- arbitre %s ---" % arbitre)
        print("    cas juges            %4d" % len(par_paire))
        print("    victoires %-16s %4d" % (CANDIDATS[0], v[CANDIDATS[0]]))
        print("    victoires %-16s %4d" % (CANDIDATS[1], v[CANDIDATS[1]]))
        print("    egalites             %4d" % v["egalite"])
        print("    instables            %4d  (comptees comme egalite)" % v["instable"])

    # Cas CONCORDANTS : tous les arbitres qui ont pu trancher ce cas
    # tranchent le MEME gagnant. Un desaccord entre arbitres n'est ni une
    # victoire ni une egalite : il est exclu du z, qui mesurerait sinon le
    # bruit du juge plutot que l'ecart entre les deux professeurs.
    v12c = v31c = desaccords = 0
    for i, verdicts in par_id.items():
        gagnants = {v for v in verdicts.values() if v in CANDIDATS}
        if len(verdicts) < 2:
            continue
        if len(gagnants) == 1:
            g = next(iter(gagnants))
            if g == CANDIDATS[0]:
                v12c += 1
            else:
                v31c += 1
        elif len(gagnants) > 1:
            desaccords += 1

    z = (v12c - v31c) / math.sqrt(v12c + v31c) if (v12c + v31c) else None
    print("\n  --- cas CONCORDANTS entre arbitres ---")
    print("    victoires %-16s %4d" % (CANDIDATS[0], v12c))
    print("    victoires %-16s %4d" % (CANDIDATS[1], v31c))
    print("    desaccords entre arbitres (exclus) %4d" % desaccords)
    if z is None:
        print("    z indefini -- aucun cas concordant tranche")
    else:
        sig = "SIGNIFICATIF" if abs(z) >= 1.96 else "non significatif"
        print("    z = (v12b - v31b) / sqrt(v12b + v31b) = %.2f  -- %s (seuil 1.96, "
              "bruit du juge ~16%% -- §0.17)" % (z, sig))

    reco = recommande(resultats, v12c, v31c, z)
    print("\n  RECOMMANDATION : %s" % reco)

    dst = os.path.join(SP, "prof_en_synthese.json")
    json.dump({
        "invariants": {k: dict(v) for k, v in resultats.items()},
        "ab": ab_stats,
        "concordant": {"victoires_%s" % CANDIDATS[0]: v12c,
                       "victoires_%s" % CANDIDATS[1]: v31c,
                       "desaccords": desaccords, "z": z},
        "recommandation": reco,
    }, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("-> %s" % dst)


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    cmd, argv = sys.argv[1], sys.argv[2:]
    if cmd == "enseigner":
        cmd_enseigner(argv)
    elif cmd == "arbitrer":
        cmd_arbitrer(argv)
    elif cmd == "synthese":
        cmd_synthese(argv)
    else:
        raise SystemExit("commande inconnue : %r -- enseigner | arbitrer | synthese" % cmd)


if __name__ == "__main__":
    main()
