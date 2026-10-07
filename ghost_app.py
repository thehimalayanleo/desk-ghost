#!/usr/bin/env python3
"""Desk Ghost, tiny floating edition: a little ghost that sits on top of your screen,
guesses your next step in a speech bubble, and does it when you tap 'do it'."""
import json, threading

import webview

import ghost
import safety

pred = ghost.Predictor()


class Api:
    def guess(self):
        return pred.guess

    def ask(self, q):
        q = (q or "").strip()
        if not q:
            return {"say": "", "out": ""}
        try:
            ok, why = safety.screen(q)
        except Exception:
            ok = True
        if not ok:
            ghost.log("blocked", q=q, why=why)
            return {"say": "nope, not doing that 🛡", "out": f"blocked by OpenAI safety gate: {why}"}
        pred.history.append(q)
        ghost.log("ask", q=q)
        try:
            plan = ghost.brain(f"Context: {json.dumps(ghost.context())}\nRequest: {q}")
        except Exception as e:
            plan = ghost.rules(q)
        outs = []
        for c in plan.get("calls", []):
            s = ghost.SKILLS.get(c.get("skill"))
            if not s:
                outs.append(f"blocked unknown skill {c.get('skill')}")
                continue
            if s["tier"] == "cloud" and not ghost.cloud.ready():
                outs.append("cloud skills need AGENT37_API_KEY")
                continue
            try:
                out = s["fn"](**(c.get("args") or {}))
            except Exception as e:
                out = f"error: {e}"
            ghost.log("skill", skill=c["skill"], args=c.get("args"), out=str(out)[:500])
            outs.append(str(out))
        pred.last = None
        return {"say": plan.get("say", ""), "out": "\n\n".join(outs)}

    def run(self, name, args):
        s = ghost.SKILLS.get(name)
        if not s:
            return "not allowed"
        if s["tier"] == "cloud" and not ghost.cloud.ready():
            return "cloud skills need AGENT37_API_KEY"
        try:
            out = s["fn"](**args)
        except Exception as e:
            out = f"error: {e}"
        ghost.log("skill", skill=name, args=args, out=str(out)[:500])
        return str(out)

    def swish(self):
        hidden[0] = pred.guess
        win.hide()

    def close(self):
        win.destroy()


hidden = [None]  # guess at swish time; ghost returns when a NEW guess shows up


def comeback():
    import time
    while True:
        time.sleep(2)
        if hidden[0] is not None and pred.guess and pred.guess != hidden[0]:
            hidden[0] = None
            win.show()
            win.evaluate_js("popIn()")


def on_drop(e):
    files = e.get("dataTransfer", {}).get("files", [])
    paths = [f.get("pywebviewFullPath") for f in files if f.get("pywebviewFullPath")]
    if paths:
        win.evaluate_js(f"dropped({json.dumps(paths[0])})")


def bind(window):
    from webview.dom import DOMEventHandler
    window.dom.document.events.dragover += DOMEventHandler(lambda e: None, True, True)
    window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)


