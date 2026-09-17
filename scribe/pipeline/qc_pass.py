# -*- coding: utf-8 -*-
"""Controle qualite du cote SALE — jugement seul, aucune retouche.

Le juge ne corrige RIEN. Il dit si la transcription est saine, et pourquoi pas.
Une transcription verolee — boucle degeneree, phrase hallucinee sur du silence,
milieu d'enregistrement effondre — empoisonne l'entrainement des deux cotes :
elle devient l'entree du professeur, qui produit une sortie propre a partir
d'une entree fausse, et le modele apprend a fabriquer du sens sur du bruit.

Usage : python qc_pass.py <cohere.jsonl> <corpus.jsonl> <out.jsonl>
"""
import json, os, sys, time, threading, queue, urllib.request, collections

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chemins                 # RACINE / PROMPTS / TRAVAIL — voir scribe/chemins.py

SP = chemins.TRAVAIL           # donnees : hors depot ; SCRIBE_TRAVAIL, sinon le cwd

# ── Grille de jugement ──────────────────────────────────────────────────────
# BINAIRE par defaut depuis le 2026-09-02. L'echelle a trois classes
# sain/suspect/verole a ete abandonnee sur mesure : DeepSeek ne reproduisait
# que 57 % de ses PROPRES verdicts « verole » sur les memes entrees a
# temperature 0, alors que l'axe binaire tenait a 93 %. La frontiere
# suspect/verole ne portait donc aucune information reproductible.
#
# La grille binaire definit l'OK par une liste FERMEE de differences tolerees
# et rend tout le reste KO, avec UNE cause prise dans une liste fermee et un
# ordre de priorite. Deux modeles que 19 milliards de parametres separent
# s'accordent a 95,0 % sur le verdict (kappa 0,88) et a 85,4 % sur la cause.
#
# QC_GRILLE=3classes restaure l'ancienne, pour rejouer un lot historique.
GRILLE = os.environ.get("QC_GRILLE", "binaire")

# ── Fournisseur ─────────────────────────────────────────────────────────────
# Local par defaut : llama-server repond sur :8899 sans jeton (voir juge.ps1).
# QC_PROVIDER=deepseek repasse par l'API payante.
PROVIDER = os.environ.get("QC_PROVIDER", "llamacpp")
if PROVIDER == "deepseek":
    API = "https://api.deepseek.com/v1/chat/completions"
    MODEL = os.environ.get("QC_MODEL", "deepseek-v4-flash")
    KEY = json.load(open(os.path.expanduser("~/.budgie/custom_api_keys.json"),
                         encoding="utf-8"))["deepseek"]
    WORKERS = int(os.environ.get("QC_WORKERS", "12"))
else:
    API = os.environ.get("LLAMACPP_URL", "http://127.0.0.1:8899") + "/v1/chat/completions"
    MODEL = os.environ.get("QC_MODEL", "gemma-12b-qat")
    KEY = None
    # llama-server ouvre 4 slots ; au-dela les requetes sont refusees net.
    WORKERS = int(os.environ.get("QC_WORKERS", "4"))
MAX_CHARS = 26000

