# -*- coding: utf-8 -*-
"""Banc d'essai des juges locaux — peut-on remplacer DeepSeek sans rien perdre ?

QUATRE mesures, et elles ne pesent pas pareil :

  ACCORD QC      part des verdicts sain/suspect/verole identiques a ceux de
                 DeepSeek sur les MEMES entrees. Utile, mais DeepSeek n'est pas
                 la verite : c'est seulement la reference qu'on remplace.

  LAISSER-PASSER DeepSeek a dit « verole », le juge local dit « sain ». C'est la
                 faute qui compte, parce que c'est elle qui laisse entrer une
                 transcription corrompue dans le corpus d'entrainement.

  MIROIR         chaque cas A/B est pose DEUX FOIS, une fois avec A et B
                 echanges. Un juge qui lit repond l'inverse ; un juge qui suit
                 la position repond pareil. VERITE TERRAIN, sans arbitre.

  EGALITE        18 des 80 cas A/B ont deux sorties identiques au caractere
                 pres. La seule reponse defendable est « egalite ». Declarer un
                 gagnant entre deux textes identiques prouve que le juge n'a pas
                 lu. VERITE TERRAIN, sans arbitre. DeepSeek fait 18/18.

Usage : bench_juge.py <nom> [port] [nb_cas_qc]
"""
import json, os, sys, time, random, threading, queue, collections, urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd
SEED = 20260902
WORKERS = int(os.environ.get("BENCH_WORKERS", "4"))
# Gemma 4 et Qwen 3.x raisonnent avant de repondre : la reflexion part dans
# `reasoning_content` et NON dans `content`. Laissee libre, elle mange tout le
# budget de tokens et `content` revient vide.
#
# MESURE, pas hypothese : sur gemma-12b-qat, la reflexion libre atteint le
# plafond de 2000 tokens sans jamais ecrire le verdict sur les cas durs
#   « eval time = 50774 ms / 2000 tokens » — 50 s par appel, contre 3,2 s
# reflexion coupee, et un `content` vide au bout. On la coupe par defaut.
THINK = os.environ.get("BENCH_THINK", "0") == "1"

# Le prompt QC d'origine nomme les trois verdicts dans le schema JSON mais ne
# les DEFINIT nulle part. Chaque modele s'invente donc un seuil : DeepSeek un
# severe, Gemma un clement — d'ou 81 verolees requalifiees en « suspect ».
# C'est aussi pourquoi DeepSeek ne reproduit que 57 % de ses propres verdicts
# « verole » : un seuil non ecrit n'est reproductible par personne, pas meme
# par celui qui l'a pose. BENCH_QC_SYS=calibre charge la variante qui l'ecrit.
QC_FILE = "_sys_qc_calibre.txt" if os.environ.get("BENCH_QC_SYS") == "calibre" else "_sys_qc.txt"
QC_SYSTEM = chemins.prompt(QC_FILE)
AB_SYSTEM = chemins.prompt("_sys_ab.txt")


