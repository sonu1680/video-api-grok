"""
Job Persistence — cache/job_persistence.py
=========================================
Saves and restores pending job payloads so the pipeline can resume
after a server restart or unexpected crash.

Job files are stored as JSON in cache/jobs/<job_id>.json

Structure of a job file:
{
    "job_id": "...",
    "pipeline_type": "objectvideo" | "generate_images" | "chatgpt_generation",
    "created_at": "ISO8601",
    "status": "pending" | "running" | "done" | "failed",
    "stories": [ <serialised story dicts> ],
    "progress": {
        "<story_id>": {
            "phase1_done": false,          # image generation for objectvideo
            "phase2_done": false,          # video generation for objectvideo
            "images_done": false,          # for generate_images pipeline
            "completed_modules": []        # list of module_numbers finished
        }
    }
}
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("GrokAPI.JobPersistence")

JOBS_DIR = Path(__file__).parent / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)


class JobPersistence:
    """Thin wrapper for reading/writing job state to disk."""

    # ------------------------------------------------------------------ create
    @staticmethod
    def create(pipeline_type: str, stories: list) -> str:
        """
        Persist a new job and return its job_id.

        Args:
            pipeline_type: "objectvideo" or "generate_images"
            stories: list of story dicts (already serialised from Pydantic .dict())
        """
        job_id = uuid.uuid4().hex[:12]
        progress = {}
        for story in stories:
            sid = str(story.get("story_id") or story.get("id", "unknown"))
            progress[sid] = {
                "phase1_done": False,
                "phase2_done": False,
                "images_done": False,
                "completed_modules": [],
            }

        job = {
            "job_id": job_id,
            "pipeline_type": pipeline_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending",
            "stories": stories,
            "progress": progress,
        }
        JobPersistence._write(job_id, job)
        log.info(f"[JobPersistence] 💾 Created job {job_id} ({pipeline_type}), {len(stories)} stories")
        return job_id

    # ------------------------------------------------------------------- load
    @staticmethod
    def load(job_id: str) -> dict | None:
        path = JOBS_DIR / f"{job_id}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.error(f"[JobPersistence] ❌ Failed to load {job_id}: {e}")
            return None

    # ---------------------------------------------------------------- list pending
    @staticmethod
    def list_pending() -> list[dict]:
        """Return all jobs whose status is 'pending' or 'running', sorted oldest-first (FIFO)."""
        jobs = []
        for path in JOBS_DIR.glob("*.json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    job = json.load(f)
                if job.get("status") in ("pending", "running"):
                    jobs.append(job)
            except Exception as e:
                log.warning(f"[JobPersistence] ⚠️ Could not read {path.name}: {e}")
        # Sort by original creation time (oldest first) so FIFO order is preserved on resume
        return sorted(jobs, key=lambda x: x.get("created_at", ""))

    # --------------------------------------------------------- mark running
    @staticmethod
    def mark_running(job_id: str):
        job = JobPersistence.load(job_id)
        if job:
            job["status"] = "running"
            job["started_at"] = datetime.now(timezone.utc).isoformat()
            JobPersistence._write(job_id, job)

    # -------------------------------------------------------- mark done
    @staticmethod
    def mark_done(job_id: str):
        job = JobPersistence.load(job_id)
        if job:
            job["status"] = "done"
            job["completed_at"] = datetime.now(timezone.utc).isoformat()
            JobPersistence._write(job_id, job)
            log.info(f"[JobPersistence] ✅ Job {job_id} marked done")

    # -------------------------------------------------------- mark failed
    @staticmethod
    def mark_failed(job_id: str, error: str = ""):
        job = JobPersistence.load(job_id)
        if job:
            job["status"] = "failed"
            job["error"] = error
            job["failed_at"] = datetime.now(timezone.utc).isoformat()
            JobPersistence._write(job_id, job)
            log.info(f"[JobPersistence] ❌ Job {job_id} marked failed: {error}")

    # -------------------------------------------------- update story progress
    @staticmethod
    def update_progress(job_id: str, story_id: str, **kwargs):
        """
        Update story-level progress flags.
        Supported kwargs: phase1_done, phase2_done, images_done, completed_modules
        """
        job = JobPersistence.load(job_id)
        if not job:
            return
        sid = str(story_id)
        if sid not in job["progress"]:
            job["progress"][sid] = {
                "phase1_done": False,
                "phase2_done": False,
                "images_done": False,
                "completed_modules": [],
            }
        for key, val in kwargs.items():
            job["progress"][sid][key] = val
        JobPersistence._write(job_id, job)

    # ----------------------------------------- add completed module
    @staticmethod
    def add_completed_module(job_id: str, story_id: str, module_number: int):
        job = JobPersistence.load(job_id)
        if not job:
            return
        sid = str(story_id)
        done = job["progress"].get(sid, {}).get("completed_modules", [])
        if module_number not in done:
            done.append(module_number)
            JobPersistence.update_progress(job_id, sid, completed_modules=done)

    # -------------------------------------------------------- get progress
    @staticmethod
    def get_progress(job_id: str, story_id: str) -> dict:
        job = JobPersistence.load(job_id)
        if not job:
            return {}
        return job["progress"].get(str(story_id), {})

    # ------------------------------------------------------------ delete
    @staticmethod
    def delete(job_id: str):
        path = JOBS_DIR / f"{job_id}.json"
        try:
            if path.exists():
                path.unlink()
                log.info(f"[JobPersistence] 🗑️ Deleted job file {job_id}")
        except Exception as e:
            log.warning(f"[JobPersistence] ⚠️ Failed to delete job {job_id}: {e}")

    # ---------------------------------------------------------------- write
    @staticmethod
    def _write(job_id: str, job: dict):
        path = JOBS_DIR / f"{job_id}.json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(job, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            log.error(f"[JobPersistence] ❌ Failed to write {job_id}: {e}")
