# -*- coding: utf-8 -*-
"""Professeur + filtre + arbitrage, sur un fichier d'unites quelconque.

Usage : teach.py <unites.jsonl> <paires.jsonl>

Reprend les fonctions de make_pairs_v2 (filtre de mots inventes, controle de
polarite) et d'adjudicate (arbitrage par lecture des paires signalees), pour
que la chaine de nuit n'ait qu'un point d'entree.

Le filtre TRIE, il ne tranche pas : ses rejets passent au juge, qui en avait
recupere 55 % a la passe precedente (notes d'entrainement §0.15).
"""
import json, os, sys, time, threading, queue, urllib.request, collections

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd

spec = chemins.spec()          # spec_en si SCRIBE_LANG=en, sinon spec — voir chemins.spec()
from make_pairs_v2 import filter_pair, call as teacher_call, MODEL as TEACHER_MODEL

# L'arbitre suit le meme fournisseur que le professeur (voir make_pairs_v2).
from make_pairs_v2 import API, KEY, PROVIDER
import adjudicate
WORKERS = 16 if PROVIDER == "deepseek" else 4
ADJ_MODEL = "deepseek-v4-flash" if PROVIDER == "deepseek" else     os.environ.get("POC_ADJUDGE", "gemma-12b-qat")
WRITE_LOCK = threading.Lock()   # partage : un verrou neuf par appel ne serialise rien

# Avant : on decoupait le TEXTE SOURCE d'adjudicate.py pour en extraire SYSTEM
# — fragile (un renommage de variable dans adjudicate.py cassait teach.py sans
# le dire). Maintenant adjudicate.system_prompt() renvoie la bonne version
# (francaise ou SYSTEM_EN) selon chemins.LANG, un seul endroit a maintenir.
ADJ_SYSTEM = adjudicate.system_prompt()


