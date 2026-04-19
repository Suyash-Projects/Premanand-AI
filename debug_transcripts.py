import yt_dlp

opts = {'quiet': True}
with yt_dlp.YoutubeDL(opts) as ydl:
    info = ydl.extract_info('https://www.youtube.com/watch?v=TytCVbM3G5Y', download=False)
    subs = info.get('subtitles', {})
    auto_subs = info.get('automatic_captions', {})
    print(f"Manual subtitle languages: {list(subs.keys())[:15]}")
    print(f"Auto-caption languages: {list(auto_subs.keys())[:15]}")
    print(f"Total auto-caption langs: {len(auto_subs)}")
    if 'hi' in auto_subs:
        print("Hindi auto-captions AVAILABLE!")
        print(f"Formats: {[f['ext'] for f in auto_subs['hi']]}")
    elif auto_subs:
        first_lang = list(auto_subs.keys())[0]
        print(f"First available auto lang: {first_lang}")
