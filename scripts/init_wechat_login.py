import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PROFILE_DIR = SKILL_DIR / "assets" / "wechat_profile"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Initialize and persist WeChat Official Account login session."
    )
    parser.add_argument(
        "--user-data-dir",
        default=str(DEFAULT_PROFILE_DIR),
        help="Persistent profile directory for Playwright.",
    )
    return parser.parse_args()


def extract_token(page):
    if "token=" in page.url:
        return page.url.split("token=")[1].split("&")[0]
    try:
        return page.evaluate(
            "() => new URLSearchParams(window.location.search).get('token') || ''"
        )
    except Exception:
        return ""


def main():
    args = parse_args()
    profile_dir = Path(args.user_data_dir).expanduser().resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            channel="chrome",
            viewport={"width": 1440, "height": 980},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        print("Opening WeChat Official Account login page...")
        print("Scan the QR code and wait until the backend home page appears.")
        page.goto("https://mp.weixin.qq.com/", wait_until="domcontentloaded")

        try:
            page.wait_for_url("**/cgi-bin/home**", timeout=180000)
        except Exception:
            token = extract_token(page)
            if not token:
                context.close()
                raise RuntimeError("Login not detected within 180 seconds.")

        token = extract_token(page)
        if not token:
            context.close()
            raise RuntimeError("Login page opened, but token was not captured.")

        print(f"Login success. Session saved to: {profile_dir}")
        context.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
