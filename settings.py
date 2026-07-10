### IMPORT LIBRARIES AND SETUP
import os
import json

DASH_DIR = os.path.expanduser("~/.dash")
CONFIG_FILE = os.path.join(DASH_DIR, "config.json")

# user-editable defaults — written to ~/.dash/config.json on first run
DEFAULTS = {
    "work_minutes": 25,
    "short_break_minutes": 5,
    "long_break_minutes": 15,
    "pomos_per_cycle": 3,          # work phases before the long break
    "units": "imperial",          # "imperial" (°f, mph) or "metric" (°c, km/h)
    "notify_desktop": True,        # os-level popup on phase change
    "notify_sound": True,          # terminal bell on phase change
    "latitude": None,              # weather override; leave null to auto-detect from ip
    "longitude": None,
    "city": None,
}


### FUNCTIONS
# clamp / sanitize values so a malformed config can't break the app
def _validate(cfg):
    for k in ("work_minutes", "short_break_minutes", "long_break_minutes", "pomos_per_cycle"):
        try:
            cfg[k] = max(1, int(cfg[k]))
        except (TypeError, ValueError):
            cfg[k] = DEFAULTS[k]
    if cfg.get("units") not in ("imperial", "metric"):
        cfg["units"] = DEFAULTS["units"]
    cfg["notify_desktop"] = bool(cfg.get("notify_desktop", True))
    cfg["notify_sound"] = bool(cfg.get("notify_sound", True))
    return cfg


# load config, filling missing keys from defaults; writes a starter file on first run so there's something to edit
# any failure falls back to defaults
def _load():
    cfg = dict(DEFAULTS)
    try:
        os.makedirs(DASH_DIR, exist_ok=True)
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE) as f:
                user = json.load(f)
            if isinstance(user, dict):
                for k in DEFAULTS:
                    if k in user:
                        cfg[k] = user[k]
        else:
            with open(CONFIG_FILE, "w") as f:
                json.dump(DEFAULTS, f, indent=2)
    except Exception:
        pass
    return _validate(cfg)


# loaded once at import — the whole app shares this dict
CONFIG = _load()