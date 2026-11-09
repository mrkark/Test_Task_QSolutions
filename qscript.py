import os
import re
import sys
import time
import math
import json
import random
from typing import Optional, Dict, Any, List
from playwright.sync_api import sync_playwright, Page

PATH_TO_VIDEO_FOLDER = "./video"

_CURRENT_PAGE: Optional[Page] = None

INJECTED_VISUALS_SCRIPT = """
(() => {
    if (window !== window.top) return;
    if (window.__playwright_visuals_initialized__) return;
    window.__playwright_visuals_initialized__ = true;

    function initVisuals() {
        if (!document.documentElement) {
            setTimeout(initVisuals, 10);
            return;
        }

        let container = document.getElementById('__playwright_overlay_container__');
        if (!container) {
            container = document.createElement('div');
            container.id = '__playwright_overlay_container__';
            container.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                width: 100vw;
                height: 100vh;
                pointer-events: none;
                z-index: 2147483647;
                overflow: hidden;
            `;

            const highlight = document.createElement('div');
            highlight.id = '__playwright_cursor_highlight__';
            highlight.style.cssText = `
                position: absolute;
                top: 0;
                left: 0;
                width: 64px;
                height: 64px;
                margin-left: -32px;
                margin-top: -32px;
                background: rgba(255, 235, 59, 0.45);
                border-radius: 50%;
                pointer-events: none;
                z-index: 2147483646;
                transform: translate(-100px, -100px);
                will-change: transform;
            `;

            const cursor = document.createElement('div');
            cursor.id = '__playwright_cursor_arrow__';
            cursor.style.cssText = `
                position: absolute;
                top: 0;
                left: 0;
                width: 32px;
                height: 32px;
                pointer-events: none;
                z-index: 2147483647;
                transform: translate(-100px, -100px);
                will-change: transform;
            `;

            cursor.innerHTML = `
                <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M 1 1 L 1 24 L 6.5 18.5 L 12.5 29.5 L 16 28 L 10.5 17 L 18 17 Z"
                          fill="#FFFFFF"
                          stroke="#000000"
                          stroke-width="1.8"
                          stroke-linejoin="round"
                          stroke-linecap="round"/>
                </svg>
            `;

            const callout = document.createElement('div');
            callout.id = '__playwright_callout__';
            callout.style.cssText = `
                position: absolute;
                top: 28px;
                left: 50%;
                transform: translateX(-50%);
                padding: 10px 24px;
                border-radius: 8px;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
                font-size: 16pt;
                font-weight: 600;
                line-height: 1.4;
                box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
                pointer-events: none;
                z-index: 2147483647;
                opacity: 0;
                display: none;
            `;

            container.appendChild(highlight);
            container.appendChild(cursor);
            container.appendChild(callout);
            document.documentElement.appendChild(container);
        }

        const highlight = document.getElementById('__playwright_cursor_highlight__');
        const cursor = document.getElementById('__playwright_cursor_arrow__');
        const callout = document.getElementById('__playwright_callout__');

        let lastMouseX = 640;
        let lastMouseY = 360;
        let isZoomedIn = false;

        function updatePosition(x, y) {
            lastMouseX = x;
            lastMouseY = y;
            if (highlight && cursor) {
                highlight.style.transform = `translate(${x}px, ${y}px)`;
                cursor.style.transform = `translate(${x}px, ${y}px)`;
            }
        }

        window.addEventListener('mousemove', (e) => {
            updatePosition(e.clientX, e.clientY);
        }, { capture: true, passive: true });

        function createRipple(x, y) {
            const ripple = document.createElement('div');
            ripple.className = '__playwright_click_ripple__';
            ripple.style.cssText = `
                position: absolute;
                top: 0;
                left: 0;
                width: 8px;
                height: 8px;
                margin-left: -4px;
                margin-top: -4px;
                border-radius: 50%;
                border: 2px solid rgba(255, 152, 0, 0.9);
                background: rgba(255, 235, 59, 0.5);
                pointer-events: none;
                z-index: 2147483645;
                transform: translate(${x}px, ${y}px) scale(0.2);
                opacity: 0.9;
                transition: transform 0.45s cubic-bezier(0.1, 0.8, 0.3, 1), opacity 0.45s ease-out;
            `;
            container.appendChild(ripple);

            requestAnimationFrame(() => {
                ripple.style.transform = `translate(${x}px, ${y}px) scale(8)`;
                ripple.style.opacity = '0';
            });

            setTimeout(() => {
                if (ripple.parentNode) ripple.parentNode.removeChild(ripple);
            }, 500);
        }

        window.addEventListener('mousedown', (e) => {
            createRipple(e.clientX, e.clientY);
        }, { capture: true, passive: true });

        function showZoomIndicator(x, y, type) {
            let ind = document.getElementById('__playwright_zoom_indicator__');
            if (!ind) {
                ind = document.createElement('div');
                ind.id = '__playwright_zoom_indicator__';
                container.appendChild(ind);
            }
            const isZoomIn = (type === 'in');
            const ringBorder = isZoomIn ? '4px solid #00e676' : '4px dashed #ff3d00';
            const bg = isZoomIn ? 'rgba(0, 230, 118, 0.25)' : 'rgba(255, 61, 0, 0.2)';
            const shadow = isZoomIn ? '0 0 24px rgba(0, 230, 118, 0.85)' : '0 0 24px rgba(255, 61, 0, 0.85)';

            ind.style.cssText = `
                position: absolute;
                top: 0;
                left: 0;
                width: 80px;
                height: 80px;
                margin-left: -40px;
                margin-top: -40px;
                border-radius: 50%;
                border: ${ringBorder};
                background: ${bg};
                box-shadow: ${shadow};
                pointer-events: none;
                z-index: 2147483647;
                transform: translate(${x}px, ${y}px) scale(${isZoomIn ? 0.2 : 1.8});
                opacity: 0.95;
                transition: transform 0.6s cubic-bezier(0.1, 0.8, 0.3, 1), opacity 0.6s ease-out;
            `;

            requestAnimationFrame(() => {
                ind.style.transform = `translate(${x}px, ${y}px) scale(${isZoomIn ? 1.6 : 0.3})`;
                ind.style.opacity = '0';
            });
        }

        function toggleZoom(x, y) {
            isZoomedIn = !isZoomedIn;
            const evType = isZoomedIn ? 'in' : 'out';
            showZoomIndicator(x, y, evType);
            const ev = {
                x: Math.round(x),
                y: Math.round(y),
                type: evType
            };
            if (window.__playwright_record_zoom_event) {
                try {
                    window.__playwright_record_zoom_event(ev);
                } catch(e) {}
            }
            return ev;
        }

        window.addEventListener('keydown', (e) => {
            if (e.key === 'F5' || e.code === 'F5') {
                e.preventDefault();
                e.stopPropagation();
                toggleZoom(lastMouseX, lastMouseY);
            }
        }, { capture: true });

        window.__zoomAt = function(x, y) {
            const targetX = (typeof x === 'number') ? x : lastMouseX;
            const targetY = (typeof y === 'number') ? y : lastMouseY;
            updatePosition(targetX, targetY);
            return toggleZoom(targetX, targetY);
        };

        window.__showCallout = function(text, bgColor, textColor, fade) {
            if (!callout) return;
            callout.innerText = text;
            callout.style.backgroundColor = bgColor || '#ffeb3b';
            callout.style.color = textColor || '#000000';
            callout.style.display = 'block';

            if (fade) {
                callout.style.transition = 'opacity 2s ease-in-out';
                callout.style.opacity = '0';
                requestAnimationFrame(() => {
                    callout.style.opacity = '1';
                });
                setTimeout(() => {
                    callout.style.opacity = '0';
                    setTimeout(() => {
                        callout.style.display = 'none';
                    }, 2000);
                }, 3000);
            } else {
                callout.style.transition = 'none';
                callout.style.opacity = '1';
            }
        };

        window.__updateCursorPosition = updatePosition;
        window.__createRipple = createRipple;
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initVisuals);
    } else {
        initVisuals();
    }
})();
"""


