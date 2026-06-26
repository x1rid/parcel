from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

from .segment import Segment


def _clamp_frame(value: int, total_frames: int) -> int:
    total_frames = max(0, int(total_frames))
    return max(0, min(int(value), total_frames))


@dataclass
class FrameTimeline:
    total_frames: int
    fps: float
    layers: Dict[str, List[Segment]] = field(default_factory=dict)
    active_layer: str = "base"
    mark_in_frame: Optional[int] = None
    mark_out_frame: Optional[int] = None
    cursor_frame: int = 0

    def __post_init__(self) -> None:
        self.total_frames = max(0, int(self.total_frames))
        self.fps = float(self.fps or 0.0)
        if self.active_layer not in self.layers:
            self.layers[self.active_layer] = []

    @property
    def base_segments(self) -> List[Segment]:
        return self.layers.setdefault("base", [])

    @property
    def keep_segments(self) -> List[Segment]:
        return self.layers.setdefault(self.active_layer, self.layers.get("base", []))

    @keep_segments.setter
    def keep_segments(self, value: List[Segment]) -> None:
        self.layers[self.active_layer] = value
        if self.active_layer == "base":
            self.layers["base"] = value

    def set_cursor(self, frame_index: int) -> None:
        self.cursor_frame = _clamp_frame(frame_index, self.total_frames)

    def set_mark_in(self, frame_index: int) -> None:
        self.mark_in_frame = _clamp_frame(frame_index, self.total_frames)
        self.mark_out_frame = None

    def clear_mark_in(self) -> None:
        self.mark_in_frame = None
        self.mark_out_frame = None

    def has_markers(self) -> bool:
        return self.mark_in_frame is not None and self.mark_out_frame is not None

    def set_mark_out(self, frame_index: int) -> None:
        if self.mark_in_frame is None:
            return
        self.mark_out_frame = _clamp_frame(frame_index, self.total_frames)

    def add_segment(
        self,
        start_frame: int,
        end_frame: int,
        layer: Optional[str] = None,
        normalize: bool = True,
    ) -> Segment:
        layer_name = layer or self.active_layer
        segment = Segment(
            _clamp_frame(start_frame, self.total_frames),
            _clamp_frame(end_frame, self.total_frames),
            self.fps,
            layer=layer_name,
        )
        self.layers.setdefault(layer_name, []).append(segment)
        if normalize:
            self.normalize_layer(layer_name)
        return segment

    def commit_mark_out(self, frame_index: int, layer: Optional[str] = None) -> Optional[Segment]:
        self.set_mark_out(frame_index)
        return self.create_segment_from_marks(layer=layer)

    def create_segment_from_marks(self, layer: Optional[str] = None) -> Optional[Segment]:
        if self.mark_in_frame is None or self.mark_out_frame is None:
            return None
        start = min(self.mark_in_frame, self.mark_out_frame)
        end = max(self.mark_in_frame, self.mark_out_frame)
        segment = self.add_segment(start, end, layer=layer)
        self.clear_mark_in()
        return segment

    def delete_segment(self, segment_id: str, layer: Optional[str] = None) -> bool:
        layer_name = layer or self.active_layer
        segments = self.layers.get(layer_name, [])
        before = len(segments)
        self.layers[layer_name] = [segment for segment in segments if segment.id != segment_id]
        return len(self.layers[layer_name]) != before

    def split_at_frame(self, frame_index: int, layer: Optional[str] = None) -> Optional[tuple[Segment, Segment]]:
        layer_name = layer or self.active_layer
        frame_index = _clamp_frame(frame_index, self.total_frames)
        segments = self.layers.get(layer_name, [])
        for index, segment in enumerate(segments):
            if segment.start_frame < frame_index < segment.end_frame:
                left = Segment(segment.start_frame, frame_index, self.fps, layer=layer_name)
                right = Segment(frame_index, segment.end_frame, self.fps, layer=layer_name)
                self.layers[layer_name] = segments[:index] + [left, right] + segments[index + 1 :]
                return left, right
        return None

    def remove_range(self, start_frame: int, end_frame: int, layer: Optional[str] = None) -> bool:
        """Removes a frame range, splitting and resizing segments as necessary."""
        layer_name = layer or self.active_layer
        start = _clamp_frame(start_frame, self.total_frames)
        end = _clamp_frame(end_frame, self.total_frames)
        if start >= end:
            return False

        segments = self.layers.get(layer_name, [])
        new_segments = []
        changed = False

        for segment in segments:
            if segment.end_frame <= start or segment.start_frame >= end:
                # No overlap
                new_segments.append(segment)
            elif segment.start_frame >= start and segment.end_frame <= end:
                # Fully contained within removal range - delete it
                changed = True
            else:
                # Partial overlap
                changed = True
                if segment.start_frame < start and segment.end_frame > end:
                    # Cut in the middle - split into two
                    new_segments.append(Segment(segment.start_frame, start, self.fps, layer=layer_name))
                    new_segments.append(Segment(end, segment.end_frame, self.fps, layer=layer_name))
                elif segment.start_frame < start:
                    # Trim right
                    new_segments.append(Segment(segment.start_frame, start, self.fps, layer=layer_name))
                else:
                    # Trim left
                    new_segments.append(Segment(end, segment.end_frame, self.fps, layer=layer_name))

        if changed:
            self.layers[layer_name] = new_segments
        return changed

    def segment_at_frame(self, frame_index: int, layer: Optional[str] = None) -> Optional[Segment]:
        layer_name = layer or self.active_layer
        for segment in self.layers.get(layer_name, []):
            if segment.start_frame <= frame_index < segment.end_frame:
                return segment
        return None

    def timecode(self, frame_index: int) -> str:
        """Returns timecode in MM:SS:FRAME format."""
        if self.fps <= 0:
            return "00:00:00"
        total_seconds = frame_index / self.fps
        minutes = int(total_seconds // 60)
        seconds = int(total_seconds % 60)
        frame_remainder = int(round((total_seconds - int(total_seconds)) * self.fps))
        return f"{minutes:02d}:{seconds:02d}:{frame_remainder:02d}"

    def duration_timecode(self, start_frame: int, end_frame: int) -> str:
        return self.timecode(max(0, int(end_frame) - int(start_frame)))

    def snap_frame(self, frame_index: int, tolerance: int = 3) -> int:
        """Snap to markers, segment boundaries, and timeline ends when close enough."""
        if self.total_frames <= 0:
            return 0

        frame = _clamp_frame(frame_index, self.total_frames)
        candidates = {0, self.total_frames}
        if self.mark_in_frame is not None:
            candidates.add(self.mark_in_frame)
        if self.mark_out_frame is not None:
            candidates.add(self.mark_out_frame)
        for segment in self.flatten_layers():
            candidates.add(segment.start_frame)
            candidates.add(segment.end_frame)

        closest = min(candidates, key=lambda candidate: abs(candidate - frame))
        return closest if abs(closest - frame) <= max(0, int(tolerance)) else frame

    def reorder_segment(self, segment_id: str, new_index: int, layer: Optional[str] = None) -> bool:
        layer_name = layer or self.active_layer
        segments = self.layers.get(layer_name, [])
        for index, segment in enumerate(segments):
            if segment.id == segment_id:
                moved = segments.pop(index)
                new_index = max(0, min(int(new_index), len(segments)))
                segments.insert(new_index, moved)
                self.layers[layer_name] = segments
                return True
        return False

    def merge_adjacent(self, layer: Optional[str] = None, gap_tolerance_frames: int = 0) -> None:
        layer_name = layer or self.active_layer
        self.layers[layer_name] = self._merge_segments(self.layers.get(layer_name, []), gap_tolerance_frames)

    def normalize_layer(self, layer: Optional[str] = None) -> None:
        layer_name = layer or self.active_layer
        self.layers[layer_name] = self._normalize_segments(self.layers.get(layer_name, []), self.total_frames)

    def clamp_segment_to_neighbors(self, segment: Segment, exclude_id: Optional[str] = None) -> Segment:
        start = _clamp_frame(segment.start_frame, self.total_frames)
        end = _clamp_frame(segment.end_frame, self.total_frames)
        if end <= start:
            end = min(self.total_frames, start + 1)

        others = [
            seg
            for seg in self.keep_segments
            if seg.id != exclude_id
        ]
        left_limit = 0
        right_limit = self.total_frames
        for seg in others:
            if seg.end_frame <= start and seg.end_frame > left_limit:
                left_limit = seg.end_frame
            if seg.start_frame >= end and seg.start_frame < right_limit:
                right_limit = seg.start_frame
        start = max(start, left_limit)
        end = min(end, right_limit)
        if end <= start:
            if start >= right_limit:
                start = max(left_limit, right_limit - 1)
                end = right_limit
            else:
                end = min(self.total_frames, start + 1)
        return Segment(start, end, segment.fps, id=segment.id, layer=segment.layer)

    def add_layer(self, name: str) -> None:
        self.layers.setdefault(name, [])

    def flatten_layers(self) -> List[Segment]:
        all_segments: List[Segment] = []
        for layer_name, segments in self.layers.items():
            for segment in segments:
                all_segments.append(
                    Segment(
                        segment.start_frame,
                        segment.end_frame,
                        self.fps,
                        id=segment.id,
                        layer=layer_name,
                    )
                )
        return self._normalize_segments(all_segments, self.total_frames)

    def get_gap_cuts(self, source_segments: Optional[Iterable[Segment]] = None) -> List[Segment]:
        keep_segments = self._normalize_segments(list(source_segments or self.flatten_layers()), self.total_frames)
        cuts: List[Segment] = []
        prev_end = 0
        for segment in keep_segments:
            if segment.start_frame > prev_end:
                cuts.append(Segment(prev_end, segment.start_frame, self.fps, layer="cut"))
            prev_end = max(prev_end, segment.end_frame)
        if prev_end < self.total_frames:
            cuts.append(Segment(prev_end, self.total_frames, self.fps, layer="cut"))
        return cuts

    def inverted_keep_segments(self) -> List[Segment]:
        return self.get_gap_cuts()

    def validate(self) -> None:
        self.flatten_layers()

    @staticmethod
    def _normalize_segments(segments: List[Segment], total_frames: int) -> List[Segment]:
        normalized = []
        for segment in segments:
            start = _clamp_frame(segment.start_frame, total_frames)
            end = _clamp_frame(segment.end_frame, total_frames)
            if end <= start:
                continue
            normalized.append(Segment(start, end, segment.fps, id=segment.id, layer=segment.layer))

        normalized.sort(key=lambda item: (item.start_frame, item.end_frame))
        return normalized

    @staticmethod
    def _merge_segments(segments: List[Segment], gap_tolerance_frames: int = 0) -> List[Segment]:
        if not segments:
            return []
        merged = [segments[0]]
        for current in segments[1:]:
            previous = merged[-1]
            if current.start_frame <= previous.end_frame + gap_tolerance_frames:
                previous.end_frame = max(previous.end_frame, current.end_frame)
            else:
                merged.append(current)
        return merged


Timeline = FrameTimeline
