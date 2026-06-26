from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from .segment import Segment


@dataclass
class DragState:
    mode: str
    segment_id: Optional[str] = None
    start_frame: int = 0
    original_start: int = 0
    original_end: int = 0


class SegmentResizeController:
    def __init__(self):
        self.drag_state: Optional[DragState] = None
        self.selection_start: Optional[int] = None
        self.selection_end: Optional[int] = None
        self.is_dragging: bool = False

    def initiate_drag(
        self,
        timeline,
        frame: int,
        drag_mode: str,
        target_segment_id: Optional[str] = None,
    ) -> None:
        self.is_dragging = True
        if drag_mode in {"move_segment", "left_handle", "right_handle"} and target_segment_id:
            segment = next((seg for seg in timeline.keep_segments if seg.id == target_segment_id), None)
            if segment:
                self.drag_state = DragState(
                    mode=drag_mode,
                    segment_id=target_segment_id,
                    start_frame=frame,
                    original_start=segment.start_frame,
                    original_end=segment.end_frame,
                )
                return

        if drag_mode == "drag_select":
            self.selection_start = frame
            self.selection_end = frame
        self.drag_state = DragState(mode=drag_mode, start_frame=frame, segment_id=target_segment_id)

    def update_drag(self, timeline, current_frame: int) -> Tuple[int, bool]:
        if not self.is_dragging or not self.drag_state:
            return current_frame, False

        frame = max(0, min(int(current_frame), max(0, timeline.total_frames - 1)))
        state = self.drag_state

        if state.mode == "drag_select":
            self.selection_end = frame
            return frame, True

        if state.mode == "move_segment" and state.segment_id:
            segment = next((seg for seg in timeline.keep_segments if seg.id == state.segment_id), None)
            if not segment:
                return frame, False
            delta = frame - state.start_frame
            max_right = timeline.total_frames - state.original_end
            max_left = -state.original_start
            delta = max(max_left, min(delta, max_right))
            proposed = segment.shifted(delta)
            adjusted = timeline.clamp_segment_to_neighbors(proposed, exclude_id=segment.id)
            segment.start_frame = adjusted.start_frame
            segment.end_frame = adjusted.end_frame
            return frame, True

        if state.mode == "left_handle" and state.segment_id:
            segment = next((seg for seg in timeline.keep_segments if seg.id == state.segment_id), None)
            if not segment:
                return frame, False
            proposed = Segment(min(frame, segment.end_frame - 1), segment.end_frame, timeline.fps, id=segment.id, layer=segment.layer)
            adjusted = timeline.clamp_segment_to_neighbors(proposed, exclude_id=segment.id)
            segment.start_frame = min(adjusted.start_frame, segment.end_frame - 1)
            return frame, True

        if state.mode == "right_handle" and state.segment_id:
            segment = next((seg for seg in timeline.keep_segments if seg.id == state.segment_id), None)
            if not segment:
                return frame, False
            proposed = Segment(segment.start_frame, max(frame, segment.start_frame + 1), timeline.fps, id=segment.id, layer=segment.layer)
            adjusted = timeline.clamp_segment_to_neighbors(proposed, exclude_id=segment.id)
            segment.end_frame = max(adjusted.end_frame, segment.start_frame + 1)
            return frame, True

        return frame, False

    def end_drag(self) -> Optional[str]:
        mode = self.drag_state.mode if self.drag_state else None
        self.is_dragging = False
        self.drag_state = None
        return mode

    def get_selection_bounds(self) -> Optional[Tuple[int, int]]:
        if self.selection_start is None or self.selection_end is None:
            return None
        return min(self.selection_start, self.selection_end), max(self.selection_start, self.selection_end)

    def clear_selection(self) -> None:
        self.selection_start = None
        self.selection_end = None
