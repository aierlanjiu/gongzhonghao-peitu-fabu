import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright


SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PROFILE_DIR = SKILL_DIR / "assets" / "wechat_profile"
DEFAULT_BM_MD_URL = "http://localhost:2663/api/markdown/render"
COPY_SCRIPT = SKILL_DIR / "scripts" / "copy-to-clipboard.ts"
PASTE_SCRIPT = SKILL_DIR / "scripts" / "paste-from-clipboard.ts"


def resolve_bm_md_url(cli_value):
    if cli_value:
        return cli_value
    if os.getenv("BM_MD_RENDER_URL"):
        return os.environ["BM_MD_RENDER_URL"].rstrip("/")
    base_url = (
        os.getenv("BM_MD_API_URL")
        or os.getenv("VITE_API_URL")
        or os.getenv("BM_MD_APP_URL")
        or os.getenv("VITE_APP_URL")
    )
    if base_url:
        return base_url.rstrip("/") + "/api/markdown/render"
    return DEFAULT_BM_MD_URL


def parse_args():
    parser = argparse.ArgumentParser(
        description="Publish a markdown article to WeChat Official Account drafts."
    )
    parser.add_argument("--title", required=True, help="Draft title.")
    parser.add_argument("--markdown", required=True, help="Absolute path to markdown file.")
    parser.add_argument("--cover", required=True, help="Absolute path to cover image.")
    parser.add_argument(
        "--inline-image",
        action="append",
        default=[],
        help="Placeholder mapping in the form LABEL=/abs/path/to/image.jpg. Repeatable.",
    )
    parser.add_argument("--markdown-style", default="newsprint", help="bm-md style name.")
    parser.add_argument("--platform", default="wechat", help="bm-md target platform.")
    parser.add_argument(
        "--bm-md-url",
        default=None,
        help="bm-md render endpoint. If omitted, read bm-md related environment variables.",
    )
    parser.add_argument(
        "--user-data-dir",
        default=str(DEFAULT_PROFILE_DIR),
        help="Persistent Playwright profile directory for WeChat login.",
    )
    return parser.parse_args()


def require_file(path_str, label):
    path = Path(path_str).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


def parse_inline_mappings(items):
    mappings = []
    for item in items:
        if "=" not in item:
            raise ValueError(f"Invalid --inline-image value: {item}")
        label, image_path = item.split("=", 1)
        mappings.append((label.strip(), require_file(image_path.strip(), f"Inline image for {label.strip()}")))
    return mappings


def render_markdown(markdown_path, style, platform, endpoint):
    with markdown_path.open("r", encoding="utf-8") as f:
        markdown = f.read()

    payload = {
        "markdown": markdown,
        "markdownStyle": style,
        "platform": platform,
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError("bm-md render failed. Check your bm-md service and env configuration.") from exc

    html = result.get("result", "").strip()
    if not html:
        raise RuntimeError("bm-md returned empty HTML.")
    return "<meta charset=\"utf-8\">\\n" + html


def copy_html_to_clipboard(html_content):
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as tmp:
        tmp.write(html_content)
        tmp_path = tmp.name
    try:
        run_bun_script(COPY_SCRIPT, ["html", "--file", tmp_path])
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def copy_image_to_clipboard(image_path):
    run_bun_script(COPY_SCRIPT, ["image", str(image_path)])


def run_bun_script(script_path, args):
    if shutil.which("bun"):
        cmd = ["bun", str(script_path), *args]
    elif shutil.which("npx"):
        cmd = ["npx", "-y", "bun", str(script_path), *args]
    else:
        raise RuntimeError("Neither bun nor npx is available. Install bun or Node.js with npx.")
    subprocess.run(cmd, check=True)


def send_real_paste_keystroke():
    run_bun_script(PASTE_SCRIPT, ["--app", "Google Chrome"])


def extract_token(page):
    if "token=" in page.url:
        return page.url.split("token=")[1].split("&")[0]
    try:
        return page.evaluate("() => new URLSearchParams(window.location.search).get('token') || ''")
    except Exception:
        return ""


def ensure_logged_in(page):
    page.goto("https://mp.weixin.qq.com/", wait_until="domcontentloaded")
    try:
        page.wait_for_url("**/cgi-bin/home**", timeout=15000)
    except Exception:
        pass
    token = extract_token(page)
    if not token:
        raise RuntimeError("WeChat account is not logged in. Run init_wechat_login.py first.")
    return token


def open_editor(context, token):
    draft_url = (
        "https://mp.weixin.qq.com/cgi-bin/appmsg"
        f"?t=media/appmsg_edit_v2&action=edit&isNew=1&type=77&createType=0&token={token}&lang=zh_CN"
    )
    page = context.new_page()
    page.goto(draft_url, wait_until="networkidle")
    page.bring_to_front()
    return page


def replace_placeholder_with_image(page, label, image_path):
    found = page.evaluate(
        """(needle) => {
            const root = document.querySelector('.ProseMirror');
            if (!root) return false;
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
            let node;
            while ((node = walker.nextNode())) {
                if (!node.nodeValue || !node.nodeValue.includes(needle)) continue;
                const range = document.createRange();
                range.selectNodeContents(node.parentElement);
                const selection = window.getSelection();
                selection.removeAllRanges();
                selection.addRange(range);
                node.parentElement.scrollIntoView({ block: 'center' });
                return true;
            }
            return false;
        }""",
        label,
    )
    if not found:
        print(f"Placeholder not found: {label}")
        return
    copy_image_to_clipboard(image_path)
    send_real_paste_keystroke()
    time.sleep(2)


def upload_cover(page, cover_path):
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(1)
    file_input = page.locator("input[type='file'][accept*='image']").first
    if file_input.count() == 0:
        print("Cover upload input not found.")
        return
    file_input.set_input_files(str(cover_path))
    time.sleep(3)


def save_draft(page):
    try:
        save_button = page.locator("#js_submit").first
        if save_button.count() > 0:
            save_button.click()
            time.sleep(3)
            return
    except Exception:
        pass
    page.evaluate(
        """() => {
            for (const button of document.querySelectorAll('button')) {
                const text = button.innerText || '';
                if (text.includes('保存为草稿') || text.includes('保存')) {
                    button.click();
                    return;
                }
            }
        }"""
    )
    time.sleep(3)


def main():
    args = parse_args()
    markdown_path = require_file(args.markdown, "Markdown file")
    cover_path = require_file(args.cover, "Cover image")
    inline_mappings = parse_inline_mappings(args.inline_image)
    bm_md_url = resolve_bm_md_url(args.bm_md_url)
    html = render_markdown(markdown_path, args.markdown_style, args.platform, bm_md_url)

    copy_html_to_clipboard(html)
    print("Rendered HTML copied to clipboard.")

    user_data_dir = Path(args.user_data_dir).expanduser().resolve()
    user_data_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=False,
            channel="chrome",
            viewport={"width": 1440, "height": 980},
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            token = ensure_logged_in(page)
            editor_page = open_editor(context, token)
            editor_page.locator("#title").first.fill(args.title)
            editor = editor_page.locator(".ProseMirror, .js_pmEditorArea").first
            editor.click()
            send_real_paste_keystroke()
            time.sleep(3)
            for label, image_path in inline_mappings:
                replace_placeholder_with_image(editor_page, label, image_path)
            upload_cover(editor_page, cover_path)
            save_draft(editor_page)
            print("Done. Draft pasted and saved.")
        finally:
            context.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