def adj_call(user, retries=3):
    body = json.dumps({
        "model": ADJ_MODEL,
        "messages": [{"role": "system", "content": ADJ_SYSTEM},
                     {"role": "user", "content": user}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")
    last = None
    entetes = {"Content-Type": "application/json"}
    if KEY:
        entetes["Authorization"] = "Bearer " + KEY
    for attempt in range(retries):
        req = urllib.request.Request(API, data=body, headers=entetes)
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(json.load(r)["choices"][0]["message"]["content"])
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(str(last))


def pool(items, work, workers=WORKERS, every=200):
    q = queue.Queue()
    for i, it in enumerate(items):
        q.put((i, it))
    out = [None] * len(items)
    done = [0]
    lock = threading.Lock()

    def loop():
        while True:
            try:
                i, it = q.get_nowait()
            except queue.Empty:
                return
            try:
                out[i] = work(it)
            except Exception as e:
                it["erreur"] = str(e)[:200]
                out[i] = it
            with lock:
                done[0] += 1
                if done[0] % every == 0:
                    print("   %d/%d" % (done[0], len(items)), flush=True)

    ts = [threading.Thread(target=loop, daemon=True) for _ in range(workers)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return [o for o in out if o]


def main():
    src, dst = sys.argv[1], sys.argv[2]
    units = [json.loads(l) for l in open(src, encoding="utf-8")]
    print("professeur : %d unites | modele=%s" % (len(units), TEACHER_MODEL), flush=True)
    t0 = time.time()

    def clean_one(u):
        return _clean_one(u)

    def _clean_one(u):
        system = spec.SYSTEM + "\n\n" + spec.teacher_prompt(u["styling"], u["structure"], u["context"])
        control = spec.control_line(u["styling"], u["structure"], u["context"], u.get("lang", "fr"))
        u["control"] = control
        text, _ = teacher_call(system, "%s\n%s" % (control, u["dirty"]))
        u["clean"] = text
        u["rejet"] = filter_pair(u["dirty"], text, u["structure"], u["context"])
        return u

    # ── Reprise : ce qui a ete paye est garde ───────────────────────────────
    # Un run interrompu ne doit rien couter deux fois. Les paires deja produites
    # sont relues depuis la sortie ; seules les unites manquantes repartent chez
    # le professeur. Le journal brut (`.progress`) garde AUSSI les paires
    # rejetees par le filtre, pour ne pas les repayer avant arbitrage.
    import budget as budget_mod
    progress = dst + ".progress"

    def has_output(rec):
        return bool(rec.get("clean")) or bool(rec.get("rejet"))

    acquired = budget_mod.done_ids(progress, has_output)
    todo = [u for u in units if u["id"] not in acquired]
    budget_mod.announce("professeur", len(units), len(acquired), per_item_usd=(0.00017 if PROVIDER == "deepseek" else 0.0))
    stream = budget_mod.rewrite_kept(progress, acquired)

    def clean_and_keep(u):
        r = clean_one(u)
        with WRITE_LOCK:
            stream.write(json.dumps(r, ensure_ascii=False) + "\n")
            stream.flush()
        return r

    done = list(acquired.values()) + (pool(todo, clean_and_keep) if todo else [])
    stream.close()
    kept = [u for u in done if not u.get("rejet") and u.get("clean")]
    flagged = [u for u in done if u.get("rejet") and u.get("clean")]
    print("filtre : %d gardees, %d signalees (%.0f s)" % (len(kept), len(flagged), time.time() - t0), flush=True)

    # Arbitrage : le filtre s'etait trompe sur 55 % de ses rejets.
    if flagged:
        def judge_one(u):
            user = "CONSIGNE : %s\n\nATTENDU POUR CE REGLAGE :\n%s\n\nENTREE :\n%s\n\nSORTIE :\n%s" % (
                u["control"],
                "%s | %s | %s" % (spec.STYLING_RULES[u["styling"]],
                                  spec.STRUCTURE_RULES[u["structure"]],
                                  spec.CONTEXT_RULES[u["context"]]),
                u["dirty"], u["clean"])
            u["arbitrage"] = adj_call(user)
            return u
        adj_path = dst + ".adjudged"
        adj_done = budget_mod.done_ids(adj_path, lambda r: bool(r.get("arbitrage")))
        pending = [u for u in flagged if u["id"] not in adj_done]
        budget_mod.announce("arbitrage", len(flagged), len(adj_done), per_item_usd=(0.001 if PROVIDER == "deepseek" else 0.0))
        adj_stream = budget_mod.rewrite_kept(adj_path, adj_done)

        def judge_and_keep(u):
            r = judge_one(u)
            with WRITE_LOCK:
                adj_stream.write(json.dumps(r, ensure_ascii=False) + chr(10)); adj_stream.flush()
            return r

        judged = list(adj_done.values()) + (pool(pending, judge_and_keep) if pending else [])
        adj_stream.close()
        recovered = [u for u in judged if (u.get("arbitrage") or {}).get("conforme")]
        motifs = collections.Counter((u.get("arbitrage") or {}).get("motif")
                                     for u in judged if not (u.get("arbitrage") or {}).get("conforme"))
        print("arbitrage : %d recuperees sur %d (%.0f %%) | rejets confirmes %s"
              % (len(recovered), len(judged), 100.0 * len(recovered) / max(1, len(judged)), dict(motifs)),
              flush=True)
        for u in recovered:
            u.pop("rejet", None)
        kept += recovered

    with open(dst, "w", encoding="utf-8") as f:
        for u in kept:
            f.write(json.dumps(u, ensure_ascii=False) + "\n")
    combos = collections.Counter((u["styling"], u["structure"], u["context"]) for u in kept)
    print("PAIRES ECRITES : %d  |  %d combinaisons de controle" % (len(kept), len(combos)), flush=True)
    print("-> %s" % dst, flush=True)


if __name__ == "__main__":
    main()
