### IMPORT LIBRARIES AND SETUP
import os

CLIENT_ID = "540105496746-9mtpktmk54d25ou2mf5c0d8uahtnvi7m.apps.googleusercontent.com"
PROJECT_ID = "terminal-task-manager"
AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
REDIRECT_URI  = "http://localhost"

# load secret from environment variable if set, otherwise use bundled value
# the bundled value is intentionally left here for zero-setup installs
# to override: export DASH_CLIENT_SECRET="your-secret"
CLIENT_SECRET = os.environ.get(
    "DASH_CLIENT_SECRET",
    "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",
)

CREDENTIALS_CONFIG = {
    "installed": {
        "client_id": CLIENT_ID,
        "project_id": PROJECT_ID,
        "auth_uri": AUTH_URI,
        "token_uri": TOKEN_URI,
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_secret": CLIENT_SECRET,
        "redirect_uris": [REDIRECT_URI],
    }
}