SYSTEM_3CLASSES = """Tu es controleur qualite d'un corpus de transcription automatique.

Ton role est de JUGER, jamais de corriger. Tu ne produis aucun texte normalise,
aucune version amelioree, aucune suggestion de reecriture. Tu rends un verdict.

On te donne deux transcriptions du MEME audio, par deux moteurs differents :
- REFERENCE : Whisper, moteur historique. Parfois incomplet, ponctuation approximative.
- CANDIDAT  : Cohere Transcribe, le moteur evalue. C'est LUI que tu juges.

Tu n'as pas l'audio. Tu ne juges donc que ce qui est decidable depuis les textes.

DEFAUTS DISQUALIFIANTS, par gravite decroissante :

1. BOUCLE — le decodeur repete une phrase ou un segment en continu, bien au-dela
   de ce qu'un locuteur ferait. Souvent sur de l'audio silencieux ou bruite.

2. HALLUCINATION — le candidat introduit un sujet, des entites ou des phrases
   entieres sans aucune contrepartie dans la reference. A distinguer d'un mot
   mal entendu remplace par un mot proche, qui est normal.

3. EFFONDREMENT — le candidat perd une part substantielle de ce que porte la
   reference, typiquement le milieu de l'enregistrement.

4. LANGUE — le candidat bascule dans une langue que la reference ne porte pas.

5. INCOHERENCE — de longs passages sans structure syntaxique interpretable.

NE SONT PAS DES DEFAUTS, ce sont les ameliorations attendues du moteur evalue :
- meilleure ponctuation, meilleure capitalisation
- accords, homophones et conjugaisons corriges (« de ce donne » -> « de se donner »)
- hesitations legerement lissees
- un mot mal entendu remplace par un mot plausible et proche
- un ecart de longueur modere, jusqu'a environ 20 %, du a une segmentation differente
- un contenu cru, intime ou vulgaire : tu juges la FIDELITE DE TRANSCRIPTION,
  jamais le contenu lui-meme, qui ne te regarde pas

Reponds UNIQUEMENT par un objet JSON, sans texte autour :
{"verdict": "sain" | "suspect" | "verole",
 "defauts": ["boucle"|"hallucination"|"effondrement"|"langue"|"incoherence"|"aucun", ...],
 "gravite": 0-3,
 "preuve": "citation LITTERALE et courte du candidat qui montre le defaut, ou \\"\\"",
 "explication": "une a deux phrases, en francais",
 "portion_atteinte": "aucune" | "fin" | "debut" | "milieu" | "eparse" | "totale"}"""


SYSTEM = (chemins.prompt("_sys_qc_binaire.txt")
          if GRILLE == "binaire" else SYSTEM_3CLASSES)



def clip(text, budget):
    if len(text) <= budget:
        return text
    half = budget // 2
    return text[:half] + "\n[…COUPE POUR LA LECTURE…]\n" + text[-half:]


def call(user, retries=4):
    corps = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    if PROVIDER != "deepseek":
        # Gemma raisonne avant de repondre, et sa reflexion part dans
        # `reasoning_content`, PAS dans `content`. Laissee libre, elle epuise
        # le budget sans jamais ecrire le verdict : 50 s par appel et une
        # reponse vide, contre 3 s reflexion coupee, a verdict identique.
        corps.update({"max_tokens": 1500,
                      "chat_template_kwargs": {"enable_thinking": False},
                      "reasoning_effort": "none"})
    # Aucun plafond de tokens cote DeepSeek : il raisonne LUI AUSSI, et ses
    # `reasoning_tokens` comptent dans max_tokens — un plafond decapite son
    # JSON en silence.
    body = json.dumps(corps).encode("utf-8")
    entetes = {"Content-Type": "application/json"}
    if KEY:
        entetes["Authorization"] = "Bearer " + KEY
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(API, data=body, headers=entetes)
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                payload = json.load(r)
            return json.loads(payload["choices"][0]["message"]["content"]), payload.get("usage", {})
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("echec: %s" % last)


