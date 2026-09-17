# -*- coding: utf-8 -*-
"""Passe de lecture par agent — DeepSeek V4 Flash lit et juge chaque sortie.

Ce n'est pas un score. Chaque cas est lu, classe dans une taxonomie d'echecs,
et cite ses propres preuves. Un compteur ne trouve que ce qu'on a pense a
compter (notes d'entrainement §D10).

Usage :
  python read_pass.py <in.jsonl> <out.jsonl> [--mode dirty|ab] [--limit N]

  mode dirty : juge la sortie ASR Cohere contre la reference Whisper.
  mode ab    : juge deux sorties Scribe (avant / apres fine-tune) sur la meme entree.
"""
import json, os, sys, time, threading, queue, urllib.request, urllib.error

API = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-v4-flash"
KEY = json.load(open(os.path.expanduser("~/.budgie/custom_api_keys.json"), encoding="utf-8"))["deepseek"]
MAX_CHARS = 24000
WORKERS = 8

SYSTEM_DIRTY = """Tu es relecteur qualité pour un corpus de transcription automatique en français.

On te donne, pour un même enregistrement audio, deux transcriptions produites par deux moteurs différents :
- REFERENCE : sortie de Whisper (moteur historique, parfois incomplet, ponctuation approximative)
- CANDIDAT  : sortie de Cohere Transcribe (moteur évalué)

Tu n'as PAS l'audio. Tu juges donc uniquement ce qui est décidable depuis les textes.

Ta tâche : dire si le CANDIDAT est utilisable comme donnée d'entraînement.

Le défaut à traquer en priorité est la BOUCLE DÉGÉNÉRÉE : le décodeur se met à répéter
une phrase ou un segment en continu, souvent sur de l'audio silencieux ou bruité. Elle se
reconnaît à une répétition quasi identique répétée bien au-delà de ce qu'un locuteur ferait.

Second défaut : le CONTENU INVENTÉ — le candidat introduit un sujet, des entités ou des
phrases entières qui n'ont aucune contrepartie dans la référence, sans que ce soit une
simple correction de mot mal entendu.

Troisième défaut : la PERTE — le candidat omet une part substantielle de ce que porte la référence.

Attention, ce ne sont PAS des défauts, ce sont des améliorations attendues :
- ponctuation et capitalisation meilleures
- accords, homophones et conjugaisons corrigés (« de ce donné » -> « de se donner »)
- hésitations légèrement lissées
- un mot mal entendu remplacé par un mot plausible et proche
- un écart de longueur modéré (±20 %) dû à une segmentation différente

Réponds UNIQUEMENT par un objet JSON, sans texte autour :
{"verdict": "utilisable" | "suspect" | "inutilisable",
 "defauts": ["boucle"|"invention"|"perte"|"aucun", ...],
 "gravite": 0-3,
 "preuve": "citation courte et littérale du candidat qui prouve le défaut, ou \\"\\" si aucun",
 "explication": "une à deux phrases, en français"}"""

SYSTEM_AB = """Tu es relecteur qualité pour un normaliseur de transcription français.

On te donne une ENTREE (transcription ASR brute) et deux normalisations : A et B.
Tu ne sais pas laquelle vient de quel modèle, et l'ordre est aléatoire.

Le travail attendu d'un normaliseur : retirer les hésitations et faux départs, trancher
les auto-corrections en gardant la valeur finale, corriger la ponctuation, et rendre le
texte lisible — SANS JAMAIS changer le sens.

Les fautes graves, par ordre de gravité décroissante :
1. INVERSION DE SENS — une négation retournée, un fait changé
2. INVENTION — un mot de contenu, une entité, une date ou un chiffre absent de l'entrée
3. SUPPRESSION SILENCIEUSE — une proposition entière de l'entrée qui disparaît
4. BOUCLE — répétition dégénérée
5. OBEISSANCE — l'entrée contient un ordre ou une question et le modèle y répond au lieu de le normaliser

Réponds UNIQUEMENT par un objet JSON, sans texte autour :
{"gagnant": "A" | "B" | "egalite",
 "a_fautes": ["inversion"|"invention"|"suppression"|"boucle"|"obeissance"|"aucune", ...],
 "b_fautes": [...],
 "preuve": "citation littérale qui justifie le verdict",
 "explication": "une à deux phrases, en français"}"""


