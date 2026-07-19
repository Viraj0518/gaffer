# 🎙 Etymology Voice

A single, self-contained page: ask by voice — *"what is the etymology of
serendipity?"* — and get the word's origins, what it meant back then, how it
evolved, and what it means today (slang included).

## Run it

No build, no server, no API keys. Either:

```bash
# open the file directly
open etymology/index.html          # macOS
xdg-open etymology/index.html      # Linux

# or serve it (nicer for mic permissions)
python3 -m http.server -d etymology 8080   # → http://localhost:8080
```

Voice input needs Chrome, Edge, or Safari (the Web Speech API). Firefox users
can type words instead.

## How it works

- **Voice mode** — browser Web Speech API; tap the orb, or flip on hands-free
  mode to keep listening. Answers are spoken back via speech synthesis.
- **Fuzzy word grab** — the target word is extracted from natural phrasings
  ("where does *rizz* come from", "origin of *yeet*", or just the bare word).
  If the mic mishears, candidates from Wiktionary search + Datamuse
  sound-alike matching are ranked by edit distance: confident matches
  auto-correct, otherwise you get "did you mean…" chips.
- **Etymology** — Wiktionary's etymology section (origin-language chain,
  original meaning, evolution) plus current definitions from the Wikimedia
  REST API.
- **Slang** — Urban Dictionary's API fills in for words Wiktionary doesn't
  have, and adds a "street usage" section for words it does.

All lookups are client-side `fetch` calls to public, CORS-enabled APIs.
Wiktionary content is CC BY-SA; Urban Dictionary content is crowd-sourced and
may be unreliable or explicit.
