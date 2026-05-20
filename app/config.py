import os
from pathlib import Path

# Project layout: this file lives at <project_root>/app/config.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASE_DIR = PROJECT_ROOT  # kept as alias for back-compat with callers using BASE_DIR

# Runtime data (gitignored)
DATA_DIR = PROJECT_ROOT / "data"
VIDEOS_DIR = DATA_DIR / "videos"
IMAGES_DIR = DATA_DIR / "images"
JOBS_DIR = DATA_DIR / "jobs"
for _d in (DATA_DIR, VIDEOS_DIR, IMAGES_DIR, JOBS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Static assets
ASSETS_DIR = PROJECT_ROOT / "assets"
IMAGE_PATH = str(ASSETS_DIR / "default.jpg")  # default static image path
VIDEO_PROFILES = [
    os.path.expanduser("~/.config/google-chrome-bot-profile-1"),
    os.path.expanduser("~/.config/google-chrome-bot-profile-2"),
    os.path.expanduser("~/.config/google-chrome-bot-profile-3")
]

# R2 Bucket Credentials
R2_ACCESS_KEY = "233810c82d9efd1375a5c9151bd88468"
R2_SECRET_KEY = "05e61949446f435cc659e88dafb01abbe8cf5597a91a18f9909b6a79dfb71452"
R2_ACCOUNT_ID = "6613a5931848e80d555ccf73b6e553e0"
R2_BUCKET_NAME = "ai-videos"

# Webhook Config
N8N_BASE_URL = "https://n8n.sonupandit.in"

# Video pipeline (shared inbound — n8n branches by video_type internally)
N8N_WEBHOOK_URL = f"{N8N_BASE_URL}/webhook/f399fe7e-c65b-4dd1-b848-0f4d50b569d4"

# object_talking
OBJECT_GET_SCRIPT_URL   = f"{N8N_BASE_URL}/webhook/df5a2f10-c375-4d79-90d6-c0f79c52e6f1"
OBJECT_STORE_SCRIPT_URL = f"{N8N_BASE_URL}/webhook/c24ec734-cf0c-40cd-b168-58779fcde463"
OBJECT_GET_MEMORY_URL   = f"{N8N_BASE_URL}/webhook/b475f8a7-00b1-4c61-be5e-25c2ea9ec393"
OBJECT_STORE_NAME_URL   = f"{N8N_BASE_URL}/webhook/ff045203-6928-4375-85af-208cf22b4d4c"

# food_discovery
FOOD_GET_SCRIPT_URL     = f"{N8N_BASE_URL}/webhook/df5a2f10-c375-4d79-90d6-c0f79c52e6f2"
FOOD_STORE_SCRIPT_URL   = f"{N8N_BASE_URL}/webhook/8f08ec11-d1ad-45d8-ae8f-4f9c37f72612"
FOOD_GET_MEMORY_URL     = f"{N8N_BASE_URL}/webhook/b475f8a7-00b1-4c61-be5e-25c2ea9ec391"
FOOD_STORE_NAME_URL     = f"{N8N_BASE_URL}/webhook/ff045203-6928-4375-85af-208cf22b4d4a"

VIDEO_PUBLIC_DOMAIN = "https://cdn.sonupandit.in"


# source venv/bin/activate
#   uvicorn app.server:app --host 0.0.0.0 --port 8000 --reload