def call(system, user, retries=4):
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(API, data=body, headers={
            "Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                payload = json.load(r)
            text = payload["choices"][0]["message"]["content"]
            usage = payload.get("usage", {})
            return json.loads(text), usage
        except Exception as e:  # réseau, 429, JSON malformé
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("échec après %d tentatives : %s" % (retries, last))


def clip(text, budget=MAX_CHARS):
    if len(text) <= budget:
        return text, False
    half = budget // 2
    return text[:half] + "\n[…COUPÉ POUR LA LECTURE…]\n" + text[-half:], True


def run(rows, build_user, system, out_path):
    q = queue.Queue()
    for i, r in enumerate(rows):
        q.put((i, r))
    results = [None] * len(rows)
    lock = threading.Lock()
    counters = {"in": 0, "out": 0, "err": 0, "done": 0}

    def worker():
        while True:
            try:
                i, r = q.get_nowait()
            except queue.Empty:
                return
            try:
                verdict, usage = call(system, build_user(r))
                with lock:
                    counters["in"] += usage.get("prompt_tokens", 0)
                    counters["out"] += usage.get("completion_tokens", 0)
            except Exception as e:
                verdict = {"erreur": str(e)}
                with lock:
                    counters["err"] += 1
            verdict["id"] = r["id"]
            results[i] = verdict
            with lock:
                counters["done"] += 1
                if counters["done"] % 10 == 0:
                    print("   lu %d/%d" % (counters["done"], len(rows)), flush=True)
            q.task_done()

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(WORKERS)]
    started = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    with open(out_path, "w", encoding="utf-8") as f:
        for v in results:
            if v:
                f.write(json.dumps(v, ensure_ascii=False) + "\n")
    print("lecture terminée en %.0f s | tokens in=%d out=%d | erreurs=%d"
          % (time.time() - started, counters["in"], counters["out"], counters["err"]))
    # tarif public DeepSeek V4 Flash, ordre de grandeur seulement
    print("coût estimé : ~%.3f $" % (counters["in"] / 1e6 * 0.028 + counters["out"] / 1e6 * 0.42))
    return results


def main():
    src, dst = sys.argv[1], sys.argv[2]
    mode = "dirty"
    limit = None
    for i, a in enumerate(sys.argv):
        if a == "--mode":
            mode = sys.argv[i + 1]
        if a == "--limit":
            limit = int(sys.argv[i + 1])

    rows = [json.loads(l) for l in open(src, encoding="utf-8")]
    if limit:
        rows = rows[:limit]
    print("mode=%s | %d cas | modèle=%s | %d workers" % (mode, len(rows), MODEL, WORKERS))

    if mode == "dirty":
        def build(r):
            ref, c1 = clip(r["reference"], MAX_CHARS // 2)
            cand, c2 = clip(r["candidat"], MAX_CHARS // 2)
            note = "\n(NOTE : textes coupés en leur milieu pour la lecture.)" if (c1 or c2) else ""
            return ("REFERENCE (Whisper) :\n%s\n\nCANDIDAT (Cohere) :\n%s%s" % (ref, cand, note))
        system = SYSTEM_DIRTY
    else:
        def build(r):
            entree, _ = clip(r["entree"], MAX_CHARS // 3)
            a, _ = clip(r["a"], MAX_CHARS // 3)
            b, _ = clip(r["b"], MAX_CHARS // 3)
            return "ENTREE :\n%s\n\nA :\n%s\n\nB :\n%s" % (entree, a, b)
        system = SYSTEM_AB

    run(rows, build, system, dst)


if __name__ == "__main__":
    main()
