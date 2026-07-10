### IMPORT LIBRARIES AND SETUP
import sys
import subprocess

# toggles for the two alert channels (wired to the config file later)
NOTIFY_DESKTOP = True    # os-level popup notification
NOTIFY_SOUND   = True    # terminal bell

_SYSTEM = sys.platform   # "darwin", "linux", "win32", ...


### FUNCTIONS
# ring the terminal bell
def _bell():
    if not NOTIFY_SOUND:
        return
    try:
        sys.stdout.write("\a")
        sys.stdout.flush()
    except Exception:
        pass


# fire a desktop notification without blocking — fails silently if unsupported
def _desktop(title, message):
    if not NOTIFY_DESKTOP:
        return
    try:
        if _SYSTEM == "darwin":
            # escape double quotes so they don't break the applescript string
            t = title.replace('"', '\\"')
            m = message.replace('"', '\\"')
            script = f'display notification "{m}" with title "{t}"'
            subprocess.Popen(
                ["osascript", "-e", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif _SYSTEM.startswith("linux"):
            subprocess.Popen(
                ["notify-send", title, message],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        # other platforms fall through to the bell only
    except Exception:
        # notifier not installed or not permitted
        pass


# public: alert the user (bell + desktop popup)
def notify(title, message=""):
    _bell()
    _desktop(title, message)