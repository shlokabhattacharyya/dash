#!/usr/bin/env python3

"""
dash — a terminal productivity dashboard
run with: python dash.py
or via tmux alias: alias dash='tmux new-session -A -s dash "python ~/dash/dash.py"'
"""


### IMPORT LIBRARIES AND FUNCTIONS
import sys
import time
import select
import threading

try:
    import tty
    import termios
    HAS_TTY = True
except ImportError:
    HAS_TTY = False

from state  import (
    load_tasks, save_tasks, add_task, mark_done,
    remove_task, rename_task,
    load_timer, start_session, stop_session,
    pause_timer, resume_timer, get_timer_state,
    advance_phase, load_review, save_review, clear_review,
    rollover_tasks, CYCLE,
)
from weather import fetch_weather, fmt_weather
from render  import (
    build_dashboard, print_dashboard,
    render_command_bar, render_input_bar, render_select_bar,
    print_cycle_summary, print_review,
    console,
)
from ai import (
    _local_parse, suggest_focus,
    generate_cycle_summary, generate_daily_review,
)
from gcal import get_display_events
from notify import notify


### GLOBAL
_input_mode   = None                    # None, "add", or "rename"
_input_buffer = ""                      # current input string
_rename_index = None                    # index of task being renamed
_select_mode  = None                    # None, "done", "delete", or "edit"
_suggestion   = ""                      # current pomo focus suggestion
_weather_str  = "loading weather..."    # weather string
_events       = []                      # cached calendar events
_last_phase   = None                    # track phase transitions
_exit_flag    = False


### BACKGROUND THREADS 
# refresh weather every 10 minutes
def weather_thread():
    global _weather_str
    while not _exit_flag:
        w = fetch_weather()
        _weather_str = fmt_weather(w)
        time.sleep(600)

# refresh calendar every 5 minutes
def calendar_thread():
    global _events
    while not _exit_flag:
        _events = get_display_events()
        time.sleep(300)

# check for 11:59pm rollover
def scheduler_thread():
    global _exit_flag
    while not _exit_flag:
        now = time.strftime("%H:%M")
        if now == "23:59":
            _trigger_daily_review()
            rollover_tasks()
            time.sleep(61)  # skip past midnight
        time.sleep(30)

# generate and save the daily review in the background
def _trigger_daily_review():
    tasks = load_tasks()
    timer = get_timer_state()
    pomos_done = timer["pomos_done"] if timer else 0
    text = generate_daily_review(tasks, pomos_done)
    today = time.strftime("%Y-%m-%d")
    done_tasks = [t for t in tasks if t["done"]]
    left_tasks = [t for t in tasks if not t["done"]]
    overdue  = [t for t in left_tasks if t.get("due_date") and t["due_date"] < today]
    save_review({
        "text": text,
        "pomos": pomos_done,
        "done": len(done_tasks),
        "carried": len(left_tasks),
        "overdue": len(overdue),
    })


### KEYBOARD INPUT
# non-blocking check for a keypress (terminal held in cbreak mode for full session)
def get_input_char():
    if not HAS_TTY:
        return None
    if select.select([sys.stdin], [], [], 0)[0]:
        return sys.stdin.read(1)
    return None


### PHASE TRANSITION HANDLING
# build a short message for the new phase and fire the alert (bell + desktop popup)
def _notify_phase_change(timer):
    mins = timer["duration"] // 60
    if timer["label"] == "work":
        notify("back to work", f"pomo {timer['pomo_num']}/{timer['pomo_total']} · {mins} min focus")
    elif timer["break_type"] == "long":
        notify("cycle complete", f"long break · {mins} min")
    else:
        notify("pomo done", f"short break · {mins} min")


