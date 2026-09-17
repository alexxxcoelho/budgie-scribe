# -*- coding: utf-8 -*-
"""QC binaire OK/KO a causes fermees — contre l'echelle a trois classes.

POURQUOI CE BANC EXISTE
La matrice de confusion de DeepSeek face a ses PROPRES verdicts passes, sur
les memes entrees et a temperature 0, donne ceci :

    sain    (120) -> 111 sain,   8 suspect,   1 verole   = 92,5 %
    suspect (120) ->  10 sain,  70 suspect,  38 verole   = 58,3 %
    verole  (120) ->   7 sain,  44 suspect,  68 verole   = 56,7 %

L'axe binaire tient a 93 %. L'axe a trois classes s'effondre a 57 %. La
frontiere suspect/verole ne porte donc AUCUNE information reproductible :
c'est du bruit promu au rang de verdict.

Le prompt binaire renverse en plus la charge de la preuve. L'ancien definissait
le KO par une liste de defauts, ce qui demandait au juge d'estimer une gravite.
Le nouveau definit l'OK par une liste FERMEE de differences tolerees, et rend
tout le reste KO — « est-ce dans la liste ? » se verifie, « est-ce assez
grave ? » ne se verifie pas.

CE QU'ON MESURE
  ACCORD       verdict OK/KO contre l'or replie (sain -> OK, le reste -> KO)
  KO MANQUE    l'or dit KO, le juge dit OK. Detaille selon que l'or disait
               « verole » (faute grave) ou « suspect » (moins grave).
  FAUX KO      l'or dit sain, le juge dit KO. Cout en volume, pas en purete.
  CAUSES       distribution, et ACCORD SUR LA CAUSE quand les deux disent KO.
               C'est la mesure que l'echelle a trois classes ne pouvait pas
               produire, et c'est elle qui dit si la categorisation est
               deterministe ou decorative.

Usage : bench_qc_binaire.py <nom> [port] [n_cas]
        BENCH_API=deepseek pour passer par l'API payante.
"""
import collections, json, os, queue, sys, threading, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd
from bench_juge import load_qc, norm_verdict          # meme tirage, meme graine

SYSTEM = chemins.prompt("_sys_qc_binaire.txt")
WORKERS = int(os.environ.get("BENCH_WORKERS", "4"))
DISTANT = os.environ.get("BENCH_API") == "deepseek"

# Les 5 causes que l'ancien schema portait deja sous le nom `defauts`. Les
# trois nouvelles (ajout, sens, vide) n'ont pas d'equivalent dans l'or, donc
# l'accord sur la cause ne se mesure que sur ces cinq-la.
CAUSES_COMMUNES = {"boucle", "effondrement", "langue", "incoherence"}
# v4 : `ajout` et `hallucination` fusionnes en `invention`. Leur frontiere
# etait une affaire de LONGUEUR — « une phrase entiere » contre « moins qu'une
# phrase » — c'est-a-dire le meme seuil de degre non verifiable qu'on venait de
# supprimer au niveau du verdict. Les deux modeles les confondaient 106 fois
# sur 239 KO communs, de loin la premiere source de desaccord.
CAUSES_VALIDES = CAUSES_COMMUNES | {"sens", "invention", "vide"}


def make_caller(port, model):
    if DISTANT:
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

    def call(user, retries=2):
        body = {"model": model,
                "messages": [{"role": "system", "content": SYSTEM},
                             {"role": "user", "content": user}],
                "temperature": 0, "response_format": {"type": "json_object"}}
        if not DISTANT:
            # Gemma raisonne sinon jusqu'a epuiser son budget sans repondre.
            body.update({"max_tokens": 1500,
                         "chat_template_kwargs": {"enable_thinking": False},
                         "reasoning_effort": "none"})
        data = json.dumps(body).encode("utf-8")
        for essai in range(retries + 1):
            try:
                req = urllib.request.Request(url, data=data, headers=headers)
                t0 = time.time()
                with urllib.request.urlopen(req, timeout=300) as r:
                    p = json.load(r)
                dt = time.time() - t0
                txt = (p["choices"][0]["message"].get("content") or "").strip()
                with lock:
                    stats["appels"] += 1
                    stats["secondes"] += dt
                try:
                    return json.loads(txt)
                except Exception:
                    a, b = txt.find("{"), txt.rfind("}")
                    if a >= 0 and b > a:
                        try:
                            return json.loads(txt[a:b + 1])
                        except Exception:
                            pass
                with lock:
                    stats["json_casse"] += 1
                return None
            except Exception:
                if essai == retries:
                    with lock:
                        stats["erreur"] += 1
                    return None
                time.sleep(1.5 * (essai + 1))
    return call, stats


