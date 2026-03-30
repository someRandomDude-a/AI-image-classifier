import os
import time
import base64
from playwright.sync_api import sync_playwright

DOWNLOAD_DIR = "downloads"
USER_DATA_DIR = "data"
GROUPS = ["Alina", "Cool people club"]
MAX_IMAGES_IF_NO_LAST = 50
SCROLLS_PER_GROUP = 20


def ensure_folder(name):
    safe = "".join(c for c in name if c.isalnum() or c in " _-")
    path = os.path.join(DOWNLOAD_DIR, safe)
    os.makedirs(path, exist_ok=True)
    return path


def save_base64_image(data_url, folder):
    header, encoded = data_url.split(",", 1)
    data = base64.b64decode(encoded)
    filename = f"{int(time.time() * 1000)}.jpg"
    filepath = os.path.join(folder, filename)
    with open(filepath, "wb") as f:
        f.write(data)
    return filename


def get_last_downloaded_timestamp(folder):
    if not os.path.exists(folder):
        return None
    timestamps = []
    for f in os.listdir(folder):
        if f.endswith(".jpg"):
            try:
                ts = int(os.path.splitext(f)[0])
                timestamps.append(ts)
            except:
                continue
    return max(timestamps) if timestamps else None


def scroll_to_load_images(page, scrolls=SCROLLS_PER_GROUP):
    for _ in range(scrolls):
        page.keyboard.press("PageUp")
        time.sleep(0.1)


def click_download_buttons(page):
    clicked = set()
    buttons = page.locator('div[role="button"] svg[aria-label="Download"]')
    for i in range(buttons.count()):
        try:
            btn = buttons.nth(i).locator('xpath=..')
            btn_id = btn.evaluate("el => el.outerHTML")
            if btn_id in clicked:
                continue
            btn.click()
            clicked.add(btn_id)
            time.sleep(0.1)
        except:
            continue


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(USER_DATA_DIR, headless=False)
        page = browser.new_page()
        page.goto("https://web.whatsapp.com")

        print("Waiting for login...")
        # Locate the search bar once at login
        search_bar = page.locator('input[role="textbox"][type="text"]')
        search_bar.wait_for(state="visible", timeout=0)
        print("Logged in!")

        last_group = None

        for group in GROUPS:
            print(f"\n--- {group} ---")
            folder = ensure_folder(group)
            last_ts = get_last_downloaded_timestamp(folder)
            print(f"[i] Last downloaded timestamp: {last_ts}" if last_ts else "[i] No previous downloads found")

            # Focus search bar and clear previous text (previous group)
            search_bar.scroll_into_view_if_needed()
            search_bar.click()
            search_bar.fill("")  # Clear previous group text
            time.sleep(0.1)
            page.keyboard.press("Escape")  # ensure not typing into chat
            search_bar.click()
            search_bar.type(group, delay=100)
            time.sleep(1.5)

            chat = page.locator(f'span[title="{group}"]')
            if chat.count() == 0:
                print("[!] Group not found")
                continue
            chat.first.click()
            time.sleep(1)

            # Scroll and download images
            scroll_to_load_images(page)
            click_download_buttons(page)
            time.sleep(1)

            images = page.locator('div[data-testid="media-message"] img')
            count = images.count()
            print(f"[i] Found {count} image candidates")
            downloaded_count = 0

            for i in range(count - 1, -1, -1):
                try:
                    src = images.nth(i).get_attribute("src")
                    if not src or not src.startswith("blob:"):
                        continue

                    data_url = page.evaluate(
                        """async (src) => {
                            try {
                                const res = await fetch(src);
                                const blob = await res.blob();
                                return await new Promise(resolve => {
                                    const reader = new FileReader();
                                    reader.onloadend = () => resolve(reader.result);
                                    reader.readAsDataURL(blob);
                                });
                            } catch { return null; }
                        }""",
                        src
                    )
                    if not data_url:
                        continue

                    now_ts = int(time.time() * 1000)
                    if last_ts and now_ts <= last_ts:
                        print("[i] Reached last downloaded image. Stopping.")
                        break

                    save_base64_image(data_url, folder)
                    downloaded_count += 1
                    print("[✓] Saved image")
                    if not last_ts and downloaded_count >= MAX_IMAGES_IF_NO_LAST:
                        print(f"[i] Reached {MAX_IMAGES_IF_NO_LAST} images. Stopping.")
                        break
                except Exception as e:
                    print("Error:", e)

            last_group = group

        print("\nDone. Waiting 10s before closing...")
        time.sleep(10)
        browser.close()


if __name__ == "__main__":
    run()