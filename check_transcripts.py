import os, json, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

folder = 'transcripts_raw'
files = sorted(os.listdir(folder))
print(f'Total files: {len(files)}')

empty = 0
good = 0
total_segs = 0

for f in files:
    path = os.path.join(folder, f)
    size = os.path.getsize(path)
    with open(path, 'r', encoding='utf-8') as fh:
        data = json.load(fh)
    segs = len(data.get('transcript', []))
    title = data.get('title', '?')[:50]
    lang = data.get('language', '?')
    
    if segs == 0:
        empty += 1
        print(f'  EMPTY: {f} ({size} bytes)')
    else:
        good += 1
        total_segs += segs
        sample = data['transcript'][0]['text'][:40]
        print(f'  OK: {f} | {segs} segs | {lang} | {size/1024:.0f}KB | {sample}')

print(f'\n=== SUMMARY ===')
print(f'Total files: {len(files)}')
print(f'With content: {good}')
print(f'Empty: {empty}')
print(f'Total segments: {total_segs}')
total_bytes = sum(os.path.getsize(os.path.join(folder, f)) for f in files)
print(f'Total size: {total_bytes/1024/1024:.2f} MB')