def ShowCallout(
    text: str,
    bgColor: str = "#ffeb3b",
    textColor: str = "#000000",
    fade: bool = True,
    page: Optional[Page] = None,
) -> None:
    global _CURRENT_PAGE
    if hasattr(text, "evaluate"):
        page, text = text, str(bgColor)
        bgColor = (
            textColor
            if isinstance(textColor, str) and textColor.startswith(("#", "rgb", "hsl"))
            else "#ffeb3b"
        )
        textColor = "#000000"

    target_page = page or _CURRENT_PAGE
    if target_page is None:
        return

    try:
        target_page.evaluate(
            """({text, bgColor, textColor, fade}) => {
                if (window.__showCallout) {
                    window.__showCallout(text, bgColor, textColor, fade);
                }
            }""",
            {
                "text": str(text),
                "bgColor": str(bgColor),
                "textColor": str(textColor),
                "fade": bool(fade),
            },
        )
        if fade:
            time.sleep(1.5)
    except Exception:
        pass


def TriggerZoom(
    page: Optional[Page] = None,
    x: Optional[float] = None,
    y: Optional[float] = None,
) -> Optional[dict]:
    """Programmatically triggers zoom-in or zoom-out at coordinates (x, y)."""
    global _CURRENT_PAGE
    target_page = page or _CURRENT_PAGE
    if target_page is None:
        return None
    try:
        return target_page.evaluate(
            "({x, y}) => (window.__zoomAt ? window.__zoomAt(x, y) : null)",
            {"x": x, "y": y},
        )
    except Exception as exc:
        print(f"TriggerZoom error: {exc}", file=sys.stderr)
        return None