def build_user(r, ref):
    src = ref.get(r["id"], {})
    # `ref_text` d'abord : les unites VoxPopuli (anglais) portent une reference
    # humaine sous ce nom, pas `asr_whisper` (qui reste le nom du champ pour le
    # corpus francais, transcrit par Whisper et non par un humain). Un
    # enregistrement francais n'a jamais de `ref_text` : le repli est donc
    # invisible cote francais.
    reference = src.get("ref_text") or src.get("asr_whisper", "")
    return "REFERENCE (Whisper) :\n%s\n\nCANDIDAT (Cohere) :\n%s" % (
        clip(reference, MAX_CHARS // 2), clip(r["text"], MAX_CHARS // 2))


def main():
    cohere_path, corpus_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    ref = {json.loads(l)["id"]: json.loads(l) for l in open(corpus_path, encoding="utf-8")}
    rows = [json.loads(l) for l in open(cohere_path, encoding="utf-8")]
    print("%d transcriptions a juger | modele=%s | %d workers" % (len(rows), MODEL, WORKERS))

    # ── Reprise : ce qui a ete paye est garde ───────────────────────────────
    # Le 2026-09-01, ce lot s'est vide en cours de route : 278 verdicts valides
    # et 7 446 en erreur. Relancer le tout aurait rejete les 278 deja payes.
    # On repart donc de ce qui existe et on ne refait QUE ce qui manque.
    import budget as budget_mod

    def is_valid(rec):
        v = (rec.get("verdict") or "").replace("é", "e").strip()
        # les deux grilles : rien d acquis ne doit etre refait ni repaye
        return v in ("sain", "suspect", "verole") or v.upper() in ("OK", "KO")

    acquired = budget_mod.done_ids(out_path, is_valid)
    todo = [r for r in rows if r["id"] not in acquired]
    # Le tarif ne vaut QUE pour DeepSeek. En local le cout est nul, et annoncer
    # « ~3,78 $ » pour un travail gratuit est un mensonge alarmant.
    tarif = 0.00049 if PROVIDER == "deepseek" else 0.0
    budget_mod.announce("QC %s [%s]" % (os.path.basename(cohere_path), PROVIDER),
                        len(rows), len(acquired), per_item_usd=tarif)
    if not todo:
        print("tout est deja acquis — rien a repayer", flush=True)
        summarize(out_path)
        return
    rows = todo

    q = queue.Queue()
    for i, r in enumerate(rows):
        q.put((i, r))
    counters = {"in": 0, "out": 0, "err": 0, "done": 0}
    lock = threading.Lock()
    # Le fichier est reecrit avec les seuls verdicts ACQUIS — les lignes en
    # erreur du run precedent disparaissent — puis rouvert en AJOUT. Chaque
    # verdict est ecrit et vide sur disque des qu'il arrive : si le lot
    # s'interrompt, rien de paye n'est perdu.
    stream = budget_mod.rewrite_kept(out_path, acquired)

    def worker():
        while True:
            try:
                i, r = q.get_nowait()
            except queue.Empty:
                return
            user = build_user(r, ref)
            try:
                v, usage = call(user)
                with lock:
                    counters["in"] += usage.get("prompt_tokens", 0)
                    counters["out"] += usage.get("completion_tokens", 0)
            except Exception as e:
                v = {"verdict": "erreur", "erreur": str(e)}
                with lock:
                    counters["err"] += 1
            v["id"] = r["id"]
            v["lang"] = ref.get(r["id"], {}).get("lang")
            v["audio_seconds"] = r.get("audio_seconds")
            v["words"] = r.get("words")
            with lock:
                counters["done"] += 1
                stream.write(json.dumps(v, ensure_ascii=False) + "\n")
                stream.flush()
                if counters["done"] % 50 == 0:
                    print("   %d/%d" % (counters["done"], len(rows)), flush=True)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(WORKERS)]
    t0 = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    stream.close()

    summarize(out_path, counters, time.time() - t0)


def summarize(out_path, counters=None, seconds=None):
    """Synthese lisible du fichier de verdicts, quel que soit le nombre
    de reprises qu'il a fallu pour le remplir."""
    verdicts = [json.loads(l) for l in open(out_path, encoding="utf-8")]
    counts = collections.Counter(v.get("verdict") for v in verdicts)
    faults = collections.Counter()
    for v in verdicts:
        for f in (v.get("defauts") or []):
            faults[f] += 1
    print("\njuge en %.0f s | tokens in=%d out=%d | erreurs=%d"
          % ((seconds or 0), (counters or {}).get("in", 0), (counters or {}).get("out", 0), (counters or {}).get("err", 0)))
    print("cout estime : ~%.2f $" % ((counters or {}).get("in", 0) / 1e6 * 0.028 + (counters or {}).get("out", 0) / 1e6 * 0.42))
    print("VERDICTS :", dict(counts))
    print("DEFAUTS  :", dict(faults))
    causes = collections.Counter()
    for v in verdicts:
        for c in (v.get("causes") or []):
            causes[c] += 1
    if causes:
        print("CAUSES   :", dict(causes))
    # « retenu » = sain dans l ancienne grille, OK dans la nouvelle
    keep = [v for v in verdicts
            if (v.get("verdict") or "").strip().upper() == "OK"
            or v.get("verdict") == "sain"]
    print("RETENU POUR L'ENTRAINEMENT : %d / %d (%.0f%%)"
          % (len(keep), len(verdicts), 100.0 * len(keep) / max(1, len(verdicts))))



if __name__ == "__main__":
    main()
