"""Quick debug: check what transcripts are available on Ekantik videos."""
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi

# Get first video from an older Ekantik playlist
url = 'https://www.youtube.com/@BhajanMarg/playlists'
opts = {'extract_flat': True, 'quiet': True, 'ignoreerrors': True}

print("=== PLAYLISTS ===")
with yt_dlp.YoutubeDL(opts) as ydl:
    r = ydl.extract_info(url, download=False)
    ekantik = []
    for e in r['entries']:
        if e and 'ekantik' in e.get('title','').lower():
            ekantik.append(e)
            print(f"  {e['title']}  |  {e['id']}")

# Pick the OLDEST ekantik playlist (likely to have transcripts)
if ekantik:
    oldest = ekantik[-1]
    print(f"\nChecking oldest playlist: {oldest['title']}")
    playlist_url = oldest.get('url', f"https://www.youtube.com/playlist?list={oldest['id']}")
    
    with yt_dlp.YoutubeDL(opts) as ydl:
        r2 = ydl.extract_info(playlist_url, download=False)
        if r2 and 'entries' in r2:
            # Check first 3 videos
            for v in r2['entries'][:3]:
                if v:
                    vid_id = v['id']
                    print(f"\n--- Video: {v.get('title','')} ({vid_id}) ---")
                    try:
                        transcripts = YouTubeTranscriptApi.list_transcripts(vid_id)
                        for t in transcripts:
                            print(f"  Language: {t.language} ({t.language_code}), auto-generated: {t.is_generated}")
                    except Exception as ex:
                        print(f"  ERROR: {ex}")
