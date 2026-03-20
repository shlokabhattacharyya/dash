### IMPORT LIBRARIES AND SETUP
import httpx
import json
import re
import time

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3"


### FUNCTIONS
# send a prompt to ollama and return the response text
def _ask(prompt, timeout=30):
    try:
        r = httpx.post(
            OLLAMA_URL,
            json={"model": MODEL, "prompt": prompt, "stream": False},
            timeout=timeout,
        )
        return r.json().get("response", "").strip()
    except Exception:
        return None


# strip markdown code fences from a response string
def _strip_fences(text):
    text = text.strip()
    # remove opening fence (```json or ```)
    text = re.sub(r"^```(?:json)?\s*", "", text)
    # remove closing fence
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


# local keyword fallback — extract priority and due date without ai
def _local_parse(raw):
    text = raw.strip()
    priority = "medium"
    due_date = None

    # extract priority keywords
    for level in ("high", "low", "medium"):
        pattern = re.compile(
            r"\b(?:" + level + r"\s+priority|priority\s+" + level + r"|" + level + r"\s+pri)\b",
            re.IGNORECASE,
        )
        if pattern.search(text):
            priority = level
            text = pattern.sub("", text).strip()
            break

    # extract bare priority word only if it's clearly a tag, not part of the title
    if priority == "medium":
        for level in ("high", "low"):
            pattern = re.compile(r"\b" + level + r"\b", re.IGNORECASE)
            if pattern.search(text):
                priority = level
                text = pattern.sub("", text).strip()
                break

    # extract inline date (YYYY-MM-DD)
    date_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if date_match:
        due_date = date_match.group(1)
        text = text[:date_match.start()] + text[date_match.end():]

    # extract relative day keywords
    today = time.strftime("%Y-%m-%d")
    if re.search(r"\btoday\b", text, re.IGNORECASE):
        due_date = today
        text = re.sub(r"\btoday\b", "", text, flags=re.IGNORECASE)
    elif re.search(r"\btomorrow\b", text, re.IGNORECASE):
        import datetime
        tmrw = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        due_date = tmrw
        text = re.sub(r"\btomorrow\b", "", text, flags=re.IGNORECASE)

    # extract day-of-week keywords (next occurrence)
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for i, day in enumerate(days):
        if re.search(r"\b" + day + r"\b", text, re.IGNORECASE):
            import datetime
            today_dt = datetime.date.today()
            today_dow = today_dt.weekday()  # 0=monday
            delta = (i - today_dow) % 7
            if delta == 0:
                delta = 7  # next week if it's the same day
            due_date = (today_dt + datetime.timedelta(days=delta)).isoformat()
            text = re.sub(r"\b" + day + r"\b", "", text, flags=re.IGNORECASE)
            break

    # clean up extra whitespace and dangling punctuation
    title = re.sub(r"\s+", " ", text).strip().strip(",-–—").strip().lower()
    if not title:
        title = raw.strip().lower()

    return {"title": title, "priority": priority, "due_date": due_date}


# parse a natural language task string into structured fields
def parse_task(raw):
    today = time.strftime("%Y-%m-%d")
    prompt = f"""parse this task into json with exactly these fields:

                    - title: clean task title (string, lowercase)
                    - priority: one of "low", "medium", "high"
                    - due_date: date string YYYY-MM-DD or null

                today is {today}. keep the title lowercase.

                task: "{raw}"

                return only valid json, no markdown, no explanation, nothing else."""

    response = _ask(prompt, timeout=60)
    if not response: # fallback to local keyword parser
        return _local_parse(raw)

    try:
        clean = _strip_fences(response)
        return json.loads(clean)
    except Exception:
        return _local_parse(raw)

# suggest which task to focus on at the start of a work pomo
def suggest_focus(tasks, pomo_num, pomo_total, pomos_done):
    incomplete = [t for t in tasks if not t["done"]]
    if not incomplete:
        return "all tasks complete — add something new"

    task_list = "\n".join(
        f"- {t['title']} (priority: {t['priority']}, due: {t.get('due_date') or 'no due date'})"
        for t in incomplete
    )

    prompt = f"""you are a productivity assistant. suggest which single task the user should focus on right now.

                context:
                    - this is pomo {pomo_num} of {pomo_total} in the current cycle
                    - {pomos_done} pomos completed so far today

                incomplete tasks: {task_list}

                respond in one short line, e.g. "focus: fix auth bug"
                no explanation, no markdown, just the one line."""

    response = _ask(prompt, timeout=30)
    if not response:
        # fallback (pick first high priority task)
        high = next((t for t in incomplete if t["priority"] == "high"), incomplete[0])
        return f"focus: {high['title']}"
    return response.strip().lower()

# short summary shown at end of each 25/5/25/5/25/15 cycle
def generate_cycle_summary(tasks, pomos_done):
    done_today = [t for t in tasks if t["done"]]
    incomplete = [t for t in tasks if not t["done"]]
    today = time.strftime("%Y-%m-%d")
    overdue = [t for t in incomplete if t.get("due_date") and t["due_date"] < today]

    prompt = f"""you are a productivity assistant. write a short 1-2 sentence summary for the end of a pomodoro cycle.

                stats:
                    - pomos completed this cycle: 3
                    - total pomos today: {pomos_done}
                    - tasks completed today: {len(done_today)}
                    - tasks remaining: {len(incomplete)}
                    - overdue tasks: {len(overdue)}

                remaining tasks: {', '.join(t['title'] for t in incomplete) or 'none'}

                keep it brief, encouraging, and specific. lowercase. no markdown."""

    response = _ask(prompt, timeout=20)
    if not response:
        return f"cycle done. {len(done_today)} tasks completed, {len(incomplete)} remaining."
    return response.strip().lower()

# generate full end of day review
def generate_daily_review(tasks, pomos_done):
    done_today = [t for t in tasks if t["done"]]
    incomplete = [t for t in tasks if not t["done"]]
    today = time.strftime("%Y-%m-%d")
    overdue = [t for t in incomplete if t.get("due_date") and t["due_date"] < today]

    done_list = "\n".join(f"- {t['title']}" for t in done_today)   or "none"
    incomplete_list = "\n".join(f"- {t['title']}" for t in incomplete)   or "none"
    overdue_list = "\n".join(f"- {t['title']}" for t in overdue)      or "none"

    prompt = f"""you are a productivity assistant. write an end of day review.

                stats for today:
                    - total pomos: {pomos_done}
                    - tasks completed: {len(done_today)}
                    - tasks carried over: {len(incomplete)}
                    - overdue tasks: {len(overdue)}

                completed tasks: {done_list}

                carried over: {incomplete_list}

                overdue: {overdue_list}

                write 2-3 sentences. be specific about what was done and what to prioritize tomorrow. lowercase. no markdown."""

    response = _ask(prompt, timeout=30)
    if not response:
        return f"today: {pomos_done} pomos, {len(done_today)} tasks done, {len(incomplete)} carried over."
    return response.strip().lower()