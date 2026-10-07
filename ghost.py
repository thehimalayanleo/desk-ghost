#!/usr/bin/env python3
"""Desk Ghost: a terminal that drives your Mac, but only through safe skills.

You type what you want; the brain picks from a fixed skill registry (no raw shell).
A watcher reads your context (front app, clipboard, Downloads) and predicts your
next step as a ghost suggestion. Press Tab to accept it.
Cloud skills (research, drafting) run on an Agent37 instance.
"""
import json, os, re, shutil, subprocess, threading, time, hashlib
from datetime import datetime
from pathlib import Path

import requests
import safety
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.formatted_text import HTML
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

con = Console()
HOME = Path.home()
GHOST_DIR = HOME / "DeskGhost"
STATE = HOME / ".deskghost"
for d in (GHOST_DIR / "notes", STATE):
    d.mkdir(parents=True, exist_ok=True)
JOURNAL = STATE / "journal.jsonl"
UNDO = STATE / "undo.json"
KEYS = STATE / "keys.env"  # saved once by `./deskghost --save-keys`, chmod 600
if KEYS.exists():
    for line in KEYS.read_text().splitlines():
        k, _, v = line.partition("=")
        if v and not os.environ.get(k):
            os.environ[k] = v
A37_KEY = os.environ.get("AGENT37_API_KEY")
CLAUDE = bool(os.environ.get("ANTHROPIC_API_KEY"))
MODEL = os.environ.get("GHOST_MODEL", "claude-opus-5-5")


def claude(content, system=None):
    import anthropic
    kw = {"system": system} if system else {}
    r = anthropic.Anthropic().messages.create(model=MODEL, max_tokens=4096, output_config={"effort": "low"},
                                              messages=[{"role": "user", "content": content}], **kw)
    return next((b.text for b in r.content if b.type == "text"), "").strip()
SAFE_APPS = {"Safari", "Notes", "Music", "Calendar", "Reminders", "Finder", "Preview",
             "Messages", "Mail", "Maps", "Photos", "Terminal", "Ghostty", "Google Chrome",
             "Slack", "Spotify", "Zoom", "System Settings", "Calculator", "TextEdit"}


def osa(script):
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=15)
    return (r.stdout or r.stderr).strip()


def log(event, **kw):
    with open(JOURNAL, "a") as f:
        f.write(json.dumps({"t": datetime.now().isoformat(timespec="seconds"), "event": event, **kw}) + "\n")


# ---------------- Agent37 cloud hand ----------------
class Cloud:
    API = "https://api.agent37.com/v1"

    def __init__(self):
        self.f = STATE / "instance.json"
        self.inst = json.loads(self.f.read_text()) if self.f.exists() else None
        self.session = None

    def ready(self):
        return bool(A37_KEY)

    def ensure(self):
        if self.inst:
            try:
                h = requests.get(f"{self.inst['url']}/v1/health", headers={"X-Agent37-Key": A37_KEY}, timeout=10)
                if h.ok:
                    return self.inst
            except requests.RequestException:
                pass
        con.print("[dim]👻 waking a cloud ghost on Agent37 (first time takes a minute)...[/]")
        r = requests.post(f"{self.API}/instances", headers={"Authorization": f"Bearer {A37_KEY}"},
                          json={"budget": {"credit_micros": 1_000_000}}, timeout=600)
        r.raise_for_status()
        j = r.json()
        self.inst = {"id": j["id"], "url": j.get("url") or f"https://{j['id']}.agent37.app"}
        self.f.write_text(json.dumps(self.inst))
        log("cloud_up", id=self.inst["id"])
        return self.inst

    def upload(self, p):
        """Copy a local file into the instance's sandbox; returns its path there."""
        inst = self.ensure()
        r = requests.put(f"{inst['url']}/v1/files/content", params={"path": f"~/inbox/{p.name}"},
                         headers={"X-Agent37-Key": A37_KEY}, data=p.read_bytes(), timeout=300)
        r.raise_for_status()
        return r.json().get("path") or f"~/inbox/{p.name}"

    def ask(self, text, files=None):
        inst = self.ensure()
        body = {"input": text}
        if files:
            body["files"] = files
        if self.session:
            body["session_id"] = self.session
        r = requests.post(f"{inst['url']}/v1/responses", headers={"X-Agent37-Key": A37_KEY}, json=body, timeout=600)
        r.raise_for_status()
        j = r.json()
        self.session = j.get("session_id", self.session)
        return j.get("output_text", "").strip()

    def down(self):
        if not self.inst:
            return "no cloud ghost running"
        requests.delete(f"{self.API}/instances/{self.inst['id']}", headers={"Authorization": f"Bearer {A37_KEY}"}, timeout=60)
        self.f.unlink(missing_ok=True)
        self.inst = None
        return "cloud ghost released (billing stopped)"