def make_caller(port, model):
    """Un seul appelant pour les deux mondes : llama-server local et DeepSeek.

    BENCH_API=deepseek fait passer le banc par l'API payante, pour poser la
    LIGNE DE REFERENCE. Sans elle, « 87,5 % de miroir » ne veut rien dire :
    on ignore si l'arbitre qu'on remplace fait 100 % ou 85 %.
    """
    distant = os.environ.get("BENCH_API") == "deepseek"
    if distant:
        url = "https://api.deepseek.com/v1/chat/completions"
        key = json.load(open(os.path.expanduser("~/.budgie/custom_api_keys.json"),
                             encoding="utf-8"))["deepseek"]
        headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
        model = "deepseek-v4-flash"
    else:
        url = "http://127.0.0.1:%d/v1/chat/completions" % port
        headers = {"Content-Type": "application/json"}
    stats = collections.Counter()
    lock = threading.Lock()

    def call(system, user, retries=2):
        body = json.dumps({
            "model": model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": 0,
            # Piege mesure : DeepSeek v4 Flash raisonne LUI AUSSI, et ses
            # `reasoning_tokens` sont comptes dans `max_tokens`. Un plafond de
            # 400 puis de 1500 laissait la reflexion consommer le budget entier
            # et `content` revenait vide ou tronque — 185 puis 127 JSON casses
            # sur 220, alors que le modele repondait tres bien. Les scripts
            # d'origine ne fixaient aucun plafond ; on ne lui en met donc pas.
            # Un plafond ne change rien a un modele qui ne l'atteint pas, mais
            # il decapite silencieusement celui qui l'atteint.
            **({"max_tokens": 4000 if THINK else 1500} if not distant else {}),
            "response_format": {"type": "json_object"},
            **({} if (THINK or distant)
               else {"chat_template_kwargs": {"enable_thinking": False},
                     "reasoning_effort": "none"}),
        }).encode("utf-8")
        for attempt in range(retries + 1):
            try:
                req = urllib.request.Request(url, data=body, headers=headers)
                t0 = time.time()
                with urllib.request.urlopen(req, timeout=300) as r:
                    payload = json.load(r)
                dt = time.time() - t0
                txt = payload["choices"][0]["message"]["content"]
                usage = payload.get("usage") or {}
                with lock:
                    stats["appels"] += 1
                    stats["secondes"] += dt
                    stats["tokens_sortie"] += usage.get("completion_tokens", 0)
                try:
                    return json.loads(txt)
                except Exception:
                    pass
                # tolerance : un JSON noye dans du texte reste exploitable
                a, b = txt.find("{"), txt.rfind("}")
                if a >= 0 and b > a:
                    try:
                        v = json.loads(txt[a:b + 1])
                        with lock:
                            stats["json_repare"] += 1
                        return v
                    except Exception:
                        pass
                with lock:
                    stats["json_casse"] += 1
                return None
            except Exception:
                if attempt == retries:
                    with lock:
                        stats["erreur"] += 1
                    return None
                time.sleep(1.5 * (attempt + 1))
    return call, stats


