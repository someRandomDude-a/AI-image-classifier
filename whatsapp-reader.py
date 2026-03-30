import os
import time
import base64
from playwright.sync_api import sync_playwright

DOWNLOAD_DIR = "downloads"
USER_DATA_DIR = "data"
GROUPS = ["Alina", "Cool people club"]  # Update with your groups
MAX_IMAGES_IF_NO_LAST = 50
SCROLLS_PER_GROUP = 10


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


def wait_for_new_blob(img_element, previous_src=None, timeout=5000):
    """
    Wait until the img element's src attribute changes (new blob).
    """
    start_time = time.time()
    while True:
        src = img_element.get_attribute("src")
        if src and src.startswith("blob:") and src != previous_src:
            return src
        if (time.time() - start_time) * 1000 > timeout:
            return None
        time.sleep(0.1)


def scroll_to_load_images(page, scrolls=SCROLLS_PER_GROUP):
    for _ in range(scrolls):
        page.keyboard.press("PageUp")
        time.sleep(0.1)


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
            last_ts = get_last_downloaded_timestamp(folder)
            if last_ts:
                print(f"[i] Last downloaded timestamp: {last_ts}")
            else:
                print("[i] No previous downloads found")

            # Refocus search bar
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

            # Click group header to open media
            header_button = page.locator('div[title="Profile details"]').first
            header_button.click()
            time.sleep(1)

            # Click "Media" tab
            media_tab = page.locator('div[role="button"]:has-text("Media")').first
            media_tab.click()
            time.sleep(2)

            # Open first image in media gallery
            first_image = page.locator('div.x1xsqp64').first
            first_image.click()
            time.sleep(1)

            # Navigate images in modal and save
            downloaded_count = 0
            previous_src = None

            while True:
                try:
                    img = page.locator('img[draggable="true"]').first
                    src = wait_for_new_blob(img, previous_src)

                    if not src:
                        print("[i] Waiting 3s for more images to load...")
                        time.sleep(3)
                        src = wait_for_new_blob(img, previous_src, timeout=3000)
                        if not src:
                            print("[i] End of images. Exiting modal.")
                            break

                    previous_src = src

                    # Save image
                    data_url = page.evaluate(
                        """async (src) => {
                            const res = await fetch(src);
                            const blob = await res.blob();
                            return await new Promise(resolve => {
                                const reader = new FileReader();
                                reader.onloadend = () => resolve(reader.result);
                                reader.readAsDataURL(blob);
                            });
                        }""",
                        src
                    )
                    if data_url:
                        save_base64_image(data_url, folder)
                        downloaded_count += 1
                        print(f"[✓] Saved image #{downloaded_count}")

                    if not last_ts and downloaded_count >= MAX_IMAGES_IF_NO_LAST:
                        print(f"[i] Reached {MAX_IMAGES_IF_NO_LAST} images. Stopping.")
                        break

                    # Click left arrow to go to previous image
                    left_arrow = page.locator('button[aria-label="Previous"]').first
                    if left_arrow.count() == 0 or not left_arrow.is_visible() or left_arrow.is_disabled():
                        print("[i] Reached the first image in the chat. Exiting modal.")
                        break

                    left_arrow.click()
                    time.sleep(0.1)

                except Exception as e:
                    print(f"[!] Error navigating/saving images: {e}")
                    break

            # Close modal after finishing images
            try:
                close_btn = page.locator('span[aria-hidden="true"][data-icon="ic-close"]').first
                close_btn.click()
                time.sleep(0.5)
            except:
                pass

            # Go back to search bar for next group
            search_bar.click()
            search_bar.fill("")

        print("\nDone. Waiting 10s before closing...")
        time.sleep(10)
        browser.close()


if __name__ == "__main__":
    run()