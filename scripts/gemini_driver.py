import os
import asyncio
import time
import re
import fcntl
import sys
from pathlib import Path
from playwright.async_api import async_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent

# Keep bundled sibling imports working when the skill is copied to another machine/repo.
for candidate in (SCRIPT_DIR, SKILL_DIR):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

# Lock file for serializing browser profile access across concurrent processes
_PROFILE_LOCK_PATH = SKILL_DIR / '.gemini' / 'browser_profile.lock'

# Try to import WatermarkRemover safely and instantiate it once
try:
    from scripts.remove_watermark import WatermarkRemover
    WATERMARK_REMOVER_INSTANCE = WatermarkRemover()
except ImportError:
    try:
        from remove_watermark import WatermarkRemover
        WATERMARK_REMOVER_INSTANCE = WatermarkRemover()
    except ImportError:
        print("⚠️ WatermarkRemover not found. Watermark removal will be skipped.")
        WATERMARK_REMOVER_INSTANCE = None
except Exception as init_err:
    print(f"⚠️ Error initializing WatermarkRemover: {init_err}")
    WATERMARK_REMOVER_INSTANCE = None

# Define Persistent Path
USER_DATA_DIR = SKILL_DIR / '.gemini' / 'browser_profile'

class ImageDownloadError(Exception):
    """Custom exception raised when image download fails and fallback is disabled."""
    pass