def main():
    nom = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8899
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 360
    call, stats = make_caller(port, nom)

    jobs = load_qc(n)                      # meme echantillon que le banc a 3 classes
    # l'or de reference porte aussi ses `defauts` : on les recupere pour
    # pouvoir comparer les CAUSES, pas seulement les verdicts
    defauts_or = {}
    for l in open(os.path.join(SP, "qc_units_out.jsonl"), encoding="utf-8"):
        r = json.loads(l)
        defauts_or[r["id"]] = {d for d in (r.get("defauts") or []) if d != "aucun"}

    print("\n=== QC binaire — %s — %d cas ===" % (nom, len(jobs)), flush=True)
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
            v = call(j["user"]) or {}
            with lock:
                out.append((j, v))
                k = len(out)
            if k % 60 == 0:
                print("   %d/%d" % (k, len(jobs)), flush=True)

    t0 = time.time()
    ts = [threading.Thread(target=worker, daemon=True) for _ in range(WORKERS)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    c = collections.Counter()
    desaccords = []
    causes = collections.Counter()
    hors_liste = collections.Counter()
    cause_accord = collections.Counter()
    manques = []
    for j, v in out:
        or3 = j["gold"]
        or_bin = "OK" if or3 == "sain" else "KO"
        pred = (v.get("verdict") or "").strip().upper()
        if pred not in ("OK", "KO"):
            c["verdict_illisible"] += 1
            continue
        c["n"] += 1
        c["accord"] += (pred == or_bin)
        if or_bin == "KO" and pred == "OK":
            c["ko_manque"] += 1
            c["ko_manque_verole" if or3 == "verole" else "ko_manque_suspect"] += 1
            if len(manques) < 8:
                manques.append({"id": j["id"], "or": or3,
                                "expl": (v.get("explication") or "")[:110]})
            desaccords.append({"id": j["id"], "or": or3, "type": "ko_manque",
                               "entree": j["user"], "verdict": v})
        if or_bin == "OK" and pred == "KO":
            c["faux_ko"] += 1
            # On GARDE l'entree complete. Un « faux KO » mesure contre un or
            # produit par l'ANCIEN prompt, plus clement, peut aussi bien etre
            # le resserrement voulu qu'une erreur : seule la lecture tranche.
            desaccords.append({"id": j["id"], "or": or3, "type": "faux_ko",
                               "entree": j["user"], "verdict": v})
        if or3 == "verole":
            c["verole_total"] += 1
            c["verole_attrapee"] += (pred == "KO")
        if pred == "KO":
            liste = [str(x).strip().lower() for x in (v.get("causes") or [])]
            if not liste:
                c["ko_sans_cause"] += 1
            for x in liste:
                (causes if x in CAUSES_VALIDES else hors_liste)[x] += 1
            # accord sur la cause : uniquement quand l'or en portait une des cinq
            attendu = defauts_or.get(j["id"], set()) & CAUSES_COMMUNES
            propose = set(liste) & CAUSES_COMMUNES
            if attendu:
                cause_accord["comparables"] += 1
                cause_accord["intersection"] += bool(attendu & propose)

    n_ = max(1, c["n"])
    ko_or = sum(1 for j, _ in out if j["gold"] != "sain")
    ok_or = len(out) - ko_or
    res = {
        "modele": nom, "n": c["n"],
        "accord_binaire": round(100 * c["accord"] / n_, 1),
        "ko_manque": c["ko_manque"], "ko_or": ko_or,
        "ko_manque_pct": round(100 * c["ko_manque"] / max(1, ko_or), 1),
        "ko_manque_verole": c["ko_manque_verole"],
        "ko_manque_suspect": c["ko_manque_suspect"],
        "verole_attrapee_pct": round(100 * c["verole_attrapee"] / max(1, c["verole_total"]), 1),
        "verole_total": c["verole_total"],
        "faux_ko": c["faux_ko"], "ok_or": ok_or,
        "faux_ko_pct": round(100 * c["faux_ko"] / max(1, ok_or), 1),
        "ko_sans_cause": c["ko_sans_cause"],
        "causes": dict(causes.most_common()),
        "causes_hors_liste": dict(hors_liste.most_common()),
        "cause_accord_pct": round(100 * cause_accord["intersection"]
                                  / max(1, cause_accord["comparables"]), 1),
        "cause_comparables": cause_accord["comparables"],
        "verdict_illisible": c["verdict_illisible"],
        "json_casse": stats["json_casse"], "erreurs": stats["erreur"],
        "s_par_appel": round(stats["secondes"] / max(1, stats["appels"]), 2),
        "minutes": round((time.time() - t0) / 60, 1),
        "manques": manques,
    }
    dst = os.path.join(SP, "qcbin_%s.json" % nom.replace("/", "_").replace(":", "_"))
    json.dump(res, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # Les verdicts case par case, pour l'accord INTER-JUGES sur la nouvelle
    # grille : c'est lui le vrai test de determinisme, pas l'accord avec une
    # taxonomie qui n'existait plus.
    par_cas = os.path.join(SP, "qcbin_cas_%s.jsonl" % nom.replace("/", "_").replace(":", "_"))
    with open(par_cas, "w", encoding="utf-8") as f:
        for j, v in out:
            f.write(json.dumps({"id": j["id"], "or": j["gold"],
                                "verdict": (v.get("verdict") or "").strip().upper(),
                                "causes": sorted(str(x).lower() for x in (v.get("causes") or [])),
                                "explication": v.get("explication", "")},
                               ensure_ascii=False) + "\n")
    # Le corpus ne sort pas d'ici : ce fichier reste local et n'est jamais
    # affiche ni publie.
    dsc = os.path.join(SP, "qcbin_desaccords_%s.jsonl" % nom.replace("/", "_").replace(":", "_"))
    with open(dsc, "w", encoding="utf-8") as f:
        for d in desaccords:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    print("\n  --- %s ---" % nom)
    print("  accord OK/KO        %5.1f%%   (or replie : sain -> OK)" % res["accord_binaire"])
    print("  KO manques          %4d/%-4d %5.1f%%   dont %d verolees, %d suspectes"
          % (res["ko_manque"], ko_or, res["ko_manque_pct"],
             res["ko_manque_verole"], res["ko_manque_suspect"]))
    print("  verolees attrapees  %5.1f%%   (%d cas)"
          % (res["verole_attrapee_pct"], res["verole_total"]))
    print("  faux KO             %4d/%-4d %5.1f%%   cout en volume, pas en purete"
          % (res["faux_ko"], ok_or, res["faux_ko_pct"]))
    print("  KO sans cause       %4d" % res["ko_sans_cause"])
    print("  causes hors liste   %4d %s"
          % (sum(hors_liste.values()), list(hors_liste)[:4] or ""))
    print("  accord sur la CAUSE %5.1f%%   (sur %d cas comparables)"
          % (res["cause_accord_pct"], res["cause_comparables"]))
    print("  verdict illisible   %4d | JSON casse %d | erreurs %d"
          % (res["verdict_illisible"], res["json_casse"], res["erreurs"]))
    print("  vitesse             %5.2f s/appel, %.1f min" % (res["s_par_appel"], res["minutes"]))
    print("\n  distribution des causes :")
    for k, v in list(causes.most_common())[:8]:
        print("    %-16s %4d" % (k, v))
    print("\n  -> %s" % dst)


if __name__ == "__main__":
    main()
