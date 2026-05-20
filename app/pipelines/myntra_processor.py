import logging
import os
import time
from pathlib import Path
from typing import List
from playwright.sync_api import sync_playwright

import app as grok_app
from app import IMAGE_USER_DATA, GrokTimeoutError
from config import IMAGES_DIR

log = logging.getLogger("GrokAPI.MyntraProcessor")

MAX_RETRIES = 2
RESTART_WAIT_S = 5

# Phase 1 Prompt: Remove face, hands and neck from the Myntra product image
GROK_EDIT_PROMPT = (
    "Analyze the uploaded image and carefully remove the subject's hands, neck, and face. "
    "Seamlessly reconstruct the missing regions using surrounding visual context so the result "
    "looks natural, realistic, and anatomically consistent. Preserve the original body proportions, "
    "clothing, lighting, skin tone, textures, and overall composition without distortion. "
    "Ensure smooth blending with no visible cuts, seams, or artifacts. Keep the background unchanged. "
    "The final image should look naturally complete even without visible hands, neck, or face."
)

# Phase 2 Prompt: Dress the green screen model using the processed clothing image
GROK_DRESS_PROMPT = (
    "Use the FIRST IMAGE as the primary identity reference.\n\n"
    "STRICT IDENTITY LOCK:\n"
    "- Keep the EXACT same face, body shape, proportions, skin tone, and hairstyle.\n"
    "- Do NOT modify facial features or body in any way.\n"
    "- Same person, same identity, no variation.\n\n"
    "TASK:\n"
    "Analyze the PROVIDED CLOTHING REFERENCE IMAGE(S) and automatically extract:\n"
    "- garment type\n"
    "- colors\n"
    "- patterns\n"
    "- textures\n"
    "- embroidery/prints\n"
    "- fit and structure\n\n"
    "Then accurately dress the model in that exact outfit.\n\n"
    "RULES FOR CLOTHING TRANSFER:\n"
    "- Do NOT invent or simplify details\n"
    "- Preserve 1:1 design accuracy from reference images\n"
    "- Maintain exact stitching, embroidery, patterns, and fabric behavior\n"
    "- Ensure realistic cloth physics and proper fitting on the body\n"
    "- Maintain scale and placement of design elements\n\n"
    "POSE & FRAME:\n"
    "- Same pose as original (front-facing, standing straight, arms relaxed)\n"
    "- No pose change\n\n"
    "STYLE:\n"
    "- Ultra-realistic, photorealistic\n"
    "- High detail (4K)\n"
    "- Sharp focus\n"
    "- Natural lighting\n\n"
    "BACKGROUND:\n"
    "- Keep solid green screen background (chroma key green)\n\n"
    "NEGATIVE PROMPT:\n"
    "- different person\n"
    "- face change\n"
    "- body modification\n"
    "- incorrect outfit\n"
    "- missing details\n"
    "- distorted clothing\n"
    "- low quality\n"
    "- blur\n"
    "- cartoon\n"
    "- extra limbs"
)

# Path to the base model image (green screen model identity reference)
_BASE_DIR = Path(__file__).parent.parent
MYNTRA_BASE_MODEL_PATH = str(_BASE_DIR / "default_images" / "myntra.jpeg")


def _start_editing_session(p_context, image_path):
    """Launch a fresh browser session using the IMAGE Chrome profile and upload images."""
    log_session = grok_app._make_logger(f"GrokBot_Myntra_{os.getpid()}")
    try:
        browser = grok_app._stage_launch(p_context, log_session, user_data_dir=IMAGE_USER_DATA)
        page = grok_app._stage_navigate(browser, log_session)
        # Do NOT call _stage_video_mode — stays in Image mode
        grok_app._stage_upload_image(page, image_path, log_session)
        return {"browser": browser, "page": page, "log": log_session, "status": "success"}
    except Exception as e:
        log_session.error(f"❌ Session start failed: {e}")
        return {"browser": None, "page": None, "log": log_session, "status": "failure", "error": str(e)}


def _close_session(browser, p_context, product_id, index):
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
    log.info(f"[product_id: {product_id}] [img: {index}] 👋 Browser session closed")


