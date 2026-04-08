"""
Quick helper to launch Chromium with the IMAGE profile so you can log in to Grok.
Run this once, log in manually, then close the browser.
After that, the /api/generate_images endpoint will use this authenticated profile.

Usage:
    python setup_image_profile.py
"""
from playwright.sync_api import sync_playwright
import os, time

IMAGE_USER_DATA = os.path.expanduser("~/.config/chromium-bot-image-profile")

print(f"🚀 Launching Chromium with IMAGE profile: {IMAGE_USER_DATA}")
print("👉 Please log in to https://grok.com/imagine, then close the browser window.")
print("   This only needs to be done ONCE.\n")

with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(
        user_data_dir=IMAGE_USER_DATA,
        executable_path="/usr/bin/chromium",
        headless=False,
        args=[
            "--profile-directory=Default",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-setuid-sandbox",
            "--no-zygote",
            "--single-process",
        ],
        ignore_default_args=["--enable-automation"],
    )
    page = browser.pages[0] if browser.pages else browser.new_page()
    page.goto("https://grok.com/imagine", timeout=0, wait_until="domcontentloaded")
    
    print("✅ Browser opened. Log in and close the window when done.")
    
    # Wait until user closes the browser
    try:
        while True:
            time.sleep(1)
            # Check if browser is still alive
            try:
                page.evaluate("1")
            except:
                break
    except KeyboardInterrupt:
        pass
    
    try:
        browser.close()
    except:
        pass

print("✅ Profile saved! You can now use /api/generate_images.")
