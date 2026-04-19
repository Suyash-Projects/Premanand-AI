"""
Parallel transcript fetcher for BhajanMarg Ekantik playlists.
Uses ThreadPoolExecutor for ~10x speedup on I/O-bound fetching.
"""
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

CHANNEL_URL = "https://www.youtube.com/@BhajanMarg"
OUTPUT_DIR = "transcripts_raw"
MAX_WORKERS = 10  # parallel threads

# Thread-safe counters
lock = threading.Lock()
stats = {"saved": 0, "failed": 0, "skipped": 0, "total_bytes": 0}

def get_ekantik_playlists():
    print("Scanning channel for Ekantik playlists...")
    url = CHANNEL_URL + "/playlists"
    opts = {'extract_flat': True, 'quiet': True, 'ignoreerrors': True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        result = ydl.extract_info(url, download=False)
        playlists = []
        if result and 'entries' in result:
            for entry in result['entries']:
                if entry and re.search(r'ekantik', entry.get('title',''), re.IGNORECASE):
                    playlists.append({
                        'id': entry.get('id', ''),
                        'title': entry.get('title', ''),
                        'url': entry.get('url', ''),
                    })
        return playlists

def get_videos_from_playlist(playlist):
    opts = {'extract_flat': True, 'quiet': True, 'ignoreerrors': True}
    playlist_url = playlist.get('url', f"https://www.youtube.com/playlist?list={playlist['id']}")
    with yt_dlp.YoutubeDL(opts) as ydl:
        result = ydl.extract_info(playlist_url, download=False)
        videos = []
        if result and 'entries' in result:
            for entry in result['entries']:
                if entry and entry.get('id'):
                    videos.append({
                        'id': entry['id'],
                        'title': entry.get('title', 'Unknown'),
                        'playlist': playlist['title'],
                    })
        return videos

def fetch_single_video(video):
    """Worker function: fetch transcript for one video."""
    vid_id = video['id']
    title = video['title']
    playlist_name = video['playlist']
    filepath = os.path.join(OUTPUT_DIR, f"{vid_id}.json")
    
    # Skip if cached
    if os.path.exists(filepath):
        size = os.path.getsize(filepath)
        with lock:
            stats["skipped"] += 1
            stats["total_bytes"] += size
        return f"SKIP  {title[:50]}"
    
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(vid_id)
        
        transcript = None
        lang = None
        is_auto = False
        
        # Try Hindi
        try:
            t = transcript_list.find_transcript(['hi'])
            transcript = t.fetch()
            lang = t.language_code
            is_auto = t.is_generated
        except Exception:
            # Try translating any auto-generated to Hindi
            try:
                for t in transcript_list:
                    if t.is_generated:
                        translated = t.translate('hi')
                        transcript = translated.fetch()
                        lang = 'hi-translated'
                        is_auto = True
                        break
            except Exception:
                # Take whatever is available
                try:
                    for t in transcript_list:
                        transcript = t.fetch()
                        lang = t.language_code
                        is_auto = t.is_generated
                        break
                except Exception:
                    pass
        
        if transcript:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump({
                    "video_id": vid_id,
                    "title": title,
                    "playlist": playlist_name,
                    "language": lang,
                    "auto_generated": is_auto,
                    "transcript": transcript
                }, f, ensure_ascii=False)
            
            size = os.path.getsize(filepath)
            with lock:
                stats["saved"] += 1
                stats["total_bytes"] += size
            return f"OK    {title[:50]} ({lang}, {len(transcript)} segs, {size/1024:.0f}KB)"
        else:
            with lock:
                stats["failed"] += 1
            return f"FAIL  {title[:50]}"
            
    except Exception:
        with lock:
            stats["failed"] += 1
        return f"FAIL  {title[:50]}"

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Step 1: Get all Ekantik playlists
    playlists = get_ekantik_playlists()
    print(f"Found {len(playlists)} Ekantik playlists.\n")
    
    # Step 2: Collect ALL videos across all playlists
    print("Collecting video list from all playlists...")
    all_videos = []
    seen_ids = set()
    
    for p in playlists:
        videos = get_videos_from_playlist(p)
        for v in videos:
            if v['id'] not in seen_ids:
                seen_ids.add(v['id'])
                all_videos.append(v)
        print(f"  {p['title']}: {len(videos)} videos")
    
    print(f"\nTotal unique videos to process: {len(all_videos)}")
    print(f"Starting parallel fetch with {MAX_WORKERS} threads...\n")
    
    # Step 3: Parallel fetch
    completed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(fetch_single_video, v): v for v in all_videos}
        
        for future in as_completed(futures):
            completed += 1
            result = future.result()
            print(f"  [{completed}/{len(all_videos)}] {result}")
    
    # Final report
    total_mb = stats["total_bytes"] / (1024 * 1024)
    print(f"\n{'='*60}")
    print(f"  FINAL REPORT")
    print(f"{'='*60}")
    print(f"  Playlists:                 {len(playlists)}")
    print(f"  Total Unique Videos:       {len(all_videos)}")
    print(f"  Saved (with transcript):   {stats['saved']}")
    print(f"  Skipped (already cached):  {stats['skipped']}")
    print(f"  Failed (no transcript):    {stats['failed']}")
    print(f"  Total Size on Disk:        {total_mb:.2f} MB ({stats['total_bytes']:,} bytes)")
    print(f"  Saved to:                  ./{OUTPUT_DIR}/")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
