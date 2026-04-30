import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).parent
VIDEOS_DIR = BASE_DIR / "videos"
VIDEOS_DIR.mkdir(exist_ok=True)
IMAGES_DIR = BASE_DIR / "images"
IMAGES_DIR.mkdir(exist_ok=True)

# Application Context
IMAGE_PATH = str(BASE_DIR / "default.jpg") # Default static image path if needed
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
N8N_WEBHOOK_URL = "https://n8n.sonupandit.in/webhook/f399fe7e-c65b-4dd1-b848-0f4d50b569d4"
N8N_JOB_FETCH_URL = "https://n8n.sonupandit.in/webhook/df5a2f10-c375-4d79-90d6-c0f79c52e6f1"
VIDEO_PUBLIC_DOMAIN = "https://cdn.sonupandit.in"


# source venv/bin/activate
    #uvicorn server:app --host 0.0.0.0 --port 8000 --reload
