# -*- coding: utf-8 -*-
"""Repasse les paires REELLES d'entrainement sous la grille QC binaire.

POURQUOI
Les 1 200 paires reelles de pairs_mix4 ont ete filtrees par l'echelle a trois
classes, dont §0.18 a montre qu'elle ne reproduit que 57 % de ses propres
verdicts « verole ». La grille binaire, elle, obtient 95,0 % d'accord entre
deux modeles separes par 19 milliards de parametres (kappa 0,88) et laisse
passer 0,6 % de verolees contre 1,6 %.

Ce que ca change, mesure sur le corpus complet (§0.18) : le jeu retenu passe
de 1,6 % a 0,6 % de transcriptions verolees. Ici on applique le meme filtre a
ce qui sert DEJA a entrainer.

PERIMETRE, ET SA LIMITE
  SUMM-RE  1 038 paires, chacune avec sa reference Whisper PAR UNITE. Rejugees.
  Budgie     162 paires, qui sont des SOUS-UNITES d'enregistrements dont la
             reference couvre l'enregistrement entier — 107 mots de candidat
             contre 7 823 de reference. Les comparer n'aurait aucun sens ; ces
             paires sont conservees telles quelles et le rapport le dit.

Le juge est local (llama-server, gemma-12b-qat) : aucun cout.

Usage : rejuge_paires.py <paires.jsonl> <sortie_verdicts.jsonl> [n]
"""
import collections, json, os, queue, sys, threading, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd
SYSTEM = chemins.prompt("_sys_qc_binaire.txt")
URL = os.environ.get("LLAMACPP_URL", "http://127.0.0.1:8899") + "/v1/chat/completions"
WORKERS = int(os.environ.get("QC_WORKERS", "4"))
MAX_CHARS = 6000


def clip(t, n):
    return t if len(t) <= n else t[:n // 2] + "\n[…COUPE…]\n" + t[-n // 2:]


def juge(user, essais=3):
    corps = json.dumps({
        "model": "gemma-12b-qat",
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": user}],
        "temperature": 0, "max_tokens": 1500,
        "response_format": {"type": "json_object"},
        # Gemma raisonne dans `reasoning_content` : laissee libre, la reflexion
        # epuise le budget et `content` revient vide.
        "chat_template_kwargs": {"enable_thinking": False},
        "reasoning_effort": "none",
    }).encode("utf-8")
    for k in range(essais):
        try:
            req = urllib.request.Request(
                URL, data=corps, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=240) as r:
                p = json.load(r)
            txt = (p["choices"][0]["message"].get("content") or "").strip()
            try:
                return json.loads(txt)
            except Exception:
                a, b = txt.find("{"), txt.rfind("}")
                if a >= 0 and b > a:
                    return json.loads(txt[a:b + 1])
                return None
        except Exception:
            if k == essais - 1:
                return None
            time.sleep(1.5 * (k + 1))


def main():
    src, dst = sys.argv[1], sys.argv[2]
    limite = int(sys.argv[3]) if len(sys.argv) > 3 else 0

    paires = [json.loads(l) for l in open(src, encoding="utf-8")]
    reel = [r for r in paires if r.get("source") in ("summre", "budgie")]
    ref = {json.loads(l)["id"]: json.loads(l)
           for l in open(os.path.join(SP, "summre_unit_ref.jsonl"), encoding="utf-8")}

    jugeables = [r for r in reel if r["source"] == "summre" and r["id"] in ref]
    hors = [r for r in reel if r not in jugeables]
    if limite:
        jugeables = jugeables[:limite]
    print("paires reelles : %d | rejugeables : %d | hors perimetre : %d (Budgie, "
          "reference a l'echelle de l'enregistrement)"
          % (len(reel), len(jugeables), len(hors)), flush=True)

    q = queue.Queue()
    for r in jugeables:
        q.put(r)
    out, lock = [], threading.Lock()

    def worker():
        while True:
            try:
                r = q.get_nowait()
            except queue.Empty:
                return
            user = "REFERENCE (Whisper) :\n%s\n\nCANDIDAT (Cohere) :\n%s" % (
                clip(ref[r["id"]].get("asr_whisper", ""), MAX_CHARS // 2),
                clip(r["dirty"], MAX_CHARS // 2))
            v = juge(user) or {}
            v["id"] = r["id"]
            with lock:
                out.append(v)
                n = len(out)
            if n % 100 == 0:
                print("   %d/%d" % (n, len(jugeables)), flush=True)

    t0 = time.time()
    ts = [threading.Thread(target=worker, daemon=True) for _ in range(WORKERS)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    with open(dst, "w", encoding="utf-8") as f:
        for v in out:
            f.write(json.dumps(v, ensure_ascii=False) + "\n")

    c = collections.Counter((v.get("verdict") or "?").strip().upper() for v in out)
    causes = collections.Counter()
    for v in out:
        if (v.get("verdict") or "").strip().upper() == "KO":
            for x in (v.get("causes") or []):
                causes[str(x).lower()] += 1
    n = max(1, len(out))
    print("\n=== verdicts sur %d paires deja utilisees pour l'entrainement ===" % n)
    for k, v in c.most_common():
        print("  %-8s %5d  %5.1f %%" % (k, v, 100.0 * v / n))
    print("\n  causes des KO :")
    for k, v in causes.most_common():
        print("    %-14s %5d" % (k, v))
    print("\n  %.1f min" % ((time.time() - t0) / 60))
    print("-> %s" % dst)


if __name__ == "__main__":
    main()
