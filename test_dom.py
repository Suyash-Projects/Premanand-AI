from playwright.sync_api import sync_playwright
import time

def run():
    print("Launching Chromium...")
    with sync_playwright() as p:
        # Run headed to appear as a real human
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        print("Navigating to video...")
        page.goto('https://www.youtube.com/watch?v=GEUd_p5zrco', wait_until='load')
        
        # Wait a few seconds for page to settle
        time.sleep(3)
        
        # Try to find and click the "description" expand button first to reveal the transcript button
        try:
            page.click("tp-yt-paper-button#expand", timeout=5000)
            print("Clicked expand description...")
            time.sleep(1)
        except Exception as e:
            print("No expand button found or needed.")

        # Click "Show transcript" button
        try:
            page.locator("button.yt-spec-button-shape-next[aria-label='Show transcript']").click(timeout=5000)
            print("Clicked 'Show transcript'...")
        except Exception:
            try:
                # Alternate selector
                page.click("ytd-button-renderer.ytd-transcript-search-panel-renderer button", timeout=5000)
                print("Clicked alternate transcript button...")
            except Exception as e:
                print("Could not click transcript button:", e)
        
        # Wait for transcript segments to populate
        print("Waiting for transcript panel...")
        try:
            page.wait_for_selector("ytd-transcript-segment-renderer", timeout=10000)
            segments = page.locator("ytd-transcript-segment-renderer").all()
            print(f"BINGO! Found {len(segments)} transcript segments explicitly rendered on screen!")
            
            if len(segments) > 0:
                print("First line:", segments[0].locator(".segment-text").inner_text().replace('\n', ' '))
                print("Second line:", segments[1].locator(".segment-text").inner_text().replace('\n', ' '))
        except Exception as e:
            print("Failed to find transcript segments:", e)
            
        print("Closing browser...")
        browser.close()

run()