class AsyncGeminiDriver:
    def __init__(self, headless=False, allow_screenshot_fallback=True):
        self.headless = headless
        self.allow_screenshot_fallback = allow_screenshot_fallback
        self.playwright = None
        self.browser = None
        self.page = None
        self.last_gen_time = None  # Record time taken by last successful generation
        self._lock_fd = None  # File descriptor for profile lock

    async def start(self):
        # ── Acquire exclusive file lock (blocks until other instances finish) ──
        print("🔒 Acquiring browser profile lock (waiting for other instances to finish)...")
        os.makedirs(_PROFILE_LOCK_PATH.parent, exist_ok=True)
        self._lock_fd = open(_PROFILE_LOCK_PATH, 'w')
        fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_EX)  # Blocking exclusive lock
        print("🔓 Profile lock acquired. Launching browser...")

        self.playwright = await async_playwright().start()
        launch_args = [
            "--disable-blink-features=AutomationControlled", 
            "--no-sandbox", 
            "--disable-infobars", 
            "--start-maximized"
        ]
        self.browser = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=self.headless,
            channel="chrome",
            args=launch_args,
            permissions=['clipboard-read', 'clipboard-write']
        )
        self.page = self.browser.pages[0]
        await self.page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        await self._ensure_clean_session()
        return self

    async def _wait_for_condition(self, check_func, timeout=30, interval=1.0, msg="Waiting"):
        """Generic polling wait to replace hardcoded sleeps. Returns True if condition met, False if timed out."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                if await check_func():
                    return True
            except Exception:
                pass
            await asyncio.sleep(interval)
        print(f"   ⚠️ Timeout ({timeout}s) exceeded: {msg}")
        return False

    async def _ensure_clean_session(self):
        """Navigates to the app, waits for it to load, clicks 'New Chat' to ensure a clean context, and ensures we are on Advanced/Pro if possible."""
        print("🔗 Navigating to Gemini...")
        
        for attempt in range(3):
            try:
                await self.page.goto("https://gemini.google.com/app", timeout=60000)
                if "accounts.google.com" in self.page.url:
                    await self.page.wait_for_url("https://gemini.google.com/app", timeout=120000)
                
                # Wait for main input area to signify loaded
                await self._wait_for_condition(
                    lambda: self.page.locator("div[role='textbox']").first.is_visible(),
                    timeout=20,
                    msg="Main input box to become visible"
                )
                
                # ── CRITICAL: Force a New Chat to clear context pollution ──
                print("   🧹 Initiating 'New Chat' to purge context pollution...")
                new_chat_btn = (
                    self.page.locator("a[aria-label*='新聊天'], a[aria-label*='New chat']").first
                    .or_(self.page.locator("button[aria-label*='新聊天'], button[aria-label*='New chat']").first)
                    .or_(self.page.locator("a[href='/app']").first)
                )
                if await new_chat_btn.is_visible():
                    await new_chat_btn.click(force=True)
                    await asyncio.sleep(2)  # Give UI time to reset
                    print("   ✅ New Chat context established.")
                else:
                    print("   ⚠️ New Chat button not found, context might be polluted!")

                break
            except Exception as e:
                print(f"⚠️ Navigation attempt {attempt+1} failed: {e}")
                if attempt == 2: raise
                await asyncio.sleep(3)

        self._last_pro_result = await self._attempt_switch_to_pro()

    async def _get_current_model_name(self) -> str:
        """读取页面上当前显示的模型名称，用于诊断。"""
        try:
            # 常见的模型名显示区域
            selectors = [
                "button[data-test-id='bard-mode-menu-button']",
                "button.input-area-switch",
                "button[data-test-id='mode-switcher-button']",
                "button[aria-label*='模型'], button[aria-label*='model']",
            ]
            for sel in selectors:
                el = self.page.locator(sel).first
                if await el.count() > 0 and await el.is_visible():
                    text = (await el.inner_text()).strip()
                    if text:
                        return text[:40]
            return "未知"
        except Exception:
            return "读取失败"

    async def _attempt_switch_to_pro(self) -> tuple[bool, str]:
        """
        Attempts to select the best multimodal logic model (Advanced/Pro/Think).
        Returns (success, detail_message) for Telegram status reporting.
        """
        try:
            print("   🎯 Checking model selector...")

            # 先读取当前模型名
            current_model = await self._get_current_model_name()
            print(f"   📋 Current model on page: {current_model}")

            # Step 1: Open menu — try multiple selectors for Gemini UI versions
            quick_btn = (
                self.page.locator("button[data-test-id='bard-mode-menu-button']").first
                .or_(self.page.locator("button.input-area-switch").first)
                .or_(self.page.locator("button[data-test-id='mode-switcher-button']").first)
                .or_(self.page.locator("button[aria-label*='模型'], button[aria-label*='model'], button[aria-label*='Model']").first)
                .or_(self.page.locator("button").filter(has_text=re.compile(r"2\.0 Flash|2\.5 Pro|3\.1|Advanced|Gemini|\bpro\b", re.I)).first)
            )

            found = await quick_btn.count() > 0
            if found:
                try:
                    found = await quick_btn.is_visible()
                except Exception:
                    found = False

            if not found:
                msg = f"⚠️ 模型切换器按钮未找到，当前模型: {current_model}"
                print(f"   ℹ️ {msg}")
                return False, msg

            await quick_btn.click(force=True)

            # Wait for menu popup
            await self._wait_for_condition(
                lambda: self.page.locator("mat-menu, [role='menu'], [role='listbox']").first.is_visible(),
                timeout=5,
                interval=0.5,
                msg="Model menu popup"
            )
            await asyncio.sleep(1)

            # Step 2: 读取所有菜单选项文本（用于诊断）
            options = await self.page.locator(
                "button[role='menuitem'], .mat-mdc-menu-item, [role='option'], li[role='option']"
            ).all()

            all_option_texts = []
            clicked = False
            selected_name = ""
            for op in options:
                try:
                    text = await op.inner_text()
                    text_clean = text.strip()
                    if text_clean:
                        all_option_texts.append(text_clean[:30])
                    if re.search(r"\bPro\b|3\.1 Pro|2\.5 Pro|Advanced|Gemini Pro|Pro 1\.5|Experimental", text, re.I):
                        is_disabled = (
                            await op.get_attribute("disabled") is not None
                            or await op.get_attribute("aria-disabled") == "true"
                        )
                        if not is_disabled:
                            selected_name = text_clean[:30]
                            print(f"   🎯 Found enabled option: {selected_name}")
                            await op.click(timeout=3000)
                            print("   ✅ Successfully selected Advanced/Pro model.")
                            clicked = True
                            await asyncio.sleep(1)
                            break
                except Exception as e:
                    print(f"   ⚠️ Could not interact with model option: {e}")

            if clicked:
                return True, f"✅ 已切换至: {selected_name}"
            else:
                await self.page.keyboard.press("Escape")
                options_summary = " | ".join(all_option_texts[:5]) if all_option_texts else "无"
                msg = f"⚠️ 菜单内无可用Pro选项。可见选项: [{options_summary}]"
                print(f"   ℹ️ {msg}")
                return False, msg

        except Exception as e:
            msg = f"❌ 模型切换异常: {str(e)[:60]}"
            print(f"   ⚠️ {msg}")
            return False, msg

    async def chat(self, prompt):
        await self._submit_prompt(prompt, activate_imagen_tool=False, raw_mode=True)
        
        print("   ⏳ Waiting for text response...")
        async def response_finished():
            last_msg = self.page.locator("message-content").last
            thumb_up = last_msg.locator("button[aria-label='答得好'], button[aria-label='Good response']").last
            return await thumb_up.count() > 0 and await thumb_up.is_visible()

        await self._wait_for_condition(response_finished, timeout=60, interval=2.0, msg="Text generation thumb_up")
            
        try:
             response_elements = await self.page.locator("message-content .markdown").all()
             return await response_elements[-1].inner_text() if response_elements else None
        except Exception as e:
             print(f"   ⚠️ Error reading final text: {e}")
             return None

    # =========================================================================
    # IMAGE GENERATION PIPELINE
    # =========================================================================

    async def generate_image(self, prompt, output_dir=None):
        downloads_dir = Path(output_dir) if output_dir else SKILL_DIR / 'downloads'
        os.makedirs(downloads_dir, exist_ok=True)
        print(f"🎨 Starting Image Generation Pipeline...")

        # 1. Clean state if necessary
        try:
            initial_msg_count = await self.page.locator("message-content").count()
            if initial_msg_count > 4:
                print("   ♻️ Memory hygiene: Reloading page to flush DOM bloat...")
                await self._ensure_clean_session()
                initial_msg_count = await self.page.locator("message-content").count()
        except Exception:
            initial_msg_count = 0

        # 2. Activate tool & Submit prompt
        tool_activated = await self._activate_imagen_tool()
        await self._submit_prompt(prompt, activate_imagen_tool=tool_activated)
        
        # 3. Wait for standard generation
        generation_complete = await self._wait_for_image_generation(initial_msg_count)
        
        # Fallback trigger if standard gen hung/failed
        if not generation_complete:
            print("   ⚠️ Generation timeout or detection failed. Attempting one-time re-trigger...")
            try:
                last_msg_text = await self.page.locator("message-content").last.inner_text()
                if last_msg_text and len(last_msg_text) > 20:
                     print("   🔄 Forcing Imagen tool via text command...")
                     await self._submit_prompt(f"Please generate the image for this description now: {last_msg_text}", activate_imagen_tool=False)
                     generation_complete = await self._wait_for_image_generation(initial_msg_count + 1, fallback=True)
            except Exception as e:
                print(f"   ⚠️ Re-trigger failed: {e}")

        # Let rendering stabilize slightly
        await asyncio.sleep(2)

        # 4. Pro Redo (Imagen 3 Pro Overlay)
        await self._attempt_pro_redo()

        # 5. Extract and Download
        return await self._download_highest_res_image(downloads_dir)

    # --- Pipeline Steps ---

    async def _activate_imagen_tool(self):
        print("   🔍 Attempting to activate UI image tool tag...")
        try:
            input_box = self.page.locator("div[role='textbox']").first
            await input_box.click()
            
            # Clear input with battle-tested keyboard shortcuts
            # (JS textContent='' breaks Gemini's contenteditable chip system)
            await self.page.keyboard.press("Meta+A")
            await self.page.keyboard.press("Backspace")
            await asyncio.sleep(0.5)
            
            tool_btn = self.page.locator("button.toolbox-drawer-button, button[aria-label*='工具']").or_(
                       self.page.locator("button").filter(has_text=re.compile(r"工具|Tools"))).first
            
            if await tool_btn.is_visible():
                await tool_btn.click()
                
                async def is_imagen_option_visible():
                     gen_btn = self.page.locator("text=/制作图片|生成图片|创建图片|Create image|Imagen/i").first
                     return await gen_btn.is_visible()

                if await self._wait_for_condition(is_imagen_option_visible, timeout=4, interval=0.5, msg="Tool list popup"):
                    gen_btn = self.page.locator("text=/制作图片|生成图片|创建图片|Create image|Imagen/i").first
                    await gen_btn.click()
                    print("   ✅ Clicked 'Generate Image' tool plugin.")
                    await asyncio.sleep(0.5)
                    return True
            print("   ℹ️ Special UI tool button not found. Proceeding with raw prompt.")
            return False
        except Exception as e: 
            print(f"   ⚠️ Auto-tool trigger error: {e}")
            return False

    async def _submit_prompt(self, prompt, activate_imagen_tool, raw_mode=False):
        try:
            input_box = self.page.locator("div[role='textbox']").first
            await input_box.click()
            
            if not activate_imagen_tool:
                # Clear with keyboard (safe for contenteditable)
                await self.page.keyboard.press("Meta+A")
                await self.page.keyboard.press("Backspace")
            else:
                # Ensure we append AFTER the blue tool chip
                await self.page.keyboard.press("End")
            
            # raw_mode: send prompt as-is (for chat or re-trigger)
            # image mode: trust the upstream prompt fully, only add minimal nudge if no tool chip
            if raw_mode:
                text_to_paste = prompt
            elif activate_imagen_tool:
                # Tool chip already tells Gemini to generate image, just send the description
                text_to_paste = prompt
            else:
                # No tool chip active — need a short prefix to force image generation mode
                text_to_paste = f"请直接为我生成图片：\n{prompt}"
            await self.page.evaluate("text => navigator.clipboard.writeText(text)", text_to_paste)
            await self.page.keyboard.press("Meta+V")
            await asyncio.sleep(0.5)
            
            # Try send button, else enter
            send_btn = self.page.locator("button[aria-label*='Send'], button[aria-label*='发送'], button.send-button").first
            if await send_btn.is_visible():
                await send_btn.click()
                print("   🚀 Prompt submitted (via Button).")
            else:
                await self.page.keyboard.press("Enter")
                print("   🚀 Prompt submitted (via Enter).")
        except Exception as e:
            print(f"   ⚠️ Prompt submission encountered issue, hitting Enter as fallback: {e}")
            await self.page.keyboard.press("Enter")

    async def _wait_for_image_generation(self, benchmark_msg_count, fallback=False):
        # Dynamic patience calculation
        base_time = self.last_gen_time if self.last_gen_time and self.last_gen_time > 15 else 45
        max_wait_time = max(90, int(base_time * 2.0))
        fallback_time = max(45, int(base_time * 0.8))
        
        print(f"   ⏳ Polling for generated visualization... (Dynamic Max: {max_wait_time}s)")
        start_time = time.time()
        
        for _ in range(max_wait_time // 2):
            try:
                current_count = await self.page.locator("message-content").count()
                if current_count > benchmark_msg_count:
                    last_msg = self.page.locator("message-content").last
                    elapsed = time.time() - start_time
                    
                    img_count = await last_msg.locator("img").count()
                    thumb_up_count = await last_msg.locator("button[aria-label='答得好'], button[aria-label='Good response']").count()
                    
                    # Ideal completion
                    if img_count > 0 and thumb_up_count > 0 and elapsed > 5:
                        print(f"   ✅ Baseline Image Generated in {int(elapsed)}s!")
                        self.last_gen_time = elapsed
                        return True
                        
                    # Slow/silent completion without thumbs up
                    if img_count > 0 and elapsed > fallback_time:
                         print(f"   ✅ Implicit Graphic Delivery assumed after {int(elapsed)}s.")
                         self.last_gen_time = elapsed
                         return True
            except Exception:
                pass
            await asyncio.sleep(2)
        return False

    async def _attempt_pro_redo(self):
        """Attempts to press the '🍌 使用 Pro 重做' button via the three-dots menu."""
        print("   🍌 Attempting Pro Redo escalation (Imagen 3 Pro)...")
        try:
            # ── Pre-capture: record current image src for change detection ──
            pre_redo_img_src = None
            try:
                last_msg_pre = self.page.locator("message-content").last
                pre_redo_img = last_msg_pre.locator("img").first
                if await pre_redo_img.count() > 0:
                    pre_redo_img_src = await pre_redo_img.get_attribute("src")
            except Exception:
                pass

            # ── Step 1: Click the three-dots "more options" menu on the last response ──
            last_response = self.page.locator("response-container").last
            more_btn = (
                last_response.locator("button.more-menu-button").last
                .or_(last_response.locator("button[aria-label*='更多'], button[aria-label*='more'], button[aria-label*='More']").last)
                .or_(last_response.locator("mat-icon").filter(has_text=re.compile(r"^more_vert$")).last)
                .or_(last_response.locator("button").filter(has_text=re.compile(r"^more_vert$")).last)
            )

            more_btn_found = await more_btn.count() > 0 and await more_btn.is_visible()
            if not more_btn_found:
                more_btn = self.page.locator("button[aria-label*='更多选项'], button[aria-label*='More options']").last
                more_btn_found = await more_btn.count() > 0 and await more_btn.is_visible()

            if not more_btn_found:
                print("   ℹ️ Three-dots menu button not found. Pro Redo skipped.")
                return

            await more_btn.scroll_into_view_if_needed()
            await more_btn.click()
            print("   🔓 Opened three-dots menu...")

            # ── Step 2: Wait for menu to render, then find Pro Redo ──
            await self._wait_for_condition(
                lambda: self.page.locator("button[role='menuitem'], .mat-mdc-menu-item, [role='menuitem']").first.is_visible(),
                timeout=4, interval=0.5, msg="Context menu popup"
            )

            options = await self.page.locator("button[role='menuitem'], .mat-mdc-menu-item, [role='menuitem']").all()
            clicked_pro_redo = False
            for op in options:
                try:
                    text = await op.inner_text()
                    if re.search(r"Pro 重做|Pro Redo|使用 Pro", text, re.I):
                        is_disabled = (
                            await op.get_attribute("disabled") is not None
                            or await op.get_attribute("aria-disabled") == "true"
                        )
                        if not is_disabled:
                            print(f"   🎯 Found enabled Pro Redo option.")
                            # ── Step 3: Click Pro Redo ──
                            try:
                                await op.click(timeout=3000)
                            except Exception as e:
                                print(f"   ⚠️ Native click failed: {e}. Trying JS evaluation...")
                                await op.evaluate("el => el.click()")
                            print("   🍌 Pro Redo click fired! Starting two-phase wait...")
                            clicked_pro_redo = True
                            break
                        else:
                            print("   ℹ️ 'Pro Redo' option found but it is disabled by Gemini.")
                except Exception:
                    pass

            if not clicked_pro_redo:
                print("   ℹ️ 'Pro Redo' option not found or disabled. Pressing Escape and continuing.")
                await self.page.keyboard.press("Escape")
                return

            # ── Step 4: Two-phase wait ──
            # Phase 1: Confirm click triggered generation (image must change or disappear)
            # This prevents the old image from being mistaken as "Pro done"
            await asyncio.sleep(2)  # Brief pause for the click to register

            async def generation_started():
                last_msg = self.page.locator("message-content").last
                imgs = await last_msg.locator("img").all()
                if not imgs:
                    return True  # Image gone = generating in progress
                try:
                    current_src = await imgs[0].get_attribute("src")
                    return current_src != pre_redo_img_src  # src changed = new generation
                except Exception:
                    return False

            phase1_ok = await self._wait_for_condition(
                generation_started, timeout=15, interval=0.5,
                msg="Pro Redo generation to start (image change/disappear)"
            )

            if not phase1_ok:
                print("   ⚠️ Pro Redo click did not trigger generation (image unchanged after 15s). Skipping.")
                return

            # Phase 2: Wait for new Pro image to fully render
            print("   ⏳ Phase 2: Waiting for Pro HD image to complete rendering...")
            async def pro_completed():
                last_msg = self.page.locator("message-content").last
                img_ok = await last_msg.locator("img").count() > 0
                thumb_ok = await last_msg.locator(
                    "button[aria-label='答得好'], button[aria-label='Good response']"
                ).count() > 0
                return img_ok and thumb_ok

            if await self._wait_for_condition(pro_completed, timeout=120, interval=2.0, msg="Pro HD Render Finalization"):
                print("   ✅ Pro HD Image rendered successfully.")
            else:
                print("   ⚠️ Pro render timeout. Downloading best available image.")
            return

        except Exception as e:
            print(f"   ⚠️ Pro Redo flow soft error: {e}")
            try:
                await self.page.keyboard.press("Escape")
            except Exception:
                pass
            return

    async def _download_highest_res_image(self, downloads_dir, hover_timeout=6, retry_timeout=3, download_timeout=90):
        # 1. Bring element into view
        print("   Scrolling to viewport baseline...")
        await self.page.keyboard.press("End")
        await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1)

        # 2. Extract image node
        last_response = self.page.locator("message-content").last
        target_image = None
        
        # Scoped search
        for img in reversed(await last_response.locator("img").all()):
            if await img.is_visible():
                box = await img.bounding_box()
                if box and box['width'] > 200 and box['height'] > 200:
                    target_image = img
                    break
        
        # Unscoped fallback
        if not target_image:
            print("   ⚠️ Scoped search failed. Broadening scan...")
            for img in reversed(await self.page.locator("img").all()):
                if await img.is_visible():
                    box = await img.bounding_box()
                    if box and box['width'] > 300 and box['height'] > 300:
                        target_image = img
                        break

        if not target_image: 
            return await self._emergency_screenshot_fallback(downloads_dir, "Image node vanished from DOM.")

        # 3. Activate hover controls
        print("   Hovering over canvas to expose HD download controls...")
        await target_image.scroll_into_view_if_needed()
        await target_image.hover()
        
        async def download_btn_appears():
             return await self.page.locator("button[aria-label*='下载'], button[aria-label*='Download']").last.is_visible()

        btn_visible = await self._wait_for_condition(download_btn_appears, timeout=hover_timeout, interval=0.5, msg="Download button UI")

        if not btn_visible:
             # Force overlay by clicking
             await target_image.click()
             await self.page.mouse.move(0,0) # Move away
             await asyncio.sleep(0.5)
             await target_image.hover() # Move back
             btn_visible = await self._wait_for_condition(download_btn_appears, timeout=retry_timeout, msg="Download button UI retry")

        # 4. Strategy A: Direct UI Download
        if btn_visible:
            print("   Initiating HD payload transfer (Strategy A: Native Download)...")
            download_btn = self.page.locator("button[aria-label*='下载'], button[aria-label*='Download']").last
            try:
                async with self.page.expect_download(timeout=download_timeout * 1000) as download_info:
                    await download_btn.click(force=True)
                
                download = await download_info.value
                final_path = downloads_dir / f"poster_{int(time.time())}.png"
                await download.save_as(final_path)
                print(f"✅ Download complete: {final_path}")
                self._apply_watermark_removal(final_path)
                return str(final_path)
            except Exception as e:
                print(f"   ⚠️ Native UI download aborted: {e}")
                # Fall through to B

        # 5. Strategy B: Blob / Base64 JS Extraction
        print("   ⚠️ UI control failed. Executing Strategy B: JS Blob Extraction...")
        try:
            img_src = await target_image.get_attribute("src")
            if img_src:
                final_path = downloads_dir / f"poster_{int(time.time())}.png"
                if img_src.startswith("data:"):
                    import base64
                    header, data = img_src.split(",", 1)
                    with open(final_path, "wb") as f:
                        f.write(base64.b64decode(data))
                else:
                    img_bytes_b64 = await self.page.evaluate("""
                        async (src) => {
                            const resp = await fetch(src);
                            const blob = await resp.blob();
                            return new Promise((resolve) => {
                                const reader = new FileReader();
                                reader.onloadend = () => resolve(reader.result.split(',')[1]);
                                reader.readAsDataURL(blob);
                            });
                        }
                    """, img_src)
                    import base64
                    with open(final_path, "wb") as f:
                        f.write(base64.b64decode(img_bytes_b64))
                
                print(f"✅ Extraction complete: {final_path}")
                self._apply_watermark_removal(final_path)
                return str(final_path)
        except Exception as js_err:
            print(f"   ⚠️ JS Blob extraction failed: {js_err}")

        # 6. Strategy C: Emergency Screenshot
        return await self._emergency_screenshot_fallback(downloads_dir, "All HD pipelines exhausted.")

    async def _emergency_screenshot_fallback(self, downloads_dir, reason):
        if not self.allow_screenshot_fallback:
            print(f"❌ HD Capture Failed ({reason}). Screenshot fallback is disabled.")
            raise ImageDownloadError(f"Image download failed: {reason}")
            
        print(f"🧨 HD Capture Failed ({reason}). Initializing emergency viewport screenshot.")
        final_path = downloads_dir / f"poster_fallback_{int(time.time())}.png"
        try:
            if self.page and not self.page.is_closed():
                await self.page.screenshot(path=str(final_path))
                print(f"✅ Emergency screenshot saved: {final_path}")
                return str(final_path)
            else:
                raise Exception("Page closed context lost.")
        except Exception as seq_err:
            print(f"🔥 Catastrophic failure in fallback: {seq_err}")
            raise

    def _apply_watermark_removal(self, file_path):
        if WATERMARK_REMOVER_INSTANCE:
            try:
                WATERMARK_REMOVER_INSTANCE.process_image(file_path)
            except Exception as e:
                print(f"⚠️ Non-fatal issue during watermark removal: {e}")

    async def _send_prompt(self, text, submit=True):
         # Legacy helper for pure text chats if used externally
         await self._submit_prompt(text, activate_imagen_tool=False, raw_mode=True)

    async def close(self):
        try:
            if self.browser: await self.browser.close()
            if self.playwright: await self.playwright.stop()
        except Exception as e:
            print(f"⚠️ Error shutting down Playwright: {e}")
        finally:
            # ── Release profile lock so next queued instance can proceed ──
            if self._lock_fd:
                try:
                    fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_UN)
                    self._lock_fd.close()
                    print("🔓 Browser profile lock released.")
                except Exception:
                    pass
                self._lock_fd = None
