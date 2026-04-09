import logging
import json
import time
from pathlib import Path
from typing import List, Dict, Optional
from playwright.sync_api import sync_playwright
import app as grok_app
from app import GrokTimeoutError
from config import VIDEOS_DIR

log = logging.getLogger("GrokAPI.ObjectVideoProcessor")

VIDEO_GENERATION_MAX_RETRIES = 3   # retries per module before giving up
RESTART_WAIT_S = 5                  # seconds between session restarts


def _start_video_session(story_id: str):
    """Launch a fresh Playwright + browser session for video generation."""
    p = sync_playwright().start()
    session = grok_app.start_session(None, p)
    session["p_context"] = p
    if session.get("status") != "success":
        p.stop()
        raise RuntimeError(f"Session init failed: {session.get('error')}")
    log.info(f"[obj_id: {story_id}] ✅ New browser session started")
    return session


def _close_video_session(session: dict, story_id: str):
    """Safely close browser and playwright context from a session dict."""
    browser = session.get("browser")
    p_context = session.get("p_context")
    session_log = session.get("log", log)
    try:
        if browser:
            grok_app.close_session(browser, session_log)
    except Exception:
        pass
    try:
        if p_context:
            p_context.stop()
    except Exception:
        pass
    log.info(f"[obj_id: {story_id}] 👋 Browser session closed")


def generate_object_modules_sequentially(
    story_id: str,
    modules: List[dict],
    image_paths: Optional[Dict[int, str]] = None,
) -> List[Path]:
    """
    Generates mp4 videos for each module sequentially using Playwright.

    Resilience features:
    - A single browser session is opened and reused across modules for efficiency.
    - If a GrokTimeoutError occurs (>2min), the session is closed and a fresh one
      is started before retrying the exact same module.
    - Modules with an existing output file are automatically skipped (resume).
    - After VIDEO_GENERATION_MAX_RETRIES failures the function raises.

    Args:
        story_id: Identifier for the current story/job.
        modules: List of module dictionaries containing prompts.
        image_paths: Optional dict mapping module_number → image file path.
    """
    log.info(f"[obj_id: {story_id}] 🚀 Starting object video processor session")

    generated_videos = []

    # Start the initial session
    session = _start_video_session(story_id)
    browser    = session["browser"]
    page       = session["page"]
    session_log = session["log"]

    try:
        for module in modules:
            module_number = module.get("module_number")
            video_prompt  = module.get("video_generation_prompt", "")
            image_prompt  = module.get("image_generation_prompt", "")

            # Ensure prompts are strings
            if not isinstance(video_prompt, str):
                video_prompt = json.dumps(video_prompt, ensure_ascii=False, indent=2)
            if not isinstance(image_prompt, str):
                image_prompt = json.dumps(image_prompt, ensure_ascii=False, indent=2)

            output_video_filename = f"module_{module_number}.mp4"
            output_video_path     = str(VIDEOS_DIR / output_video_filename)

            # ── Resume / Skip Logic ────────────────────────────────────────────
            if Path(output_video_path).exists() and Path(output_video_path).stat().st_size > 0:
                log.info(
                    f"[obj_id: {story_id}] [module_number: {module_number}] "
                    f"⏭️  Video already exists. Skipping."
                )
                generated_videos.append(Path(output_video_path))
                continue
            # ──────────────────────────────────────────────────────────────────

            # Determine if we have a pre-generated image for this module
            module_image_path = None
            if image_paths and module_number in image_paths:
                candidate = image_paths[module_number]
                if Path(candidate).exists() and Path(candidate).stat().st_size > 0:
                    module_image_path = candidate
                    log.info(
                        f"[obj_id: {story_id}] [module_number: {module_number}] "
                        f"🖼️  Using pre-generated image: {candidate}"
                    )

            success = False
            attempt = 0

            while attempt <= VIDEO_GENERATION_MAX_RETRIES and not success:
                log.info(
                    f"[obj_id: {story_id}] [module_number: {module_number}] "
                    f"🎬 Video generation attempt {attempt + 1}/{VIDEO_GENERATION_MAX_RETRIES + 1}"
                )

                try:
                    # Ensure we are in video mode for every attempt
                    grok_app._stage_video_mode(page, session_log)

                    if module_image_path:
                        grok_app._stage_upload_image(page, module_image_path, session_log)
                        prompt_text = video_prompt
                        log.info(
                            f"[obj_id: {story_id}] [module_number: {module_number}] "
                            f"📤 Image uploaded + video prompt only"
                        )
                    else:
                        prompt_text = f"IMAGE CONTEXT:\n{image_prompt}\n\n{video_prompt}".strip()
                        log.info(
                            f"[obj_id: {story_id}] [module_number: {module_number}] "
                            f"📝 Using combined text prompt (no pre-generated image)"
                        )

                    result = grok_app.generate_single_video(
                        page, prompt_text, output_video_path, session_log
                    )

                    if result.get("status") == "success":
                        log.info(
                            f"[obj_id: {story_id}] [module_number: {module_number}] "
                            f"✅ Video generated → {result['file_path']}"
                        )
                        success = True
                        generated_videos.append(Path(result["file_path"]))
                    else:
                        raise RuntimeError(result.get("error"))

                except GrokTimeoutError as e:
                    # ── Hard timeout: close session, start fresh, retry ──────────
                    log.warning(
                        f"[obj_id: {story_id}] [module_number: {module_number}] "
                        f"⏰ Generation TIMED OUT (attempt {attempt + 1}): {e}"
                    )

                    # Close the stale session
                    _close_video_session(session, story_id)

                    if attempt < VIDEO_GENERATION_MAX_RETRIES:
                        log.info(
                            f"[obj_id: {story_id}] [module_number: {module_number}] "
                            f"🔄 Restarting browser in {RESTART_WAIT_S}s and retrying …"
                        )
                        time.sleep(RESTART_WAIT_S)
                        # Start a completely fresh session
                        session      = _start_video_session(story_id)
                        browser      = session["browser"]
                        page         = session["page"]
                        session_log  = session["log"]
                    attempt += 1
                    continue

                except Exception as e:
                    log.error(
                        f"[obj_id: {story_id}] [module_number: {module_number}] "
                        f"❌ Failure (attempt {attempt + 1}): {e}"
                    )
                    if attempt < VIDEO_GENERATION_MAX_RETRIES:
                        log.info(
                            f"[obj_id: {story_id}] [module_number: {module_number}] "
                            f"🔄 Retrying in {RESTART_WAIT_S}s …"
                        )
                        time.sleep(RESTART_WAIT_S)
                    attempt += 1

            if not success:
                log.error(
                    f"[obj_id: {story_id}] 🛑 Stopped — "
                    f"module {module_number} failed after {VIDEO_GENERATION_MAX_RETRIES + 1} attempts"
                )
                raise RuntimeError(
                    f"Failed to generate obj module {module_number} after "
                    f"{VIDEO_GENERATION_MAX_RETRIES + 1} attempts"
                )

    finally:
        # Close the session that is currently active (may have been replaced on restart)
        _close_video_session(session, story_id)

    return generated_videos
