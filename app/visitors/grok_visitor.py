import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
import os
import random

async def send_grok_message(page, message):
    """Helper to send a message to Grok."""
    print(f"Sending message to Grok: '{message}'")
    
    # Selector for Grok's Tiptap editor
    input_selector = "div.tiptap.ProseMirror"
    
    try:
        input_field = page.locator(input_selector).first
        await input_field.wait_for(state="visible", timeout=10000)
        
        # Click to focus
        await input_field.click()
        await asyncio.sleep(0.5)
        
        # Grok uses a rich text editor, so typing directly is better than fill()
        await page.keyboard.type(str(message))
        await asyncio.sleep(0.5)
        await page.keyboard.press("Enter")
        return True
    except Exception as e:
        print(f"Error sending message: {e}")
        return False

async def execute_grok_steps(page):
    """Executes the sequence of Grok interactions in an optimized single message."""
    
    # 1. Start the process
    if not await send_grok_message(page, "make script"): return False
    print("Waiting 60 seconds for initial processing...")
    await asyncio.sleep(60)
    
    # 2. Generate random values
    script_choice = random.randint(1, 20)
    personas = ["default"] + [str(i) for i in range(1, 12)]
    persona_choice = random.choice(personas)
    
    # 3. Combine into a single comma-separated response
    # Format: Script Type, Persona, Confirmation
    combined_message = f"{script_choice}, {persona_choice}, yes"
    print(f"Sending combined selection: '{combined_message}'")
    
    if not await send_grok_message(page, combined_message): return False
    
    # Wait for completion
    print("Waiting 60 seconds for final generation processing...")
    await asyncio.sleep(60)
    
    return True

async def run_grok_generation():
    url = "https://grok.com/project/c87eada8-16e3-442c-9c5e-d51f9fd09b75?tab=conversations&chat=7fb8815e-ad35-45a4-9a1c-88eebc5f5c5f&rid=261c3114-c9fd-4b95-bdbc-39d6e46cc392"
    profile_path = os.path.expanduser("~/.config/google-chrome-bot-profile")
    
    print(f"Starting Grok Visitor with profile: {profile_path}")
    async with async_playwright() as p:
        try:
            # Launch with persistent context to keep login session
            context = await p.chromium.launch_persistent_context(
                user_data_dir=profile_path,
                channel="chrome",
                headless=False, # Set to True for background execution
                viewport={'width': 1280, 'height': 800},
                args=["--disable-blink-features=AutomationControlled"],
                ignore_default_args=["--enable-automation"]
            )
            
            page = context.pages[0] if context.pages else await context.new_page()
            
            # Apply stealth
            await Stealth().apply_stealth_async(page)
            await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            print(f"Navigating to Grok: {url}")
            try:
                await page.goto(url, wait_until="networkidle", timeout=60000)
                await asyncio.sleep(5) # Extra buffer for page hydration
                
                success = await execute_grok_steps(page)
                
                if success:
                    print("Grok interaction complete!")
                    return True
                else:
                    print("Grok interaction failed.")
                    await page.screenshot(path="grok_error.png", full_page=True)
                    return False
                    
            except Exception as e:
                print(f"An error occurred: {e}")
                await page.screenshot(path="grok_exception.png", full_page=True)
                return False
            finally:
                await asyncio.sleep(5)
                await context.close()
                print("Browser closed.")
                
        except Exception as e:
            print(f"Could not launch browser: {e}")
            return False

if __name__ == "__main__":
    asyncio.run(run_grok_generation())
