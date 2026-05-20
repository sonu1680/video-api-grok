import logging
import re
import json
from pathlib import Path
from typing import List
import requests

from app.config import IMAGES_DIR

log = logging.getLogger("GrokAPI.MyntraScraper")

def extract_product_id(url: str) -> str:
    """Extract product ID from Myntra URL"""
    match = re.search(r'/(\d+)/buy', url)
    if match:
        return match.group(1)
    
    match = re.search(r'/(\d+)(?:/|$|\?)', url)
    if match:
        return match.group(1)
        
    return "unknown_product"

def get_high_res_url(url: str) -> str:
    """
    Myntra image URLs in the JSON data are often the base assets without resize params.
    However, if they do have them or we want to ensure high res, we can modify them.
    Typically, we want to inject /h_1440,q_100,w_1080/ after assets.myntassets.com/
    But the raw asset URL is usually already high-res.
    Let's just use the raw URL directly.
    """
    # Fix unicode escapes
    url = url.replace('\\u002F', '/')
    # Change http to https if needed
    if url.startswith('http://'):
        url = url.replace('http://', 'https://')
    return url

def scrape_myntra_images(url: str) -> List[str]:
    """
    Scrape images from Myntra product URL using HTTP requests.
    Returns list of local file paths.
    """
    product_id = extract_product_id(url)
    log.info(f"Scraping images for Myntra Product ID: {product_id} from {url}")
    
    output_dir = IMAGES_DIR / "myntra" / product_id
    output_dir.mkdir(parents=True, exist_ok=True)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    
    log.info("Fetching product page HTML...")
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
    except Exception as e:
        log.error(f"Failed to fetch Myntra URL: {e}")
        raise RuntimeError(f"Failed to fetch Myntra URL: {e}")
        
    # Extract image URLs from the JSON payload in the HTML
    # We look for "imageURL":"..."
    matches = re.findall(r'"imageURL":"([^"]+)"', response.text)
    
    if not matches:
        # Fallback to other possible JSON keys
        matches = re.findall(r'"src":"(https://assets.myntassets.com/[^"]+)"', response.text)
        
    if not matches:
        log.warning("No images found in the HTML.")
        return []
        
    image_urls = []
    for match in matches:
        clean_url = get_high_res_url(match)
        if clean_url not in image_urls:
            # Myntra URLs sometimes have duplicate structures, only keep unique ones
            image_urls.append(clean_url)
            
    log.info(f"Found {len(image_urls)} unique image URLs.")
    
    local_paths = []
    for i, img_url in enumerate(image_urls):
        log.info(f"Downloading {img_url}")
        
        try:
            img_response = requests.get(img_url, timeout=30)
            img_response.raise_for_status()
            
            ext = ".jpg"
            if ".png" in img_url.lower(): ext = ".png"
            elif ".webp" in img_url.lower(): ext = ".webp"
            
            filename = f"image_{i+1}{ext}"
            file_path = output_dir / filename
            
            with open(file_path, 'wb') as f:
                f.write(img_response.content)
                
            local_paths.append(str(file_path))
            
        except Exception as e:
            log.error(f"Failed to download image {img_url}: {e}")
            
    return local_paths