cloud = Cloud()

# ---------------- Skills: the only things the ghost can do ----------------
SKILLS = {}


def skill(name, desc, params=None, tier="safe"):
    def wrap(fn):
        SKILLS[name] = {"fn": fn, "desc": desc, "params": params or {}, "tier": tier}
        return fn
    return wrap


@skill("open_app", "Open a Mac app by name", {"name": "app name"})
def open_app(name):
    match = next((a for a in SAFE_APPS if a.lower() == name.lower()), None)
    if not match:
        return f"'{name}' is not on the safe app list"
    subprocess.run(["open", "-a", match])
    return f"opened {match}"


@skill("open_url", "Open a web page in the default browser", {"url": "http(s) url"})
def open_url(url):
    if not re.match(r"^https?://", url):
        url = "https://" + url
    subprocess.run(["open", url])
    return f"opened {url}"


@skill("set_volume", "Set output volume 0-100", {"level": "0-100"})
def set_volume(level):
    level = max(0, min(100, int(level)))
    osa(f"set volume output volume {level}")
    return f"volume {level}"


@skill("dark_mode", "Turn dark mode on or off", {"on": "true/false"})
def dark_mode(on):
    on = str(on).lower() in ("1", "true", "on", "yes")
    osa(f'tell application "System Events" to tell appearance preferences to set dark mode to {str(on).lower()}')
    return f"dark mode {'on' if on else 'off'}"


@skill("music", "Control Music: play, pause, next, previous", {"action": "play|pause|next|previous"})
def music(action):
    cmd = {"play": "play", "pause": "pause", "next": "next track", "previous": "previous track"}.get(action)
    if not cmd:
        return "unknown music action"
    osa(f'tell application "Music" to {cmd}')
    return f"music {action}"


@skill("notify", "Show a Mac notification", {"text": "message"})
def notify(text):
    osa(f'display notification {json.dumps(text)} with title "Desk Ghost"')
    return "notified"


@skill("say", "Speak text out loud", {"text": "what to say"})
def say(text):
    subprocess.Popen(["say", text[:300]])
    return "speaking"


@skill("timer", "Start a timer that notifies when done", {"minutes": "number", "label": "what for"})
def timer(minutes, label="timer"):
    secs = float(minutes) * 60
    threading.Timer(secs, lambda: (notify(f"⏰ {label} done"), say(f"{label} done"))).start()
    return f"timer {minutes} min: {label}"


@skill("note", "Save a note to ~/DeskGhost/notes", {"text": "note body"})
def note(text):
    p = GHOST_DIR / "notes" / f"{datetime.now():%Y-%m-%d_%H%M%S}.md"
    p.write_text(text + "\n")
    return f"saved {p.name}"


@skill("clipboard", "Read the clipboard", tier="look")
def clipboard():
    return subprocess.run(["pbpaste"], capture_output=True, text=True).stdout[:2000] or "(empty)"


@skill("copy", "Put text on the clipboard", {"text": "text"})
def copy(text):
    subprocess.run(["pbcopy"], input=text, text=True)
    return "copied"


@skill("status", "Battery, uptime and front app", tier="look")
def status():
    batt = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True).stdout.splitlines()[-1].strip()
    up = subprocess.run(["uptime"], capture_output=True, text=True).stdout.strip()
    return f"{batt}\n{up}\nfront: {front_app()}"


