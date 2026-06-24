from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

import av
import numpy as np


def _format_timecode(frame_index: int, fps: float) -> str:
    if fps <= 0:
        return "00:00:00.00"
    total_seconds = frame_index / fps
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:05.2f}"


@dataclass
class FrameInfo:
    frame_index: int
    timestamp: str
    fps: float


class FrameAccurateEngine:
    def __init__(self, video_path: str):
        self.video_path = video_path
        self.container = av.open(video_path)
        self.stream = self.container.streams.video[0]
        self.stream.thread_type = "AUTO"
        self.source_width = int(getattr(self.stream, "width", 0) or 0)
        self.source_height = int(getattr(self.stream, "height", 0) or 0)
        self.fps = float(self.stream.average_rate or self.stream.base_rate or 25.0)
        self.total_frames = self._compute_total_frames()
        self.current_frame_index = 0
        self._sequential_decoder = None
        self._playback_decoder = None
        self._frame_cache: OrderedDict[int, np.ndarray] = OrderedDict()
        self._frame_cache_limit = 96

    def _compute_total_frames(self) -> int:
        if self.stream.frames and self.stream.frames > 0:
            return int(self.stream.frames)
        if self.stream.duration and self.stream.time_base:
            return max(1, int(float(self.stream.duration * self.stream.time_base) * self.fps))
        return 0

    def frame_timecode(self, frame_index: int) -> str:
        return _format_timecode(max(0, frame_index), self.fps)

    def frame_info(self, frame_index: int) -> FrameInfo:
        return FrameInfo(frame_index=frame_index, timestamp=self.frame_timecode(frame_index), fps=self.fps)

    def seek_to_frame(self, frame_index: int) -> None:
        frame_index = max(0, min(int(frame_index), max(0, self.total_frames - 1)))
        if self.total_frames == 0:
            self.current_frame_index = 0
            return

        # OPTIMIZATION: If the target frame is already in the memory cache, avoid re-seeking entirely.
        if frame_index in self._frame_cache:
            self.current_frame_index = frame_index
            return

        self.reset_playback()
        self._prepare_decoder(frame_index)
        self.current_frame_index = frame_index

    def get_exact_frame(self, frame_index: int) -> Optional[np.ndarray]:
        if self.total_frames <= 0:
            return None

        frame_index = max(0, min(int(frame_index), self.total_frames - 1))
        cached = self._frame_cache.get(frame_index)
        if cached is not None:
            self._frame_cache.move_to_end(frame_index)
            self.current_frame_index = frame_index
            return cached

        if self._sequential_decoder is not None and frame_index == self.current_frame_index + 1:
            try:
                frame = next(self._sequential_decoder)
                array = frame.to_ndarray(format="rgb24")
                self.current_frame_index = frame_index
                self._store_frame(frame_index, array)
                return array
            except StopIteration:
                self._sequential_decoder = None

        array = self._decode_frame(frame_index, keep_decoder=False)
        if array is not None:
            return array

        return None

    def step_frame(self, step: int = 1) -> Optional[np.ndarray]:
        return self.get_exact_frame(self.current_frame_index + int(step))

    def prepare_playback(self, frame_index: int = 0) -> Optional[np.ndarray]:
        return self._decode_frame(frame_index, keep_decoder=True)

    def read_next_playback_frame(self) -> Optional[np.ndarray]:
        if self._playback_decoder is None:
            return self.prepare_playback(self.current_frame_index + 1)
        try:
            frame = next(self._playback_decoder)
        except StopIteration:
            self._playback_decoder = None
            return None

        array = frame.to_ndarray(format="rgb24")
        pts_seconds = float(frame.pts * self.stream.time_base) if frame.pts is not None else self.current_frame_index / max(self.fps, 1.0)
        candidate_frame = int(round(pts_seconds * self.fps)) if self.fps else self.current_frame_index + 1
        self.current_frame_index = max(self.current_frame_index + 1, candidate_frame)
        self._store_frame(self.current_frame_index, array)
        return array

    def _decode_frame(self, frame_index: int, keep_decoder: bool) -> Optional[np.ndarray]:
        if self.total_frames <= 0:
            return None

        frame_index = max(0, min(int(frame_index), self.total_frames - 1))
        target_seconds = frame_index / self.fps if self.fps else 0.0
        target_pts = int(target_seconds / self.stream.time_base)
        self.container.seek(target_pts, stream=self.stream, backward=True, any_frame=False)
        decoder = self.container.decode(self.stream)
        
        for decoded_index, frame in enumerate(decoder):
            pts_seconds = float(frame.pts * self.stream.time_base) if frame.pts is not None else decoded_index / max(self.fps, 1.0)
            candidate_frame = int(round(pts_seconds * self.fps)) if self.fps else decoded_index
            
            # OPTIMIZATION: Only perform the highly expensive format conversion to ndarray
            # for the target destination frame. Skip it for intermediate frames.
            if candidate_frame >= frame_index:
                array = frame.to_ndarray(format="rgb24")
                self._store_frame(candidate_frame, array)
                self.current_frame_index = candidate_frame
                if keep_decoder:
                    self._playback_decoder = decoder
                else:
                    self._sequential_decoder = decoder
                return array

        if keep_decoder:
            self._playback_decoder = None
        else:
            self._sequential_decoder = None
        return None

    def _prepare_decoder(self, frame_index: int) -> None:
        self._decode_frame(frame_index, keep_decoder=False)

    def _store_frame(self, frame_index: int, frame_array: np.ndarray) -> None:
        self._frame_cache[frame_index] = frame_array
        self._frame_cache.move_to_end(frame_index)
        while len(self._frame_cache) > self._frame_cache_limit:
            self._frame_cache.popitem(last=False)

    def release(self) -> None:
        if self.container is not None:
            self.container.close()
        self.container = None
        self._sequential_decoder = None
        self._playback_decoder = None
        self._frame_cache.clear()

    def reset_playback(self) -> None:
        self._playback_decoder = None