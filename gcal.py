### IMPORT LIBRARIES AND SETUP
import os
import time
import datetime
import json

# google calendar dependencies
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import CREDENTIALS_CONFIG

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
DASH_DIR = os.path.expanduser("~/.dash")
TOKEN_FILE = os.path.join(DASH_DIR, "token.json")

_cache = {"events": [], "fetched_at": 0}
CACHE_TTL = 300


### FUNCTIONS
# get Google credentials
def _get_credentials():

    creds = None
    os.makedirs(DASH_DIR, exist_ok=True)

    # load existing token if it exists
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # if no valid creds, do the oauth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow  = InstalledAppFlow.from_client_config(CREDENTIALS_CONFIG, SCOPES)
            creds = flow.run_local_server(
                port = 0,
                success_message  = "dash is connected to your google calendar. you may close this tab now.",
                open_browser  = True,
            )

        # save token with restricted permissions - owner read/write only
        token_data = creds.to_json()
        fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(token_data)

    return creds


# parse times of events
def _parse_event_time(event):

    # handle both timed events and all-day events
    start = event.get("start", {})
    end = event.get("end",   {})

    if "dateTime" in start: # timed event
        start_dt = datetime.datetime.fromisoformat(start["dateTime"])
        end_dt = datetime.datetime.fromisoformat(end["dateTime"])
        all_day = False
    else: # all-day event
        d = datetime.date.fromisoformat(start["date"])
        start_dt = datetime.datetime.combine(d, datetime.time.min)
        d_end = datetime.date.fromisoformat(end["date"])
        end_dt = datetime.datetime.combine(d_end, datetime.time.min)
        all_day = True

    return start_dt, end_dt, all_day

# format time
def _fmt_time(dt, all_day):
    if all_day:
        return "all day"
    return dt.strftime("%-I:%M %p").lower()

# fetch events from calendar
def fetch_events():
    now = time.time()
    if _cache["events"] and (now - _cache["fetched_at"]) < CACHE_TTL:
        return _cache["events"]

    try:
        creds = _get_credentials()
        if not creds:
            return _fallback_events()

        service = build("calendar", "v3", credentials=creds)

        # fetch from start of today through end of tomorrow
        today = datetime.datetime.now().astimezone()
        start_of_day = today.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_tomorrow = (start_of_day + datetime.timedelta(days=2))

        result = service.events().list(
            calendarId = "primary",
            timeMin = start_of_day.isoformat(),
            timeMax = end_of_tomorrow.isoformat(),
            maxResults = 20,
            singleEvents = True,
            orderBy = "startTime",
        ).execute()

        raw_events = result.get("items", [])
        now_dt = datetime.datetime.now().astimezone()
        today_date = now_dt.date()
        events = []

        for e in raw_events:
            title = e.get("summary", "(no title)").lower()
            start_dt, end_dt, all_day = _parse_event_time(e)

            # make timezone-aware for comparison
            if start_dt.tzinfo is None:
                start_dt = start_dt.astimezone()
            if end_dt.tzinfo is None:
                end_dt = end_dt.astimezone()

            is_today = start_dt.date() == today_date
            is_tomorrow = start_dt.date() == today_date + datetime.timedelta(days=1)

            events.append({
                "title": title,
                "time": _fmt_time(start_dt, all_day),
                "start_dt": start_dt,
                "end_dt": end_dt,
                "all_day": all_day,
                "is_today": is_today,
                "is_tmrw": is_tomorrow,
                "now": False,
            })

        _mark_active_or_next(events, now_dt)

        _cache["events"] = events
        _cache["fetched_at"] = time.time()
        return events

    except Exception:
        return _fallback_events()

# mark either currently active event or the upcoming next one
def _mark_active_or_next(events, now_dt):
    # try to mark any currently active event
    active_found = False
    for e in events:
        if not e["all_day"] and e["start_dt"] <= now_dt < e["end_dt"]:
            e["now"] = True
            active_found  = True
            break

    # if nothing active, mark the next upcoming event today
    if not active_found:
        for e in events:
            if e["is_today"] and not e["all_day"] and e["start_dt"] > now_dt:
                e["now"] = True
                break

# shown if credentials.json is missing or auth fails
def _fallback_events():
    return [{"title": "add credentials.json to ~/.dash", "time": "", "now": False, "is_today": True, "is_tmrw": False, "all_day": False}]

# display events on window
def get_display_events():
    events = fetch_events()
    now_dt = datetime.datetime.now().astimezone()
    today = now_dt.date()

    # split into today and tomorrow
    today_events = [e for e in events if e["is_today"]]
    tmrw_events = [e for e in events if e["is_tmrw"]]

    display = []

    for e in today_events:
        display.append({
            "time":  e["time"],
            "title": e["title"],
            "now":   e["now"],
        })

    if tmrw_events:
        display.append({"time": "── tmrw", "title": "──", "now": False, "separator": True})
        for e in tmrw_events[:2]:  # cap at 2 tomorrow events to save space
            display.append({
                "time":  e["time"],
                "title": e["title"],
                "now":   False,
            })

    return display