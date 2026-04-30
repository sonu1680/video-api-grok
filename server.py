"""
Grok Video Generation – FastAPI Server
========================================
Endpoints:
  GET  /api/getvideo/{prompt}          – Generate & stream back the MP4
  POST /api/getvideo  body: {"prompt"} – Same but accepts JSON body
  GET  /health                         – Health check + queue status

Usage:
  uvicorn server:app --host 0.0.0.0 --port 8000 --reload
"""

import asyncio
import os
import sys
import uuid
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from send2trash import send2trash

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

# Import our automation core
import app as grok_app

# Import job persistence
from cache.job_persistence import JobPersistence

# ─────────────────────────── CONFIG ───────────────────────────────────────────

BASE_DIR     = Path(__file__).parent
VIDEOS_DIR   = BASE_DIR / "videos"          # temp storage for generated videos
MAX_QUEUE    = 5                             # max jobs waiting in queue

VIDEOS_DIR.mkdir(exist_ok=True)

# ─────────────────────────── LOGGING ──────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("GrokAPI")

# ─────────────────────────── QUEUE / SEMAPHORE ────────────────────────────────
# Only ONE Chrome session can run at a time; we serialize with a semaphore 
# and track active jobs for the /health endpoint.

_chrome_lock  = asyncio.Semaphore(1)   # serialise generation (1 at a time)
_pending_jobs: dict[str, dict] = {}    # job_id → {"status", "prompt", "path"}


# ─────────────────────────── LIFESPAN ─────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("🚀 GrokAPI server starting …")
    log.info(f"   Videos dir: {VIDEOS_DIR}")

    # ── Resume unfinished jobs from before last shutdown ──────────────────────
    pending = JobPersistence.list_pending()
    if pending:
        log.info(f"🔁 Found {len(pending)} unfinished job(s) — resuming …")
        for job in pending:
            job_id        = job["job_id"]
            pipeline_type = job["pipeline_type"]
            stories_raw   = job["stories"]

            # Reconstruct story Pydantic objects from raw dicts
            story_objs = []
            for s in stories_raw:
                try:
                    story_objs.append(StoryPayload(**s))
                except Exception as e:
                    log.warning(f"  ⚠️ Could not deserialize story in job {job_id}: {e}")

            if not story_objs:
                log.warning(f"  ⚠️ Job {job_id} has no valid stories — skipping.")
                JobPersistence.mark_failed(job_id, "No valid stories on resume")
                continue

            log.info(f"  ▶ Resuming job {job_id} ({pipeline_type}) with {len(story_objs)} stories")
            if pipeline_type == "objectvideo":
                asyncio.create_task(_run_objectvideo_pipeline(story_objs, job_id=job_id))
            elif pipeline_type == "generate_images":
                asyncio.create_task(_run_image_pipeline(story_objs, job_id=job_id))
            else:
                log.warning(f"  ⚠️ Unknown pipeline type '{pipeline_type}' for job {job_id}")
    else:
        log.info("✅ No pending jobs to resume.")
        # If no pending jobs on startup, check the webhook
        asyncio.create_task(_trigger_next_job_if_idle())

    async def _polling_loop():
        """Continuously polls for new jobs every 5 minutes."""
        while True:
            await asyncio.sleep(300)  # 5 minutes
            log.info("⏰ 5-minute interval reached. Checking for new jobs...")
            await _trigger_next_job_if_idle()

    # Start the continuous 5-minute polling loop
    asyncio.create_task(_polling_loop())

    yield
    log.info("👋 GrokAPI server shutting down.")


# ─────────────────────────── APP ──────────────────────────────────────────────

app = FastAPI(
    title="Grok Video Generator API",
    description="POST or GET a text prompt → receive a generated MP4 video.",
    version="2.0.0",
    lifespan=lifespan,
)


# ─────────────────────────── SCHEMAS ──────────────────────────────────────────

class PromptBody(BaseModel):
    prompt: str

from typing import List, Any, Union, Optional
import json

class ModulePayload(BaseModel):
    module_number: int
    video_generation_prompt: Any
    voiceover: Optional[str] = None

    class Config:
        extra = "allow"

