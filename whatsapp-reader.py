import os
import time
import base64
from playwright.sync_api import sync_playwright
DOWNLOAD_DIR = "downloads"
USER_DATA_DIR = "data"

from dotenv import load_dotenv
load_dotenv()
GROUPS = [
    g.strip()
    for g in os.getenv("WHATSAPP_GROUPS", "").split(",")
    if g.strip()
]

def ensure_folder(name):
    safe = "".join(c for c in name if c.isalnum() or c in " _-")
    path = os.path.join(DOWNLOAD_DIR, safe)
    os.makedirs(path, exist_ok=True)
    return path


def save_base64_image(data_url, folder):
    header, encoded = data_url.split(",", 1)
    data = base64.b64decode(encoded)

    filename = f"{int(time.time()*1000)}.jpg"
    with open(os.path.join(folder, filename), "wb") as f:
        f.write(data)


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            USER_DATA_DIR,
            headless=False
        )

        page = browser.new_page()
        page.goto("https://web.whatsapp.com")

        print("Waiting for login...")
        page.wait_for_selector('div[role="textbox"]', timeout=0)
        print("Logged in!")

        for group in GROUPS:
            print(f"\n--- {group} ---")

            # Search
            search = page.locator('div[role="textbox"]').first
            search.click()
            search.fill("")
            search.type(group, delay=100)
            time.sleep(2)

            chat = page.locator(f'span[title="{group}"]')
            if chat.count() == 0:
                print("Group not found")
                continue

            chat.first.click()
            time.sleep(3)

            folder = ensure_folder(group)

            # Scroll to load images
            for _ in range(15):
                page.keyboard.press("PageUp")
                time.sleep(1)

            # 🔥 Find image elements
            images = page.locator("img")

            print(f"Found {images.count()} img elements")

            for i in range(images.count()):
                img = images.nth(i)

                try:
                    src = img.get_attribute("src")

                    # Skip icons/emojis
                    if not src or not src.startswith("blob:"):
                        continue

                    # Convert blob → base64 inside browser
                    data_url = page.evaluate(
                        """async (src) => {
                            const response = await fetch(src);
                            const blob = await response.blob();

                            return await new Promise(resolve => {
                                const reader = new FileReader();
                                reader.onloadend = () => resolve(reader.result);
                                reader.readAsDataURL(blob);
                            });
                        }""",
                        src
                    )

                    save_base64_image(data_url, folder)
                    print("[✓] Saved image")

                except Exception as e:
                    print("Error:", e)

        print("Done. Waiting before closing...")
        time.sleep(20)
        browser.close()


if __name__ == "__main__":
    run()