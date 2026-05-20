import json
import logging
import requests
from typing import List, Dict, Any, Optional
from app.config import OBJECT_GET_SCRIPT_URL

log = logging.getLogger("GrokAPI.JobFetcher")

def fetch_new_jobs(url: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Polls the specified n8n webhook URL for new jobs.
    Returns a list of story dictionaries if found, otherwise an empty list.
    """
    target_url = url or OBJECT_GET_SCRIPT_URL
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

def fetch_food_discovery_jobs(url: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Polls the food_discovery webhook for new jobs.
    Returns a list of story dicts (same format as objectvideo).
    """
    from app.config import FOOD_GET_SCRIPT_URL
    target_url = url or FOOD_GET_SCRIPT_URL
    log.info(f"📡 Polling food_discovery webhook for new jobs: {target_url}")
    
    try:
        response = requests.get(target_url, timeout=30)
        
        if response.status_code == 200:
            try:
                data = response.json()
                # Same expected format as objectvideo: {"result": "{\"data\":{\"stories\":[...]}}"}
                if "result" in data and data["result"]:
                    if isinstance(data["result"], str):
                        inner_data = json.loads(data["result"])
                    else:
                        inner_data = data["result"]
                    
                    stories = inner_data.get("data", {}).get("stories", [])
                    if stories:
                        log.info(f"✅ Found {len(stories)} stories from food_discovery webhook.")
                        return stories
                    else:
                        log.info("ℹ️ Food discovery webhook returned success but no stories found.")
                else:
                    log.info("ℹ️ Food discovery webhook returned empty or no result field.")
            except (json.JSONDecodeError, AttributeError) as e:
                log.error(f"❌ Failed to parse food_discovery webhook JSON: {e}. Raw response: {response.text[:200]}")
        elif response.status_code == 204:
            log.info("ℹ️ Food discovery webhook returned 204 (No Content).")
        else:
            log.warning(f"⚠️ Food discovery webhook returned status {response.status_code}: {response.text[:200]}")
            
    except requests.exceptions.RequestException as e:
        log.error(f"❌ Network error while polling food_discovery webhook: {e}")
    except Exception as e:
        log.error(f"❌ Unexpected error in food_discovery job fetcher: {e}")
        
    return []


def fetch_chatgpt_jobs(url: Optional[str] = None) -> int:
    """
    Polls the ChatGPT webhook URL.
    Returns the number of generations requested (count).
    """
    from app.config import FOOD_GET_SCRIPT_URL
    target_url = url or FOOD_GET_SCRIPT_URL
    log.info(f"📡 Polling ChatGPT webhook: {target_url}")
    
    try:
        response = requests.get(target_url, timeout=30)
        
        if response.status_code == 200:
            try:
                data = response.json()
                
                # Check for explicit count
                if isinstance(data, dict):
                    if "count" in data:
                        count = int(data["count"])
                        log.info(f"✅ Found ChatGPT job count: {count}")
                        return count
                    
                    # Handle n8n standard result wrapper
                    if "result" in data and data["result"]:
                        inner_data = data["result"]
                        if isinstance(inner_data, str):
                            inner_data = json.loads(inner_data)
                            
                        # If it's a list, return its length
                        if isinstance(inner_data, list):
                            log.info(f"✅ Found ChatGPT list, count: {len(inner_data)}")
                            return len(inner_data)
                            
                        # Check for count inside result
                        if isinstance(inner_data, dict) and "count" in inner_data:
                            return int(inner_data["count"])
                            
                        # Check for data wrapper
                        if "data" in inner_data and isinstance(inner_data["data"], list):
                            return len(inner_data["data"])
                            
                # If no strict match is found, return 0 instead of falling back to 1
                log.warning("⚠️ ChatGPT Webhook returned success, but no explicit count or valid data array was found.")
                return 0
                    
            except (json.JSONDecodeError, AttributeError, ValueError) as e:
                log.error(f"❌ Failed to parse ChatGPT webhook JSON: {e}")
                
        elif response.status_code == 204:
            log.info("ℹ️ ChatGPT Webhook returned 204 (No Content).")
        else:
            log.warning(f"⚠️ ChatGPT Webhook returned status {response.status_code}")
            
    except Exception as e:
        log.error(f"❌ Error polling ChatGPT webhook: {e}")
        
    return 0

if __name__ == "__main__":
    # Quick debug test
    logging.basicConfig(level=logging.INFO)
    jobs = fetch_new_jobs()
    print(f"Fetched {len(jobs)} jobs.")
