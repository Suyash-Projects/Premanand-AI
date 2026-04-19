from playwright.sync_api import sync_playwright
import time

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto('https://www.youtube.com/watch?v=GEUd_p5zrco', wait_until='domcontentloaded')
        time.sleep(2)
        response_json = page.evaluate('window.ytInitialPlayerResponse')
        captions = response_json.get('captions', {})
        player_captions_tracklist = captions.get('playerCaptionsTracklistRenderer', {})
        caption_tracks = player_captions_tracklist.get('captionTracks', [])
        
        for track in caption_tracks:
            url = track.get('baseUrl')
            lang = track.get('languageCode')
            if 'hi' in lang or 'en' in lang:
                print('Found track:', lang)
                # Fetch securely inside the Chromium browser's exact network session
                raw = page.evaluate(f'''async () => {{
                    const res = await fetch("{url}&fmt=json3");
                    return await res.json();
                }}''')
                events = len(raw.get('events', []))
                print(f'Downloaded {events} events successfully via fully stealth Playwright bypass!')
                print('First segment text:', raw['events'][0]['segs'][0]['utf8'])
                break
        
        browser.close()

run()
