# -*- coding: utf-8 -*-
"""Cote propre, spec du format complete — professeur + filtre de rejet.

Entrees  : cohere_full.jsonl (cote sale) + qc_full.jsonl (verdicts qualite)
Sortie   : pairs_v2.jsonl (paires retenues) + pairs_v2_rejected.jsonl

Deux garde-fous distincts, et il faut les deux :
  - le CONTROLE QUALITE en amont ecarte les transcriptions verolees, pour qu'on
    ne demande jamais au professeur de nettoyer proprement du bruit ;
  - le FILTRE ci-dessous ecarte les sorties ou le professeur a derape.
"""
import json, os, re, sys, time, threading, queue, unicodedata, urllib.request, random, collections

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd

spec = chemins.spec()          # spec_en si SCRIBE_LANG=en, sinon spec — voir chemins.spec()

# Professeur LOCAL par defaut depuis le 2026-09-03. Mesure sur 120 entrees
# propres (bench_prof.py), contre DeepSeek sur les memes :
#   valeurs inventees   0 des deux cotes
#   invention lexicale  20,0 % DeepSeek / 23,3 % gemma
#   amputation          0,8 % / 1,7 %   | polarite, langue, vide : 0 / 0
#   A/B en aveugle      23-17 pour DeepSeek, z = -0,95 NON significatif
# L'arbitre de cet A/B est gemma-31b-qat, indépendant des deux candidats : un
# modele qui juge sa propre production se prefere.
# POC_PROVIDER=deepseek repasse par l'API payante.
PROVIDER = os.environ.get("POC_PROVIDER", "llamacpp")
if PROVIDER == "deepseek":
    API = "https://api.deepseek.com/v1/chat/completions"
    MODEL = os.environ.get("POC_TEACHER", "deepseek-v4-flash")
    KEY = json.load(open(os.path.expanduser("~/.budgie/custom_api_keys.json"),
                         encoding="utf-8"))["deepseek"]
    WORKERS = int(os.environ.get("POC_WORKERS", "12"))
else:
    API = os.environ.get("LLAMACPP_URL", "http://127.0.0.1:8899") + "/v1/chat/completions"
    MODEL = os.environ.get("POC_TEACHER", "gemma-12b-qat")
    KEY = None
    WORKERS = int(os.environ.get("POC_WORKERS", "4"))   # llama-server : 4 slots
SEED = 20260901

# Mots-outils et hesitations, par langue — table choisie par chemins.LANG, EN
# UN SEUL ENDROIT (2026-09-05). Le francais est laisse VERBATIM : c'est
# l'ancienne liste, aucun mot ajoute ni retire, pour que les 300+300 paires de
# reference rendent EXACTEMENT les memes verdicts qu'avant l'anglais.
#
# Elle contenait deja des mots-outils anglais (les trois dernieres lignes du
# bloc « fr » ci-dessous) : c'etait pour ne pas signaler un ilot anglais
# legitime comme mot invente. On les laisse la, on ne les deplace pas.
STOP_FR = set("""le la les un une des du de d au aux a à et ou mais donc or ni car que qui quoi dont où
je tu il elle on nous vous ils elles me te se lui leur y en ce cet cette ces celui celle
mon ton son ma ta sa mes tes ses notre votre nos vos leurs
est sont était étaient sera seront suis es sommes êtes ai as avons avez ont avait avaient
pas ne plus moins très trop bien mal peu tout tous toute toutes même aussi encore déjà
pour par sans sous sur dans avec chez vers entre depuis pendant avant après
si comme quand alors ainsi puis enfin voilà voila
the a an of and or but is are was were to in on at it its this that these those
i you he she we they me him her them my your his our their be been being have has had
do does did not no yes for with from by as so if then than""".split())

