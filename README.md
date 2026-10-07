# 👻 Desk Ghost

*Your busywork, haunted away.*

**Demo video:** [desk_ghost_demo.mp4](desk_ghost_demo.mp4)

A terminal that drives your Mac, but only through safe skills. It watches what you are doing and guesses your next step; press Tab and it does it.

**Workflow it replaces:** the dozen tiny chores you do between real work (tidy Downloads, look something up from a copied link, draft a reply, set a timer, switch to call mode). Each one is 30 seconds of context switching; Desk Ghost does them from one prompt, or before you ask.

**Why it is safe:** the model never gets a shell. It can only call skills from a fixed registry (17 today). Unknown skills are blocked, file moves preview first and are undoable, and every action is logged to `~/.deskghost/journal.jsonl`.

## How it works

```
context watcher (front app, clipboard, Downloads, time)
        │ every 4 s, only when context changes
        ▼
predictor (Claude) ──► ghost suggestion in the prompt ──► Tab accepts
                                                             │
you type a request ──────────────────────────────────────────┤
                                                             ▼
                              brain picks skills (JSON, registry only)
                                         │
              ┌──────────────────────────┼──────────────────────────┐
              ▼                          ▼                          ▼
     local safe skills           look (screenshot +          cloud skills on an
  (apps, volume, dark mode,       vision description)        Agent37 instance
   music, timer, notes,                                     (research, drafting)
   tidy + undo, clipboard)
              └─────────────── journal + undo log ──────────────────┘
```

Stack: **Agent37** cloud instance runs the cloud skills (and is the brain if no Claude key). **Claude** powers the brain, the next-step predictor and screen reading.

## Run

```bash
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt
export ANTHROPIC_API_KEY=...   # brain + predictor + look
export AGENT37_API_KEY=sk_live_...   # cloud skills
.venv/bin/python ghost.py
```

With no keys it still runs on offline rules. `skills` lists everything, `cloud off` deletes the Agent37 instance.
