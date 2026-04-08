import logging
import json
import time
from pathlib import Path
from typing import List
from playwright.sync_api import sync_playwright
import app as grok_app
from app import IMAGE_USER_DATA
from config import IMAGES_DIR

log = logging.getLogger("GrokAPI.ImageProcessor")

def generate_image_modules_sequentially(story_id: str, modules: List[dict]) -> List[Path]:
    """
    Generates images for each module sequentially using Playwright.
    Each module gets a FRESH browser session (open → generate → download → close)
    to avoid stale image issues from previous generations in the masonry grid.
    Uses a SEPARATE Chrome profile (IMAGE_USER_DATA) from the video endpoints.
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
        
        # --- Resume / Backup Logic ---
        if Path(output_image_path).exists() and Path(output_image_path).stat().st_size > 0:
            log.info(f"[story_id: {story_id}] [module_number: {module_number}] ⏭️ Image already exists. Skipping.")
            generated_images.append(Path(output_image_path))
            continue
        # -----------------------------
        
        success = False
        retries = 0
        max_retries = 3
        
        while retries <= max_retries and not success:
            log.info(f"[story_id: {story_id}] [module_number: {module_number}] 🎬 image prompt submitted (Attempt {retries + 1})")
            
            # Open a FRESH browser for each module using the IMAGE profile
            p_context = None
            browser = None
            try:
                p_context = sync_playwright().start()
                session = grok_app.start_session(None, p_context, user_data_dir=IMAGE_USER_DATA)
                
                if session.get("status") != "success":
                    raise RuntimeError(f"Session init failed: {session.get('error')}")
                
                browser = session["browser"]
                page = session["page"]
                session_log = session["log"]
                
                # Generate the image (no video mode — just enter prompt and download)
                result = grok_app.generate_single_image(page, image_prompt, output_image_path, session_log)
                
                if result.get("status") == "success":
                    log.info(f"[story_id: {story_id}] [module_number: {module_number}] ✅ image downloaded (file: {result['file_path']})")
                    success = True
                    generated_images.append(Path(result['file_path']))
                else:
                    raise RuntimeError(result.get("error"))
                    
            except Exception as e:
                log.error(f"[story_id: {story_id}] [module_number: {module_number}] ❌ failure: {e}")
                if retries < max_retries:
                    log.info(f"[story_id: {story_id}] [module_number: {module_number}] 🔄 retry attempt {retries + 1}")
                    time.sleep(5)
                retries += 1
            finally:
                # ALWAYS close the browser after each module
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
                    
        if not success:
            log.error(f"[story_id: {story_id}] 🛑 stopped processing due to module {module_number} failure")
            raise RuntimeError(f"Failed to generate image for module {module_number} after {max_retries} retries")

    return generated_images
