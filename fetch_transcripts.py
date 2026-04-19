"""
Automated batch transcript fetcher.
Fetches in small batches with concurrent threading to speed up extraction!
Re-run safe: skips already downloaded files.
"""
import yt_dlp
import json
import os
import re
import sys
import time
import concurrent.futures

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

CHANNEL_URL = "https://www.youtube.com/@BhajanMarg"
OUTPUT_DIR = "transcripts_raw"
VIDEO_LIST_CACHE = "video_list_cache.json"
BATCH_SIZE = 1         # fetch 1 by 1 sequentially to avoid setting off alarms
COOLDOWN_BETWEEN_VIDEOS = (3, 7) # random seconds between videos
COOLDOWN_ON_BAN = 300  # 5 min sleep if 429 triggered

def load_video_list():
    """Load cached video list or fetch fresh from YouTube."""
    if os.path.exists(VIDEO_LIST_CACHE):
        with open(VIDEO_LIST_CACHE, 'r', encoding='utf-8') as f:
            videos = json.load(f)
        return videos
    return []

def fetch_transcript_worker(v):
    """Fetch auto-generated Hindi subtitles for one video."""
    vid_id = v['id']
    opts = {
        'quiet': True,
        'ignoreerrors': True,
        'allow_unplayable_formats': True,
        'dynamic_mpd': False,
        'remote_components': ['ejs:github'],
        'lazy_playlist': True,
    }
    if os.path.exists('cookies.txt'):
        opts['cookiefile'] = 'cookies.txt'
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid_id}", download=False)
        
        if not info:
            return v, None, None
        
        auto_subs = info.get('automatic_captions', {})
        manual_subs = info.get('subtitles', {})
        
        sub_data = None
        lang_used = None
        for lang in ['hi', 'en']:
            if lang in manual_subs:
                for fmt in manual_subs[lang]:
                    if fmt.get('ext') == 'json3':
                        sub_data = fmt
                        lang_used = f"{lang}-manual"
                        break
            if sub_data: break
            if lang in auto_subs:
                for fmt in auto_subs[lang]:
                    if fmt.get('ext') == 'json3':
                        sub_data = fmt
                        lang_used = f"{lang}-auto"
                        break
            if sub_data: break
        
        if sub_data and sub_data.get('url'):
            import urllib.request
            req = urllib.request.Request(sub_data['url'])
            with urllib.request.urlopen(req, timeout=15) as response:
                raw = json.loads(response.read().decode('utf-8'))
            
            transcript = []
            if 'events' in raw:
                for event in raw['events']:
                    if 'segs' in event:
                        text = ''.join(seg.get('utf8', '') for seg in event['segs']).strip()
                        if text and text != '\n':
                            transcript.append({
                                'start': event.get('tStartMs', 0) / 1000,
                                'duration': event.get('dDurationMs', 0) / 1000,
                                'text': text
                            })
            return v, transcript, lang_used
    except Exception as e:
        if '429' in str(e) or 'bot' in str(e).lower() or 'challenge' in str(e).lower():
            return v, "RATE_LIMITED", None
    return v, "NO_TRANSCRIPT", None

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    all_videos = load_video_list()
    if not all_videos:
        print("Need to run old fetcher first to build video list cache!")
        return
        
    # Filter out already downloaded
    remaining = [v for v in all_videos if not os.path.exists(os.path.join(OUTPUT_DIR, f"{v['id']}.json"))]
    already = len(all_videos) - len(remaining)
    
    print(f"Total videos: {len(all_videos)}")
    print(f"Already downloaded: {already}")
    print(f"Remaining: {len(remaining)}")
    print(f"Fetch Mode: Sequential | Cooldown Range: {COOLDOWN_BETWEEN_VIDEOS}s")
    print("="*60 + "\n")
    
    import random
    
    saved_this_run = 0
    failed_this_run = 0
    
    print(f"Resuming autonomous scraping loop for {len(remaining)} remaining videos...")
    
    while remaining:
        v = remaining.pop(0)
        title = v['title'][:50]
        vid_id = v['id']
        
        # Add random human-like delay
        delay = random.uniform(*COOLDOWN_BETWEEN_VIDEOS)
        print(f"Sleeping {delay:.1f}s before fetching...")
        time.sleep(delay)
        
        _, transcript, lang = fetch_transcript_worker(v)
        
        if transcript == "RATE_LIMITED":
            print(f"  [RATE LIMITED] {title}")
            print(f"  ** IP soft-banned. Sleeping for {COOLDOWN_ON_BAN // 60} minutes and resuming completely automatically! **")
            time.sleep(COOLDOWN_ON_BAN)
            remaining.insert(0, v) # Put it back in queue to try again
            continue
            
        elif transcript == "NO_TRANSCRIPT":
            print(f"  [NO TRANSCRIPT] {title}")
            failed_this_run += 1
            
        elif isinstance(transcript, list) and len(transcript) > 0:
            filepath = os.path.join(OUTPUT_DIR, f"{vid_id}.json")
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump({
                    "video_id": vid_id,
                    "title": v['title'],
                    "playlist": v['playlist'],
                    "language": lang,
                    "segments": len(transcript),
                    "transcript": transcript
                }, f, ensure_ascii=False)
            size = os.path.getsize(filepath)
            saved_this_run += 1
            print(f"  [OK] {title} ({lang}, {len(transcript)} segs, {size/1024:.0f}KB)")
        else:
            print(f"  [FAILED] {title}")
            failed_this_run += 1
    
    # Final report
    print(f"\n{'='*60}")
    print(f"  RUN COMPLETE")
    print(f"{'='*60}")
    print(f"  New downloads this run:  {saved_this_run}")
    print(f"  Failed this run:         {failed_this_run}")
    
    total_files = len(os.listdir(OUTPUT_DIR))
    print(f"  Total files on disk:     {total_files} / {len(all_videos)}")

if __name__ == '__main__':
    main()
