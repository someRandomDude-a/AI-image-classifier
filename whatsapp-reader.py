import os
import time
import base64
import hashlib
from playwright.sync_api import sync_playwright

DOWNLOAD_DIR = "downloads"
USER_DATA_DIR = "data"
GROUPS = ["Alina", "Cool people club"]
MAX_IMAGES_IF_NO_LAST = 50
SCROLLS_PER_GROUP = 10


def ensure_folder(name):
    safe = "".join(c for c in name if c.isalnum() or c in " _-")
    path = os.path.join(DOWNLOAD_DIR, safe)
    os.makedirs(path, exist_ok=True)
    return path


# 🔐 Hash helper
def hash_bytes(data):
    return hashlib.md5(data).hexdigest()


# 📂 Load existing image hashes
def load_existing_hashes(folder):
    hashes = set()
    if not os.path.exists(folder):
        return hashes

    for f in os.listdir(folder):
        if f.endswith(".jpg"):
            path = os.path.join(folder, f)
            try:
                with open(path, "rb") as img:
                    hashes.add(hash_bytes(img.read()))
            except:
                continue

    return hashes


def wait_for_new_blob(img_element, previous_src=None, timeout=5000):
    start_time = time.time()
    while True:
        try:
            src = img_element.get_attribute("src")
            if src and src.startswith("blob:") and src != previous_src:
                return src
        except:
            pass

        if (time.time() - start_time) * 1000 > timeout:
            return None
        time.sleep(0.1)


def scroll_to_load_images(page, scrolls=SCROLLS_PER_GROUP):
    for _ in range(scrolls):
        page.keyboard.press("PageUp")
        time.sleep(0.1)


def click_previous(page):
    try:
        left_arrow = page.locator('button[aria-label="Previous"]').first
        if left_arrow.count() > 0 and left_arrow.is_visible() and not left_arrow.is_disabled():
            left_arrow.click()
            time.sleep(0.2)
            return True
    except:
        pass
    return False


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(USER_DATA_DIR, headless=False)
        page = browser.new_page()
        page.goto("https://web.whatsapp.com")

        print("Waiting for login...")
        search_bar = page.locator('input[aria-label]')
        search_bar.wait_for(state="visible", timeout=0)
        print("Logged in!")

        for group in GROUPS:
            print(f"\n--- {group} ---")

            folder = ensure_folder(group)

            # 🔑 Load existing hashes
            existing_hashes = load_existing_hashes(folder)

            if existing_hashes:
                print(f"[i] Loaded {len(existing_hashes)} existing images")
            else:
                print("[i] No previous downloads found")

            # Search group
            search_bar.scroll_into_view_if_needed()
            search_bar.click()
            search_bar.fill("")
            time.sleep(0.3)
            search_bar.type(group, delay=100)
            time.sleep(2)

            chat = page.locator(f'span[title="{group}"]')
            if chat.count() == 0:
                print("[!] Group not found")
                continue

            chat.first.click()
            time.sleep(1)

            # Open media panel
            header_button = page.locator('div[title="Profile details"]').first
            header_button.click()
            time.sleep(1)

            media_tab = page.locator('div[role="button"]:has-text("Media")').first
            media_tab.click()
            time.sleep(2)

            # Open first image
            first_image = page.locator('div.x1xsqp64').first
            if first_image.count() == 0:
                print("[!] No images found in this group")
                continue

            first_image.click()
            time.sleep(1)

            downloaded_count = 0
            previous_src = None

            while True:
                try:
                    img = page.locator('img[draggable="true"]').first
                    src = wait_for_new_blob(img, previous_src)

                    if not src:
                        print("[!] No valid image src found, skipping...")
                        if click_previous(page):
                            continue
                        else:
                            print("[i] Cannot move further. Exiting modal.")
                            break

                    previous_src = src

                    # Fetch image data
                    try:
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
                                } catch {
                                    return null;
                                }
                            }""",
                            src
                        )
                    except:
                        data_url = None

                    if not data_url:
                        print("[!] Failed to fetch image data, skipping...")
                    else:
                        try:
                            header, encoded = data_url.split(",", 1)
                            data = base64.b64decode(encoded)
                        except:
                            print("[!] Failed to decode image")
                            data = None

                        if data:
                            img_hash = hash_bytes(data)

                            # 🛑 STOP when hitting old images
                            if img_hash in existing_hashes:
                                print("[i] Found already-downloaded image. Stopping.")
                                break

                            # 💾 Save new image
                            filename = f"{int(time.time() * 1000)}.jpg"
                            filepath = os.path.join(folder, filename)

                            with open(filepath, "wb") as f:
                                f.write(data)

                            existing_hashes.add(img_hash)
                            downloaded_count += 1

                            print(f"[✓] Saved image #{downloaded_count}")

                    # 🛑 Safety cap
                    if downloaded_count >= MAX_IMAGES_IF_NO_LAST:
                        print(f"[i] Reached safety cap ({MAX_IMAGES_IF_NO_LAST}). Stopping.")
                        break

                    # Move to next image
                    if not click_previous(page):
                        print("[i] Reached the first image. Exiting modal.")
                        break

                except Exception as e:
                    print(f"[!] Error navigating/saving images: {e}")
                    if click_previous(page):
                        continue
                    break

            # Close modal
            try:
                close_btn = page.locator('span[aria-hidden="true"][data-icon="ic-close"]').first
                close_btn.click()
                time.sleep(0.5)
            except:
                pass

            # Reset search
            search_bar.click()
            search_bar.fill("")

        print("\nDone. Waiting 10s before closing...")
        time.sleep(10)
        browser.close()


if __name__ == "__main__":
    run()