def _custom_submit_and_wait(page, session_log):
    """Submit the prompt and wait until 'Make video' appears (signals generation done)."""
    session_log.info("STAGE 6 (Image): Submitting generation request")
    grok_app._human_delay(0.5, 1.5, "before pressing Enter", session_log)
    page.keyboard.press("Enter")
    session_log.info("✅ Generation request submitted. Waiting for 'Make video' to appear...")
    try:
        page.get_by_text("Make video").first.wait_for(state="visible", timeout=120000)
        session_log.info("✅ 'Make video' appeared! Image generation is complete.")
        time.sleep(2)
    except Exception as e:
        session_log.warning(f"⚠️ Timed out waiting for 'Make video' button: {e}")


def _custom_download_edited_image(page, output_path, session_log):
    """Click the download button in Grok's UI and intercept the download."""
    session_log.info("STAGE 8 (Image): Downloading generated image via download button")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    try:
        download_btn = None

        # Try aria-label selectors first
        for selector in [
            'button[aria-label="Download"]',
            'button[aria-label="download"]',
            'a[download]',
            'button:has(svg[data-icon="download"])',
        ]:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=2000):
                    download_btn = btn
                    session_log.info(f"✅ Found download button via selector: {selector}")
                    break
            except Exception:
                continue

        if download_btn is None:
            session_log.warning("⚠️ Could not find download button by aria-label, trying SVG icon approach")
            download_btn = page.locator('button').filter(has=page.locator('svg')).nth(-3)

        if download_btn:
            session_log.info("🖱️ Clicking download button and intercepting download...")
            with page.expect_download(timeout=30000) as download_info:
                download_btn.click()
            download = download_info.value
            download.save_as(output_path)

            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                mb = os.path.getsize(output_path) / (1024 * 1024)
                session_log.info(f"✅ Image downloaded via button: {output_path} ({mb:.2f} MB)")
                return True
            else:
                session_log.error("❌ Downloaded file is empty.")
                return False
        else:
            session_log.error("❌ Could not find download button on page.")
            return False

    except Exception as e:
        session_log.error(f"❌ Download via button failed: {e}")
        return False