# Equivalent anglais (brief 2026-09-05) : mots-outils standard + hesitations
# explicites {um, uh, er, erm, hmm, mm, mhm, like, you know, well, so, okay,
# right}. « you know » n'a pas de contrepartie a un seul mot : ses deux mots
# sont deja des mots-outils (« you » et « know » y sont donc chacun).
STOP_EN = set("""the a an of and or but is are was were to in on at it its this that these those
i you he she we they me him her them my your his our their be been being have has had
do does did not no yes for with from by as so if then than
um uh er erm hmm mm mhm like know well okay right""".split())

STOP = {"fr": STOP_FR, "en": STOP_EN}[chemins.LANG]

WORD = re.compile(r"[0-9]+|[a-zA-ZÀ-ÿ]+(?:['’][a-zA-ZÀ-ÿ]+)*")
NUMWORDS = {"zero":"0","un":"1","une":"1","deux":"2","trois":"3","quatre":"4","cinq":"5",
            "six":"6","sept":"7","huit":"8","neuf":"9","dix":"10","onze":"11","douze":"12",
            "treize":"13","quatorze":"14","quinze":"15","seize":"16","vingt":"20",
            "trente":"30","quarante":"40","cinquante":"50","soixante":"60","cent":"100",
            "cents":"100","mille":"1000"}
DIGIT_TO_WORD = {v: k for k, v in reversed(list(NUMWORDS.items()))}

# Marqueurs de negation, par langue. Le POC (notes d'entrainement §0.14) a produit une
# negation INSEREE — « je sais » devenu « je ne sais » — invisible au controle
# des mots inventes, puisque « ne » et « pas » sont des mots-outils exclus par
# construction. C'est la faute la plus grave de la taxonomie ; elle a besoin de
# son propre compteur.
#
# Le francais a une PARTICULE (« ne »/« n' ») que la negation_delta tolere en
# plus quand elle restaure une elision orale (« sais pas » -> « ne sais pas »).
# L'anglais n'a pas d'equivalent : chaque marqueur — y compris le suffixe
# « n't » de « don't/can't/won't/isn't » — compte pour un negateur plein, la
# table PARTICLES anglaise est donc vide.
NEG_TABLES = {
    "fr": {
        "regex": re.compile(r"\b(ne|n['’]|pas|plus|jamais|rien|aucun[e]?s?|nul[le]*s?|ni|personne)\b",
                            re.IGNORECASE),
        "particles": ("ne", "n'", "n’"),
    },
    "en": {
        # « no » EXCLU quand il introduit une auto-correction (« no wait » —
        # voir spec_en.py CORE_RULES, « friday no wait thursday » -> « Thursday »),
        # sinon compte comme negateur plein partout ailleurs (« no » isole,
        # « no way », etc.). Sans cette exception mesuree sur l'exemple du
        # brief, « no wait » aurait fait declencher une polarite changee sur
        # une paire ou rien n'a change de sens.
        "regex": re.compile(r"\b(not|never|none|nothing|nobody|neither|nor|cannot)\b"
                            r"|n['’]t\b"
                            r"|\bno\b(?!\s*,?\s*wait\b)",
                            re.IGNORECASE),
        "particles": (),
    },
}
NEG = NEG_TABLES[chemins.LANG]["regex"]
NEG_PARTICLES = NEG_TABLES[chemins.LANG]["particles"]


def fold(word):
    w = unicodedata.normalize("NFD", word.lower())
    return "".join(c for c in w if unicodedata.category(c) != "Mn")


def content_words(text):
    out = set()
    for token in WORD.findall(text):
        for piece in re.split(r"['’]", fold(token)):
            if not piece or piece in STOP or len(piece) < 3:
                continue
            if piece.isdigit():
                value = piece.lstrip("0") or "0"
                out.add(value)
                out.add(DIGIT_TO_WORD.get(value, value))
                continue
            if piece in NUMWORDS:
                out.add(NUMWORDS[piece])
            out.add(piece)
    return out


def has_counterpart(word, source):
    if word in source:
        return True
    head = word[:4]
    return any(c.startswith(head) for c in source if len(c) >= 4)