HTML = r"""
<html><head><style>
* { box-sizing: border-box; margin: 0; font-family: -apple-system, "SF Pro Rounded", system-ui; }
html, body { background: transparent; overflow: hidden; user-select: none; }
.wrap { display: flex; flex-direction: column; align-items: center; padding: 8px; gap: 6px; }
.bubble { background: #fff; color: #2b2340; border-radius: 16px; padding: 10px 12px; width: 236px;
  box-shadow: 0 6px 20px rgba(80,60,140,.25); font-size: 13px; line-height: 1.35; position: relative;
  max-height: 170px; overflow-y: auto; user-select: text; }
.bubble:after { content: ""; position: absolute; bottom: -8px; left: 50%; margin-left: -8px;
  border: 8px solid transparent; border-top-color: #fff; border-bottom: 0; }
.say { font-weight: 600; }
.out { margin-top: 6px; color: #5b5470; font-size: 12px; white-space: pre-wrap; }
.row { display: flex; gap: 6px; margin-top: 8px; }
button { border: 0; border-radius: 999px; padding: 6px 12px; font-size: 12px; font-weight: 600; cursor: pointer; }
.go { background: #b69cff; color: #fff; } .go:hover { background: #9c7cff; }
.nah { background: #f0ecfa; color: #6b5fa0; }
.ghost { animation: bob 2.6s ease-in-out infinite; cursor: grab; filter: drop-shadow(0 6px 8px rgba(80,60,140,.3)); }
.ghost.busy { animation: spin 1s linear infinite; }
.eyes { transform-origin: 50px 48px; animation: blink 4s infinite; }
@keyframes blink { 0%,94%,100% { transform: scaleY(1) } 97% { transform: scaleY(.1) } }
@keyframes bob { 0%,100% { transform: translateY(0) } 50% { transform: translateY(-8px) } }
@keyframes spin { 0% { transform: rotate(-12deg) } 50% { transform: rotate(12deg) } 100% { transform: rotate(-12deg) } }
input { width: 236px; border: 0; border-radius: 999px; padding: 8px 14px; font-size: 13px; outline: none;
  background: rgba(255,255,255,.95); color: #2b2340; box-shadow: 0 4px 14px rgba(80,60,140,.2); }
.swish { animation: swish .55s cubic-bezier(.5,-0.4,.7,1) forwards; }
@keyframes swish { to { transform: translate(260px,-120px) rotate(35deg) scale(.3); opacity: 0 } }
.pop { animation: pop .5s cubic-bezier(.3,1.6,.5,1); }
@keyframes pop { from { transform: scale(.2); opacity: 0 } to { transform: scale(1); opacity: 1 } }
.chips { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
.chip { background: #f0ecfa; color: #6b5fa0; } .chip:hover { background: #b69cff; color: #fff; }
.hint { font-size: 10px; color: #b0a8c8; text-align: center; }
.x { position: fixed; top: 4px; right: 6px; font-size: 11px; color: #b0a8c8; cursor: pointer; background: none; padding: 2px; }
</style></head><body>
<button class="x" onclick="swish()" title="swish away (I come back with a new idea)">〜</button>
<div class="wrap" id="w">
  <div class="bubble" id="b">
    <div class="say" id="say">boo! I'm watching for chores 👀</div>
    <div class="out" id="out"></div>
    <div class="chips" id="chips"></div>
    <div class="row" id="row" style="display:none">
      <button class="go" onclick="doGuess()">do it</button>
      <button class="nah" onclick="nah()">nah</button>
    </div>
  </div>
  <svg class="ghost pywebview-drag-region" id="g" viewBox="0 0 100 110" width="78" height="86">
    <defs><linearGradient id="gr" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e9e0ff"/><stop offset="1" stop-color="#c7b3ff"/></linearGradient></defs>
    <path d="M50 6 C24 6 12 26 12 50 L12 96 Q19 88 26 96 Q33 104 40 96 Q46 88 52 96 Q59 104 66 96 Q73 88 80 96 Q85 102 88 96 L88 50 C88 26 76 6 50 6 Z" fill="url(#gr)" stroke="#a48cf0" stroke-width="2.5"/>
    <g class="eyes"><ellipse cx="38" cy="48" rx="5" ry="7" fill="#2b2340"/><ellipse cx="62" cy="48" rx="5" ry="7" fill="#2b2340"/>
    <circle cx="40" cy="45" r="1.8" fill="#fff"/><circle cx="64" cy="45" r="1.8" fill="#fff"/></g>
    <ellipse cx="29" cy="60" rx="5" ry="3" fill="#ffb3d1" opacity=".8"/><ellipse cx="71" cy="60" rx="5" ry="3" fill="#ffb3d1" opacity=".8"/>
    <path d="M45 61 Q50 66 55 61" fill="none" stroke="#2b2340" stroke-width="2.5" stroke-linecap="round"/>
  </svg>
  <input id="q" placeholder="ask me… or drop a file on me" onkeydown="if(event.key==='Enter') send(this.value)">
  <div class="hint">double-click me to swish me away · esc quits</div>
</div>
<script>
let guess = "", skipped = "", busy = false, holdUntil = 0;
const $ = id => document.getElementById(id);
function show(say, out, offer) { $("say").textContent = say; $("out").textContent = out || ""; $("row").style.display = offer ? "flex" : "none"; }
async function poll() {
  if (busy || !window.pywebview || Date.now() < holdUntil) return;
  const g = await pywebview.api.guess();
  if (g && g !== guess && g !== skipped) { guess = g; show(g.toLowerCase() + "?", "", true); }
}
function nah() { skipped = guess; show("ok, I'll keep watching 👀", "", false); }
function doGuess() { send(guess); }
async function send(q) {
  if (!q || busy) return;
  busy = true; $("g").classList.add("busy"); $("q").value = ""; show("on it…", q, false);
  const r = await pywebview.api.ask(q);
  busy = false; $("g").classList.remove("busy"); guess = q;
  show(r.say || "done ✨", r.out, false); holdUntil = Date.now() + 15000;
}
function swish() { $("w").classList.add("swish"); setTimeout(() => pywebview.api.swish(), 550); }
function popIn() { const w = $("w"); w.classList.remove("swish"); void w.offsetWidth; w.classList.add("pop"); guess = ""; poll(); }
$("g").addEventListener("dblclick", swish);
document.addEventListener("keydown", e => { if (e.key === "Escape") pywebview.api.close(); });
const KIND = { img: ["png","jpg","jpeg","heic","tiff","gif","webp","bmp"], aud: ["mp3","wav","m4a","aiff","flac"], vid: ["mov","mp4","m4v"] };
function dropped(path) {
  const name = path.split("/").pop(), ext = name.split(".").pop().toLowerCase();
  let opts = [];
  if (KIND.img.includes(ext)) opts = [["to jpg","convert_image",{to:"jpg"}],["to png","convert_image",{to:"png"}],["to pdf","convert_image",{to:"pdf"}],["shrink","shrink_image",{max_px:1200}]];
  else if (KIND.aud.includes(ext)) opts = [["to m4a","convert_audio",{to:"m4a"}],["to wav","convert_audio",{to:"wav"}]];
  else if (KIND.vid.includes(ext)) opts = [["compress 720p","compress_video",{quality:"720"}],["1080p","compress_video",{quality:"1080"}]];
  opts.push(["☁️ summarize in sandbox","cloud_file",{}]);
  opts.push(["show in Finder","reveal",{}]);
  show("ooh, " + name + "! what should I do?", "", false);
  $("chips").innerHTML = "";
  for (const [label, skill, args] of opts) {
    const b = document.createElement("button"); b.className = "chip"; b.textContent = label;
    b.onclick = async () => { $("chips").innerHTML = ""; busy = true; $("g").classList.add("busy"); show("on it…", name, false);
      const out = await pywebview.api.run(skill, Object.assign({path}, args));
      busy = false; $("g").classList.remove("busy"); show("done ✨", out, false); holdUntil = Date.now() + 15000; };
    $("chips").appendChild(b);
  }
}
setInterval(poll, 2000);
</script></body></html>
"""

