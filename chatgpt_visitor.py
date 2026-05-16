import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
import os
import random

async def send_message(page, message):
    """Helper to send a message to ChatGPT."""
    print(f"Sending message: '{message}'")
    
    # Try common input selectors
    input_selectors = [
        "textarea#prompt-textarea",
        "div[contenteditable='true']",
        "textarea[placeholder*='Message']",
        "div#prompt-textarea"
    ]
    
    input_field = None
    for selector in input_selectors:
        try:
            input_field = page.locator(selector).first
            if await input_field.is_visible(timeout=3000):
                break
        except Exception:
            continue
            
    if not input_field or not await input_field.is_visible():
        print("Error: Could not find input field.")
        return False
    
    # Click to focus
    await input_field.click()
    await asyncio.sleep(0.5)
    
    # Use type instead of fill for contenteditable
    await page.keyboard.type(str(message))
    await asyncio.sleep(1)
    await page.keyboard.press("Enter")
    return True

async def wait_and_click_confirm(page):
    """Poll for the Confirm/Allow button and click it with a human delay."""
    print("Waiting for button to appear (polling up to 2 minutes)...")
    
    btn = None
    for i in range(60): # 60 * 2 seconds = 120 seconds
        try:
            # First try finding by text (more robust for ChatGPT)
            btn = page.get_by_role("button", name="Confirm", exact=False).first
            if not await btn.is_visible(timeout=500):
                btn = page.get_by_role("button", name="Allow", exact=False).first
                if not await btn.is_visible(timeout=500):
                    # Fallback to class name if text fails
                    btn = page.locator("button.btn-primary").first
            
            if btn and await btn.is_visible(timeout=500):
                print("Found the button. Simulating human delay...")
                await btn.hover()
                await asyncio.sleep(3) # Human reading time
                print("Clicking the button!")
                await btn.click()
                return True
        except Exception:
            pass # Ignore timeout/not found and keep polling
            
        await asyncio.sleep(1.5) # Wait before next poll attempt
        
        if (i + 1) % 15 == 0:
            print(f"  ...still waiting for button ({ (i + 1) * 2 }s elapsed)...")
            
    print("Error: Confirm button never appeared.")
    return False

async def execute_steps(page):
    """Executes the sequence of interactions linearly."""
    
    # Generate random choices
    script_choice = random.randint(1, 20)
    speech_choice = random.randint(1, 10)
    print(f"Randomly picked Script Type: {script_choice}, Speech Type: {speech_choice}")
    
    # Step 1: Send "next"
    if not await send_message(page, "next"): return False
    print("Waiting 5 seconds for reply...")
    await asyncio.sleep(5)
    
    # Step 2: Reply with script choice
    if not await send_message(page, script_choice): return False
    print("Waiting 5 seconds for reply...")
    await asyncio.sleep(5)
    
    # Step 3: Reply with speech choice
    if not await send_message(page, speech_choice): return False
    print("Waiting 10 seconds for reply...")
    await asyncio.sleep(10)
    
    # Step 4: Reply with "yes"
    if not await send_message(page, "yes"): return False
    
    # Step 5: Wait for and click the Confirm button
    if not await wait_and_click_confirm(page): return False
    
    # Wait for webhook processing
    print("Waiting 10 seconds for webhook processing before closing...")
    await asyncio.sleep(10)
    
    return True

async def run_chatgpt_generation():
    url = "https://chatgpt.com/g/g-69e4d084dfa08191a788e722fed4b633-object-benefits/c/6a074f81-1228-8323-b27c-afd689d204ff"
    profile_path = os.path.expanduser("~/.config/google-chrome-bot-profile")
    
    print(f"Starting Playwright with profile: {profile_path}")
    async with async_playwright() as p:
        try:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=profile_path,
                channel="chrome",
                headless=False,
                viewport={'width': 1280, 'height': 800},
                args=["--disable-blink-features=AutomationControlled"],
                ignore_default_args=["--enable-automation"]
            )
            
            page = context.pages[0] if context.pages else await context.new_page()
            
            # Apply stealth to bypass advanced bot detection
            await Stealth().apply_stealth_async(page)
            
            # Additional stealth script to bypass basic webdriver checks
            await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            print(f"Navigating to: {url}")
            try:
                await page.goto(url, wait_until="networkidle", timeout=60000)
                await asyncio.sleep(2)
                
                success = await execute_steps(page)
                
                if success:
                    print("Interaction complete!")
                    return True
                else:
                    print("Interaction failed during execution.")
                    await page.screenshot(path="error_screenshot.png", full_page=True)
                    print("Error screenshot saved to error_screenshot.png")
                    return False
                    
            except Exception as e:
                print(f"An error occurred during interaction: {e}")
                try:
                    await page.screenshot(path="error_screenshot.png", full_page=True)
                    print("Error screenshot saved to error_screenshot.png")
                except:
                    pass
                return False
            finally:
                await asyncio.sleep(5)
                await context.close()
                print("Browser closed.")
                
        except Exception as e:
            print(f"Could not launch browser: {e}")
            return False

if __name__ == "__main__":
    asyncio.run(run_chatgpt_generation())
