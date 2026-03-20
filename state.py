### IMPORT LIBRARIES AND SETUP
import json
import os
import time

# paths for all state files
DASH_DIR = os.path.expanduser("~/.dash")
TASKS_FILE = os.path.join(DASH_DIR, "tasks.json")
TIMER_FILE = os.path.join(DASH_DIR, "timer.json")
REVIEW_FILE = os.path.join(DASH_DIR, "review.json")

# pomodoro cycle
CYCLE = [
    ("work",  25 * 60),
    ("break", 5  * 60),
    ("work",  25 * 60),
    ("break", 5  * 60),
    ("work",  25 * 60),
    ("break", 15 * 60),
]

WORK_PHASES  = [i for i, (label, _) in enumerate(CYCLE) if label == "work"]
BREAK_PHASES = [i for i, (label, _) in enumerate(CYCLE) if label == "break"]


### FUNCTIONS

## file and directory 

# ensure directory path
def ensure_dir():
    # make sure ~/.dash exists with strict permissions (owner only)
    if not os.path.exists(DASH_DIR):
        os.makedirs(DASH_DIR, mode=0o700, exist_ok=True)
    else:
        # enforce permissions even if dir already exists
        os.chmod(DASH_DIR, 0o700)

# write to a temp file then rename — prevents corruption if killed mid-write
def _atomic_write(path, data):
    import tempfile
    dir_ = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=dir_, prefix=".tmp_")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.chmod(tmp, 0o600)        # owner read/write only
        os.replace(tmp, path)       # atomic on posix
    except Exception:
        os.unlink(tmp)
        raise


## tasks

# check file permissions before reading — warn if world-readable
def _safe_load(path):
    if os.path.exists(path):
        mode = oct(os.stat(path).st_mode & 0o777)
        if mode not in ("0o600", "0o400"):
            os.chmod(path, 0o600)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)

# load tasks
def load_tasks():
    ensure_dir()
    return _safe_load(TASKS_FILE) or []

# save tasks
def save_tasks(tasks):
    ensure_dir()
    _atomic_write(TASKS_FILE, tasks)

# add new task
def add_task(title, priority="medium", due_date=None):
    tasks = load_tasks()
    tasks.append({
        "id": len(tasks),
        "title": title,
        "priority": priority,
        "due_date": due_date,
        "done": False,
        "done_at": None,
        "created_at": time.strftime("%Y-%m-%d"),
    })
    save_tasks(tasks)

# mark tasks as done
def mark_done(index):
    tasks = load_tasks()
    if 0 <= index < len(tasks):
        tasks[index]["done"] = True
        tasks[index]["done_at"] = time.strftime("%Y-%m-%d")
        save_tasks(tasks)

# remove a task entirely
def remove_task(index):
    tasks = load_tasks()
    if 0 <= index < len(tasks):
        tasks.pop(index)
        save_tasks(tasks)

# rename a task
def rename_task(index, new_title):
    tasks = load_tasks()
    if 0 <= index < len(tasks):
        tasks[index]["title"] = new_title
        save_tasks(tasks)

# roll over tasks display
def rollover_tasks():
    # archive completed tasks, carry over incomplete (called at 11:59pm)
    tasks = load_tasks()
    today = time.strftime("%Y-%m-%d")
    # keep only tasks not done, or done today (will be cleared tomorrow)
    surviving = [t for t in tasks if not t["done"]]
    save_tasks(surviving)


## timer

# load timer
def load_timer():
    return _safe_load(TIMER_FILE)

# save timer
def save_timer(state):
    ensure_dir()
    _atomic_write(TIMER_FILE, state)

# start session (create a fresh timer at phase 0)
def start_session():
    state = {
        "phase_index": 0,
        "phase_start": time.time(),
        "paused": False,
        "pause_start": None,
        "remaining": CYCLE[0][1],
        "pomos_done": 0,
        "session_start": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    save_timer(state)
    return state

# stop session (wipe timer, leave tasks untouched)
def stop_session():
    if os.path.exists(TIMER_FILE):
        os.remove(TIMER_FILE)

# pause timer
def pause_timer():
    state = load_timer()
    if not state or state["paused"]:
        return
    state["paused"] = True
    state["pause_start"] = time.time()
    save_timer(state)


def resume_timer():
    state = load_timer()
    if not state or not state["paused"]:
        return
    # shift phase_start forward by the pause duration
    paused_for = time.time() - state["pause_start"]
    state["phase_start"] += paused_for
    state["paused"] = False
    state["pause_start"] = None
    save_timer(state)

# returns enriched timer state with computed fields
def get_timer_state():
    state = load_timer()
    if not state:
        return None

    i = state["phase_index"]
    label, duration = CYCLE[i]
    now = time.time()

    if state["paused"]:
        remaining = state["remaining"]
    else:
        elapsed = now - state["phase_start"]
        remaining = max(0, duration - int(elapsed))
        state["remaining"] = remaining

    # figure out pomo number and total work phases
    work_index = WORK_PHASES.index(i) if i in WORK_PHASES else None
    pomo_num   = (work_index + 1) if work_index is not None else None
    pomo_total = len(WORK_PHASES)

    # short vs long break
    break_type = None
    if label == "break":
        break_type = "long" if duration == 15 * 60 else "short"

    return {
        **state,
        "label": label,
        "duration": duration,
        "remaining": remaining,
        "pomo_num": pomo_num,
        "pomo_total": pomo_total,
        "break_type": break_type,
        "phase_done": remaining == 0,
    }

# move to next phase in cycle
def advance_phase(state):
    next_index = (state["phase_index"] + 1) % len(CYCLE)
    next_label, next_duration = CYCLE[next_index]

    # count completed pomos
    pomos_done = state["pomos_done"]
    if state["label"] == "work":
        pomos_done += 1

    # persist only base fields — don't carry over stale computed fields
    new_state = {
        "phase_index": next_index,
        "phase_start": time.time(),
        "paused": False,
        "pause_start": None,
        "remaining": next_duration,
        "pomos_done": pomos_done,
        "session_start": state.get("session_start", ""),
    }
    save_timer(new_state)

    # attach computed fields for immediate use by callers
    work_index = WORK_PHASES.index(next_index) if next_index in WORK_PHASES else None
    new_state["label"] = next_label
    new_state["duration"] = next_duration
    new_state["pomo_num"] = (work_index + 1) if work_index is not None else None
    new_state["pomo_total"] = len(WORK_PHASES)
    new_state["break_type"] = "long" if next_label == "break" and next_duration == 15 * 60 else ("short" if next_label == "break" else None)
    new_state["phase_done"] = False

    return new_state


## review

# load review
def load_review():
    return _safe_load(REVIEW_FILE)

# save review
def save_review(content):
    ensure_dir()
    _atomic_write(REVIEW_FILE, {"content": content, "date": time.strftime("%Y-%m-%d")})

# clear review
def clear_review():
    if os.path.exists(REVIEW_FILE):
        os.remove(REVIEW_FILE)