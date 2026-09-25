"""Download pinned official llama.cpp and Liquid weights into this directory."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parent
REV = '36fc16bc95133424921bcc3da009e83b2f23ffb5'
REPO = 'LiquidAI/LFM2.5-VL-1.6B-GGUF'
VERSION = 'b11191'
ARCHIVE = f'llama-{VERSION}-bin-macos-arm64.tar.gz'

def download(url, target, expected=None):
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        temporary = target.with_suffix(target.suffix + '.part')
        with urllib.request.urlopen(url, timeout=120) as source, temporary.open('wb') as out:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
        temporary.rename(target)
    digest = hashlib.sha256()
    with target.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    actual = digest.hexdigest()
    if expected and actual != expected:
        raise RuntimeError(f'Checksum mismatch: {target.name}')
    print(f'Verified {target.name}: {target.stat().st_size:,} bytes', flush=True)
    return {'file': str(target.relative_to(ROOT)), 'url': url, 'sha256': actual,
            'bytes': target.stat().st_size, 'publisher_checksum_verified': bool(expected)}

def main():
    tree_url = f'https://huggingface.co/api/models/{REPO}/tree/{REV}?recursive=false'
    tree = json.load(urllib.request.urlopen(tree_url, timeout=30))
    files = ['LFM2.5-VL-1.6B-Q4_K_M.gguf', 'mmproj-LFM2.5-VL-1.6b-Q8_0.gguf']
    tasks = [(f'https://github.com/ggml-org/llama.cpp/releases/download/{VERSION}/{ARCHIVE}',
              ROOT / 'downloads' / ARCHIVE,
              '18a5342183b0f4bad7290195b64b4efdcb577917d187ff5955127f2117afe77b')]
    for name in files:
        entry = next(x for x in tree if x['path'] == name)
        tasks.append((f'https://huggingface.co/{REPO}/resolve/{REV}/{name}',
                      ROOT / 'models' / name, entry['lfs']['oid']))
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        records = list(pool.map(lambda args: download(*args), tasks))
    runtime = ROOT / 'runtime'
    runtime.mkdir(exist_ok=True)
    subprocess.run(['tar', '-xzf', str(ROOT / 'downloads' / ARCHIVE), '-C', str(runtime)], check=True)
    download(f'https://huggingface.co/{REPO}/resolve/{REV}/LICENSE', ROOT / 'models' / 'LICENSE')
    (ROOT / 'installation.json').write_text(json.dumps({'runtime_version': VERSION,
        'model_repo': REPO, 'model_revision': REV, 'artifacts': records}, indent=2) + '\n')

if __name__ == '__main__':
    main()
