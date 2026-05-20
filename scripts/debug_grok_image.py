"""
Debug script - opens a real browser, navigates to Grok, uploads an image,
submits the prompt, waits for 'Make video', then inspects what image data 
comes back from our JS evaluate call.
"""
import sys
import os
import time

sys.path.append(os.getcwd())

from app import grok_client as grok_app
from app.grok_client import IMAGE_USER_DATA
from playwright.sync_api import sync_playwright

TEST_IMAGE = "/home/sonupandit/Documents/videoapi/images/myntra/38347404/image_1.jpg"

GROK_EDIT_PROMPT = (
    "Analyze the uploaded image and carefully remove the subject's hands, neck, and face. "
    "Seamlessly reconstruct the missing regions using surrounding visual context so the result "
    "looks natural, realistic, and anatomically consistent. Preserve the original body proportions, "
    "clothing, lighting, skin tone, textures, and overall composition without distortion. "
    "Ensure smooth blending with no visible cuts, seams, or artifacts. Keep the background unchanged. "
    "The final image should look naturally complete even without visible hands, neck, or there face."
)

def main():
    print("Starting debug run...")
    with sync_playwright() as p:
        log = grok_app._make_logger("DebugBot")
        
        browser = grok_app._stage_launch(p, log, user_data_dir=IMAGE_USER_DATA)
        page = grok_app._stage_navigate(browser, log)
        grok_app._stage_upload_image(page, TEST_IMAGE, log)
        grok_app._stage_enter_prompt(page, GROK_EDIT_PROMPT, log)
        
        print("Submitting...")
        grok_app._human_delay(0.5, 1.5, "before pressing Enter", log)
        page.keyboard.press("Enter")
        
        print("Waiting for 'Make video' button...")
        try:
            page.get_by_text("Make video").first.wait_for(state="visible", timeout=120000)
            print("✅ 'Make video' appeared!")
        except Exception as e:
            print(f"⚠️ Timed out: {e}")
        
        time.sleep(2)
        
        print("--- Inspecting page for images ---")
        
        # Check all imgs on page
        img_data = page.evaluate("""() => {
            const imgs = document.querySelectorAll('img');
            return Array.from(imgs).map(img => {
                const rect = img.getBoundingClientRect();
                return {
                    src: img.src ? img.src.substring(0, 100) : 'no-src',
                    alt: img.alt,
                    width: Math.round(rect.width),
                    height: Math.round(rect.height)
                };
            });
        }""")
        
        print(f"\nFound {len(img_data)} images on page:")
        for i, img in enumerate(img_data):
            print(f"  [{i}] {img['width']}x{img['height']} | alt='{img['alt']}' | src={img['src']}")
        
        # Now try the fetch approach and see what comes back
        print("\n--- Testing fetch approach ---")
        result = page.evaluate("""async () => {
            const imgs = document.querySelectorAll('img');
            let largestImg = null;
            let maxArea = 0;
            
            for (const img of imgs) {
                const rect = img.getBoundingClientRect();
                const area = rect.width * rect.height;
                if (area > maxArea) {
                    maxArea = area;
                    largestImg = img;
                }
            }
            
            if (!largestImg || !largestImg.src) return {error: "no image found"};
            
            try {
                const response = await fetch(largestImg.src);
                const blob = await response.blob();
                return new Promise((resolve, reject) => {
                    const reader = new FileReader();
                    reader.onloadend = () => resolve({
                        data: reader.result,
                        length: reader.result ? reader.result.length : 0,
                        starts_with: reader.result ? reader.result.substring(0, 50) : 'none'
                    });
                    reader.onerror = reject;
                    reader.readAsDataURL(blob);
                });
            } catch (e) {
                return {error: e.toString()};
            }
        }""")
        
        print(f"Result type: {type(result)}")
        print(f"Result: {result}")
        
        if result and not result.get('error'):
            data = result.get('data', '')
            print(f"Data length: {len(data)}")
            print(f"Starts with: {data[:80]}")
            print(f"Has comma: {',' in data}")
            
            if ',' in data:
                header, encoded = data.split(',', 1)
                print(f"Header: {header}")
                print(f"Encoded length: {len(encoded)}")
                
                # Try saving it
                import base64
                with open("/tmp/debug_grok_image.jpg", "wb") as f:
                    f.write(base64.b64decode(encoded))
                print(f"✅ Saved to /tmp/debug_grok_image.jpg")
            else:
                print("❌ No comma in data - split will fail!")
        else:
            print(f"❌ Error: {result}")
        
        input("\nPress Enter to close browser...")
        browser.close()

if __name__ == "__main__":
    main()
