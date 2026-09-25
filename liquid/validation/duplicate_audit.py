#!/usr/bin/env python3
"""CPU-only duplicate indicators for frozen validation manifests; never read model outputs."""
import collections
import datetime
import hashlib
import itertools
import json
from pathlib import Path
import platform
import time

from PIL import Image, ImageOps, __version__ as PILLOW_VERSION

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
INPUTS = {'primary': HERE / 'manifest.json', 'external': HERE / 'external/manifest.json'}
THRESHOLD = 3


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def dhash(path):
    # Decode one image at a time, using libjpeg's reduced-resolution decode.
    with Image.open(path) as original:
        size = list(original.size)
        original.draft('RGB', (512, 512))
        with ImageOps.exif_transpose(original) as oriented:
            with oriented.convert('L') as gray:
                with gray.resize((9, 8), Image.Resampling.LANCZOS) as small:
                    pixels = list(small.getdata())
    result = 0
    for row in range(8):
        for column in range(8):
            result = (result << 1) | (pixels[row * 9 + column] > pixels[row * 9 + column + 1])
    return result, size


def components(records, pairs):
    parent = list(range(len(records)))
    def find(node):
        while node != parent[node]:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node
    for pair in pairs:
        left, right = find(pair['left_index']), find(pair['right_index'])
        parent[left] = right
    groups = collections.defaultdict(list)
    for index, record in enumerate(records):
        groups[find(index)].append(record['id'])
    return sorted((members for members in groups.values() if len(members) > 1), key=lambda value: (-len(value), value))


def summary(records, pairs):
    groups = components(records, pairs)
    segments = collections.Counter()
    label_segments = collections.Counter()
    distance_counts = collections.Counter()
    affected = set()
    for pair in pairs:
        left, right = records[pair['left_index']], records[pair['right_index']]
        segment = f"within_{left['source']}" if left['source'] == right['source'] else 'across_sources'
        segments[segment] += 1
        label_segments['same_label' if left['source_label'] == right['source_label'] else 'different_labels'] += 1
        if 'hamming_distance' in pair:
            distance_counts[str(pair['hamming_distance'])] += 1
        affected.update((pair['left_index'], pair['right_index']))
    return {'pair_count': len(pairs), 'pairs_by_source': {key: segments[key] for key in ['within_primary', 'within_external', 'across_sources']},
            'pairs_by_label_agreement': dict(label_segments), 'hamming_distance_histogram': dict(sorted(distance_counts.items())),
            'affected_image_count': len(affected), 'affected_image_fraction': len(affected) / len(records),
            'affected_images_by_source': dict(collections.Counter(records[index]['source'] for index in affected)),
            'connected_component_count_non_singleton': len(groups),
            'component_sizes': [len(group) for group in groups], 'components': groups}


def main():
    started = time.perf_counter()
    records, manifest_evidence = [], []
    for source, path in INPUTS.items():
        content = path.read_bytes()
        manifest = json.loads(content)
        manifest_evidence.append({'source': source, 'path': str(path.relative_to(ROOT)),
                                  'sha256': hashlib.sha256(content).hexdigest(), 'image_count': len(manifest['images'])})
        for entry in manifest['images']:
            actual = sha256_file(ROOT / entry['path'])
            if actual != entry['sha256']:
                raise ValueError(f"Original no longer matches frozen manifest: {entry['path']}")
            value, dimensions = dhash(ROOT / entry['path'])
            records.append({'id': source + ':' + Path(entry['path']).stem, 'source': source,
                            'source_label': entry['source_label'], 'path': entry['path'], 'sha256': actual,
                            'dhash64_hex': f'{value:016x}', 'original_dimensions': dimensions})
    exact, near = [], []
    for left_index, right_index in itertools.combinations(range(len(records)), 2):
        left, right = records[left_index], records[right_index]
        pair = {'left_index': left_index, 'right_index': right_index, 'left_id': left['id'], 'right_id': right['id']}
        if left['sha256'] == right['sha256']:
            exact.append(pair)
        distance = (int(left['dhash64_hex'], 16) ^ int(right['dhash64_hex'], 16)).bit_count()
        if distance <= THRESHOLD:
            near.append({**pair, 'hamming_distance': distance})
    report = {'created_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'purpose': 'Independent dependence-risk indicators; no inference outputs read and no samples changed.',
              'software': {'python': platform.python_version(), 'pillow': PILLOW_VERSION},
              'method': {'exact': 'SHA256 of full original bytes, verified against frozen source manifest',
                         'perceptual': '64-bit horizontal dHash: Pillow JPEG draft RGB512, EXIF transpose, grayscale, LANCZOS resize9x8, left>right per row; row-major bits',
                         'hamming_threshold': THRESHOLD, 'comparison': 'All unordered pairs; one image decoded at a time on CPU',
                         'components': 'Connected components of candidate-pair graph; transitive links need not meet threshold pairwise'},
              'input_manifests': manifest_evidence, 'image_count': len(records),
              'class_counts_by_source': {source: dict(collections.Counter(record['source_label'] for record in records if record['source'] == source)) for source in INPUTS},
              'compared_pairs': len(records) * (len(records) - 1) // 2,
              'exact_summary': summary(records, exact), 'perceptual_summary': summary(records, near),
              'exact_pairs': exact, 'perceptual_candidate_pairs': near, 'images': records,
              'limitations': ['dHash candidates indicate similar coarse visual structure; not proof of duplicate files or the same physical fruit.',
                              'Backgrounds, viewpoint, illumination, uniform fruit shape, or resizing can create false matches.',
                              'True related views can exceed the threshold; zero matches does not establish independence.',
                              'Fruit identity and capture-session grouping are unavailable; effective independent sample size cannot be inferred from these counts.',
                              'No sample removal or post-output selection was performed; grouped external data is needed for stronger generalization claims.'],
              'elapsed_seconds': time.perf_counter() - started}
    (HERE / 'duplicate_audit.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ['image_count', 'compared_pairs', 'exact_summary', 'perceptual_summary', 'elapsed_seconds']}, indent=2))


if __name__ == '__main__':
    main()
