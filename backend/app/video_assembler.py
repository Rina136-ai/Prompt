"""ffmpeg-based assembly: concatenate scene clips, crop for shorts, burn lyric captions.

Requires the `ffmpeg` binary on PATH. All functions shell out to it rather
than reimplementing video encoding.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


class AssemblyError(RuntimeError):
    pass


def _run_ffmpeg(args: list[str]) -> None:
    result = subprocess.run(["ffmpeg", "-y", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise AssemblyError(f"ffmpeg a echoue: {result.stderr[-2000:]}")


def concat_clips(clip_paths: list[str], output_path: str) -> str:
    if not clip_paths:
        raise AssemblyError("Aucun clip a assembler.")
    concat_list_path = str(Path(output_path).with_suffix(".concat.txt"))
    with open(concat_list_path, "w", encoding="utf-8") as f:
        for path in clip_paths:
            f.write(f"file '{Path(path).resolve()}'\n")
    _run_ffmpeg(["-f", "concat", "-safe", "0", "-i", concat_list_path, "-c", "copy", output_path])
    return output_path


def crop_to_vertical(input_path: str, output_path: str, width: int = 1080, height: int = 1920) -> str:
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}"
    )
    _run_ffmpeg(["-i", input_path, "-vf", vf, "-c:a", "copy", output_path])
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