@skill("look", "Screenshot the screen and describe what is on it", tier="look")
def look():
    p = STATE / "look.jpg"
    subprocess.run(["screencapture", "-x", "-t", "jpg", str(p)])
    if not CLAUDE:
        return f"screenshot saved to {p} (set ANTHROPIC_API_KEY to describe it)"
    import base64
    subprocess.run(["sips", "-Z", "1440", str(p)], capture_output=True)
    b64 = base64.b64encode(p.read_bytes()).decode()
    return claude([{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                   {"type": "text", "text": "In 2 short sentences, what is the user doing on this screen?"}])


BUCKETS = {"Images": {".png", ".jpg", ".jpeg", ".gif", ".heic", ".webp", ".svg"},
           "Docs": {".pdf", ".doc", ".docx", ".txt", ".md", ".pages", ".key", ".pptx", ".xlsx", ".csv"},
           "Archives": {".zip", ".tar", ".gz", ".dmg", ".pkg"},
           "Media": {".mp4", ".mov", ".mp3", ".wav", ".m4a"},
           "Code": {".py", ".js", ".ts", ".json", ".ipynb", ".html"}}


def loose_downloads():
    d = HOME / "Downloads"
    return [p for p in d.iterdir() if p.is_file() and not p.name.startswith(".")] if d.exists() else []


@skill("tidy_downloads", "Sort loose files in ~/Downloads into folders (undoable)", {"apply": "false to preview, true to move"})
def tidy_downloads(apply=False):
    apply = str(apply).lower() in ("1", "true", "yes")
    plan = []
    for p in loose_downloads():
        b = next((k for k, v in BUCKETS.items() if p.suffix.lower() in v), None)
        if b:
            plan.append((p, p.parent / b / p.name))
    if not plan:
        return "Downloads already tidy"
    if not apply:
        counts = {}
        for _, dst in plan:
            counts[dst.parent.name] = counts.get(dst.parent.name, 0) + 1
        return f"would move {len(plan)} files: {counts}. Say 'tidy downloads for real' to do it."
    moved = []
    for src, dst in plan:
        dst.parent.mkdir(exist_ok=True)
        if not dst.exists():
            shutil.move(src, dst)
            moved.append([str(dst), str(src)])
    UNDO.write_text(json.dumps(moved))
    return f"moved {len(moved)} files. 'undo' puts them back."


@skill("undo", "Undo the last file move")
def undo():
    if not UNDO.exists():
        return "nothing to undo"
    moves = json.loads(UNDO.read_text())
    for cur, orig in moves:
        if Path(cur).exists() and not Path(orig).exists():
            shutil.move(cur, orig)
    UNDO.unlink()
    return f"put back {len(moves)} files"


def resolve(path):
    """'latest' = newest file in Downloads. Only files under your home folder."""
    if str(path).lower() in ("latest", "newest", "last", ""):
        loose = loose_downloads()
        if not loose:
            raise ValueError("no files in Downloads")
        return max(loose, key=lambda p: p.stat().st_mtime)
    p = Path(str(path)).expanduser().resolve()
    if HOME not in p.parents or not p.is_file():
        raise ValueError(f"{p} is not a file in your home folder")
    return p


def fresh(p, suffix):
    out, i = p.with_suffix(suffix), 1
    while out.exists():
        out, i = p.with_name(f"{p.stem}-{i}{suffix}"), i + 1
    return out


SIPS = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "heic": "heic", "tiff": "tiff", "gif": "gif", "pdf": "pdf", "bmp": "bmp"}


@skill("convert_image", "Convert an image to jpg/png/heic/tiff/gif/pdf (new file, original kept)", {"path": "file path or 'latest'", "to": "jpg|png|heic|tiff|gif|pdf"})
def convert_image(path, to="jpg"):
    p, fmt = resolve(path), SIPS.get(str(to).lower().strip("."))
    if not fmt:
        return f"can't convert to {to}"
    out = fresh(p, "." + ("jpg" if fmt == "jpeg" else fmt))
    r = subprocess.run(["sips", "-s", "format", fmt, str(p), "--out", str(out)], capture_output=True, text=True)
    return f"✨ {p.name} → {out.name}" if out.exists() else f"failed: {r.stderr.strip()[:200]}"