def dress_model_with_grok(product_id: str, processed_paths: List[Path]) -> List[Path]:
    """
    Phase 2: Upload the green screen base model + each processed clothing image to Grok,
    send the dressing prompt, wait for generation, and download the dressed result.
    """
    log.info(f"[product_id: {product_id}] 👗 Phase 2: Starting model dressing for {len(processed_paths)} images.")

    if not Path(MYNTRA_BASE_MODEL_PATH).exists():
        log.error(f"❌ Base model image not found at {MYNTRA_BASE_MODEL_PATH}. Skipping Phase 2.")
        return []

    dressed_dir = IMAGES_DIR / "myntra" / product_id / "processed" / "dressed"
    dressed_dir.mkdir(parents=True, exist_ok=True)

    dressed_images = []

    for idx, clothing_image_path in enumerate(processed_paths):
        output_filename = f"dressed_{idx + 1}.jpg"
        output_path = str(dressed_dir / output_filename)

        if Path(output_path).exists() and Path(output_path).stat().st_size > 0:
            log.info(f"[product_id: {product_id}] [dress: {idx}] ⏭️  Dressed image already exists. Skipping.")
            dressed_images.append(Path(output_path))
            continue

        success = False
        attempt = 0

        while attempt <= MAX_RETRIES and not success:
            log.info(f"[product_id: {product_id}] [dress: {idx}] 👗 Dressing attempt {attempt + 1}/{MAX_RETRIES + 1}")

            p_context = None
            browser = None
            try:
                p_context = sync_playwright().start()
                log_session = grok_app._make_logger(f"GrokBot_Dress_{os.getpid()}_{idx}")

                browser = grok_app._stage_launch(p_context, log_session, user_data_dir=IMAGE_USER_DATA)
                page = grok_app._stage_navigate(browser, log_session)

                # Upload BOTH images: identity reference FIRST, then clothing reference
                image_paths = [MYNTRA_BASE_MODEL_PATH, str(clothing_image_path)]
                log_session.info(f"📤 Uploading 2 images: identity={MYNTRA_BASE_MODEL_PATH}, clothing={clothing_image_path}")
                grok_app._stage_upload_image(page, image_paths, log_session)

                # Enter prompt, submit, wait, download
                grok_app._stage_enter_prompt(page, GROK_DRESS_PROMPT, log_session)
                _custom_submit_and_wait(page, log_session)
                download_success = _custom_download_edited_image(page, output_path, log_session)

                if download_success and Path(output_path).exists() and Path(output_path).stat().st_size > 0:
                    log.info(f"[product_id: {product_id}] [dress: {idx}] ✅ Dressed image saved → {output_path}")
                    success = True
                    dressed_images.append(Path(output_path))
                else:
                    raise RuntimeError("Dressed image download failed or empty file.")

            except Exception as e:
                log.error(f"[product_id: {product_id}] [dress: {idx}] ❌ Failure: {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(RESTART_WAIT_S)
                attempt += 1

            finally:
                if browser is not None or p_context is not None:
                    _close_session(browser, p_context, product_id, f"dress_{idx}")

        if not success:
            log.error(f"[product_id: {product_id}] 🛑 Failed to dress image {idx} after {MAX_RETRIES + 1} attempts. Continuing.")

    log.info(f"[product_id: {product_id}] 🎉 Phase 2 complete. {len(dressed_images)}/{len(processed_paths)} images dressed.")
    return dressed_images


def process_myntra_images_with_grok(product_id: str, local_paths: List[str]) -> List[Path]:
    """
    Full pipeline:
    Phase 1: Remove face/hands from each Myntra scraped image.
    Phase 2: Dress the green screen model with each processed clothing image.
    """
    log.info(f"[product_id: {product_id}] 🚀 Starting full pipeline for {len(local_paths)} images.")

    processed_images = []
    processed_dir = IMAGES_DIR / "myntra" / product_id / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    # ── Phase 1: Remove face / hands ─────────────────────────────────────────
    for idx, input_image_path in enumerate(local_paths):
        output_image_filename = f"edited_{Path(input_image_path).name}"
        output_image_path = str(processed_dir / output_image_filename)

        if Path(output_image_path).exists() and Path(output_image_path).stat().st_size > 0:
            log.info(f"[product_id: {product_id}] [p1:{idx}] ⏭️  Already exists. Skipping.")
            processed_images.append(Path(output_image_path))
            continue

        success = False
        attempt = 0

        while attempt <= MAX_RETRIES and not success:
            log.info(f"[product_id: {product_id}] [p1:{idx}] 🖼️  Attempt {attempt + 1}/{MAX_RETRIES + 1}")

            p_context = None
            browser = None
            try:
                p_context = sync_playwright().start()
                session = _start_editing_session(p_context, input_image_path)

                if session.get("status") != "success":
                    raise RuntimeError(f"Session init failed: {session.get('error')}")

                browser = session["browser"]
                page = session["page"]
                session_log = session["log"]

                grok_app._stage_enter_prompt(page, GROK_EDIT_PROMPT, session_log)
                _custom_submit_and_wait(page, session_log)
                download_success = _custom_download_edited_image(page, output_image_path, session_log)

                if download_success and Path(output_image_path).exists() and Path(output_image_path).stat().st_size > 0:
                    log.info(f"[product_id: {product_id}] [p1:{idx}] ✅ Saved → {output_image_path}")
                    success = True
                    processed_images.append(Path(output_image_path))
                else:
                    raise RuntimeError("Download failed or empty file.")

            except GrokTimeoutError as e:
                log.warning(f"[product_id: {product_id}] [p1:{idx}] ⏰ Timeout: {e}")
                _close_session(browser, p_context, product_id, idx)
                browser = None
                p_context = None
                if attempt < MAX_RETRIES:
                    time.sleep(RESTART_WAIT_S)
                attempt += 1

            except Exception as e:
                log.error(f"[product_id: {product_id}] [p1:{idx}] ❌ Failure: {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(RESTART_WAIT_S)
                attempt += 1

            finally:
                if browser is not None or p_context is not None:
                    _close_session(browser, p_context, product_id, idx)

        if not success:
            log.error(f"[product_id: {product_id}] 🛑 Failed to process image {idx} after {MAX_RETRIES + 1} attempts.")

    log.info(f"[product_id: {product_id}] ✅ Phase 1 complete. {len(processed_images)}/{len(local_paths)} images processed.")

    # ── Phase 2: Dress model ──────────────────────────────────────────────────
    if processed_images:
        dress_model_with_grok(product_id, processed_images)

    return processed_images