def handle_phase_transition(timer):
    global _suggestion, _last_phase

    if not timer or not timer["phase_done"]:
        return timer

    # advance to next phase
    timer = advance_phase(timer)

    # alert the user that the phase just changed
    _notify_phase_change(timer)

    # new work phase - generate focus suggestion in background
    if timer["label"] == "work":
        def _gen():
            global _suggestion
            tasks = load_tasks()
            _suggestion = suggest_focus(
                tasks,
                timer["pomo_num"],
                timer["pomo_total"],
                timer["pomos_done"],
            )
        threading.Thread(target=_gen, daemon=True).start()

    # just finished a work phase - show cycle summary if it was the last work phase
    elif timer["label"] == "break":
        was_last_work = (
            _last_phase == "work" and
            timer["phase_index"] == 5  # index 5 is the long break
        )

        # generate cycle summary in background then show it
        def _show_summary():
            tasks = load_tasks()
            today = time.strftime("%Y-%m-%d")
            done = [t for t in tasks if t["done"]]
            left = [t for t in tasks if not t["done"]]
            over = [t for t in left if t.get("due_date") and t["due_date"] < today]
            t_now = get_timer_state()
            pomos = t_now["pomos_done"] if t_now else 0
            stats = {"pomos": 3, "done": len(done), "overdue": len(over)}
            text = generate_cycle_summary(tasks, pomos)
            print_cycle_summary(stats, text)
            time.sleep(5)

        if was_last_work:
            threading.Thread(target=_show_summary, daemon=True).start()

    _last_phase = timer["label"]
    return timer


### INPUT HANDLING

# map a selection number (1-based) to the real index in the tasks list
# only counts incomplete tasks
def _incomplete_index(tasks, pick):
    n = 0
    for i, t in enumerate(tasks):
        if not t["done"]:
            n += 1
            if n == pick:
                return i
    return None


def handle_keypress(ch, timer):
    global _input_mode, _input_buffer, _rename_index, _select_mode
    global _suggestion, _exit_flag

    # --- text input mode (add / rename) ---
    if _input_mode is not None:
        if ch in ("\r", "\n"):
            raw = _input_buffer.strip()

            # submit new task
            if _input_mode == "add" and raw:
                parsed = _local_parse(raw)
                title = str(parsed.get("title") or raw).strip()[:200].lower()
                priority = parsed.get("priority", "medium")
                due_date = parsed.get("due_date")

                # enforce allowed values
                if priority not in ("low", "medium", "high"):
                    priority = "medium"

                # validate due_date is a real date string, not arbitrary text
                if due_date:
                    import re
                    if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(due_date)):
                        due_date = None

                add_task(title, priority, due_date)

            # submit rename
            elif _input_mode == "rename" and raw and _rename_index is not None:
                rename_task(_rename_index, raw[:200].lower())

            _input_mode = None
            _input_buffer = ""
            _rename_index = None

        # backspace
        elif ch in ("\x7f", "\x08"):
            _input_buffer = _input_buffer[:-1]

        # escape - cancel input
        elif ch == "\x1b":
            _input_mode = None
            _input_buffer = ""
            _rename_index = None

        # cap at 200 chars and reject non-printable control characters
        else:
            if len(_input_buffer) < 200 and ch.isprintable():
                _input_buffer += ch

        return timer

    # --- select mode (pick a task by number) ---
    if _select_mode is not None:
        if ch == "\x1b":
            _select_mode = None
            return timer

        if ch.isdigit() and ch != "0":
            pick = int(ch)
            tasks = load_tasks()
            idx = _incomplete_index(tasks, pick)

            if idx is not None:
                if _select_mode == "done":
                    mark_done(idx)
                elif _select_mode == "delete":
                    remove_task(idx)
                elif _select_mode == "edit":
                    _input_mode = "rename"
                    _input_buffer = tasks[idx]["title"]
                    _rename_index = idx

            _select_mode = None
        return timer

    # --- normal mode keypresses ---
    if ch == "q":
        stop_session()
        _exit_flag = True

    # add new task
    elif ch == "a":
        _input_mode = "add"
        _input_buffer = ""

    # mark a task done — enter select mode
    elif ch == "d":
        _select_mode = "done"

    # remove a task — enter select mode
    elif ch == "x":
        _select_mode = "delete"

    # rename a task — enter select mode
    elif ch == "e":
        _select_mode = "edit"

    # start or stop pomodoro timer
    elif ch == "s":
        if timer:
            if timer["paused"]:
                resume_timer()
            else:
                pause_timer()
        else:
            timer = start_session()
            # generate initial suggestion
            def _gen():
                global _suggestion
                tasks = load_tasks()
                _suggestion = suggest_focus(tasks, 1, 3, 0)
            threading.Thread(target=_gen, daemon=True).start()

    elif ch == "r":
        # manual review
        def _manual_review():
            _trigger_daily_review()
            review = load_review()
            if review:
                tasks = load_tasks()
                today = time.strftime("%Y-%m-%d")
                left = [t for t in tasks if not t["done"]]
                over = [t for t in left if t.get("due_date") and t["due_date"] < today]
                stats = {
                    "pomos": review["content"]["pomos"] if isinstance(review.get("content"), dict) else 0,
                    "done": review["content"]["done"] if isinstance(review.get("content"), dict) else 0,
                    "carried": len(left),
                    "overdue": len(over),
                }
                text = review["content"]["text"] if isinstance(review.get("content"), dict) else str(review.get("content", ""))
                print_review(text, stats, tasks)
                time.sleep(5)
        threading.Thread(target=_manual_review, daemon=True).start()

    return timer