class StoryPayload(BaseModel):
    id: Optional[Union[int, str]] = None
    story_id: Optional[Union[int, str]] = None
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[str] = None
    voiceover_main_prompt: Optional[str] = None
    voiceover_script: Optional[str] = None
    modules: List[ModulePayload]

    class Config:
        extra = "allow"

class TestPayload(BaseModel):
    stories: List[StoryPayload]


# ─────────────────────────── HELPERS ──────────────────────────────────────────

async def _run_generation(prompt: str) -> str:
    """
    Run the blocking Playwright automation in a thread-pool executor
    while holding the Chrome semaphore so only one job runs at a time.
    """
    job_id     = uuid.uuid4().hex[:8]
    # Use default output path (output.mp4 in project root, replaces old one)
    output_path = str(BASE_DIR / "output.mp4")

    from app import IMAGE_PATH

    log.info(f"[{job_id}] Queued: «{prompt[:60]}»")
    _pending_jobs[job_id] = {"status": "queued", "prompt": prompt, "path": output_path}

    async with _chrome_lock:
        log.info(f"[{job_id}] Starting …")
        _pending_jobs[job_id]["status"] = "running"
        loop = asyncio.get_running_loop()
        try:
            # generate_video is synchronous – run in thread pool
            result = await loop.run_in_executor(None, grok_app.generate_video, prompt, IMAGE_PATH, output_path)
            
            if result["status"] == "success":
                _pending_jobs[job_id]["status"] = "done"
                log.info(f"[{job_id}] Done → {result['file_path']}")
                return result["file_path"]
            else:
                raise RuntimeError(result["error"])
        except Exception as e:
            _pending_jobs[job_id]["status"] = f"failed: {e}"
            log.error(f"[{job_id}] FAILED: {e}")
            raise RuntimeError(str(e)) from e


def _cleanup(path: str) -> None:
    """Delete temp video file after response is sent."""
    try:
        if os.path.exists(path):
            send2trash(path)
            log.info(f"🗑️  Cleaned up {path}")
    except Exception as e:
        log.warning(f"Cleanup failed for {path}: {e}")


async def _process_payload_sequentially(payload: Union[TestPayload, List[StoryPayload]], video_type: str = "storyvideo"):
    stories = payload.stories if isinstance(payload, TestPayload) else payload
    
    from modules.video_processor import generate_modules_sequentially
    from modules.video_merger import merge_videos
    from modules.video_uploader import upload_video_to_r2
    from modules.webhook_sender import send_n8n_webhook
    import datetime

    for story in stories:
        current_story_id = story.story_id if story.story_id is not None else story.id
        # Sort modules by module_number to ensure strict sequential processing
        modules = sorted(story.modules, key=lambda m: m.module_number)
        
        async with _chrome_lock:
            # We hold the lock for the entire story so the browser session is isolated.
            loop = asyncio.get_running_loop()
            
            try:
                # 1. Generate Videos
                def _run_generation_task():
                    # We pass model dictionaries rather than Pydantic objects since sync playwright runs in another thread easily
                    module_dicts = [m.dict() for m in modules]
                    use_default = (video_type == "dovvideo")
                    return generate_modules_sequentially(str(current_story_id), module_dicts, use_default_image_first_module=use_default)
                
                generated_video_paths = await loop.run_in_executor(None, _run_generation_task)
                
                if not generated_video_paths:
                    log.warning(f"[story_id: {current_story_id}] ⚠️ No videos generated, skipping merge.")
                    continue
                    
                # 2. Merge Videos
                def _run_merge_task():
                    return merge_videos(str(current_story_id), generated_video_paths, None)
                    
                final_video_path = await loop.run_in_executor(None, _run_merge_task)
                
                # 3. Upload to R2
                timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                prefix = "dov_video_" if video_type == "dovvideo" else "video_"
                bucket_filename = f"videos/{prefix}{timestamp_str}.mp4"
                
                log.info(f"[story_id: {current_story_id}] ☁️ Uploading {final_video_path.name} to R2 bucket as {bucket_filename}...")
                
                def _run_upload_task():
                     return upload_video_to_r2(str(final_video_path.absolute()), bucket_filename)
                     
                upload_success = await loop.run_in_executor(None, _run_upload_task)
                
                if upload_success:
                    # 4. Send Webhook
                    def _run_webhook_task():
                        return send_n8n_webhook(
                            str(current_story_id), 
                            bucket_filename, 
                            timestamp_str, 
                            title=story.title,
                            description=story.description,
                            tags=story.tags,
                            source_video_path=str(final_video_path.absolute()),
                            video_type=video_type
                        )
                    
                    webhook_success = await loop.run_in_executor(None, _run_webhook_task)
                    
                    if webhook_success:
                        import shutil
                        log.info(f"[story_id: {current_story_id}] 🧹 Webhook successful. Cleaning up videos directory...")
                        if VIDEOS_DIR.exists():
                            try:
                                send2trash(str(VIDEOS_DIR.absolute()))
                                VIDEOS_DIR.mkdir(exist_ok=True)
                                log.info(f"[story_id: {current_story_id}] ✅ Videos folder sent to trash and recreated.")
                            except Exception as cleanup_err:
                                log.error(f"[story_id: {current_story_id}] ❌ Failed to clean videos folder: {cleanup_err}")
                    
            except Exception as e:
                log.error(f"[story_id: {current_story_id}] ❌ Sequence failed: {e}")


