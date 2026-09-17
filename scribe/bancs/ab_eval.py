# -*- coding: utf-8 -*-
"""Comparaison A/B en aveugle entre deux jeux de sorties.

Usage : ab_eval.py <base.jsonl> <candidat.jsonl> <verdicts.jsonl>
Ecrit les verdicts, et imprime UNE ligne JSON de synthese sur la derniere
ligne de stdout — c'est ce que la chaine de nuit lit.

L'ordre A/B est tire au sort par cas : un juge qui verrait toujours le
candidat en B developperait un biais de position.
"""
import json, os, sys, time, random, threading, queue, collections, urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd

# Local par defaut depuis le 2026-09-02. Le juge A/B a ete mesure contre
# DeepSeek sur deux verites terrain qui ne dependent d'aucun arbitre :
#   - EGALITE FORCEE : 18 des 80 cas ont deux sorties identiques au caractere
#     pres, donc « egalite » est la seule reponse defendable. gemma-12b-qat
#     fait 18/18, comme DeepSeek.
#   - MIROIR : le meme cas pose dans les deux sens doit donner la reponse
#     inverse. Sur les 62 cas disputes, gemma-12b-qat fait 83,9 % contre 77,4 %
#     a DeepSeek — le local est PLUS coherent que l'arbitre payant.
# AB_PROVIDER=deepseek repasse par l'API.
PROVIDER = os.environ.get("AB_PROVIDER", "llamacpp")
if PROVIDER == "deepseek":
    API = "https://api.deepseek.com/v1/chat/completions"
    KEY = json.load(open(os.path.expanduser("~/.budgie/custom_api_keys.json"),
                         encoding="utf-8"))["deepseek"]
    MODEL = "deepseek-v4-flash"
    WORKERS = 12
else:
    API = os.environ.get("LLAMACPP_URL", "http://127.0.0.1:8899") + "/v1/chat/completions"
    KEY = None
    MODEL = os.environ.get("AB_MODEL", "gemma-12b-qat")
    WORKERS = 4          # llama-server n'ouvre que 4 slots
SEED = 20260902

# Chargee via chemins.prompt() : SCRIBE_LANG=en cherche d'abord _sys_ab_en.txt
# (voir chemins.py). Avant, cette invite etait dupliquee en dur ici ET dans
# scribe/prompts/_sys_ab.txt — deux endroits a mettre a jour a chaque
# retouche, et rien ne garantissait qu'ils restaient identiques.
SYSTEM = chemins.prompt("_sys_ab.txt")


def call(user, retries=3):
    corps = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    if PROVIDER != "deepseek":
        # Gemma raisonne dans `reasoning_content` et non dans `content` :
        # laissee libre, la reflexion epuise le budget et le verdict revient
        # vide. Coupee : 3 s au lieu de 50, meme verdict.
        corps.update({"max_tokens": 1500,
                      "chat_template_kwargs": {"enable_thinking": False},
                      "reasoning_effort": "none"})
    body = json.dumps(corps).encode("utf-8")
    entetes = {"Content-Type": "application/json"}
    if KEY:
        entetes["Authorization"] = "Bearer " + KEY
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(API, data=body, headers=entetes)
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(json.load(r)["choices"][0]["message"]["content"])
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(str(last))


def main():
    base_p, cand_p, dst = sys.argv[1], sys.argv[2], sys.argv[3]
    base = {json.loads(l)["id"]: json.loads(l) for l in open(base_p, encoding="utf-8")}
    cand = {json.loads(l)["id"]: json.loads(l) for l in open(cand_p, encoding="utf-8")}
    ids = sorted(set(base) & set(cand))
    rng = random.Random(SEED)
    key = {}
    jobs = []
    for i in ids:
        swap = rng.random() < 0.5
        key[i] = {"A": "tuned" if swap else "base", "B": "base" if swap else "tuned"}
        jobs.append((i, base[i]["control"] + "\n" + base[i]["dirty"],
                     cand[i]["out"] if swap else base[i]["out"],
                     base[i]["out"] if swap else cand[i]["out"]))

    q = queue.Queue()
    for j in jobs:
        q.put(j)
    out = []
    lock = threading.Lock()

    def worker():
        while True:
            try:
                i, entree, a, b = q.get_nowait()
            except queue.Empty:
                return
            try:
                v = call("ENTREE :\n%s\n\nA :\n%s\n\nB :\n%s" % (entree, a, b))
            except Exception as e:
                v = {"erreur": str(e)[:150]}
            v["id"] = i
            with lock:
                out.append(v)

    ts = [threading.Thread(target=worker, daemon=True) for _ in range(WORKERS)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    with open(dst, "w", encoding="utf-8") as f:
        for v in out:
            f.write(json.dumps(v, ensure_ascii=False) + "\n")

    win = collections.Counter()
    faults = collections.defaultdict(lambda: [0, 0])   # [base, tuned]
    for v in out:
        k = key.get(v["id"])
        if not k or "gagnant" not in v:
            continue
        g = v["gagnant"]
        win[k.get(g, "egalite") if g in ("A", "B") else "egalite"] += 1
        for side, slot in (("a", "A"), ("b", "B")):
            who = 0 if k[slot] == "base" else 1
            for fl in (v.get(side + "_fautes") or []):
                if fl != "aucune":
                    faults[fl][who] += 1
    summary = {"cases": len(out), "tuned": win["tuned"], "base": win["base"],
               "egalite": win["egalite"], "faults": {k: v for k, v in faults.items()}}
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
