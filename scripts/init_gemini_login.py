import argparse
import sys
import os
import re
from pathlib import Path
from dotenv import load_dotenv

from playwright.sync_api import sync_playwright

SKILL_DIR = Path(__file__).resolve().parent.parent
load_dotenv(SKILL_DIR / ".env")

# Defalut fallback path identical to generate_images.py
DEFAULT_DRIVER_PATH = Path("/Users/papazed/00_Publiac Account/scripts/gemini_driver.py")

def main():
    driver_path = Path(os.getenv("GEMINI_DRIVER_PATH", str(DEFAULT_DRIVER_PATH)))
    if not driver_path.exists():
        print(f"Error: gemini_driver.py not found at: {driver_path}")
        print("Please set GEMINI_DRIVER_PATH in your .env file or environment.")
        sys.exit(1)

    # Dynamically extract USER_DATA_DIR from driver OR fallback to standard layout
    user_data_dir = driver_path.parent.parent / '.gemini' / 'browser_profile'
    print(f"Targeting environment profile profile: {user_data_dir}")

    if not user_data_dir.parent.exists():
         user_data_dir.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        print("Launching browser context...")
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=False,
            channel="chrome",
            viewport={"width": 1440, "height": 980},
            args=["--disable-blink-features=AutomationControlled"],
        )
        
        page = context.pages[0] if context.pages else context.new_page()
        print("\nOpening Gemini web application...")
        print("💡 Step:")
        print("   1. Log into your Google Account if prompted.")
        print("   2. Verify you can access https://gemini.google.com/app.")
        print("   3. CLOSE THE BROWSER WINDOW to save cookie sessions and exit.")
        
        page.goto("https://gemini.google.com/app", wait_until="domcontentloaded")

        try:
            while not page.is_closed():
                 page.wait_for_timeout(1000)
        except Exception:
             pass

        print(f"\n✅ Session saved into: {user_data_dir}")
        context.close()

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
