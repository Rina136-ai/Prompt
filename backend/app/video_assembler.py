"""ffmpeg-based assembly: fetch generated scene clips, fit them to the real
section timing, concatenate, and mux with the user's original MP3 into a
final downloadable MP4.

Requires the `ffmpeg` binary on PATH. All functions shell out to it rather
than reimplementing video encoding.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from .generators.base import GeneratedAsset

STANDARD_WIDTH = 1280
STANDARD_HEIGHT = 720
STANDARD_FPS = 30


class AssemblyError(RuntimeError):
    pass


def _run_ffmpeg(args: list[str]) -> None:
    result = subprocess.run(["ffmpeg", "-y", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise AssemblyError(f"ffmpeg a echoue: {result.stderr[-2000:]}")


def download_asset(asset: "GeneratedAsset", work_dir: str, basename: str) -> str:
    """Fetches a generated asset to a local file.

    `mock://` URLs (MODE DEMO / MockGenerator) have no real bytes behind
    them -- they're turned into a real, playable placeholder clip that is
    visibly burned with "MODE DEMO", so the assembly pipeline can be
    exercised end to end in tests/dev without a real provider, and so a
    demo output can never be mistaken for a real generation.
    """
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    ext = ".mp4" if asset.kind == "video" else ".png" if asset.kind == "image" else ".bin"
    dest = str(Path(work_dir) / f"{basename}{ext}")

    if asset.url.startswith("mock://"):
        if asset.kind == "video":
            write_demo_placeholder_video(dest, duration_seconds=4.0, label=basename)
        else:
            write_demo_placeholder_image(dest, label=basename)
        return dest

    response = requests.get(asset.url, timeout=180)
    if not response.ok:
        raise AssemblyError(f"Echec du telechargement de l'asset genere ({response.status_code}): {asset.url}")
    with open(dest, "wb") as f:
        f.write(response.content)
    return dest


def write_demo_placeholder_video(output_path: str, duration_seconds: float, label: str = "") -> str:
    text = f"MODE DEMO - {label}".replace("'", "")
    vf = (
        f"drawtext=text='{text}':fontcolor=white:fontsize=36:"
        f"x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=black@0.5:boxborderw=10"
    )
    _run_ffmpeg(
        [
            "-f", "lavfi", "-i", f"color=c=gray:s={STANDARD_WIDTH}x{STANDARD_HEIGHT}:d={duration_seconds}:r={STANDARD_FPS}",
            "-vf", vf,
            "-pix_fmt", "yuv420p",
            output_path,
        ]
    )
    return output_path


def write_demo_placeholder_image(output_path: str, label: str = "") -> str:
    text = f"MODE DEMO - {label}".replace("'", "")
    vf = (
        f"drawtext=text='{text}':fontcolor=white:fontsize=36:"
        f"x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=black@0.5:boxborderw=10"
    )
    _run_ffmpeg(
        ["-f", "lavfi", "-i", f"color=c=gray:s={STANDARD_WIDTH}x{STANDARD_HEIGHT}", "-vf", vf, "-frames:v", "1", output_path]
    )
    return output_path


def fit_clip_to_duration(input_path: str, duration_seconds: float, output_path: str) -> str:
    """Loops/trims a clip to exactly `duration_seconds` and normalizes it to a
    common resolution/fps/codec so concat_clips() can safely stream-copy the
    results together afterwards.
    """
    duration_seconds = max(0.5, duration_seconds)
    vf = f"scale={STANDARD_WIDTH}:{STANDARD_HEIGHT}:force_original_aspect_ratio=decrease,pad={STANDARD_WIDTH}:{STANDARD_HEIGHT}:(ow-iw)/2:(oh-ih)/2,fps={STANDARD_FPS}"
    _run_ffmpeg(
        [
            "-stream_loop", "-1", "-i", input_path,
            "-t", str(duration_seconds),
            "-vf", vf,
            "-an",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            output_path,
        ]
    )
    return output_path


def concat_clips(clip_paths: list[str], output_path: str) -> str:
    if not clip_paths:
        raise AssemblyError("Aucun clip a assembler.")
    concat_list_path = str(Path(output_path).with_suffix(".concat.txt"))
    with open(concat_list_path, "w", encoding="utf-8") as f:
        for path in clip_paths:
            f.write(f"file '{Path(path).resolve()}'\n")
    _run_ffmpeg(["-f", "concat", "-safe", "0", "-i", concat_list_path, "-c", "copy", output_path])
    return output_path


def mux_with_audio(video_path: str, audio_path: str, output_path: str) -> str:
    """Replaces/adds the audio track with the user's original MP3, trimmed to
    the shorter of the two streams (they should already match by construction,
    since scene durations are fit to the real audio section boundaries)."""
    _run_ffmpeg(
        [
            "-i", video_path,
            "-i", audio_path,
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            output_path,
        ]
    )
    return output_path


def crop_to_vertical(input_path: str, output_path: str, width: int = 1080, height: int = 1920) -> str:
    vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
    _run_ffmpeg(["-i", input_path, "-vf", vf, "-c:a", "copy", output_path])
    return output_path


def trim_clip(input_path: str, start_seconds: float, end_seconds: float, output_path: str) -> str:
    _run_ffmpeg(["-i", input_path, "-ss", str(start_seconds), "-to", str(end_seconds), "-c", "copy", output_path])
    return output_path


def _srt_timestamp(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(captions: list[tuple[float, float, str]], srt_path: str) -> str:
    lines = []
    for i, (start, end, text) in enumerate(captions, start=1):
        lines.append(str(i))
        lines.append(f"{_srt_timestamp(start)} --> {_srt_timestamp(end)}")
        lines.append(text)
        lines.append("")
    Path(srt_path).write_text("\n".join(lines), encoding="utf-8")
    return srt_path


def burn_captions(input_path: str, srt_path: str, output_path: str) -> str:
    escaped = srt_path.replace(":", r"\:")
    _run_ffmpeg(["-i", input_path, "-vf", f"subtitles={escaped}", output_path])
    return output_path
