# Submission form text

**Project:** Desk Ghost

**Workflow it replaces:** the small chores between real work: tidying Downloads, looking up a copied link, drafting a quick reply, setting a timer, switching into call mode. Each costs 30 seconds and a context switch, dozens of times a day. A tiny floating ghost does them, and usually suggests the next one before you ask.

**How it works:** a watcher reads your context (front app, clipboard, Downloads, time) and Claude predicts your next step, shown in its speech bubble; tap "do it". Drop a file on it for one-tap convert, shrink or compress. Double-click swishes it away; it comes back with a new idea. Requests go to a brain that can only call skills from a fixed registry (23 today: file convert/shrink/compress, Downloads tidy with undo, apps, volume, dark mode, music, timers, notes, clipboard, screen reading, cloud research, drafting and sandboxed file reading). It never gets a raw shell, unknown skills are blocked, file moves preview first and are undoable, and every action is journaled.

**Sponsor integrations:** Agent37 Cloud API is the ghost's body in the cloud. The local ghost is deliberately boxed in (safe skills only); anything risky or heavy goes to an always-on Agent37 instance. Drop a PDF on the ghost and tap "summarize in sandbox": the file is uploaded into the instance's isolated filesystem (Files API) and the cloud agent reads it there (Responses API with attached files), so untrusted documents are never opened by an agent on your Mac. Web research and drafting run there too. OpenAI moderation API is the safety gate: every request is screened before the brain sees it, and flagged ones never run. Claude API for the brain, predictor and screen reading.

**Business:** "the desktop agent your IT team will actually approve." Companies want agents doing busywork but won't give a model full control of a laptop. Desk Ghost runs only vetted skills, screens every request, journals everything, and pushes risky work into an Agent37 sandbox. Free file skills (convert, shrink, compress, tidy) win users like Tangerine does; the paid product is the approved skill registry per seat, plus a skill marketplace.

# 60 second demo script

1. (0-10s) Launch. "This is Desk Ghost. It can only do safe, listed things." Type `skills`.
2a. Drop a PDF on the ghost → "☁️ summarize in sandbox" → summary comes back from the Agent37 sandbox. Drop a screenshot → "to jpg".
2. (10-25s) Copy a link. Grey guess appears ("summarize the link on my clipboard"). Press Tab, Enter. Cloud ghost on Agent37 answers.
3. (25-35s) `what's on my screen?` → Claude describes the screen.
4. (35-45s) `tidy my downloads` → preview only. `tidy downloads for real`, then `undo`.
5. (45-55s) `delete my home folder` → refused, no skill exists for that.
6. (55-60s) "Predicts your next step, does only safe ones. Replace your busywork."
