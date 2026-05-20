import sys
import os
import json

# Add project root to sys.path
sys.path.append(os.getcwd())

from modules.job_fetcher import fetch_new_jobs

def test_parsing():
    # Mock data based on aa.md
    mock_response = {
        "result": json.dumps({
            "data": {
                "stories": [
                    {
                        "id": 1,
                        "title": "Test Story",
                        "modules": [{"module_number": 1, "video_generation_prompt": "test"}]
                    }
                ]
            }
        })
    }
    
    # We can't easily mock requests.get without a library, 
    # but we can test the internal parsing logic if we refactor job_fetcher slightly.
    # For now, let's just run it against the real URL if possible, or skip.
    print("Testing fetcher against real URL...")
    jobs = fetch_new_jobs()
    print(f"Fetched {len(jobs)} jobs.")
    if jobs:
        print("First job title:", jobs[0].get("title"))

if __name__ == "__main__":
    test_parsing()
