import json, urllib.request, zipfile, io, os, sys
sys.stdout.reconfigure(encoding='utf-8')

# Download from GitHub
dl_url = 'https://github.com/Chapin-Y/StarDebate/releases/download/v6.4.0/update_v6.3.3_to_v6.4.0.zip'
resp = urllib.request.urlopen(dl_url)
data = resp.read()
print(f'Downloaded: {len(data)} bytes')

# Try every possible way to read the manifest
try:
    z = zipfile.ZipFile(io.BytesIO(data))
    names = z.namelist()
    print(f'Files in zip ({len(names)}): {names[:3]}...')
    
    raw = z.read('manifest.json')
    print(f'Raw manifest bytes: {len(raw)}')
    
    # Check for surrogate characters in raw bytes
    try:
        text = raw.decode('utf-8')
        print('UTF-8 decode: OK')
    except UnicodeDecodeError as e:
        print(f'UTF-8 decode FAILED: {e}')
        # Try with error handling
        text = raw.decode('utf-8', errors='replace')
        print('UTF-8 decode (replace): OK')
    
    # Try JSON parse
    try:
        manifest = json.loads(text)
        print(f'JSON parse: OK')
        print(f'  from: {manifest["from_version"]} -> to: {manifest["to_version"]}')
    except json.JSONDecodeError as e:
        print(f'JSON parse FAILED: {e}')
        print(f'  Around error: {text[max(0,e.pos-40):e.pos+40]}')
    
    # Simulate the exact read_manifest function
    print('\n--- Simulating read_manifest() ---')
    result = read_manifest_sim(data)
    if result:
        print('read_manifest: OK')
    else:
        print('read_manifest: FAILED (returned None)')
        
except Exception as e:
    print(f'Unexpected error: {type(e).__name__}: {e}')

def read_manifest_sim(zip_data):
    """Exact replica of update_utils.read_manifest"""
    import logging
    try:
        with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zf:
            if 'manifest.json' not in zf.namelist():
                print('  manifest.json NOT in namelist!')
                print(f'  namelist = {zf.namelist()}')
                return None
            raw = zf.read('manifest.json').decode('utf-8')
            return json.loads(raw)
    except Exception as e:
        print(f'  Exception: {type(e).__name__}: {e}')
        return None
