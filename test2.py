from playwright.sync_api import sync_playwright
import time
def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto('https://www.youtube.com/watch?v=GEUd_p5zrco', wait_until='domcontentloaded')
        time.sleep(2)
        response_json = page.evaluate('window.ytInitialPlayerResponse')
        for track in response_json.get('captions', {}).get('playerCaptionsTracklistRenderer', {}).get('captionTracks', []):
            url = track.get('baseUrl')
            print('Found URL:', url[:100])
            text = page.evaluate(f'''async () => {{
                const res = await fetch("{url}&fmt=json3");
                return await res.text();
            }}''')
            print('Text start:', text[:100])
            break
run()
