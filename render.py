### IMPORT LIBRARIES AND SETUP
import sys
import time
from rich.console import Console
from rich.text    import Text
from rich         import print as rprint

from state import sort_tasks

console = Console(width=80)

# priority colors
PRIORITY_COLORS = {
    "high": "red",
    "medium": "yellow",
    "low": "green",
}

DIVIDER = "─" * 80


### FUNCTIONS

# format timer
def fmt_timer(secs):
    m, s = divmod(secs, 60)
    return f"{m:02d}:{s:02d}"

# progress bar
def progress_bar(remaining, duration, width=16):
    if duration == 0:
        return "░" * width
    filled = int((1 - remaining / duration) * width)
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)

# format due date for display
def _fmt_due(due_date):
    if not due_date:
        return ""
    try:
        import datetime
        d = datetime.date.fromisoformat(due_date)
        today = datetime.date.today()
        diff = (d - today).days
        if diff < 0:
            return "overdue"
        if diff == 0:
            return "today"
        if diff == 1:
            return "tmrw"
        if diff < 7:
            return d.strftime("%a").lower()
        return d.strftime("%-m/%d")
    except Exception:
        return ""

# display task
def render_task(task, pick_num=None, col_width=28):
    t = Text()
    done = task["done"]
    color = PRIORITY_COLORS.get(task["priority"], "white")
    due_str = _fmt_due(task.get("due_date")) if not done else ""
    prefix_len = 4  # "[ ] " or "[x] " or "[1] "

    # budget for title: column width minus prefix, minus due date and its leading space
    due_space = (1 + len(due_str)) if due_str else 0
    max_title = col_width - prefix_len - due_space
    title = task["title"]
    if len(title) > max_title:
        title = title[:max_title - 1] + "…"

    if done:
        t.append("[x] ", style="dim")
        t.append(title, style="dim strike")
    elif pick_num is not None:
        t.append(f"[{pick_num}] ", style="cyan")
        t.append(title, style=color)
    else:
        t.append("[ ] ", style="dim")
        t.append(title, style=color)

    if due_str:
        due_style = "red" if due_str == "overdue" else "dim"
        t.append(f" {due_str}", style=due_style)

    return t

# display focus panel
def render_focus_panel(timer, suggestion):
    if not timer:
        return ["no active session", "", "", "", ""]

    label = timer["label"]
    rem = timer["remaining"]
    dur = timer["duration"]
    pomo_num = timer["pomo_num"]
    total = timer["pomo_total"]
    btype = timer["break_type"]

    bar = f"[{progress_bar(rem, dur)}]"
    time_str = fmt_timer(rem)
    next_str = ""

    if label == "break":
        from state import CYCLE, WORK_PHASES
        next_i = (timer["phase_index"] + 1) % len(CYCLE)
        next_label, _ = CYCLE[next_i]
        if next_label == "work":
            wi = WORK_PHASES.index(next_i) if next_i in WORK_PHASES else 0
            next_str = f"next: work · {wi + 1}/{total}"

    suggest_str = f"→ {suggestion}" if suggestion and label == "work" else ""
    if suggest_str and len(suggest_str) > 20:
        suggest_str = suggest_str[:19] + "…"

    lines = [time_str, bar]
    lines.append(next_str or suggest_str or "")
    while len(lines) < 5:
        lines.append("")
    return lines

# format calendar time
def _fmt_cal_time(t):
    if t in ("", "all day"):
        return t
    t = t.strip().lower()
    if t.endswith("am"):
        return t[:-2].strip() + "a"
    if t.endswith("pm"):
        return t[:-2].strip() + "p"
    return t

# display calendar (returns list of (kind, text) tuples)
def render_calendar(events):
    lines = []
    now_marker = False

    for e in events[:6]:
        if e.get("separator"):
            lines.append(("sep", "── tmrw ──"))
            continue

        time_str = _fmt_cal_time(e.get("time", ""))
        title = e["title"]
        if len(title) > 14:
            title = title[:13] + "…"

        is_now = e.get("now") and not now_marker
        if is_now:
            now_marker = True
            line = f"▶ {time_str:<7} {title}"
        else:
            line = f"  {time_str:<7} {title}"
        lines.append(("row", line))

    while len(lines) < 5:
        lines.append(("empty", ""))
    return lines

# truncate or right-pad plain string to exactly width chars
def _pad(text, width):
    if len(text) > width:
        return text[:width - 1] + "…"
    return text + " " * (width - len(text))