def run_parallel(jobs, fn):
    q = queue.Queue()
    for j in jobs:
        q.put(j)
    out, lock = [], threading.Lock()

    def worker():
        while True:
            try:
                j = q.get_nowait()
            except queue.Empty:
                return
            r = fn(j)
            with lock:
                out.append(r)
                n = len(out)
            if n % 20 == 0:
                print("      %d/%d" % (n, len(jobs)), flush=True)

    ts = [threading.Thread(target=worker, daemon=True) for _ in range(WORKERS)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return out


def norm_verdict(v):
    """Ramene les graphies de « verole » a une seule cle : le corpus DeepSeek
    contient 5 lignes accentuees « verole » parmi 182, et les modeles locaux
    inventent leurs propres variantes."""
    v = (v or "").strip().lower()
    for k in ("verole", "verol", "vérol"):
        if k in v:
            return "verole"
    if "suspect" in v:
        return "suspect"
    if "sain" in v:
        return "sain"
    return "?"


def load_qc(n):
    ref = {json.loads(l)["id"]: json.loads(l)
           for l in open(os.path.join(SP, "summre_unit_ref.jsonl"), encoding="utf-8")}
    inp = {json.loads(l)["id"]: json.loads(l)
           for l in open(os.path.join(SP, "qc_units_in.jsonl"), encoding="utf-8")}
    gold = [json.loads(l) for l in open(os.path.join(SP, "qc_units_out.jsonl"), encoding="utf-8")]
    by = collections.defaultdict(list)
    for g in gold:
        by[norm_verdict(g["verdict"])].append(g)
    rng = random.Random(SEED)
    per = max(1, n // 3)
    sample = []
    for cls in ("sain", "suspect", "verole"):
        rows = sorted(by[cls], key=lambda r: r["id"])
        rng.shuffle(rows)
        sample += rows[:per]
    jobs = []
    for g in sample:
        i = g["id"]
        jobs.append({"id": i, "gold": norm_verdict(g["verdict"]),
                     "user": "REFERENCE (Whisper) :\n%s\n\nCANDIDAT (Cohere) :\n%s"
                             % (ref[i]["asr_whisper"][:3000], inp[i]["text"][:3000])})
    return jobs


def load_ab():
    base = {json.loads(l)["id"]: json.loads(l)
            for l in open(os.path.join(SP, "fix_gen_base.jsonl"), encoding="utf-8")}
    cand = {json.loads(l)["id"]: json.loads(l)
            for l in open(os.path.join(SP, "fix_gen_p3-1200.jsonl"), encoding="utf-8")}
    gold = {json.loads(l)["id"]: json.loads(l)
            for l in open(os.path.join(SP, "fix_ab_p3-1200.jsonl"), encoding="utf-8")}
    ids = sorted(set(base) & set(cand))
    # BENCH_AB_N sert aux essais de fumee : on veut valider la plomberie sans
    # payer 160 appels. On garde les cas identiques en tete pour que le test
    # d'egalite reste mesurable meme sur un echantillon.
    lim = int(os.environ.get("BENCH_AB_N", "0"))
    if lim:
        ident = [i for i in ids if base[i]["out"].strip() == cand[i]["out"].strip()]
        autres = [i for i in ids if i not in set(ident)]
        ids = (ident[:lim // 2] + autres[:lim - len(ident[:lim // 2])])
    jobs = []
    for i in ids:
        entree = base[i]["control"] + "\n" + base[i]["dirty"]
        identique = base[i]["out"].strip() == cand[i]["out"].strip()
        # sens direct : A=base, B=tuned. sens inverse : l'echange exact.
        for sens, a, b in (("direct", base[i]["out"], cand[i]["out"]),
                           ("inverse", cand[i]["out"], base[i]["out"])):
            jobs.append({"id": i, "sens": sens, "identique": identique,
                         "gold": gold.get(i, {}).get("gagnant"),
                         "user": "ENTREE :\n%s\n\nA :\n%s\n\nB :\n%s" % (entree, a, b)})
    return jobs


def main():
    nom = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8899
    nqc = int(sys.argv[3]) if len(sys.argv) > 3 else 60
    call, stats = make_caller(port, nom)

    print("\n=== %s (port %d, %d fils) ===" % (nom, port, WORKERS), flush=True)
    t0 = time.time()

    print("  [1/2] QC — %d cas stratifies" % nqc, flush=True)
    qc_jobs = load_qc(nqc)
    qc_res = run_parallel(
        qc_jobs, lambda j: dict(j, got=(call(QC_SYSTEM, j["user"]) or {}).get("verdict")))

    if os.environ.get("BENCH_SKIP_AB") == "1":
        # Mode QC seul : sert a monter l'echantillon de veroles bien au-dela
        # des 20 d'un tirage a 60 cas, ou l'ecart « 3 laisser-passer contre 5 »
        # n'est que du bruit.
        print("  [2/2] A/B saute (BENCH_SKIP_AB=1)", flush=True)
        ab_res = []
    else:
        print("  [2/2] A/B — 80 cas x 2 sens = 160 appels", flush=True)
        ab_jobs = load_ab()
        ab_res = run_parallel(
            ab_jobs, lambda j: dict(j, got=(call(AB_SYSTEM, j["user"]) or {}).get("gagnant")))

    # ---------- QC ----------
    qc = collections.Counter()
    confusion = collections.defaultdict(collections.Counter)
    for r in qc_res:
        g, p = r["gold"], norm_verdict(r["got"])
        qc["n"] += 1
        qc["accord"] += (g == p)
        qc["binaire"] += ((g == "sain") == (p == "sain"))
        confusion[g][p] += 1
        if g == "verole":
            qc["verole_total"] += 1
            qc["verole_attrape"] += (p == "verole")
            qc["verole_signale"] += (p in ("verole", "suspect"))
            qc["laisser_passer"] += (p == "sain")

    # ---------- A/B ----------
    par_cas = collections.defaultdict(dict)
    for r in ab_res:
        par_cas[r["id"]][r["sens"]] = r
    ab = collections.Counter()
    tally = collections.Counter()
    miroir_fautes = []
    for i, d in par_cas.items():
        if "direct" not in d or "inverse" not in d:
            continue
        a, b = d["direct"]["got"], d["inverse"]["got"]
        ab["n"] += 1
        # un juge sain repond l'inverse quand on echange les colonnes
        attendu = {"A": "B", "B": "A", "egalite": "egalite"}.get(a)
        ok = attendu is not None and b == attendu
        ab["miroir_ok"] += ok
        if not ok:
            miroir_fautes.append({"id": i, "direct": a, "inverse": b})
        if a == b and a in ("A", "B"):
            ab["biais_position"] += 1
        if d["direct"]["identique"]:
            ab["ident_n"] += 1
            ab["ident_ok"] += (a == "egalite" and b == "egalite")
        # verdict du juge local, en coordonnees base/tuned (sens direct : A=base)
        mine = {"A": "base", "B": "tuned", "egalite": "egalite"}.get(a)
        if mine:
            tally[mine] += 1

    n = max(1, qc["n"])
    m = max(1, ab["n"])
    res = {
        "modele": nom,
        "reflexion": THINK,
        "qc_n": qc["n"],
        "qc_accord_3": round(100 * qc["accord"] / n, 1),
        "qc_accord_binaire": round(100 * qc["binaire"] / n, 1),
        "qc_verole_attrape": round(100 * qc["verole_attrape"] / max(1, qc["verole_total"]), 1),
        "qc_verole_signale": round(100 * qc["verole_signale"] / max(1, qc["verole_total"]), 1),
        "qc_laisser_passer": qc["laisser_passer"],
        "qc_verole_total": qc["verole_total"],
        "ab_n": ab["n"],
        "ab_miroir": round(100 * ab["miroir_ok"] / m, 1),
        "ab_biais_position": ab["biais_position"],
        "ab_egalite_forcee": "%d/%d" % (ab["ident_ok"], ab["ident_n"]),
        "ab_egalite_pct": round(100 * ab["ident_ok"] / max(1, ab["ident_n"]), 1),
        "verdict_brut": dict(tally),
        "json_casse": stats["json_casse"],
        "json_repare": stats["json_repare"],
        "erreurs": stats["erreur"],
        "s_par_appel": round(stats["secondes"] / max(1, stats["appels"]), 2),
        "tok_s": round(stats["tokens_sortie"] / max(0.001, stats["secondes"]), 1),
        "minutes_total": round((time.time() - t0) / 60, 1),
        "confusion": {k: dict(v) for k, v in confusion.items()},
        "miroir_fautes": miroir_fautes[:15],
    }
    suffixe = (("_think" if THINK else "")
               + ("_qc" if os.environ.get("BENCH_SKIP_AB") == "1" else "")
               + ("_cal" if os.environ.get("BENCH_QC_SYS") == "calibre" else ""))
    dst = os.path.join(SP, "juge_%s%s.json"
                       % (nom.replace("/", "_").replace(":", "_"), suffixe))
    json.dump(res, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("\n  --- %s ---" % nom)
    print("  QC accord 3 classes    %5.1f%%" % res["qc_accord_3"])
    print("  QC accord sain/pas     %5.1f%%" % res["qc_accord_binaire"])
    print("  QC veroles signalees   %5.1f%%  (classees verole exactement %.1f%%)"
          % (res["qc_verole_signale"], res["qc_verole_attrape"]))
    print("  QC laisser-passer      %5d    <-- la faute grave (verole vu sain)"
          % res["qc_laisser_passer"])
    print("  A/B miroir coherent    %5.1f%%  <-- verite terrain" % res["ab_miroir"])
    print("  A/B egalite forcee     %5s    <-- verite terrain (DeepSeek 18/18)"
          % res["ab_egalite_forcee"])
    print("  A/B biais de position  %5d    cas repondant pareil des deux cotes"
          % res["ab_biais_position"])
    print("  JSON casse             %5d    (repare %d, erreurs reseau %d)"
          % (res["json_casse"], res["json_repare"], res["erreurs"]))
    print("  vitesse                %5.2f s/appel, %.0f tok/s, %.1f min au total"
          % (res["s_par_appel"], res["tok_s"], res["minutes_total"]))
    print("  -> %s" % dst)


if __name__ == "__main__":
    main()