# ─────────────────────────── ROUTES ───────────────────────────────────────────

@app.get("/health", summary="Health check + queue status")
async def health():
    return JSONResponse({
        "status": "ok",
        "active_jobs": len(_pending_jobs),
        "jobs": {
            jid: {"status": info["status"], "prompt": info["prompt"][:80]}
            for jid, info in _pending_jobs.items()
        },
    })


@app.get(
    "/api/getvideo/{prompt:path}",
    summary="Generate a video from a URL-encoded prompt",
    response_description="The generated MP4 video file",
)
async def get_video_from_path(prompt: str, background_tasks: BackgroundTasks):
    """
    **Example:**
    ```
    GET /api/getvideo/a dog playing in the snow
    ```
    The prompt can contain spaces and special chars (URL-encoded by the client).
    Returns the MP4 file directly in the response body.
    """
    return await _handle_generation(prompt, background_tasks)


@app.post(
    "/api/getvideo",
    summary="Generate a video from a JSON body prompt",
    response_description="The generated MP4 video file",
)
async def post_video(body: PromptBody, background_tasks: BackgroundTasks):
    """
    **Example:**
    ```json
    POST /api/getvideo
    {"prompt": "a dog playing in the snow"}
    ```
    """
    return await _handle_generation(body.prompt, background_tasks)


@app.post(
    "/api/process_payload",
    summary="Process a test payload sequentially",
)
async def process_test_payload(payload: Union[TestPayload, List[StoryPayload]], background_tasks: BackgroundTasks):
    """
    Process a payload of stories with sequential video generation modules.
    """
    background_tasks.add_task(_process_payload_sequentially, payload)
    return JSONResponse({"status": "processing", "message": "Payload processing started in the background."})


@app.post(
    "/api/dov_video",
    summary="Process a dov payload sequentially with default image for module 1",
)
async def api_dov_video(payload: Union[TestPayload, List[StoryPayload]], background_tasks: BackgroundTasks):
    """
    Similar to process_payload, but module 1 uploads the default image.
    """
    background_tasks.add_task(_process_payload_sequentially, payload, "dovvideo")
    return JSONResponse({"status": "processing", "message": "DOV Payload processing started in the background."})


@app.post(
    "/api/objectvideo",
    summary="Generate an object video purely from text prompts",
)
async def api_objectvideo(payload: Union[TestPayload, List[StoryPayload]], background_tasks: BackgroundTasks):
    """
    Acts like process_payload but uses a simplified pipeline:
    For each module, the image_generation_prompt and video_generation_prompt 
    are combined into a single text prompt and sent directly to Grok's video mode.
    No image frames are extracted or uploaded between modules.
    """
    stories = payload.stories if isinstance(payload, TestPayload) else payload

    # Persist payload so the job can be resumed after a server restart
    story_dicts = [s.dict() for s in stories]
    job_id = JobPersistence.create("objectvideo", story_dicts)
    log.info(f"💾 Persisted objectvideo job {job_id} with {len(story_dicts)} stories")

    background_tasks.add_task(_run_objectvideo_pipeline, stories, job_id)
    return JSONResponse(
        status_code=202,
        content={"status": "processing", "job_id": job_id, "message": "Object video generation started in the background."}
    )