# build dashboard
def build_dashboard(tasks, events, timer, suggestion, weather_str, select_mode=None):
    lines = []

    # order by urgency so the most pressing tasks sit at the top; this is also
    # the order the numbered select labels follow (kept in sync with dash.py)
    tasks = sort_tasks(tasks)

    now = time.strftime("%I:%M %p").lstrip("0").lower()
    date_str = time.strftime("%A, %B %-d").lower()

    # header (date left, time right, total 80 chars)
    header = Text()
    padding = 80 - len(date_str) - len(now)
    header.append(date_str, style="bold white")
    header.append(" " * max(padding, 1))
    header.append(now, style="dim")
    lines.append(header)
    lines.append("")

    lines.append(Text(weather_str, style="dim"))
    lines.append("")
    lines.append(DIVIDER)

    focus_label = "focus"
    if timer:
        lbl = timer["label"]
        focus_label = (
            f"work · {timer['pomo_num']}/{timer['pomo_total']}"
            if lbl == "work" else f"break · {timer['break_type']}"
        )

    # column headers — tasks(28) + cal(28) + focus(rest)
    col_header = Text()
    col_header.append(_pad("tasks", 28), style="dim")
    col_header.append(_pad("calendar", 28), style="dim")
    col_header.append(focus_label, style="dim")
    lines.append(col_header)
    lines.append("")

    # number incomplete tasks when in select mode
    task_lines = []
    pick_num = 0
    for t in tasks:
        if select_mode and not t["done"]:
            pick_num += 1
            task_lines.append(render_task(t, pick_num if pick_num <= 9 else None))
        else:
            task_lines.append(render_task(t))

    cal_lines = render_calendar(events)
    focus_lines = render_focus_panel(timer, suggestion)
    row_count = max(len(task_lines), len(cal_lines), len(focus_lines))

    for i in range(row_count):
        row = Text()

        # task column (width 28)
        if i < len(task_lines):
            t = task_lines[i]
            pad = max(0, 28 - len(t.plain))
            row.append_text(t)
            row.append(" " * pad)
        else:
            row.append(" " * 28)

        # calendar column (width 28)
        if i < len(cal_lines):
            kind, text = cal_lines[i][0], cal_lines[i][1]
            padded = _pad(text, 28)
            if kind == "sep":
                row.append(padded, style="dim")
            else:
                row.append(padded)
        else:
            row.append(" " * 28)

        # focus column
        if i < len(focus_lines):
            row.append(focus_lines[i], style="cyan" if timer else "dim")

        lines.append(row)

    lines.append("")
    lines.append(DIVIDER)
    return lines

# display command bar
def render_command_bar(running):
    if running:
        return Text("a add  d done  x del  e edit  s stop  n skip  r review  q quit", style="dim")
    else:
        return Text("a add  d done  x del  e edit  s start  r review  q quit", style="dim")

# display input bar
def render_input_bar(prompt_text, mode="add"):
    t = Text()
    label = "edit> " if mode == "rename" else "> "
    t.append(label, style="green")
    t.append(prompt_text, style="white")
    t.append("_", style="green blink")
    return t

# display select bar (pick a task by number)
def render_select_bar(mode):
    labels = {"done": "done", "delete": "del", "edit": "edit"}
    action = labels.get(mode, mode)
    t = Text()
    t.append(f"{action}: ", style="cyan")
    t.append("pick a task (1-9)  ", style="dim")
    t.append("esc", style="dim")
    t.append(" cancel", style="dim")
    return t

# display dashboard
def print_dashboard(lines, command_bar):
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()
    for line in lines:
        console.print(line, end="\n")
    console.print(command_bar, end="\n")

# wrap text
def _wrap(text, prefix, cont, width):
    words = text.split()
    line_ = prefix
    wrapped = []
    for w in words:
        if len(line_) + len(w) + 1 > width:
            wrapped.append(line_)
            line_ = cont + w + " "
        else:
            line_ += w + " "
    if line_.strip():
        wrapped.append(line_)
    return wrapped

# display summary at end of pomo cycle
def print_cycle_summary(stats, summary_text):
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()
    console.print("")
    console.print(Text(DIVIDER, style="dim"))
    console.print("")
    console.print(Text("cycle complete", style="bold white"))
    console.print("")
    stat_line = (
        f"{stats['pomos']} pomos  ·  "
        f"{stats['done']} tasks completed  ·  "
        f"{stats['overdue']} overdue"
    )
    console.print(Text(stat_line, style="dim"))
    console.print("")
    for l in _wrap(summary_text, "→ ", "  ", 80):
        console.print(Text(l, style="dim"))
    console.print("")
    console.print(Text("next cycle starting...", style="dim"))
    console.print("")
    console.print(Text(DIVIDER, style="dim"))

# display review
def print_review(review_text, stats, tasks):
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()
    date_str = time.strftime("%A, %B %-d").lower()
    console.print("")
    console.print(Text(DIVIDER, style="dim"))
    console.print("")
    console.print(Text(date_str, style="bold white"))
    console.print("")
    stat_line = (
        f"{stats['pomos']} pomos  ·  "
        f"{stats['done']} tasks completed  ·  "
        f"{stats['carried']} carried over  ·  "
        f"{stats['overdue']} overdue"
    )
    console.print(Text(stat_line, style="dim"))
    console.print("")
    done_tasks = [t for t in tasks if t["done"]]
    left_tasks = [t for t in tasks if not t["done"]]
    if done_tasks:
        console.print(Text("completed", style="dim"))
        for t in done_tasks:
            console.print(Text(f"[x] {t['title']}", style="dim strike"))
        console.print("")
    if left_tasks:
        console.print(Text("carried over", style="dim"))
        for t in left_tasks:
            color = PRIORITY_COLORS.get(t["priority"], "white")
            console.print(Text(f"[ ] {t['title']}", style=color))
        console.print("")
    for l in _wrap(review_text, "→ ", "  ", 80):
        console.print(Text(l, style="dim"))
    console.print("")
    console.print(Text(DIVIDER, style="dim"))