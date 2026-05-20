# Grok Video Generation API

A modular FastAPI backend for generating, merging, uploading, and notifying external workflows of automated AI video creation.

## Project layout

```
app/                          # main Python package
├── server.py                 # FastAPI entry point  (uvicorn app.server:app)
├── config.py                 # paths, R2 creds, n8n webhook URLs
├── grok_client.py            # headless Grok automation lib (was app.py)
├── pipelines/                # media processors (image, video, merger, trimmer, uploader, myntra)
├── integrations/             # n8n webhook sender + job fetcher
├── visitors/                 # headless-browser surfaces (chatgpt, grok)
└── persistence/              # job-state persistence (data/jobs/*.json)

workflows/                    # n8n / orchestration definitions
data/                         # runtime state (gitignored) — jobs/, images/, videos/
assets/                       # static files (default.jpg, bg.mp3, default_images/)
scripts/                      # dev/ops one-offs (setup_image_profile, debug_grok_image)
tests/                        # pytest tests + fixtures/
mcp/                          # separate TS sub-project, untouched
```

## Getting Started

1. **Environment:** `source venv/bin/activate`
2. **Dependencies:** `pip install fastapi uvicorn pydantic playwright boto3 requests send2trash`
3. **Configuration:** R2 credentials and n8n webhook URLs live in `app/config.py`. Update before running.
4. **Run the server:**
   ```bash
   make dev
   # or directly:
   uvicorn app.server:app --host 0.0.0.0 --port 8000 --reload
   ```
5. **Run visitors:** `make gpt` / `make grok`
6. **Run tests:** `make test` (requires `pip install pytest`)
## Core Endpoints

### 1. Health & Queue check
`GET /health`
Returns the status of the server and any actively running generation tasks.

### 2. Generate Single Video (URL)
`GET /api/getvideo/{prompt}`
Generates a video directly from the URL and streams the MP4 file back in the HTTP response.

### 3. Generate Single Video (JSON)
`POST /api/getvideo`
**Payload:**
```json
{
  "prompt": "a dog playing in the snow"
}
```
Streams the MP4 file back directly in the HTTP response.

### 4. Process Full Story Sequential Pipeline
`POST /api/process_payload`
Generates all modules in a headless Google Chrome browser sequentially, merges the fragments, adds background audio, uploads the final MP4 to Cloudflare R2, and sends an n8n webhook notification.

**Payload:**
```json
{
  "stories": [
    {
      "id": 123,
      "story_id": "story_123",
      "modules": [
        {
          "module_number": 1,
          "video_generation_prompt": "First AI prompt visual..."
        },
        {
          "module_number": 2,
          "video_generation_prompt": "Second scene prompt..."
        }
      ]
    }
  ]
}
```

---

## Developer Debug Endpoints

The pipeline steps have been fully isolated. You can test sub-modules independently.

### 1. Test Webhook
`POST /api/test_webhook`
Sends a mock Payload to your n8n workflow.

**Payload:**
```json
{
  "story_id": "debug_123",
  "bucket_filename": "videos/video_debug.mp4",
  "timestamp_str": "20260307_120000"
}
```

### 2. Test R2 Upload
`POST /api/test_upload`
Attempts to upload a local file to Cloudflare. 

**Payload:**
```json
{
  "file_path": "/absolute/path/to/local/file.mp4",
  "bucket_filename": "videos/test_upload.mp4" 
}
```
*(Note: `bucket_filename` is optional. If omitted, it will use the default path format)*

### 3. Test FFMPEG Chunk Merging
`POST /api/test_merge`
Attempts to concatenate a list of chunk filenames found in the `videos` directory to test the FFMPEG concat stitcher.

**Payload:**
```json
{
  "story_id": "debug_123",
  "video_filenames": [
    "chunk_1_story_123.mp4",
    "chunk_2_story_123.mp4"
  ]
}
```

### 4. Test Background Audio Layering
`POST /api/test_audio_layer`
Attempts to apply `bg.mp3` from the root directory over the specified video file found in the `videos` directory.

**Payload:**
```json
{
  "story_id": "debug_123",
  "video_filename": "module_1.mp4"
}
```
