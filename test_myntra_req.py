import requests
import re

def test():
    url = "https://www.myntra.com/kurtas/kalini/kalini-ethnic-motifs-printed-mandarin-collar-straight-kurta/28375886/buy"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    print("Fetching URL...")
    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"Status Code: {response.status_code}")
        
        with open("myntra_out.html", "w") as f:
            f.write(response.text)
        print("Wrote to myntra_out.html")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test()