async def _run_objectvideo_pipeline(stories: list, job_id: str = None) -> None:
    """
    Background worker for /api/objectvideo.
    Phase 1: Generate images for all modules (separate Chrome profile).
    Phase 2: Generate videos with those images uploaded (default Chrome profile).
    Then merges, uploads to R2, and fires webhook.

    job_id: If provided, progress is checkpointed and the job file is cleaned up on success.
    """
    import datetime
    from modules.image_processor import generate_image_modules_sequentially
    from modules.video_merger import merge_videos
    from modules.video_uploader import upload_video_to_r2
    from modules.webhook_sender import send_n8n_webhook

    if job_id:
        JobPersistence.mark_running(job_id)

    for story in stories:
        current_story_id = str(story.story_id if story.story_id is not None else story.id)
        modules = sorted(story.modules, key=lambda m: m.module_number)
        
        async with _chrome_lock:
            loop = asyncio.get_running_loop()
            try:
                # ── PHASE 1: Generate images for all modules ─────────────────
                # Check if Phase 1 was already completed (resume case)
                prog = JobPersistence.get_progress(job_id, current_story_id) if job_id else {}
                
                if prog.get("phase1_done"):
                    log.info(f"[story_id: {current_story_id}] ⏭️  Phase 1 already done — loading cached image paths")
                    from config import IMAGES_DIR
                    generated_image_paths = []
                    for m in modules:
                        p = IMAGES_DIR / current_story_id / f"module_{m.module_number}img.jpg"
                        if p.exists() and p.stat().st_size > 0:
                            generated_image_paths.append(p)
                else:
                    log.info(f"[story_id: {current_story_id}] 📸 Phase 1: Generating images …")

                    def _run_image_gen():
                        module_dicts = [m.dict() for m in modules]
                        return generate_image_modules_sequentially(current_story_id, module_dicts)

                    generated_image_paths = await loop.run_in_executor(None, _run_image_gen)

                    if job_id:
                        JobPersistence.update_progress(job_id, current_story_id, phase1_done=True)

                # Build image_paths dict: module_number → image file path
                image_paths = {}
                for module, img_path in zip(modules, generated_image_paths):
                    image_paths[module.module_number] = str(img_path)

                log.info(f"[story_id: {current_story_id}] ✅ Phase 1 complete: {len(image_paths)} images")

                # ── PHASE 2: Generate videos with uploaded images ─────────
                log.info(f"[story_id: {current_story_id}] 🎬 Phase 2: Generating videos in PARALLEL …")

                def _run_gen():
                    module_dicts = [m.dict() for m in modules]
                    from modules.object_video_processor import generate_object_modules_parallel
                    return generate_object_modules_parallel(current_story_id, module_dicts, image_paths=image_paths)

                generated_video_paths = await loop.run_in_executor(None, _run_gen)

                if job_id:
                    JobPersistence.update_progress(job_id, current_story_id, phase2_done=True)

                if not generated_video_paths:
                    log.warning(f"[story_id: {current_story_id}] ⚠️ No videos generated for objectvideo.")
                    continue

                # 3. Merge 
                def _run_merge():
                    return merge_videos(current_story_id, generated_video_paths, None)

                final_video_path = await loop.run_in_executor(None, _run_merge)

                # 4. Upload to R2
                timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                bucket_filename = f"videos/obj_video_{timestamp_str}.mp4"

                def _run_upload():
                    return upload_video_to_r2(str(final_video_path.absolute()), bucket_filename)

                upload_success = await loop.run_in_executor(None, _run_upload)

                # 5. Webhook and Cleanup
                if upload_success:
                    from config import VIDEO_PUBLIC_DOMAIN, VIDEOS_DIR
                    send_n8n_webhook(
                        str(current_story_id), 
                        bucket_filename, 
                        timestamp_str, 
                        title=story.title,
                        description=story.description,
                        tags=story.tags,
                        video_type="objectvideo"
                    )
                    
                    # Cleanup videos folder
                    import shutil
                    try:
                        send2trash(str(VIDEOS_DIR.absolute()))
                        VIDEOS_DIR.mkdir(exist_ok=True)
                        log.info(f"[story_id: {current_story_id}] 🧹 Sent videos directory to trash and recreated.")
                    except Exception as e:
                        log.warning(f"[story_id: {current_story_id}] ⚠️ Failed to clean up videos directory: {e}")
                    
                    # Cleanup images folder
                    from config import IMAGES_DIR
                    try:
                        send2trash(str(IMAGES_DIR.absolute()))
                        IMAGES_DIR.mkdir(exist_ok=True)
                        log.info(f"[story_id: {current_story_id}] 🧹 Sent images directory to trash and recreated.")
                    except Exception as e:
                        log.warning(f"[story_id: {current_story_id}] ⚠️ Failed to clean up images directory: {e}")
                else:
                    log.error(f"[story_id: {current_story_id}] ❌ Failed to upload obj video.")

            except Exception as e:
                log.error(f"[story_id: {current_story_id}] ❌ Pipeline failed: {e}")
                if job_id:
                    JobPersistence.mark_failed(job_id, str(e))

    if job_id:
        job = JobPersistence.load(job_id)
        if job and job.get("status") not in ("failed",):
            JobPersistence.mark_done(job_id)

    # ── Check for more jobs after completion ────────────────────────────────
    asyncio.create_task(_trigger_next_job_if_idle())


