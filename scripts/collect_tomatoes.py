#!/usr/bin/env python3
"""Acquire the pinned, CC BY 4.0 18-day tomato sequence and verify checksums."""
import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'data/catalog/tomato'
DEST = ROOT / 'data/samples/tomato_18day'
RECORD_URL = 'https://zenodo.org/api/records/21943147'
MAX_TOTAL_BYTES = 100 * 1024 * 1024


def fetch(url, limit):
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'TomatoResearchDataCollector/1.0'})
            with urllib.request.urlopen(req, timeout=30) as response:
                body = response.read(limit + 1)
            if len(body) > limit:
                raise ValueError('response exceeds byte limit')
            return body
        except (urllib.error.URLError, TimeoutError):
            if attempt == 1:
                raise
            time.sleep(1)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')


def acquire_file(file):
    name = file['key']
    destination = DEST / ('frames' if name.startswith('RGB_') else 'source') / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    expected_md5 = file['checksum'].removeprefix('md5:')
    data = destination.read_bytes() if destination.exists() else b''
    if len(data) != file['size'] or hashlib.md5(data).hexdigest() != expected_md5:
        data = fetch(file['links']['self'], file['size'])
        if len(data) != file['size'] or hashlib.md5(data).hexdigest() != expected_md5:
            raise ValueError('size/checksum mismatch for ' + name)
        destination.write_bytes(data)
    return {'filename': name, 'source_url': file['links']['self'],
            'local_path': str(destination.relative_to(ROOT)), 'bytes': len(data),
            'md5': expected_md5, 'source_md5_verified': True,
            'sha256': hashlib.sha256(data).hexdigest()}


def read_environment(path):
    """Read original raw cells only; never use workbook correlation formulas."""
    ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        sheets = workbook.find('s:sheets', ns)
        sheet = next(s for s in sheets if s.attrib['name'] == 'Environment_Context')
        rid = sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
        rels = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        target = next(r.attrib['Target'] for r in rels if r.attrib['Id'] == rid)
        target = target.lstrip('/') if target.startswith('/') else 'xl/' + target
        tree = ET.fromstring(archive.read(target))
        shared = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            shared = [''.join(n.itertext()) for n in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
        cells = {}
        for cell in tree.findall('.//s:c', ns):
            kind = cell.attrib.get('t')
            node = cell.find('s:v', ns)
            if kind == 'inlineStr':
                value = ''.join(cell.find('s:is', ns).itertext())
            elif node is None:
                continue
            elif kind == 's':
                value = shared[int(node.text)]
            elif kind in ('str', 'e'):
                value = node.text
            else:
                value = float(node.text)
            cells[cell.attrib['r']] = value
    headers = [cells.get(column + '3') for column in 'ABCDE']
    assert headers == ['Day', 'Temperature_C', 'RelativeHumidity_pct', 'eCO2_ppm', 'TVOC_ppb']
    state = {}
    for row in range(4, 22):
        values = [cells[column + str(row)] for column in 'ABCDE']
        assert all(isinstance(v, (int, float)) for v in values)
        day = int(values[0])
        assert day not in state and values[0] == day
        state[day] = dict(zip(['storage_day', 'temperature_c', 'relative_humidity_pct', 'eco2_ppm', 'tvoc_ppb'], [day] + values[1:]))
    assert set(state) == set(range(1, 19))
    return state


def create_manifest(acquired):
    state = read_environment(DEST / 'source/Tomato_RGB_UV_Data_Availability.xlsx')
    observations = []
    for file in acquired:
        match = re.fullmatch(r'RGB_(\d{2})\.png', file['filename'])
        if not match:
            continue
        day = int(match.group(1))
        observations.append({
            'dataset_id': 'zenodo_tomato_18day_21943147', 'dataset_version': '21943147',
            'sequence_id': 'tomato_18day_specimen_01', 'entity_id': 'tomato_01',
            'observation_id': 'tomato_18day_day_%02d' % day,
            'elapsed_seconds': (day - 1) * 86400, 'observed_at': None,
            'frame_uri': file['local_path'], 'frame_sha256': file['sha256'],
            'state': state[day], 'synthetic': False, 'disease_label': None,
            'state_source': {'file': 'data/samples/tomato_18day/source/Tomato_RGB_UV_Data_Availability.xlsx',
                             'sheet': 'Environment_Context', 'range': 'A%d:E%d' % (day + 3, day + 3)},
        })
    observations.sort(key=lambda o: o['elapsed_seconds'])
    assert len(observations) == 18
    (DEST / 'observations.jsonl').write_text(''.join(json.dumps(o, ensure_ascii=False) + '\n' for o in observations))
    write_json(CATALOG / 'environment_raw.json', [{'day': day, **state[day]} for day in sorted(state)])
    return observations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh-metadata', action='store_true')
    args = parser.parse_args()
    metadata_path = CATALOG / 'zenodo_21943147.json'
    if args.refresh_metadata or not metadata_path.exists():
        metadata = json.loads(fetch(RECORD_URL, 1024 * 1024))
        write_json(metadata_path, metadata)
    else:
        metadata = json.loads(metadata_path.read_text())
    assert metadata['id'] == 21943147
    assert metadata['metadata']['license']['id'] == 'cc-by-4.0'
    files = [f for f in metadata['files'] if re.fullmatch(r'RGB_\d{2}\.png', f['key']) or f['key'] == 'Tomato_RGB_UV_Data_Availability.xlsx']
    assert {f['key'] for f in files if f['key'].startswith('RGB_')} == {'RGB_%02d.png' % day for day in range(1, 19)}
    assert sum(f['size'] for f in files) < MAX_TOTAL_BYTES
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        acquired = sorted(pool.map(acquire_file, files), key=lambda f: f['filename'])
    observations = create_manifest(acquired)
    provenance = {
        'dataset_id': 'zenodo_tomato_18day_21943147', 'dataset_version': '21943147',
        'source_page': 'https://zenodo.org/records/21943147', 'doi': metadata['doi'],
        'title': metadata['metadata']['title'], 'author': metadata['metadata']['creators'],
        'license': 'CC BY 4.0', 'license_url': 'https://creativecommons.org/licenses/by/4.0/',
        'retrieved_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'metadata_transport': 'Zenodo public API', 'binary_transport': 'HTTPS urllib',
        'files': acquired, 'biological_specimens': 1, 'days': 18,
        'disease_labels_available': False, 'synthetic': False,
        'timing': 'Relative storage day; day 1 maps to 0 seconds. Absolute acquisition times unknown.',
        'state_source': 'Environment_Context!A4:E21, joined by exact Day index to RGB_01..18',
        'state_caveats': ['eCO2 is SGP30 equivalent CO2, not a reference-grade direct CO2 measurement.',
                          'TVOC is SGP30 sensor output; all environmental values are contextual metadata.',
                          'Workbook has cached #NAME? cells in derived correlation sheets; those cells were not imported.'],
        'nimble_metadata_evidence': 'data/catalog/tomato/nimble/20260925T215658529501Z/request_00.json',
        'limitations': ['Single biological specimen, not 18 independent specimens.',
                        'Appearance and UV texture changes are not direct freshness, infection, or physicochemical measurements.'],
    }
    write_json(DEST / 'provenance.json', provenance)
    print(json.dumps({'acquired_files': len(acquired), 'total_bytes': sum(f['bytes'] for f in acquired),
                      'all_source_md5_verified': True, 'observations': len(observations),
                      'manifest': str((DEST / 'observations.jsonl').relative_to(ROOT))}))


if __name__ == '__main__':
    main()
