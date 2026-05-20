import logging
import json
import time
import concurrent.futures
from pathlib import Path
from typing import List, Dict, Optional
from playwright.sync_api import sync_playwright
from app import grok_client as grok_app
from app.grok_client import GrokTimeoutError
from app.config import VIDEOS_DIR, VIDEO_PROFILES

log = logging.getLogger("GrokAPI.ObjectVideoProcessor")

VIDEO_GENERATION_MAX_RETRIES = 3   # retries per module before giving up
RESTART_WAIT_S = 5                  # seconds between session restarts


def _start_video_session(story_id: str, user_data_dir: str = None):
    """Launch a fresh Playwright + browser session for video generation."""
    p = sync_playwright().start()
    session = grok_app.start_session(None, p, user_data_dir=user_data_dir)
    session["p_context"] = p
    if session.get("status") != "success":
        p.stop()
        raise RuntimeError(f"Session init failed: {session.get('error')}")
    log.info(f"[obj_id: {story_id}] ✅ New browser session started with profile: {user_data_dir or 'Default'}")
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


def generate_object_modules_parallel(
    story_id: str,
    modules: List[dict],
    image_paths: Optional[Dict[int, str]] = None,
) -> List[Path]:
    """
    Generates mp4 videos for each module in PARALLEL using Playwright.

    Resilience features:
    - Up to 3 modules process at once using ThreadPoolExecutor.
    - Each module gets its own browser session with a dedicated profile.
    - 5-second staggered start for parallel threads.
    - If a GrokTimeoutError occurs (>2min), the session is closed and a fresh one
      is started before retrying the exact same module.
    - Modules with an existing output file are automatically skipped (resume).
    - After VIDEO_GENERATION_MAX_RETRIES failures the function raises.

    Args:
        story_id: Identifier for the current story/job.
        modules: List of module dictionaries containing prompts.
        image_paths: Optional dict mapping module_number → image file path.
    """
    log.info(f"[obj_id: {story_id}] 🚀 Starting PARALLEL object video processor session")

    generated_videos = []

    def process_module(module, worker_index):
        # ── 5-second stagger requirement ───────────────────────────────────
        stagger = worker_index * 5
        if stagger > 0:
            log.info(f"[obj_id: {story_id}] ⏳ Staggering thread {worker_index} by {stagger}s ...")
            time.sleep(stagger)

        # Pick a profile (if we have more modules than profiles, wrap around)
        profile_dir = VIDEO_PROFILES[worker_index % len(VIDEO_PROFILES)]
        
        module_number = module.get("module_number")
        video_prompt  = module.get("video_generation_prompt", "")
        image_prompt  = module.get("image_generation_prompt", "")

        # Ensure prompts are strings
        if not isinstance(video_prompt, str):
            video_prompt = json.dumps(video_prompt, ensure_ascii=False, indent=2)
        if not isinstance(image_prompt, str):
            image_prompt = json.dumps(image_prompt, ensure_ascii=False, indent=2)

        output_video_filename = f"module_{story_id}_{module_number}.mp4"
        output_video_path     = str(VIDEOS_DIR / output_video_filename)

        # ── Resume / Skip Logic ────────────────────────────────────────────
        if Path(output_video_path).exists() and Path(output_video_path).stat().st_size > 0:
            log.info(
                f"[obj_id: {story_id}] [module_number: {module_number}] "
                f"⏭️  Video already exists. Skipping."
            )
            return Path(output_video_path)
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
                f"🎬 Video generation attempt {attempt + 1}/{VIDEO_GENERATION_MAX_RETRIES + 1} (Profile: {profile_dir})"
            )

            session = None
            try:
                # Start a FRESH session for EVERY attempt, using dedicated profile
                session      = _start_video_session(story_id, user_data_dir=profile_dir)
                browser      = session["browser"]
                page         = session["page"]
                session_log  = session["log"]

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
                    return Path(result["file_path"])
                else:
                    raise RuntimeError(result.get("error"))

            except GrokTimeoutError as e:
                log.warning(
                    f"[obj_id: {story_id}] [module_number: {module_number}] "
                    f"⏰ Generation TIMED OUT (attempt {attempt + 1}): {e}"
                )
                if attempt < VIDEO_GENERATION_MAX_RETRIES:
                    log.info(
                        f"[obj_id: {story_id}] [module_number: {module_number}] "
                        f"🔄 Waiting {RESTART_WAIT_S}s before retrying with fresh browser …"
                    )
                    time.sleep(RESTART_WAIT_S)
                attempt += 1

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
            
            finally:
                # ALWAYS close the session after each attempt
                if session:
                    _close_video_session(session, story_id)

        if not success:
            log.error(
                f"[obj_id: {story_id}] 🛑 Stopped — "
                f"module {module_number} failed after {VIDEO_GENERATION_MAX_RETRIES + 1} attempts"
            )
            raise RuntimeError(
                f"Failed to generate obj module {module_number} after "
                f"{VIDEO_GENERATION_MAX_RETRIES + 1} attempts"
            )
        return None

    # Use ThreadPoolExecutor to run up to 3 at a time
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = []
        # Assign worker index based on original module order to stagger properly
        for idx, module in enumerate(modules):
            futures.append(executor.submit(process_module, module, idx))
        
        # We need to collect results but preserve order if possible, 
        # though the main code later handles them by filename/metadata.
        # as_completed returns results as they finish.
        for future in concurrent.futures.as_completed(futures):
            try:
                res = future.result()
                if res:
                    generated_videos.append(res)
            except Exception as e:
                log.error(f"[obj_id: {story_id}] ❌ Error in parallel execution: {e}")

    # Sort the list of video paths by module number (extracted from filename like 'module_123_1.mp4')
    # to ensure the final merge is in the correct sequence.
    try:
        generated_videos.sort(key=lambda x: int(x.stem.split('_')[-1]))
        log.info(f"[obj_id: {story_id}] 📊 Sorted {len(generated_videos)} modules in correct sequence")
    except Exception as e:
        log.warning(f"[obj_id: {story_id}] ⚠️ Failed to sort modules automatically: {e}")

    return generated_videos