@skill("shrink_image", "Make an image smaller (max side in px, saves a -small jpg)", {"path": "file path or 'latest'", "max_px": "e.g. 1200"})
def shrink_image(path, max_px=1200):
    p = resolve(path)
    out = fresh(p.with_name(p.stem + "-small.jpg"), ".jpg")
    subprocess.run(["sips", "-Z", str(int(max_px)), "-s", "format", "jpeg", "-s", "formatOptions", "70", str(p), "--out", str(out)], capture_output=True)
    if not out.exists():
        return "failed"
    return f"✨ {p.name} {p.stat().st_size//1024} KB → {out.name} {out.stat().st_size//1024} KB"


@skill("convert_audio", "Convert audio to m4a/wav/aiff (new file)", {"path": "file path or 'latest'", "to": "m4a|wav|aiff"})
def convert_audio(path, to="m4a"):
    p = resolve(path)
    fmt = {"m4a": ["-f", "m4af", "-d", "aac"], "wav": ["-f", "WAVE", "-d", "LEI16"], "aiff": ["-f", "AIFF", "-d", "BEI16"]}.get(str(to).lower().strip("."))
    if not fmt:
        return f"can't convert audio to {to}"
    out = fresh(p, "." + str(to).lower().strip("."))
    subprocess.run(["afconvert", *fmt, str(p), str(out)], capture_output=True)
    return f"✨ {p.name} → {out.name}" if out.exists() else "failed"


@skill("compress_video", "Compress a video to a smaller 720p/1080p mp4 (new file)", {"path": "file path or 'latest'", "quality": "720|1080"})
def compress_video(path, quality="720"):
    p = resolve(path)
    preset = "Preset1920x1080" if str(quality).startswith("1080") else "Preset1280x720"
    out = fresh(p.with_name(p.stem + "-small.mp4"), ".mp4")
    subprocess.run(["avconvert", "--source", str(p), "--preset", preset, "--output", str(out)], capture_output=True, timeout=600)
    if not out.exists():
        return "failed"
    return f"✨ {p.name} {p.stat().st_size//1048576} MB → {out.name} {out.stat().st_size//1048576} MB"


@skill("reveal", "Show a file in Finder", {"path": "file path or 'latest'"})
def reveal(path):
    p = resolve(path)
    subprocess.run(["open", "-R", str(p)])
    return f"showing {p.name}"


@skill("cloud_research", "Research something on the web via the Agent37 cloud ghost", {"query": "question"}, tier="cloud")
def cloud_research(query):
    return cloud.ask(f"Research this and answer in under 120 words with 2-3 source links: {query}")


@skill("cloud_file", "Send a file into the Agent37 sandbox and have the cloud ghost read it (summary, action items, Q&A); it never runs on your Mac", {"path": "file path or 'latest'", "task": "what to do with it"}, tier="cloud")
def cloud_file(path, task="Summarize this in 5 bullets, then list any action items or deadlines."):
    p = resolve(path)
    if p.stat().st_size > 50 * 1024 * 1024:
        return "file too big for the sandbox (50 MB max here)"
    remote = cloud.upload(p)
    log("cloud_upload", local=str(p), remote=remote)
    return f"☁️ read in Agent37 sandbox ({remote})\n\n" + cloud.ask(f"{task} Plain text, short.", files=[remote])


@skill("cloud_draft", "Draft text (email, message, summary) via the Agent37 cloud ghost", {"task": "what to write"}, tier="cloud")
def cloud_draft(task):
    out = cloud.ask(f"Write this. Plain, short, no preamble: {task}")
    copy(out)
    return out + "\n\n(copied to clipboard)"