def _smooth_mouse_move(
    page: Page,
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
    duration: float = 0.8,
) -> tuple[float, float]:
    distance = math.hypot(end_x - start_x, end_y - start_y)
    steps = max(25, int(distance / 12))
    dt = duration / steps

    for i in range(1, steps + 1):
        t = i / steps
        ease = t * t * (3 - 2 * t)
        curr_x = start_x + (end_x - start_x) * ease
        curr_y = start_y + (end_y - start_y) * ease
        page.mouse.move(curr_x, curr_y)
        time.sleep(dt)

    return end_x, end_y


def _human_type(page: Page, text: str) -> None:
    for ch in text:
        page.keyboard.type(ch)
        base_delay = random.uniform(0.045, 0.11)
        if ch == " ":
            base_delay += random.uniform(0.04, 0.08)
        time.sleep(base_delay)


def _sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", name).strip()
    return cleaned if cleaned else "video"


def CaptureVideo_Magento(
    url: str,
    company_name: str,
    language: str,
    country: str,
    postcode: str,
    city: str,
    street: str,
    house_no: str,
    enable_zoom: bool = False,
) -> Optional[str]:
    global _CURRENT_PAGE

    target_dir = os.path.abspath(PATH_TO_VIDEO_FOLDER)
    os.makedirs(target_dir, exist_ok=True)

    headless_env = os.environ.get("HEADLESS", "0").lower() in ("1", "true", "yes")
    if not enable_zoom and os.environ.get("ENABLE_ZOOM", "0").lower() in ("1", "true", "yes"):
        enable_zoom = True

    playwright_instance = None
    browser = None
    context = None
    zoom_events: List[Dict[str, Any]] = []

    try:
        playwright_instance = sync_playwright().start()

        browser = playwright_instance.chromium.launch(
            headless=headless_env,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ],
        )

        context = browser.new_context(
            record_video_dir=target_dir,
            record_video_size={"width": 1280, "height": 720},
            viewport={"width": 1280, "height": 720},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            locale=language or "en-US",
        )

        video_start_time = time.time()

        def on_record_zoom_event(ev):
            t = round(max(0.0, time.time() - video_start_time), 2)
            event_dict = {
                "t": t,
                "x": float(ev.get("x", 640.0)),
                "y": float(ev.get("y", 360.0)),
                "type": str(ev.get("type", "in")).lower(),
            }
            zoom_events.append(event_dict)
            print(f"[{company_name}] Captured zoom event: {event_dict}")

        context.expose_function("__playwright_record_zoom_event", on_record_zoom_event)
        context.add_init_script(INJECTED_VISUALS_SCRIPT)

        page = context.new_page()
        _CURRENT_PAGE = page

        print(f"[{company_name}] Opening {url}...")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(1.0)

        cur_x, cur_y = 120.0, 120.0
        page.mouse.move(cur_x, cur_y)
        time.sleep(0.4)

        callout_text = f"Searching: Magento developer in {city}"
        ShowCallout(callout_text, bgColor="#ffeb3b", textColor="#000000", fade=True, page=page)

        search_box = page.locator('textarea[name="q"]').first
        search_box.wait_for(state="visible", timeout=15000)

        s_box = search_box.bounding_box()
        if not s_box:
            raise RuntimeError("Could not obtain search box bounding box.")

        box_center_x = s_box["x"] + s_box["width"] / 2
        box_center_y = s_box["y"] + s_box["height"] / 2

        print(f"[{company_name}] Moving cursor smoothly to search box...")
        cur_x, cur_y = _smooth_mouse_move(page, cur_x, cur_y, box_center_x, box_center_y, duration=0.85)
        time.sleep(0.2)

        page.mouse.click(cur_x, cur_y)
        time.sleep(0.3)

        search_query = f"Magento developer in {city}"
        print(f"[{company_name}] Typing query: '{search_query}'...")
        _human_type(page, search_query)
        time.sleep(0.6)

        submit_btn = None
        btns = page.locator('form button[type="submit"]')
        count = btns.count()
        for i in range(count):
            candidate = btns.nth(i)
            if candidate.is_visible():
                box = candidate.bounding_box()
                if box and box["width"] > 0 and box["height"] > 0:
                    submit_btn = candidate
                    break

        if not submit_btn:
            submit_btn = page.locator('button[type="submit"]:visible').first

        btn_box = submit_btn.bounding_box()
        if not btn_box:
            raise RuntimeError("Could not obtain search button bounding box.")

        btn_center_x = btn_box["x"] + btn_box["width"] / 2
        btn_center_y = btn_box["y"] + btn_box["height"] / 2

        print(f"[{company_name}] Moving cursor smoothly to search button...")
        cur_x, cur_y = _smooth_mouse_move(page, cur_x, cur_y, btn_center_x, btn_center_y, duration=0.75)
        time.sleep(0.25)

        print(f"[{company_name}] Clicking search button...")
        try:
            page.mouse.click(cur_x, cur_y)
        except Exception as e:
            print(f"[{company_name}] Navigation triggered on click: {e}")

        print(f"[{company_name}] Waiting for results...")
        first_result = None
        poll_start = time.time()
        timeout_seconds = 30.0

        while time.time() - poll_start < timeout_seconds:
            try:
                locator = page.locator('a[data-testid="result-title-a"]')
                if locator.count() > 0:
                    cand = locator.first
                    if cand.is_visible():
                        box = cand.bounding_box()
                        if box and box["width"] > 0 and box["height"] > 0:
                            first_result = cand
                            break
            except Exception:
                pass
            time.sleep(0.4)

        if not first_result:
            raise TimeoutError("Search results did not render within timeout period.")

        print(f"[{company_name}] Scrolling first result into view...")
        first_result.scroll_into_view_if_needed()
        time.sleep(0.4)

        res_box = first_result.bounding_box()
        if not res_box:
            raise RuntimeError("Could not obtain first result bounding box.")

        res_x = res_box["x"] + min(60.0, res_box["width"] / 2)
        res_y = res_box["y"] + res_box["height"] / 2

        print(f"[{company_name}] Moving cursor smoothly to first result ({res_x:.1f}, {res_y:.1f})...")
        cur_x, cur_y = _smooth_mouse_move(page, cur_x, cur_y, res_x, res_y, duration=0.85)
        time.sleep(0.3)

        if enable_zoom:
            print(f"[{company_name}] Scenario triggering programmatic window.__zoomAt({res_x:.1f}, {res_y:.1f}) (in)...")
            TriggerZoom(page, res_x, res_y)
            time.sleep(2.0)
            print(f"[{company_name}] Scenario triggering programmatic window.__zoomAt({res_x:.1f}, {res_y:.1f}) (out)...")
            TriggerZoom(page, res_x, res_y)
            time.sleep(0.5)

        print(f"[{company_name}] Clicking first result...")
        try:
            page.mouse.click(cur_x, cur_y)
        except Exception as e:
            print(f"[{company_name}] Result navigation: {e}")

        time.sleep(2.5)

        video_obj = page.video

        _CURRENT_PAGE = None
        context.close()
        context = None

        browser.close()
        browser = None

        raw_video_path = video_obj.path() if video_obj else None
        if not raw_video_path or not os.path.exists(raw_video_path):
            raise FileNotFoundError("Video recording file was not created by Playwright.")

        clean_name = _sanitize_filename(company_name)
        final_video_path = os.path.join(target_dir, f"{clean_name}.webm")

        if os.path.exists(final_video_path):
            os.remove(final_video_path)

        os.replace(raw_video_path, final_video_path)
        abs_final_path = os.path.abspath(final_video_path)

        if len(zoom_events) > 0:
            sidecar_path = f"{abs_final_path}.zoom.json"
            sidecar_data = {
                "viewport": {"width": 1280, "height": 720},
                "fps": 25,
                "zoom_factor": 2.0,
                "ramp_sec": 0.5,
                "events": zoom_events,
            }
            with open(sidecar_path, "w", encoding="utf-8") as sf:
                json.dump(sidecar_data, sf, indent=2)
            print(f"[{company_name}] Sidecar written with {len(zoom_events)} events: {sidecar_path}")

        print(f"[{company_name}] Success: Video recorded at {abs_final_path}")
        return abs_final_path

    except Exception as exc:
        print(f"[{company_name}] ERROR: Failed to capture video: {exc}", file=sys.stderr)
        return None

    finally:
        _CURRENT_PAGE = None
        if context:
            try:
                context.close()
            except Exception:
                pass
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        if playwright_instance:
            try:
                playwright_instance.stop()
            except Exception:
                pass
