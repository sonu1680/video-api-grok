import json
import logging
import requests
from typing import List, Dict, Any, Optional
from config import N8N_JOB_FETCH_URL

log = logging.getLogger("GrokAPI.JobFetcher")

def fetch_new_jobs(url: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Polls the specified n8n webhook URL for new jobs.
    Returns a list of story dictionaries if found, otherwise an empty list.
    """
    target_url = url or N8N_JOB_FETCH_URL
    log.info(f"📡 Polling webhook for new jobs: {target_url}")
    
    try:
        # Using a GET request as per the n8n webhook configuration for fetching
        response = requests.get(target_url, timeout=30)
        
        if response.status_code == 200:
            try:
                data = response.json()
                # data format expected: {"result": "{\"data\":{\"stories\":[...]}}"}
                if "result" in data and data["result"]:
                    # Handle the nested stringified JSON
                    if isinstance(data["result"], str):
                        inner_data = json.loads(data["result"])
                    else:
                        inner_data = data["result"]
                    
                    stories = inner_data.get("data", {}).get("stories", [])
                    if stories:
                        log.info(f"✅ Found {len(stories)} stories from webhook.")
                        return stories
                    else:
                        log.info("ℹ️ Webhook returned success but no stories found.")
                else:
                    log.info("ℹ️ Webhook returned empty or no result field.")
            except (json.JSONDecodeError, AttributeError) as e:
                log.error(f"❌ Failed to parse webhook JSON: {e}. Raw response: {response.text[:200]}")
        elif response.status_code == 204:
            log.info("ℹ️ Webhook returned 204 (No Content).")
        else:
            log.warning(f"⚠️ Webhook returned status {response.status_code}: {response.text[:200]}")
            
    except requests.exceptions.RequestException as e:
        log.error(f"❌ Network error while polling webhook: {e}")
    except Exception as e:
        log.error(f"❌ Unexpected error in job fetcher: {e}")
        
    return []

if __name__ == "__main__":
    # Quick debug test
    logging.basicConfig(level=logging.INFO)
    jobs = fetch_new_jobs()
    print(f"Fetched {len(jobs)} jobs.")
