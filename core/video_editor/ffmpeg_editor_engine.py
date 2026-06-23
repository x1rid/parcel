from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable, List

from .segment import Segment


class FFmpegEditorEngine:
    def __init__(self, ffmpeg_path: str | None = None):
        self.ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg") or "ffmpeg"

    def _run(self, args: List[str]) -> None:
        subprocess.run(args, check=True)

    def _normalize_segments(self, timeline) -> List[Segment]:
        segments = timeline.flatten_layers() if hasattr(timeline, "flatten_layers") else list(timeline.keep_segments)
        if hasattr(timeline, "total_frames"):
            max_frames = int(timeline.total_frames)
            normalized = []
            for segment in segments:
                start = max(0, min(int(segment.start_frame), max_frames))
                end = max(0, min(int(segment.end_frame), max_frames))
                if end > start:
                    normalized.append(Segment(start, end, segment.fps))
            normalized.sort(key=lambda seg: (seg.start_frame, seg.end_frame))
            return normalized
        return segments

    def _extract_segment(self, input_file: str, output_file: str, segment: Segment, fast_mode: bool) -> None:
        start_sec = segment.start_sec
        duration_sec = segment.duration_seconds

        if fast_mode:
            cmd = [
                self.ffmpeg_path,
                "-y",
                "-ss",
                f"{start_sec:.6f}",
                "-i",
                input_file,
                "-t",
                f"{duration_sec:.6f}",
                "-map",
                "0",
                "-c",
                "copy",
                output_file,
            ]
        else:
            cmd = [
                self.ffmpeg_path,
                "-y",
                "-i",
                input_file,
                "-ss",
                f"{start_sec:.6f}",
                "-t",
                f"{duration_sec:.6f}",
                "-map",
                "0",
                "-c:v",
                "libx264",
                "-crf",
                "18",
                "-preset",
                "veryfast",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                output_file,
            ]

        self._run(cmd)

    def export_timeline(self, input_file: str, output_file: str, timeline, fast_mode: bool = True) -> str:
        segments = self._normalize_segments(timeline)
        if not segments:
            raise ValueError("No segments selected for export.")

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if len(segments) == 1:
            segment = segments[0]
            with tempfile.TemporaryDirectory(prefix="compressor_v4_export_") as temp_dir:
                temp_part = Path(temp_dir) / output_path.name
                self._extract_segment(input_file, str(temp_part), segment, fast_mode)
                shutil.move(str(temp_part), str(output_path))
            return str(output_path)

        with tempfile.TemporaryDirectory(prefix="compressor_v4_export_") as temp_dir:
            temp_dir_path = Path(temp_dir)
            part_paths: List[Path] = []
            for index, segment in enumerate(segments):
                part_path = temp_dir_path / f"part_{index:04d}{output_path.suffix or '.mp4'}"
                self._extract_segment(input_file, str(part_path), segment, fast_mode)
                part_paths.append(part_path)

            concat_file = temp_dir_path / "concat_list.txt"
            with concat_file.open("w", encoding="utf-8") as handle:
                for part_path in part_paths:
                    handle.write(f"file '{part_path.as_posix()}'\n")

            concat_cmd = [
                self.ffmpeg_path,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c",
                "copy",
                str(output_path),
            ]
            self._run(concat_cmd)

        return str(output_path)

