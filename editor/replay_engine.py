from __future__ import annotations
from typing import List, Tuple, Optional


class ReplayEngine:
    """Manages playback boundaries, clip segment matrix parsing, 
    and multi-clip loop step tracking completely independent of UI updates.
    """
    def __init__(self):
        self.segment_ranges: Optional[List[Tuple[int, int]]] = None
        self.segment_index: int = 0
        self.loop_current_segment: bool = False

    def configure_ranges(self, ranges: List[Tuple[int, int]]) -> bool:
        """Normalizes track ranges. Returns True if isolated segments are active."""
        normalized = []
        for start, end in ranges:
            start = max(0, int(start))
            end = max(0, int(end))
            if end > start:
                normalized.append((start, end))
        
        normalized.sort(key=lambda item: (item[0], item[1]))
        if not normalized:
            self.segment_ranges = None
            return False

        self.segment_ranges = normalized
        self.segment_index = 0
        return True

    def clear(self) -> None:
        self.segment_ranges = None
        self.segment_index = 0
        self.loop_current_segment = False

    @property
    def is_active(self) -> bool:
        return self.segment_ranges is not None

    def get_current_bounds(self) -> Tuple[int, int]:
        if not self.segment_ranges:
            return 0, 0
        return self.segment_ranges[min(self.segment_index, len(self.segment_ranges) - 1)]

    def step_to_next_segment(self, total_frames: int) -> Tuple[Optional[int], bool, bool]:
        """Steps forward into the next segment slice.
        Returns a Tuple of (target_frame, force_seek, playback_finished).
        """
        if not self.segment_ranges:
            return None, False, True

        self.segment_index += 1
        if self.segment_index >= len(self.segment_ranges):
            if self.loop_current_segment:
                self.segment_index = 0
                return self.segment_ranges[0][0], True, False
            else:
                self.segment_ranges = None
                return None, False, True
        
        return self.segment_ranges[self.segment_index][0], True, False