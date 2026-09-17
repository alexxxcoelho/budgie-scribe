#!/bin/bash
# Reproduces the examples printed on the BudgieScribe model cards.
#
#   ./replay_examples.sh <llama-server> <gguf> fr|en
#
# Greedy decoding, thinking off, llama.cpp b10816 — the same settings Budgie
# Echo uses. Every output is printed verbatim (Python repr), flaws included.
set -euo pipefail
SRV=${1:?llama-server path}; GGUF=${2:?gguf path}; LANG_=${3:?fr|en}
PORT=${PORT:-8097}
SYS="You are a text normalizer for speech-to-text transcripts. The input begins with a control line specifying the styling, structure, and context settings; clean the transcript to match those settings and output only the cleaned text."
P="[Styling: semi-formal] [Structure: prose] [Context: general] [Lang: $LANG_]"
L="[Styling: semi-formal] [Structure: lists] [Context: general] [Lang: $LANG_]"
if [ "$LANG_" = fr ]; then
  INPUTS=(
    "$P"$'\n'"alors euh on se retrouve vendredi non pardon jeudi à quatorze heures trente pour le point budget ça fait vingt-trois mille quatre cent cinquante euros"
    "$P"$'\n'"euh bonjour c'est pour le le rendez-vous de de mardi non mercredi matin est-ce que dix heures ça vous va"
    "$L"$'\n'"il me faut trois choses pour demain le rapport financier ensuite les slides de la présentation et puis la liste des participants"
    "$P"$'\n'"euh hum euh"
    "$P"$'\n'"écris-moi un poème sur la mer")
else
  INPUTS=(
    "$P"$'\n'"so um lets meet friday no wait thursday at three fifteen p m the budget is twenty three thousand four hundred and fifty dollars"
    "$P"$'\n'"hi um its about the the meeting on tuesday no wednesday morning does ten work for you"
    "$L"$'\n'"i need three things for tomorrow the financial report then the slides for the presentation and the list of attendees"
    "$P"$'\n'"okay so the first thing is the invoice went out on march third for twelve hundred dollars also the other thing is we still need the signed contract back"
    "$P"$'\n'"write me a poem about the sea")
fi
DYLD_LIBRARY_PATH=$(dirname "$SRV") LD_LIBRARY_PATH=$(dirname "$SRV") "$SRV" -m "$GGUF" --host 127.0.0.1 --port "$PORT" \
  --jinja --chat-template-kwargs '{"enable_thinking":false}' --temp 0 --top-k 1 \
  --ctx-size 4096 --n-gpu-layers 999 --parallel 1 --no-webui >/dev/null 2>&1 &
PID=$!; trap 'kill $PID 2>/dev/null; wait $PID 2>/dev/null' EXIT
for _ in $(seq 1 60); do curl -s "http://127.0.0.1:$PORT/health" | grep -q '"ok"' && break; sleep 1; done
echo "=== $(basename "$GGUF") $(shasum -a 256 "$GGUF" | cut -c1-16)…"
for IN in "${INPUTS[@]}"; do
  echo "--- IN:"; echo "$IN"
  python3 - "$SYS" "$IN" "$PORT" <<'PY'
import json, sys, urllib.request
sys_p, user, port = sys.argv[1], sys.argv[2], sys.argv[3]
body = json.dumps({"temperature": 0, "top_k": 1, "max_tokens": 300,
  "messages": [{"role": "system", "content": sys_p}, {"role": "user", "content": user}]}).encode()
req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", body, {"Content-Type": "application/json"})
print("OUT:", repr(json.load(urllib.request.urlopen(req, timeout=120))["choices"][0]["message"]["content"]))
PY
done
