from __future__ import annotations
from typing import TYPE_CHECKING, Optional, Tuple

if TYPE_CHECKING:
    from .timeline import FrameTimeline

class SegmentResizeController:
    """
    Handles interactions for resizing segments via handles and drag-selecting regions.
    Does NOT allow segment body dragging (repositioning segments), as per trimming editor philosophy.
    """
    def __init__(self):
        self.drag_mode: Optional[str] = None  # 'left_handle', 'right_handle', 'drag_select', 'playhead'
        self.drag_start_frame: int = 0
        
        # State for segment resizing
        self.target_segment_id: Optional[str] = None
        self.original_start: int = 0
        self.original_end: int = 0
        
        # State for drag selection
        self.selection_start: Optional[int] = None
        self.selection_end: Optional[int] = None
        
        self.is_dragging: bool = False

    def initiate_drag(
        self, 
        timeline: FrameTimeline, 
        frame: int, 
        drag_mode: str,
        target_segment_id: Optional[str] = None
    ) -> None:
        self.is_dragging = True
        self.drag_start_frame = frame
        self.drag_mode = drag_mode
        
        if drag_mode in ("left_handle", "right_handle") and target_segment_id:
            self.target_segment_id = target_segment_id
            for segment in timeline.keep_segments:
                if segment.id == target_segment_id:
                    self.original_start = segment.start_frame
                    self.original_end = segment.end_frame
                    break
                    
        elif drag_mode == "drag_select":
            self.selection_start = frame
            self.selection_end = frame

    def update_drag(self, timeline: FrameTimeline, current_frame: int) -> Tuple[int, bool]:
        """
        Updates the dragging state. 
        Returns (playhead_frame_to_emit, needs_repaint).
        """
        if not self.is_dragging or not self.drag_mode:
            return current_frame, False

        def clamp(f: int) -> int:
            return max(0, min(int(f), max(0, timeline.total_frames - 1)))

        current_frame = clamp(current_frame)

        if self.drag_mode == "left_handle" and self.target_segment_id:
            # Prevent left handle from passing right handle
            new_start = min(current_frame, self.original_end - 1)
            for segment in timeline.keep_segments:
                if segment.id == self.target_segment_id:
                    segment.start_frame = new_start
                    return current_frame, True
                    
        elif self.drag_mode == "right_handle" and self.target_segment_id:
            # Prevent right handle from passing left handle
            new_end = max(current_frame, self.original_start + 1)
            for segment in timeline.keep_segments:
                if segment.id == self.target_segment_id:
                    segment.end_frame = new_end
                    return current_frame, True
                    
        elif self.drag_mode == "drag_select":
            self.selection_end = current_frame
            return current_frame, True
            
        elif self.drag_mode == "playhead":
            return current_frame, True

        return current_frame, False

    def end_drag(self) -> Optional[str]:
        mode = self.drag_mode
        self.is_dragging = False
        self.drag_mode = None
        self.target_segment_id = None
        return mode

    def get_selection_bounds(self) -> Optional[Tuple[int, int]]:
        if self.selection_start is None or self.selection_end is None:
            return None
        return min(self.selection_start, self.selection_end), max(self.selection_start, self.selection_end)
        
    def clear_selection(self) -> None:
        self.selection_start = None
        self.selection_end = None