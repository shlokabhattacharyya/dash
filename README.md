# dash

a terminal productivity dashboard. tasks, calendar, weather, and a pomodoro timer in one plain-text view. ai-powered via ollama (local, free, no api key). requires internet connection for weather and google calendar.


## quick start

```bash
git clone https://github.com/yourname/dash.git ~/dash
cd ~/dash
pip install -r requirements.txt
python dash.py
```

you'll get tasks, weather, and a pomodoro timer immediately. google calendar will prompt you to sign in on first run. ollama is optional (see [ai features](#ai-features) below).


## full setup

### 1. install ollama (optional, for ai features):
```bash
brew install ollama
ollama pull llama3
```
on linux, see [ollama.com](https://ollama.com) for install instructions.

### 2. set ollama to start automatically on login (mac):
this runs ollama in the background permanently so you never have to think about it. paste the entire block at once.
```bash
cat > ~/Library/LaunchAgents/com.dash.ollama.plist << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.dash.ollama</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/ollama</string>
        <string>serve</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/ollama.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/ollama.log</string>
</dict>
</plist>
PLIST

launchctl load ~/Library/LaunchAgents/com.dash.ollama.plist
```

verify it worked:
```bash
curl http://localhost:11434
# should print: Ollama is running
```

if `launchctl load` returns a "load failed" error, check if ollama is already running with the curl above — if it is, you can safely ignore the error.

to remove the auto-start later:
```bash
launchctl unload ~/Library/LaunchAgents/com.dash.ollama.plist
rm ~/Library/LaunchAgents/com.dash.ollama.plist
```

### 3. add the tmux alias (optional, for persistent sessions):
```bash
# add this to your ~/.zshrc or ~/.bashrc:
alias dash='tmux new-session -A -s dash "python ~/dash/dash.py"'
source ~/.zshrc
```

then just type `dash` in any terminal. close the window and it keeps running. type `dash` again to return to it.


## controls

| key | action |
|-----|--------|
| `a` | add a task (type naturally, e.g. "call dentist friday high priority") |
| `d` | mark a task as done |
| `x` | delete a task |
| `e` | edit a task — retype naturally to change title, priority, or due date |
| `s` | start / pause / resume the pomodoro timer |
| `n` | skip to the next phase (only while the timer is running) |
| `r` | generate and show today's review on demand |
| `q` | quit and wipe the timer (tasks are always saved) |

when you press `d`, `x`, or `e`, incomplete tasks show numbered labels `[1]`, `[2]`, `[3]`... in cyan. press the number of the task you want. press `esc` to cancel.


## task input

tasks are parsed instantly using a local keyword parser. type naturally and it extracts:

- **priority** — "high priority", "low pri", or just "high"/"low" anywhere in the text
- **due date** — "today", "tomorrow", day names like "friday", or explicit dates like "2025-04-01"
- **title** — everything else, cleaned up and lowercased

priorities are color-coded on the dashboard: red = high, yellow = medium, green = low. due dates show as a short label after the task title: `today`, `tmrw`, a day name like `fri`, a date like `3/21`, or `overdue` in red.


## pomodoro cycle

the cycle runs automatically and repeats forever:

```
work 25m → break 5m → work 25m → break 5m → work 25m → break 15m → repeat
```

- at the start of each work phase, ollama suggests which task to focus on
- at the end of each full cycle, a 5-second summary screen appears while the next cycle starts underneath
- pressing `q` wipes the timer but never your tasks


## google calendar

no manual setup needed. the oauth credentials are bundled in the app. on first run a browser window opens — sign in with google, click allow, done.

dash reads your primary calendar only, showing today's and tomorrow's events. the currently active event is marked with ▶. if nothing is active right now, the next upcoming event is marked instead.

if you want to use your own google cloud credentials instead of the bundled ones, set this environment variable before running:

```bash
export DASH_CLIENT_SECRET="your-client-secret"
```


## ai features

all ai runs locally via ollama — nothing is sent to the cloud.

- **task parsing** — tasks are parsed instantly with a local keyword parser. ollama is not required for adding tasks
- **focus suggestion** — at the start of each work pomo, ollama recommends which task to tackle based on priority and due dates
- **cycle summary** — a short encouraging note at the end of each full cycle
- **daily review** — a full summary auto-generated at 11:59pm and shown the next morning, or on demand with `r`

if ollama is not running, focus suggestions fall back to picking the highest priority task, and summaries fall back to a simple stat line. everything else works normally.


## notes

- weather auto-detects your location from your ip address and refreshes every 10 minutes
- calendar refreshes every 5 minutes
- the timer counts down live on screen, refreshing every second
- ollama calls run in background threads — the dashboard stays responsive while ai generates
- tasks roll over at 11:59pm and completed ones are cleared
- the daily review is auto-generated at 11:59pm and shown the next morning
- keyboard input is polled every 50ms for responsive typing