### FIRST RUN
def _first_run_calendar_auth():
    # if token already exists, skip
    import os
    token = os.path.join(os.path.expanduser("~/.dash"), "token.json")
    if os.path.exists(token):
        return

    # else, no token yet — let the user know before the browser opens
    console.clear()
    console.print("")
    console.print("[bold white]welcome to dash[/bold white]")
    console.print("")
    console.print("[dim]connecting to your google calendar for the first time.[/dim]")
    console.print("[dim]a browser window will open asking you to sign in.[/dim]")
    console.print("[dim]this only happens once.[/dim]")
    console.print("")
    console.print("[dim]if the browser doesn't open automatically, check your dock.[/dim]")
    console.print("")

    # trigger the auth flow by importing and calling gcal
    try:
        from gcal import _get_credentials
        _get_credentials()
        console.print("  [green]connected.[/green] starting dash...")
        console.print("")
    except Exception:
        console.print("  [dim]calendar auth skipped — you can still use dash without it.[/dim]")
        console.print("")

    import time as _t
    _t.sleep(1.5)


### MAIN
def main():
    global _exit_flag, _weather_str, _suggestion

    # show morning review if one exists
    review = load_review()
    if review:
        tasks = load_tasks()
        today = time.strftime("%Y-%m-%d")
        left = [t for t in tasks if not t["done"]]
        over = [t for t in left if t.get("due_date") and t["due_date"] < today]
        data = review.get("content", review)
        if isinstance(data, dict):
            stats = {
                "pomos": data.get("pomos", 0),
                "done": data.get("done", 0),
                "carried": len(left),
                "overdue": len(over),
            }
            text = data.get("text", "")
        else:
            stats = {"pomos": 0, "done": 0, "carried": len(left), "overdue": len(over)}
            text = str(data)
        print_review(text, stats, tasks)
        time.sleep(5)
        clear_review()

    # first run - check if calendar auth is needed before starting threads
    # this way the browser prompt happens before the dashboard renders
    _first_run_calendar_auth()

    # start background threads
    threading.Thread(target=weather_thread, daemon=True).start()
    threading.Thread(target=calendar_thread, daemon=True).start()
    threading.Thread(target=scheduler_thread, daemon=True).start()

    timer = get_timer_state()

    TICK         = 0.05      # check keys every 50ms
    REFRESH_RATE = 1.0       # repaint dashboard every 1s
    _last_draw   = 0

    while not _exit_flag:
        now = time.time()

        # only rebuild and repaint at the refresh interval, or immediately after a keypress
        needs_draw = (now - _last_draw) >= REFRESH_RATE

        # check for keypress
        ch = get_input_char()
        if ch:
            timer = handle_keypress(ch, timer) or timer
            needs_draw = True          # repaint immediately after input

        if needs_draw:
            # always refresh timer from disk so remaining counts down live
            timer = get_timer_state() or timer
            timer = handle_phase_transition(timer) or timer
            tasks = load_tasks()

            lines = build_dashboard(tasks, _events, timer, _suggestion, _weather_str, _select_mode)

            if _input_mode is not None:
                cmd_bar = render_input_bar(_input_buffer, _input_mode)
            elif _select_mode is not None:
                cmd_bar = render_select_bar(_select_mode)
            else:
                cmd_bar = render_command_bar(running=bool(timer and not timer["paused"]))

            print_dashboard(lines, cmd_bar)
            _last_draw = now

        time.sleep(TICK)

    console.print("\n[dim]session ended. tasks saved. see you next time.[/dim]\n")


if __name__ == "__main__":
    if HAS_TTY:
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            sys.stdout.write("\033[?1049h\033[?25l")
            sys.stdout.flush()
            tty.setcbreak(fd)
            main()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            sys.stdout.write("\033[?1049l\033[?25h")
            sys.stdout.flush()
    else:
        main()