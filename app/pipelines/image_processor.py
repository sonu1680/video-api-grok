import logging
import json
import time
from pathlib import Path
from typing import List
from playwright.sync_api import sync_playwright
from app import grok_client as grok_app
from app.grok_client import IMAGE_USER_DATA, GrokTimeoutError
from app.config import IMAGES_DIR

log = logging.getLogger("GrokAPI.ImageProcessor")

IMAGE_GENERATION_TIMEOUT_S = 120   # 2-minute hard limit per module attempt
MAX_RETRIES = 3                     # max retries before giving up
RESTART_WAIT_S = 5                  # seconds to wait between browser restarts


def _start_image_session(p_context):
    """Launch a fresh browser session using the IMAGE Chrome profile."""
    session = grok_app.start_session(None, p_context, user_data_dir=IMAGE_USER_DATA)
    if session.get("status") != "success":
        raise RuntimeError(f"Session init failed: {session.get('error')}")
    return session


def _close_image_session(browser, p_context, story_id, module_number):
    """Safely close both browser and playwright context."""
    try:
        if browser:
            grok_app.close_session(browser, log)
    except Exception:
        pass
    try:
        if p_context:
            p_context.stop()
    except Exception:
        pass
    log.info(f"[story_id: {story_id}] [module_number: {module_number}] 👋 Browser session closed")


def generate_image_modules_sequentially(story_id: str, modules: List[dict]) -> List[Path]:
    """
    Generates images for each module sequentially using Playwright.
    Each module gets a FRESH browser session (open → generate → download → close)
    to avoid stale image issues from previous generations in the masonry grid.
    Uses a SEPARATE Chrome profile (IMAGE_USER_DATA) from the video endpoints.

    Resilience features:
    - If a GrokTimeoutError occurs (>2min), the browser session is closed and a
      fresh one is started before retrying.
    - Modules that already have an output file are automatically skipped (resume).
    - After MAX_RETRIES failures the function raises to stop the pipeline.
    """
    log.info(f"[story_id: {story_id}] 🚀 Starting image processor")

    generated_images = []

    story_images_dir = IMAGES_DIR / story_id
    story_images_dir.mkdir(parents=True, exist_ok=True)

    for module in modules:
        module_number = module.get("module_number")
        image_prompt = module.get("image_generation_prompt", "")

        # Ensure prompt is string
        if not isinstance(image_prompt, str):
            image_prompt = json.dumps(image_prompt, ensure_ascii=False, indent=2)

        output_image_filename = f"module_{module_number}img.jpg"
        output_image_path = str(story_images_dir / output_image_filename)

        # ── Resume / Skip Logic ────────────────────────────────────────────────
        if Path(output_image_path).exists() and Path(output_image_path).stat().st_size > 0:
            log.info(f"[story_id: {story_id}] [module_number: {module_number}] ⏭️  Image already exists. Skipping.")
            generated_images.append(Path(output_image_path))
            continue
        # ──────────────────────────────────────────────────────────────────────

        success = False
        attempt = 0

        while attempt <= MAX_RETRIES and not success:
            log.info(
                f"[story_id: {story_id}] [module_number: {module_number}] "
                f"🖼️  Image generation attempt {attempt + 1}/{MAX_RETRIES + 1}"
            )

            p_context = None
            browser = None
            try:
                p_context = sync_playwright().start()
                session = _start_image_session(p_context)
                browser = session["browser"]
                page = session["page"]
                session_log = session["log"]

                result = grok_app.generate_single_image(
                    page, image_prompt, output_image_path, session_log
                )

                if result.get("status") == "success":
                    log.info(
                        f"[story_id: {story_id}] [module_number: {module_number}] "
                        f"✅ Image downloaded → {result['file_path']}"
                    )
                    success = True
                    generated_images.append(Path(result["file_path"]))
                else:
                    raise RuntimeError(result.get("error"))

            except GrokTimeoutError as e:
                # ── Hard timeout: close browser, wait, then retry with fresh session ──
                log.warning(
                    f"[story_id: {story_id}] [module_number: {module_number}] "
                    f"⏰ Generation TIMED OUT (attempt {attempt + 1}): {e}"
                )
                _close_image_session(browser, p_context, story_id, module_number)
                browser = None
                p_context = None  # prevent double-close in finally

                if attempt < MAX_RETRIES:
                    log.info(
                        f"[story_id: {story_id}] [module_number: {module_number}] "
                        f"🔄 Restarting browser and retrying in {RESTART_WAIT_S}s …"
                    )
                    time.sleep(RESTART_WAIT_S)
                attempt += 1
                continue

            except Exception as e:
                log.error(
                    f"[story_id: {story_id}] [module_number: {module_number}] "
                    f"❌ Failure (attempt {attempt + 1}): {e}"
                )
                if attempt < MAX_RETRIES:
                    log.info(
                        f"[story_id: {story_id}] [module_number: {module_number}] "
                        f"🔄 Retrying in {RESTART_WAIT_S}s …"
                    )
                    time.sleep(RESTART_WAIT_S)
                attempt += 1

            finally:
                # ALWAYS close the browser after each module (unless already closed above)
                if browser is not None or p_context is not None:
                    _close_image_session(browser, p_context, story_id, module_number)

        if not success:
            log.error(
                f"[story_id: {story_id}] 🛑 Stopped processing — "
                f"module {module_number} failed after {MAX_RETRIES + 1} attempts"
            )
            raise RuntimeError(
                f"Failed to generate image for module {module_number} after {MAX_RETRIES + 1} attempts"
            )

    return generated_images