def negation_delta(dirty, clean):
    """Ecart de polarite. Une elision restauree (« sais pas » -> « ne sais pas »)
    ajoute un « ne » LEGITIME, donc on tolere un ajout par « pas/plus/jamais/rien »
    deja present en entree. Au-dela, c'est une polarite changee.

    NEG_PARTICLES est vide en anglais (voir NEG_TABLES) : d_ne/c_ne restent a 0
    et le calcul se reduit a comparer le nombre de negateurs pleins des deux
    cotes — exactement ce qu'il faut pour « I don't think it works » -> « I
    think it works »."""
    d_all = [m.group(0).lower() for m in NEG.finditer(dirty)]
    c_all = [m.group(0).lower() for m in NEG.finditer(clean)]
    d_ne = sum(1 for x in d_all if x in NEG_PARTICLES)
    c_ne = sum(1 for x in c_all if x in NEG_PARTICLES)
    d_core = len(d_all) - d_ne          # pas, plus, jamais, rien, aucun, ni…
    c_core = len(c_all) - c_ne
    if c_core != d_core:
        return "polarite changee (%d -> %d marqueurs de negation)" % (d_core, c_core)
    if c_ne > d_ne + d_core:            # plus de « ne » que d'elisions restaurables
        return "« ne » ajoute sans elision correspondante (%d -> %d)" % (d_ne, c_ne)
    return None


def filter_pair(dirty, clean, structure, context):
    if not clean.strip():
        return None if not dirty.strip() else "sortie vide pour une entree non vide"
    neg = negation_delta(dirty, clean)
    if neg:
        return neg
    src, dst = content_words(dirty), content_words(clean)
    invented = sorted(w for w in dst if not has_counterpart(w, src))
    if invented:
        return "mots inventes: " + ", ".join(invented[:6])
    dw, cw = len(dirty.split()), len(clean.split())
    # `lists` et `email` ajoutent legitimement de la structure (puces, salutation,
    # signature), donc le plafond de longueur se desserre pour eux.
    ceiling = 1.15 if (structure == "prose" and context == "general") else 1.35
    if cw > dw * ceiling + 12:
        return "sortie plus longue que l'entree (%d -> %d mots)" % (dw, cw)
    if cw < dw * 0.45 and dw > 25:
        return "sortie amputee (%d -> %d mots)" % (dw, cw)
    return None


SENT = re.compile(r"(?<=[.!?…])\s+")


def segment(text, target=110, hard_max=260):
    parts, buf, n = [], [], 0
    for sentence in SENT.split(text.strip()):
        s = sentence.strip()
        if not s:
            continue
        w = len(s.split())
        if n and n + w > target:
            parts.append(" ".join(buf)); buf, n = [], 0
        buf.append(s); n += w
        if n >= hard_max:
            parts.append(" ".join(buf)); buf, n = [], 0
    if buf:
        parts.append(" ".join(buf))
    return [p for p in parts if len(p.split()) >= 6]


def call(system, user, retries=4):
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0,
        "reasoning_effort": "none",
        **({} if PROVIDER == "deepseek"
           else {"max_tokens": 1200,
                 # Gemma raisonne dans `reasoning_content`, pas dans `content` :
                 # laissee libre, la reflexion epuise le budget et la sortie
                 # revient vide.
                 "chat_template_kwargs": {"enable_thinking": False}}),
    }).encode("utf-8")
    entetes = {"Content-Type": "application/json"}
    if KEY:
        entetes["Authorization"] = "Bearer " + KEY
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(API, data=body, headers=entetes)
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                payload = json.load(r)
            return payload["choices"][0]["message"]["content"].strip(), payload.get("usage", {})
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("echec: %s" % last)