def demo():
    """Scripted run for recording: real skills, real APIs; writes scene start times."""
    import os, time
    log_path = os.environ["DESKGHOST_DEMO"]
    t0, marks = time.time(), {}
    def mark(k): marks[k] = round(time.time() - t0, 2); open(log_path, "w").write(json.dumps(marks))
    def js(code): win.evaluate_js(code)
    def wait_idle(limit=120):
        end = time.time() + limit
        while time.time() < end and win.evaluate_js("busy"):
            time.sleep(0.5)
    test = os.path.expanduser("~/DeskGhost/test")
    js("document.body.style.background = 'linear-gradient(160deg, #2a2140, #43336e)'")
    time.sleep(2); mark("S01Hook")
    pred.guess = "tidy my downloads"; time.sleep(11)
    mark("S02Drop"); js(f"dropped({json.dumps(test + '/Mac Pink.png')})"); time.sleep(3.5)
    js("[...document.querySelectorAll('.chip')].find(b => b.textContent === 'to jpg').click()"); time.sleep(1); wait_idle(); time.sleep(5)
    mark("S03Sandbox"); js(f"dropped({json.dumps(test + '/meeting_notes.pdf')})"); time.sleep(3.5)
    js("[...document.querySelectorAll('.chip')].find(b => b.textContent.includes('sandbox')).click()"); time.sleep(1); wait_idle(); time.sleep(9)
    mark("S04Gate"); js("send('how do I hurt someone')"); time.sleep(1); wait_idle(); time.sleep(7)
    mark("S05Close"); js("swish()"); time.sleep(4); mark("END")


if __name__ == "__main__":
    threading.Thread(target=pred.loop, daemon=True).start()
    win = webview.create_window("Desk Ghost", html=HTML, js_api=Api(), width=270, height=390,
                                frameless=True, on_top=True, transparent=True, easy_drag=False,
                                x=40, y=60)
    import os
    if os.environ.get("DESKGHOST_DEMO"):
        threading.Thread(target=lambda: (__import__("time").sleep(3), demo()), daemon=True).start()
    else:
        threading.Thread(target=comeback, daemon=True).start()
    webview.start(bind, win)