# ---------------- Context + brain ----------------
def front_app():
    asn = subprocess.run(["lsappinfo", "front"], capture_output=True, text=True).stdout.strip()
    out = subprocess.run(["lsappinfo", "info", "-only", "name", asn], capture_output=True, text=True).stdout
    m = re.search(r'^"([^"]+)"', out.strip())
    return m.group(1) if m else "?"


def context():
    clip = subprocess.run(["pbpaste"], capture_output=True, text=True).stdout.strip()[:200]
    loose = loose_downloads()
    newest = max(loose, key=lambda p: p.stat().st_mtime).name if loose else None
    return {"time": f"{datetime.now():%a %H:%M}", "front_app": front_app(), "clipboard": clip,
            "loose_downloads": len(loose), "newest_download": newest}


def skill_menu():
    return "\n".join(f"- {n}({', '.join(f'{k}: {v}' for k, v in s['params'].items())}): {s['desc']}"
                     for n, s in SKILLS.items())


SYS = ("You are Desk Ghost, a Mac helper that can ONLY act through these skills:\n{menu}\n"
       "Never invent skills. If the request is unsafe or not covered, say so with no calls. "
       "Reply ONLY with JSON: {{\"say\": \"one short line\", \"calls\": [{{\"skill\": name, \"args\": {{...}}}}]}}")


def brain(prompt):
    sys = SYS.format(menu=skill_menu())
    if CLAUDE:
        txt = claude(prompt, system=sys)
    elif cloud.ready():
        txt = cloud.ask(sys + "\n\nUser: " + prompt)
    else:
        return rules(prompt)
    m = re.search(r"\{.*\}", txt, re.S)
    try:
        return json.loads(m.group(0)) if m else {"say": txt, "calls": []}
    except json.JSONDecodeError:
        return {"say": txt, "calls": []}


def rules(prompt):
    """Offline fallback so the ghost still works with no keys."""
    p = prompt.lower()
    table = [(r"tidy|clean.*download", "tidy_downloads", {"apply": "for real" in p}), (r"undo", "undo", {}),
             (r"dark", "dark_mode", {"on": "off" not in p}), (r"pause", "music", {"action": "pause"}),
             (r"play|music", "music", {"action": "play"}), (r"status|battery", "status", {}),
             (r"look|screen", "look", {}), (r"clipboard", "clipboard", {})]
    for pat, s, a in table:
        if re.search(pat, p):
            return {"say": f"running {s}", "calls": [{"skill": s, "args": a}]}
    if m := re.search(r"timer (\d+)", p):
        return {"say": "timer set", "calls": [{"skill": "timer", "args": {"minutes": m.group(1), "label": "timer"}}]}
    if m := re.search(r"open (.+)", p):
        return {"say": "opening", "calls": [{"skill": "open_app", "args": {"name": m.group(1).strip().title()}}]}
    return {"say": "I only know my skills. Type 'skills' to see them.", "calls": []}


def heuristic_guess(c):
    if re.search(r"https?://", c["clipboard"] or ""):
        return "summarize the link on my clipboard"
    if c["loose_downloads"] >= 8:
        return "tidy my downloads"
    if c["front_app"] in ("Zoom", "FaceTime") :
        return "pause music and set volume to 60"
    h = datetime.now().hour
    if h >= 19 or h < 7:
        return "turn on dark mode"
    return "what's on my screen?"


class Predictor:
    """Tangerine-style: watch context, guess the next step, offer it as ghost text."""

    def __init__(self):
        self.guess, self.last, self.history = "", None, []

    def loop(self):
        while True:
            try:
                c = context()
                key = hashlib.md5(json.dumps({k: v for k, v in c.items() if k != "time"}).encode()).hexdigest()
                if key != self.last:
                    self.last = key
                    self.guess = self.predict(c)
            except Exception as e:  # never let the watcher kill the terminal
                self.guess = ""
            time.sleep(4)

    def predict(self, c):
        if not CLAUDE:
            return heuristic_guess(c)
        msg = (f"Skills:\n{skill_menu()}\nContext: {json.dumps(c)}\nRecent commands: {self.history[-5:]}\n"
               "Predict the ONE thing this user most likely wants next, as a short command they would type "
               "(under 8 words, must be doable with the skills). Reply with the command only.")
        return claude(msg).strip('"')[:80]