async def _trigger_next_job_if_idle():
    """
    Checks if there are any pending jobs in the cache. 
    If not, polls the n8n webhook for new work.
    """
    from modules.job_fetcher import fetch_new_jobs
    
    pending = JobPersistence.list_pending()
    if pending:
        log.info(f"Worker: {len(pending)} job(s) currently in queue (pending/running). Skipping webhook poll.")
        return

    log.info("Worker: Queue is empty or idle. Fetching new jobs from webhook...")
    loop = asyncio.get_running_loop()
    stories_raw = await loop.run_in_executor(None, fetch_new_jobs)
    
    if stories_raw:
        # Convert to StoryPayload objects
        story_objs = []
        for s in stories_raw:
            try:
                story_objs.append(StoryPayload(**s))
            except Exception as e:
                log.warning(f"Worker: Failed to parse story from webhook: {e}")
        
        if story_objs:
            # Create a new job in the cache
            job_id = JobPersistence.create("objectvideo", stories_raw)
            log.info(f"Worker: Starting new job {job_id} with {len(story_objs)} stories.")
            # Trigger the pipeline in the background
            asyncio.create_task(_run_objectvideo_pipeline(story_objs, job_id=job_id))
        else:
            log.warning("Worker: Webhook returned data but no valid stories were parsed.")
    else:
        log.info("Worker: No new jobs found at webhook.")


@app.post(
    "/api/generate_images",
    summary="Generate images purely from image prompts",
)
async def api_generate_images(payload: Union[TestPayload, List[StoryPayload]], background_tasks: BackgroundTasks):
    """
    Takes the same payload as other endpoints but extracts the image_generation_prompt 
    and uses Playwright to sequentially generate and download images to the local server.
    No R2 upload or webhook is sent.
    """
    stories = payload.stories if isinstance(payload, TestPayload) else payload

    # Persist payload for crash recovery
    story_dicts = [s.dict() for s in stories]
    job_id = JobPersistence.create("generate_images", story_dicts)
    log.info(f"💾 Persisted generate_images job {job_id} with {len(story_dicts)} stories")

    background_tasks.add_task(_run_image_pipeline, stories, job_id)
    return JSONResponse(
        status_code=202,
        content={"status": "processing", "job_id": job_id, "message": "Image generation started in the background."}
    )

