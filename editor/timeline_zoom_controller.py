from __future__ import annotations

class TimelineZoomController:
    """Manages timeline zooming and panning logic."""
    def __init__(self):
        self.zoom_level: float = 1.0  # 1.0 means full timeline visible
        self.pan_offset: float = 0.0  # 0.0 to 1.0, normalized scroll position

    def zoom_at(self, anchor_ratio: float, delta: float) -> None:
        """
        Zoom in or out while keeping the anchor_ratio (0.0 - 1.0 of visible area) stationary.
        delta > 0 means zoom in, delta < 0 means zoom out.
        """
        zoom_factor = 1.15
        
        old_zoom = self.zoom_level
        if delta > 0:
            self.zoom_level *= zoom_factor
        elif delta < 0:
            self.zoom_level /= zoom_factor
            
        # Clamp zoom level
        self.zoom_level = max(1.0, min(self.zoom_level, 1000.0))
        
        # Adjust pan to keep anchor stable
        # Global position of the anchor point before zoom
        global_anchor = self.pan_offset + anchor_ratio / old_zoom
        # New pan offset should make the anchor_ratio point to the same global_anchor
        self.pan_offset = global_anchor - anchor_ratio / self.zoom_level
        
        self._clamp_pan()

    def pan(self, delta_ratio: float) -> None:
        """Pan the timeline by delta_ratio (relative to the full timeline length)."""
        self.pan_offset += delta_ratio
        self._clamp_pan()

    def _clamp_pan(self) -> None:
        max_pan = max(0.0, 1.0 - 1.0 / self.zoom_level)
        self.pan_offset = max(0.0, min(self.pan_offset, max_pan))

    def visible_range(self, total_frames: int) -> tuple[int, int]:
        """Returns the (start_frame, end_frame) currently visible."""
        if total_frames <= 0:
            return 0, 0
        start = int(self.pan_offset * total_frames)
        end = int((self.pan_offset + 1.0 / self.zoom_level) * total_frames)
        return max(0, start), min(total_frames, end)

    def frame_to_ratio(self, frame: int, total_frames: int) -> float:
        """Maps a frame index to a 0.0 - 1.0 ratio within the VISIBLE area."""
        if total_frames <= 1:
            return 0.0
        global_ratio = frame / (total_frames - 1)
        visible_ratio = (global_ratio - self.pan_offset) * self.zoom_level
        return visible_ratio

    def ratio_to_frame(self, ratio: float, total_frames: int) -> int:
        """Maps a 0.0 - 1.0 ratio within the VISIBLE area to a frame index."""
        if total_frames <= 1:
            return 0
        global_ratio = ratio / self.zoom_level + self.pan_offset
        return int(round(global_ratio * (total_frames - 1)))
