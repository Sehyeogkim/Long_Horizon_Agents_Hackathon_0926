#!/usr/bin/env python3
"""Decode the attributed Fuji apple clip without fabricating disease labels.

Requires imageio, imageio-ffmpeg and numpy. No network or model calls.
"""

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import imageio.v3 as iio
import imageio_ffmpeg
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data/samples/apple_browning_fuji"
SOURCE_SHA1 = "a1c26ff97f57dcd7c32064eb5dc7058a9fd5ec6e"
SOURCE_PAGE = (
    "https://commons.wikimedia.org/wiki/"
    "File:Browning_Fuji_apple_-_32_minutes_in_16_seconds.webm"
)


def main():
    source = SAMPLE / "source.webm"
    if hashlib.sha1(source.read_bytes()).hexdigest() != SOURCE_SHA1:
        raise ValueError("Source changed; reverify timing and attribution first")
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    # Preserve decoded source frames: no fps filter, interpolation or resampling.
    with tempfile.TemporaryDirectory(prefix="apple-frames-") as temporary:
        temp = Path(temporary)
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", str(source), "-map", "0:v:0",
             "-fps_mode", "passthrough", "-start_number", "0",
             str(temp / "frame_%03d.png")],
            capture_output=True, text=True, check=True,
        )
        if "600x600" not in result.stderr or "2 fps" not in result.stderr:
            raise ValueError("Unexpected source dimensions or frame rate")
        files = sorted(temp.glob("frame_*.png"))
        if len(files) != 32:
            raise ValueError(f"Expected 32 original frames, decoded {len(files)}")
        arrays = [iio.imread(path) for path in files]
        if any(array.shape != (600, 600, 3) for array in arrays):
            raise ValueError("Unexpected decoded image dimensions")
        difference = float(np.abs(arrays[-1].astype(float) - arrays[0]).mean())
        if difference == 0:
            raise ValueError("First and last frames are identical")
        destination = SAMPLE / "frames"
        destination.mkdir(exist_ok=True)
        expected = {path.name for path in files}
        unexpected = {path.name for path in destination.iterdir()} - expected
        if unexpected:
            raise ValueError(f"Unexpected destination files: {sorted(unexpected)}")
        observations = []
        for index, frame in enumerate(files):
            target = destination / frame.name
            target.write_bytes(frame.read_bytes())
            observations.append({
                "dataset_id": "wikimedia_fuji_browning_2017",
                "sequence_id": "fuji_cut_browning_001",
                "entity_id": "fuji_apple_001",
                "observation_id": f"fuji_cut_browning_001_{index:03d}",
                "source_frame_index": index,
                "source_video_seconds": index / 2,
                "elapsed_seconds": index * 60,
                "observed_at": None,
                "time_basis": "relative to first source photo; author reports 1-minute intervals",
                "frame_uri": target.relative_to(ROOT).as_posix(),
                "frame_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "state": {},
                "disease_label": None,
                "label_available_at": None,
                "synthetic": False,
                "phenomenon": "cut-apple oxidation/browning, not confirmed disease",
                "source_page": SOURCE_PAGE,
                "license": "CC BY-SA 4.0",
                "attribution": "Vassia Atanassova - Spiritia",
                "transformation": "source video decoded to PNG; no interpolation",
            })
        manifest = SAMPLE / "observations.jsonl"
        manifest.write_text("".join(json.dumps(row) + "\n" for row in observations))
        print(json.dumps({
            "decoded_frames": len(files), "dimensions": [600, 600, 3],
            "first_last_mean_absolute_rgb_difference": difference,
            "first_elapsed_seconds": 0, "last_elapsed_seconds": 1860,
            "manifest": manifest.relative_to(ROOT).as_posix(),
        }))


if __name__ == "__main__":
    main()
