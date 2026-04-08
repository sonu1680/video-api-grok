import logging
import json
import time
from pathlib import Path
from typing import List, Dict, Optional
from playwright.sync_api import sync_playwright
import app as grok_app
from config import VIDEOS_DIR

log = logging.getLogger("GrokAPI.ObjectVideoProcessor")

def generate_object_modules_sequentially(
    story_id: str,
    modules: List[dict],
    image_paths: Optional[Dict[int, str]] = None
) -> List[Path]:
    """
    Generates mp4 videos for each module sequentially using Playwright.

    Args:
        story_id: Identifier for the current story/job.
        modules: List of module dictionaries containing prompts.
        image_paths: Optional dict mapping module_number → image file path.
                     When provided, the image is uploaded for that module and
                     only video_generation_prompt is used as the prompt text.
                     When not provided, falls back to the original combined-text behavior.

    Returns:
        List of pathlib.Path objects pointing to the generated videos.
    """
    log.info(f"[obj_id: {story_id}] 🚀 Starting object video processor session")

    generated_videos = []

    try:
        p = sync_playwright().start()
        # Start session WITHOUT an image (image will be uploaded per-module if available)
        session = grok_app.start_session(None, p)
        session["p_context"] = p
    except Exception as e:
        log.error(f"[obj_id: {story_id}] ❌ Failed to start browser session: {e}")
        raise RuntimeError(f"Playwright init failed: {e}")

    if session.get("status") != "success":
        log.error(f"[obj_id: {story_id}] ❌ Failed to start session: {session.get('error')}")
        raise RuntimeError(f"Session init failed: {session.get('error')}")

    browser = session["browser"]
    page = session["page"]
    session_log = session["log"]
    p_context = session["p_context"]

    try:
        for module in modules:
            module_number = module.get("module_number")
            video_prompt = module.get("video_generation_prompt", "")
            image_prompt = module.get("image_generation_prompt", "")

            # Ensure prompts are strings
            if not isinstance(video_prompt, str):
                video_prompt = json.dumps(video_prompt, ensure_ascii=False, indent=2)
            if not isinstance(image_prompt, str):
                image_prompt = json.dumps(image_prompt, ensure_ascii=False, indent=2)

            output_video_filename = f"module_{module_number}.mp4"
            output_video_path = str(VIDEOS_DIR / output_video_filename)

            # --- Resume / Backup Logic ---
            if Path(output_video_path).exists() and Path(output_video_path).stat().st_size > 0:
                log.info(f"[obj_id: {story_id}] [module_number: {module_number}] ⏭️ Video already exists. Skipping.")
                generated_videos.append(Path(output_video_path))
                continue
            # -----------------------------

            # Determine if we have a pre-generated image for this module
            module_image_path = None
            if image_paths and module_number in image_paths:
                candidate = image_paths[module_number]
                if Path(candidate).exists() and Path(candidate).stat().st_size > 0:
                    module_image_path = candidate
                    log.info(f"[obj_id: {story_id}] [module_number: {module_number}] 🖼️ Using pre-generated image: {candidate}")

            # Always ensure we are in video mode for every module
            grok_app._stage_video_mode(page, session_log)

            if module_image_path:
                # Upload the pre-generated image and use only the video prompt
                grok_app._stage_upload_image(page, module_image_path, session_log)
                prompt_text = video_prompt
                log.info(f"[obj_id: {story_id}] [module_number: {module_number}] 🎬 Image uploaded + video prompt")
            else:
                # Fallback: combine prompts as text (original behavior)
                prompt_text = f"IMAGE CONTEXT:\n{image_prompt}\n\n{video_prompt}".strip()
                log.info(f"[obj_id: {story_id}] [module_number: {module_number}] 🎬 Using combined text prompt (no image)")

            success = False
            retries = 0
            max_retries = 3

            while retries <= max_retries and not success:
                log.info(f"[obj_id: {story_id}] [module_number: {module_number}] 🎬 prompt submitted (Attempt {retries + 1})")

                try:
                    result = grok_app.generate_single_video(page, prompt_text, output_video_path, session_log)

                    if result.get("status") == "success":
                        log.info(f"[obj_id: {story_id}] [module_number: {module_number}] ✅ video generated (file: {result['file_path']})")
                        success = True
                        generated_videos.append(Path(result['file_path']))
                    else:
                        raise RuntimeError(result.get("error"))

                except Exception as e:
                    log.error(f"[obj_id: {story_id}] [module_number: {module_number}] ❌ failure: {e}")
                    if retries < max_retries:
                        log.info(f"[obj_id: {story_id}] [module_number: {module_number}] 🔄 retry attempt {retries + 1}")
                        time.sleep(5)
                    retries += 1

            if not success:
                log.error(f"[obj_id: {story_id}] 🛑 stopped processing due to module {module_number} failure")
                raise RuntimeError(f"Failed to generate obj module {module_number} after {max_retries} retries")

        return generated_videos

    finally:
        grok_app.close_session(browser, session_log)
        if p_context:
            p_context.stop()
        log.info(f"[obj_id: {story_id}] 👋 Browser session closed")