# ---------------- Terminal ----------------
def run_calls(plan):
    if plan.get("say"):
        con.print(f"[bold magenta]👻 {plan['say']}[/]")
    for c in plan.get("calls", []):
        s = SKILLS.get(c.get("skill"))
        if not s:
            con.print(f"[red]✗ blocked unknown skill {c.get('skill')}[/]")
            continue
        args = c.get("args") or {}
        con.print(f"[dim]  → {c['skill']}({', '.join(f'{k}={v!r}' for k, v in args.items())}) [{s['tier']}][/]")
        if s["tier"] == "cloud" and not cloud.ready():
            con.print("[yellow]  set AGENT37_API_KEY to use cloud skills[/]")
            continue
        try:
            out = s["fn"](**args)
        except Exception as e:
            out = f"error: {e}"
        log("skill", skill=c["skill"], args=args, out=str(out)[:500])
        con.print(Panel(str(out), border_style="magenta" if s["tier"] != "cloud" else "cyan", expand=False))


def show_skills():
    t = Table(title="Desk Ghost skills", border_style="magenta")
    for col in ("skill", "tier", "what it does"):
        t.add_column(col)
    for n, s in SKILLS.items():
        t.add_row(n, s["tier"], s["desc"])
    con.print(t)


def main():
    brain_name = f"Claude {MODEL}" if CLAUDE else ("Agent37 cloud" if A37_KEY else "offline rules")
    con.print(Panel.fit(f"[bold]👻 Desk Ghost[/]  brain: {brain_name}   cloud: {'Agent37 ✓' if A37_KEY else 'off'}   gate: {'OpenAI ✓' if os.environ.get('OPENAI_API_KEY') else 'off'}\n"
                        f"{len(SKILLS)} safe skills, no raw shell. Tab accepts the ghost's guess. "
                        "'skills', 'cloud off', 'quit'.", border_style="magenta"))
    pred = Predictor()
    threading.Thread(target=pred.loop, daemon=True).start()
    kb = KeyBindings()

    @kb.add("tab")
    def _(ev):
        if pred.guess:
            ev.app.current_buffer.text = pred.guess
            ev.app.current_buffer.cursor_position = len(pred.guess)

    sess = PromptSession(key_bindings=kb, refresh_interval=1,
                         placeholder=lambda: HTML(f"<style fg='#888888'>{pred.guess}  ⇥</style>") if pred.guess else "",
                         bottom_toolbar=lambda: HTML(f" 👻 guess: <b>{pred.guess or '…'}</b>   front: {front_cache[0]}"))
    while True:
        try:
            q = sess.prompt(HTML("<ansimagenta><b>ghost ❯ </b></ansimagenta>")).strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            continue
        if q in ("quit", "exit"):
            break
        if q == "skills":
            show_skills()
            continue
        if q == "cloud off":
            con.print(cloud.down())
            continue
        pred.history.append(q)
        log("ask", q=q)
        try:
            ok, why = safety.screen(q)
        except Exception as e:
            ok, why = True, f"gate error: {e}"
        if not ok:
            con.print(f"[red]🛡  OpenAI safety gate blocked this ({why}). Nothing ran.[/]")
            log("blocked", q=q, why=why)
            continue
        try:
            with con.status("👻 thinking..."):
                plan = brain(f"Context: {json.dumps(context())}\nRequest: {q}")
        except Exception as e:
            con.print(f"[red]brain error: {e}. Falling back to offline rules.[/]")
            plan = rules(q)
        run_calls(plan)
        pred.last = None  # re-predict after acting


front_cache = ["…"]
if __name__ == "__main__":
    def _fc():
        while True:
            try:
                front_cache[0] = front_app()
            except Exception:
                pass
            time.sleep(3)
    threading.Thread(target=_fc, daemon=True).start()
    main()
