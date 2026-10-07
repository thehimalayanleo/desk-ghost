#!/bin/zsh
# Records the scripted floating-ghost demo (real skills + APIs) to demo.mov; marks.json holds scene times.
cd ${0:A:h}
rm -f demo.mov marks.json; rm -f ~/DeskGhost/test/*.jpg(N)
DESKGHOST_DEMO=$PWD/marks.json .venv/bin/python ghost_app.py &
GP=$!
sleep 1.5
screencapture -v -V 75 -x -R 40,60,270,390 demo.mov
kill $GP 2>/dev/null
echo "recorded: $(ls -la demo.mov | awk '{print $5}') bytes"; cat marks.json