def main():
    cohere = [json.loads(l) for l in open(os.path.join(SP, "cohere_full2.jsonl"), encoding="utf-8")]
    qc = {json.loads(l)["id"]: json.loads(l)
          for l in open(os.path.join(SP, "qc_full.jsonl"), encoding="utf-8")}
    corpus = {json.loads(l)["id"]: json.loads(l)
              for l in open(os.path.join(SP, "corpus_full.jsonl"), encoding="utf-8")}

    rng = random.Random(SEED)
    units, dropped = [], collections.Counter()
    for r in cohere:
        verdict = qc.get(r["id"], {}).get("verdict")
        if verdict != "sain":
            dropped[verdict or "sans verdict"] += 1
            continue
        lang = corpus.get(r["id"], {}).get("lang", "fr")
        if lang == "amb":
            lang = "fr"
        for k, piece in enumerate(segment(r["text"])):
            styling, structure, context = spec.sample_control(rng, lang)
            units.append({"id": "%s#%02d" % (r["id"], k), "file": r["id"], "lang": lang,
                          "styling": styling, "structure": structure, "context": context,
                          "dirty": piece})

    print("fichiers ecartes par le controle qualite : %s" % dict(dropped))
    print("unites : %d (%d mots) sur %d fichiers sains"
          % (len(units), sum(len(u["dirty"].split()) for u in units),
             len({u["file"] for u in units})))
    combos = collections.Counter((u["styling"], u["structure"], u["context"]) for u in units)
    print("combinaisons de controle couvertes : %d / 16" % len(combos))
    for c, n in combos.most_common(5):
        print("   %-34s %d" % ("/".join(c), n))

    q = queue.Queue()
    for i, u in enumerate(units):
        q.put((i, u))
    counters = {"in": 0, "out": 0, "err": 0, "done": 0, "rej": 0}
    lock = threading.Lock()
    stream = open(os.path.join(SP, "pairs_v2_stream.jsonl"), "w", encoding="utf-8")
    out = [None] * len(units)

    def worker():
        while True:
            try:
                i, u = q.get_nowait()
            except queue.Empty:
                return
            system = spec.SYSTEM + "\n\n" + spec.teacher_prompt(u["styling"], u["structure"], u["context"])
            control = spec.control_line(u["styling"], u["structure"], u["context"], u["lang"])
            u["control"] = control
            try:
                clean, usage = call(system, "%s\n%s" % (control, u["dirty"]))
                with lock:
                    counters["in"] += usage.get("prompt_tokens", 0)
                    counters["out"] += usage.get("completion_tokens", 0)
                u["clean"] = clean
                u["rejet"] = filter_pair(u["dirty"], clean, u["structure"], u["context"])
            except Exception as e:
                u["clean"] = ""; u["rejet"] = "erreur API: %s" % e
                with lock:
                    counters["err"] += 1
            out[i] = u
            with lock:
                counters["done"] += 1
                if u["rejet"]:
                    counters["rej"] += 1
                stream.write(json.dumps(u, ensure_ascii=False) + "\n")
                stream.flush()
                if counters["done"] % 100 == 0:
                    print("   %d/%d  rejets=%d" % (counters["done"], len(units), counters["rej"]),
                          flush=True)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(WORKERS)]
    t0 = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    stream.close()

    kept = [u for u in out if u and not u["rejet"]]
    rejected = [u for u in out if u and u["rejet"]]
    with open(os.path.join(SP, "pairs_v2.jsonl"), "w", encoding="utf-8") as f:
        for u in kept:
            f.write(json.dumps(u, ensure_ascii=False) + "\n")
    with open(os.path.join(SP, "pairs_v2_rejected.jsonl"), "w", encoding="utf-8") as f:
        for u in rejected:
            f.write(json.dumps(u, ensure_ascii=False) + "\n")

    reasons = collections.Counter(u["rejet"].split(":")[0].split("(")[0].strip() for u in rejected)
    print("\ngeneration en %.0f s | tokens in=%d out=%d | erreurs=%d"
          % (time.time() - t0, counters["in"], counters["out"], counters["err"]))
    print("cout estime : ~%.2f $" % (counters["in"] / 1e6 * 0.028 + counters["out"] / 1e6 * 0.42))
    print("PAIRES GARDEES : %d / %d (%.0f%%)"
          % (len(kept), len(out), 100.0 * len(kept) / max(1, len(out))))
    for k, v in reasons.most_common():
        print("   rejet %-46s %d" % (k, v))


if __name__ == "__main__":
    main()
