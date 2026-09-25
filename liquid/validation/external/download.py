#!/usr/bin/env python3
"""Fixed-seed, source-label-only external apple sample; HTTP ZIP ranges."""
import concurrent.futures
import datetime
import hashlib
import json
from pathlib import Path
import random
import struct
import subprocess
import tempfile
import zlib

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
URL = 'https://data.mendeley.com/public-files/datasets/bdd69gyhv8/files/de93ba06-6a58-45e3-913d-837b2ae52acb/file_downloaded'
SEED = 20260925


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(item):
    start = item['offset']
    # Read one local header plus exactly the advertised compressed payload;
    # 1024 bytes accommodates ZIP local extra fields without downloading archive.
    end = start + 30 + len(item['path'].encode()) + 1024 + item['compressed'] - 1
    with tempfile.TemporaryDirectory() as temporary:
        data_path = Path(temporary)/'part.bin'
        header_path = Path(temporary)/'headers.txt'
        subprocess.run(['curl','-L','--range',f'{start}-{end}','--max-time','60',
                        '--max-filesize',str(end-start+1),'--fail','--silent','--show-error',
                        '-D',str(header_path),URL,'-o',str(data_path)],check=True)
        headers = header_path.read_text().lower()
        assert f'content-range: bytes {start}-' in headers, 'Server did not honor range'
        b = data_path.read_bytes()
    assert len(b) <= end - start + 1
    f = struct.unpack_from('<4s5H3L2H', b)
    assert f[0] == b'PK\x03\x04' and f[3] == 8
    name = b[30:30+f[9]].decode()
    assert name == item['path']
    begin = 30 + f[9] + f[10]
    compressed = b[begin:begin+item['compressed']]
    raw = zlib.decompress(compressed, -15)
    assert len(raw) == item['uncompressed']
    assert zlib.crc32(raw) == item['crc32']
    label = 'healthy' if '/FreshApple/' in name else 'infected'
    original_label = 'FreshApple' if label == 'healthy' else 'RottenApple'
    filename = original_label + '_' + hashlib.sha256(name.encode()).hexdigest()[:12] + '.jpg'
    destination = OUT / 'data' / label / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw)
    return {'path': str(destination.relative_to(ROOT)), 'source_label': label,
            'original_label': original_label, 'archive_path': name,
            'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
            'compressed_bytes': item['compressed'], 'range_start': start, 'range_end': end}


def main():
    index = json.loads((ROOT/'liquid/validation/source_research/bdd69gyhv8_full_index.json').read_text())
    rng = random.Random(SEED)
    picks = []
    for category in ('FreshApple', 'RottenApple'):
        pool = sorted([r for r in index if '/'+category+'/' in r['path'] and r['path'].endswith('.jpg')], key=lambda r:r['path'])
        assert len(pool) == 200
        picks.extend(rng.sample(pool, 20))
    # Freeze chosen names before any model result or image inspection.
    (OUT/'selection.json').write_text(json.dumps({'seed':SEED,'selected':picks},indent=2)+'\n')
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        images = list(executor.map(fetch, picks))
    other_files = list((ROOT/'liquid/inputs').glob('*')) + list((ROOT/'liquid/validation/data').rglob('*.jpg'))
    other_hashes = {sha(p) for p in other_files if p.is_file()}
    hashes = [r['sha256'] for r in images]
    assert len(hashes) == len(set(hashes)), 'Duplicate external images'
    assert not (set(hashes) & other_hashes), 'Overlap with primary/smoke data'
    manifest = {
        'status':'frozen_before_inference',
        'frozen_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'purpose':'External static apple visible-quality evaluation; not temporal diagnosis',
        'dataset':{'title':'Fresh and Rotten Fruits Dataset for Machine-Based Evaluation of Fruit Quality',
                   'url':'https://data.mendeley.com/datasets/bdd69gyhv8/1','doi':'10.17632/bdd69gyhv8.1',
                   'authors':['Nusrat Sultana','Musfika Jahan','Mohammad Shorif Uddin'],
                   'license':'CC BY 4.0','license_url':'https://creativecommons.org/licenses/by/4.0/',
                   'download_url':URL,'archive':'Original Image.zip','archive_size':2794170228,
                   'archive_sha256_from_metadata':'f89d67d4c4b24810bcd8406db877db6b1ac9834cea0b0cb56d65acebe59e66ff',
                   'full_archive_checksum_verified':False},
        'sampling':{'seed':SEED,'method':'Uniform sample of 20 names per class from sorted 200 original names, healthy then rotten, Python random.Random',
                    'inference_used_for_selection':False,'same_physical_fruit_ids_known':False},
        'label_mapping':{'FreshApple':'healthy','RottenApple':'infected'},
        'label_note':'infected is compatibility vocabulary only: source means rotten, not pathogen-confirmed infection',
        'deduplication':{'external_unique_sha256':len(set(hashes)), 'compared_primary_and_smoke_files':len(other_files),'exact_overlaps':0,
                         'near_duplicate_or_physical_fruit_overlap_not_tested':True},
        'images':images,
    }
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'count':len(images),'bytes':sum(r['bytes'] for r in images),'compared_files':len(other_files),'manifest':'liquid/validation/external/manifest.json'}))


if __name__ == '__main__':
    main()