async def _run_image_pipeline(stories: list, job_id: str = None) -> None:
    """
    Background worker for /api/generate_images.
    Generates images, bypassing R2 upload and webhooks.
    job_id: If provided, progress is checkpointed.
    """
    from modules.image_processor import generate_image_modules_sequentially

    if job_id:
        JobPersistence.mark_running(job_id)

    for story in stories:
        current_story_id = str(story.story_id if story.story_id is not None else story.id)
        modules = sorted(story.modules, key=lambda m: m.module_number)

        async with _chrome_lock:
            loop = asyncio.get_running_loop()
            try:
                # Generate images sequentially
                def _run_gen():
                    module_dicts = [m.dict() for m in modules]
                    return generate_image_modules_sequentially(current_story_id, module_dicts)

                generated_image_paths = await loop.run_in_executor(None, _run_gen)

                if not generated_image_paths:
                    log.warning(f"[story_id: {current_story_id}] ⚠️ No images generated.")
                    continue
                else:
                    log.info(f"[story_id: {current_story_id}] 🎉 All images successfully generated.")
                    if job_id:
                        JobPersistence.update_progress(job_id, current_story_id, images_done=True)

            except Exception as e:
                log.error(f"[story_id: {current_story_id}] ❌ Image pipeline failed: {e}")
                if job_id:
                    JobPersistence.mark_failed(job_id, str(e))

    if job_id:
        job = JobPersistence.load(job_id)
        if job and job.get("status") not in ("failed",):
            JobPersistence.mark_done(job_id)

    # ── Check for more jobs after completion ────────────────────────────────
    asyncio.create_task(_trigger_next_job_if_idle())


async def _handle_generation(prompt: str, background_tasks: BackgroundTasks) -> FileResponse:
    prompt = prompt.strip()
    if not prompt:
        raise HTTPException(status_code=422, detail="Prompt cannot be empty.")

    if len(prompt) > 2000:
        raise HTTPException(status_code=422, detail="Prompt too long (max 2000 chars).")

    if len(_pending_jobs) >= MAX_QUEUE:
        raise HTTPException(
            status_code=429,
            detail=f"Server busy – {MAX_QUEUE} jobs already queued. Try again later.",
        )

    log.info(f"🎬 New request → prompt: «{prompt[:60]}{'…' if len(prompt)>60 else ''}»")

    try:
        video_path = await _run_generation(prompt)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=f"Video generation failed: {e}")

    if not os.path.exists(video_path) or os.path.getsize(video_path) == 0:
        raise HTTPException(status_code=500, detail="Video file was not created.")

    # Keep the file (user wants it to persist in current folder)
    filename = f"grok_video_{uuid.uuid4().hex[:6]}.mp4"
    return FileResponse(
        path=video_path,
        media_type="video/mp4",
        filename=filename,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Prompt": prompt[:200],
        },
    )


# ─────────────────────────── DEBUG ENDPOINTS ──────────────────────────────────

class WebhookTestPayload(BaseModel):
    story_id: str
    bucket_filename: str
    timestamp_str: str
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[str] = None
    source_video_path: Optional[str] = None

@app.post("/api/test_webhook", summary="Test the n8n webhook module independently")
async def test_webhook(payload: WebhookTestPayload, background_tasks: BackgroundTasks):
    from modules.webhook_sender import send_n8n_webhook
    def _run_test():
        send_n8n_webhook(
            payload.story_id, 
            payload.bucket_filename, 
            payload.timestamp_str,
            title=payload.title,
            description=payload.description,
            tags=payload.tags,
            source_video_path=payload.source_video_path
        )
    background_tasks.add_task(_run_test)
    return JSONResponse({"status": "queued", "message": "Webhook test triggered."})

class UploadTestPayload(BaseModel):
    file_path: str
    bucket_filename: Optional[str] = None

@app.post("/api/test_upload", summary="Test the R2 upload module independently")
async def test_upload(payload: UploadTestPayload, background_tasks: BackgroundTasks):
    from modules.video_uploader import upload_video_to_r2
    def _run_test():
        upload_video_to_r2(payload.file_path, payload.bucket_filename)
    background_tasks.add_task(_run_test)
    return JSONResponse({"status": "queued", "message": "Upload test triggered."})

class MergeTestPayload(BaseModel):
    story_id: str
    video_filenames: List[str]

@app.post("/api/test_merge", summary="Test the video merging module independently")
async def test_merge(payload: MergeTestPayload, background_tasks: BackgroundTasks):
    from modules.video_merger import merge_videos
    from pathlib import Path
    
    def _run_test():
        try:
            paths = [VIDEOS_DIR / f for f in payload.video_filenames]
            for p in paths:
                if not p.exists():
                    log.error(f"Missing file: {p}")
                    return
            merge_videos(payload.story_id, paths)
        except Exception as e:
            log.error(f"Test merge error: {e}")
            
    background_tasks.add_task(_run_test)
    return JSONResponse({"status": "queued", "message": "Merge test triggered."})
