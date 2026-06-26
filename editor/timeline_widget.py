from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QRect, QSize, QEvent
from PyQt6.QtGui import QColor, QPainter, QPen, QPolygon, QBrush, QPainterPath, QCursor, QIcon, QPixmap, QImage
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QFrame, QGridLayout, QApplication

from .segment_resize_controller import SegmentResizeController
from .timeline_zoom_controller import TimelineZoomController


@dataclass(slots=True)
class HoverPreviewData:
    frame_index: int
    timestamp: str
    frame_number: int
    pixmap: QPixmap | None
    title: str
    detail: str
    duration: str | None = None
    excluded: bool = False


def _make_icon(kind: str, size: int = 18) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QPen(QColor("#9ca3af"), 1.75, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if kind == "trash":
        painter.drawRect(5, 6, 8, 8)
        painter.drawLine(4, 6, 14, 6)
        painter.drawLine(7, 4, 11, 4)
    elif kind == "segment":
        painter.drawEllipse(7, 4, 4, 4)
        painter.drawLine(9, 8, 9, 14)
    elif kind == "replay":
        painter.drawArc(4, 4, 10, 10, 45 * 16, 270 * 16)
        painter.drawLine(11, 4, 14, 4)
        painter.drawLine(14, 4, 14, 7)
    elif kind == "close":
        painter.drawLine(4, 4, 14, 14)
        painter.drawLine(14, 4, 4, 14)
    painter.end()
    return QIcon(pixmap)


def timecode_to_hmsf(frame_index: int, fps: float) -> str:
    if fps <= 0:
        return "00:00:00:00"
    total_seconds = frame_index / fps
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    frames = int(round((total_seconds - int(total_seconds)) * fps))
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"


class TimelineHeaderWidget(QFrame):
    deleteRequested = pyqtSignal()
    replayRequested = pyqtSignal()
    saveFrameRequested = pyqtSignal()
    splitRequested = pyqtSignal()
    duplicateRequested = pyqtSignal()
    undoRequested = pyqtSignal()
    redoRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TimelineHeaderWidget")
        self.setStyleSheet("""
            QFrame#TimelineHeaderWidget {
                background-color: #171A21;
                border-bottom: 1px solid #252932;
                border-radius: 8px 8px 0px 0px;
            }
            QLabel {
                color: #7d848e;
                font-family: 'Segoe UI', Helvetica, Arial, sans-serif;
                font-size: 13px;
            }
            QToolButton {
                color: #ffffff;
                background-color: #252932;
                border: 1px solid #252932;
                border-radius: 6px;
                font-family: 'Segoe UI', Helvetica, Arial, sans-serif;
                font-size: 12px;
                font-weight: 600;
                padding: 5px 10px;
            }
            QToolButton:hover {
                background-color: #2e343f;
                border-color: #d4af37;
            }
            QToolButton:pressed {
                background-color: #1a1c23;
            }
            QToolButton:disabled {
                color: #4e5460;
                background-color: #171A21;
                border-color: #252932;
            }
        """)
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 8, 12, 8)
        main_layout.setSpacing(16)
        
        # Left Side: Inspector
        self.inspector_label = QLabel("No segment selected. Click a segment to edit.")
        self.inspector_label.setWordWrap(True)
        main_layout.addWidget(self.inspector_label)
        
        main_layout.addStretch(1)
        
        # Right Side: Segment Tools Toolbar
        self.tools_layout = QHBoxLayout()
        self.tools_layout.setSpacing(6)
        
        self.btn_delete = self._create_btn("🗑 Delete", self.deleteRequested)
        self.btn_replay = self._create_btn("↺ Replay", self.replayRequested)
        self.btn_save_frame = self._create_btn("📸 Save Frame", self.saveFrameRequested)
        self.btn_split = self._create_btn("✂ Split", self.splitRequested)
        self.btn_duplicate = self._create_btn("📄 Duplicate", self.duplicateRequested)
        self.btn_undo = self._create_btn("↶ Undo", self.undoRequested)
        self.btn_redo = self._create_btn("↷ Redo", self.redoRequested)
        
        self.tools_layout.addWidget(self.btn_delete)
        self.tools_layout.addWidget(self.btn_replay)
        self.tools_layout.addWidget(self.btn_save_frame)
        self.tools_layout.addWidget(self.btn_split)
        self.tools_layout.addWidget(self.btn_duplicate)
        self.tools_layout.addWidget(self.btn_undo)
        self.tools_layout.addWidget(self.btn_redo)
        
        main_layout.addLayout(self.tools_layout)
        
        self.set_segment_selected(False)
        
    def _create_btn(self, text: str, signal: pyqtSignal) -> QToolButton:
        btn = QToolButton()
        btn.setText(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(signal.emit)
        return btn
        
    def set_segment_selected(self, selected: bool, start_tc: str = "", end_tc: str = "", dur_tc: str = "") -> None:
        self.btn_delete.setEnabled(selected)
        self.btn_replay.setEnabled(selected)
        self.btn_save_frame.setEnabled(selected)
        self.btn_split.setEnabled(selected)
        self.btn_duplicate.setEnabled(selected)
        
        if selected:
            self.inspector_label.setText(
                f"<b>Selected Segment</b> &nbsp;&nbsp;|&nbsp;&nbsp; Start: <font color='#ffffff'>{start_tc}</font> &nbsp;&nbsp; End: <font color='#ffffff'>{end_tc}</font> &nbsp;&nbsp; Duration: <font color='#d4af37'><b>{dur_tc}</b></font>"
            )
        else:
            self.inspector_label.setText("No segment selected. Click a segment to edit.")


class HoverPreviewPopup(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HoverPreviewPopup")
        self.setWindowFlags(
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        from PyQt6.QtWidgets import QGraphicsDropShadowEffect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)
        
        self.setStyleSheet("""
            QFrame#HoverPreviewPopup {
                background-color: #171A21;
                border: 1px solid #252932;
                border-radius: 8px;
            }
            QLabel {
                color: #ffffff;
                font-family: 'Segoe UI', Helvetica, Arial, sans-serif;
            }
            QLabel#HoverTimecode {
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#HoverFrame {
                color: #7d848e;
                font-size: 11px;
            }
        """)

        self.preview_label = QLabel()
        self.preview_label.setFixedSize(140, 78)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("""
            QLabel {
                background-color: #000000;
                border: 1px solid #252932;
                border-radius: 4px;
            }
        """)

        self.timecode_label = QLabel("")
        self.timecode_label.setObjectName("HoverTimecode")
        
        self.frame_label = QLabel("")
        self.frame_label.setObjectName("HoverFrame")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        layout.addWidget(self.preview_label)
        
        text_layout = QHBoxLayout()
        text_layout.addWidget(self.timecode_label)
        text_layout.addStretch(1)
        text_layout.addWidget(self.frame_label)
        layout.addLayout(text_layout)

    def set_preview(self, data: HoverPreviewData) -> None:
        if data.pixmap is None or data.pixmap.isNull():
            self.preview_label.setText("No preview")
            self.preview_label.setPixmap(QPixmap())
        else:
            scaled = data.pixmap.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.preview_label.setPixmap(scaled)
            self.preview_label.setText("")

        self.timecode_label.setText(data.timestamp)
        self.frame_label.setText(f"Frame {data.frame_number}")


class TimelineCanvas(QWidget):
    cursorFrameChanged = pyqtSignal(int)
    selectionChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.timeline = None
        self.cursor_frame = 0
        self.preview_engine = None
        self.hover_preview = HoverPreviewPopup(None) # None parent means it's an overlay and doesn't participate in layout
        self.hover_preview.hide()
        self._hover_visible = False
        self.selected_segment_id = None
        self._drag_create_start: int | None = None
        self._drag_create_end: int | None = None
        self._drag_move_original: tuple[int, int] | None = None
        
        # Caching for thumbnails
        self.thumb_frames: list[tuple[int, object]] = []
        self.thumb_cache_height = 110 # Increased ~35% from 80
        
        # Controllers
        self.resize_controller = SegmentResizeController()
        self.zoom_controller = TimelineZoomController()
        
        self.setMinimumHeight(140) # Increased to support taller thumbnails
        self.setMouseTracking(True)
        self.selection_actions = None

    def set_timeline(self, timeline) -> None:
        self.timeline = timeline
        self.thumb_frames = []
        self.selected_segment_id = None
        self._hide_hover_preview()
        self.update()

    def set_preview_source(self, engine) -> None:
        self.preview_engine = engine
        self.thumb_frames = []
        if not engine or not self.timeline or self.timeline.total_frames <= 0:
            self.update()
            return

        total = max(1, self.timeline.total_frames)
        width = max(1, self.width())
        thumb_count = max(1, min(width // 110, total))
        sample_frames = [int(round(i * (total - 1) / max(1, thumb_count - 1))) for i in range(thumb_count)]
        
        original_frame = getattr(engine, "current_frame_index", 0)

        for frame_index in sample_frames:
            frame_rgb = engine.get_exact_frame(frame_index)
            if frame_rgb is None:
                continue
            height, width_img, channel = frame_rgb.shape
            bytes_per_line = channel * width_img
            q_img = QImage(frame_rgb.tobytes(), width_img, height, bytes_per_line, QImage.Format.Format_RGB888).copy()
            pixmap = QPixmap.fromImage(q_img).scaledToHeight(self.thumb_cache_height, Qt.TransformationMode.FastTransformation)
            self.thumb_frames.append((frame_index, pixmap))

        if hasattr(engine, "seek_to_frame"):
            engine.seek_to_frame(original_frame)
        self.update()

    def set_cursor_frame(self, frame_index: int) -> None:
        self.cursor_frame = max(0, int(frame_index))
        self.update()

    def _hide_hover_preview(self) -> None:
        self._hover_visible = False
        self.hover_preview.hide()

    def _segment_at_pos(self, x: int) -> tuple[object | None, str]:
        if not self.timeline:
            return None, "empty"
        MARGIN_X = 12
        width = max(1, self.width() - 2 * MARGIN_X)
        frame = self._x_to_frame(x - MARGIN_X, width)
        segment = self.timeline.segment_at_frame(frame)
        if not segment:
            return None, "empty"
        edge_tol = 10
        if abs(frame - segment.start_frame) <= edge_tol:
            return segment, "left_edge"
        if abs(frame - segment.end_frame) <= edge_tol:
            return segment, "right_edge"
        return segment, "body"

    def _thumb_for_frame(self, frame_index: int) -> QPixmap | None:
        if not self.thumb_frames:
            return None
        return min(self.thumb_frames, key=lambda item: abs(item[0] - frame_index))[1]

    def _frame_info_for_x(self, x: int) -> HoverPreviewData | None:
        if not self.timeline or self.timeline.total_frames <= 0:
            return None

        MARGIN_X = 12
        width = max(1, self.width() - 2 * MARGIN_X)
        frame_index = self._x_to_frame(x - MARGIN_X, width)
        frame_index = max(0, min(frame_index, self.timeline.total_frames - 1))
        timestamp = self.timeline.timecode(frame_index)
        pixmap = self._thumb_for_frame(frame_index)
        frame_number = frame_index + 1

        segment = self.timeline.segment_at_frame(frame_index)
        if segment:
            segment_index = self.timeline.keep_segments.index(segment) + 1 if segment in self.timeline.keep_segments else None
            title = segment.layer if segment.layer and segment.layer != "base" else f"Segment {segment_index or 1}"
            detail = f"Segment {segment_index or 1}" if segment_index is not None else "Segment"
            duration = self.timeline.timecode(segment.duration_frames)
            return HoverPreviewData(
                frame_index=frame_index,
                timestamp=timestamp,
                frame_number=frame_number,
                pixmap=pixmap,
                title=title,
                detail=detail,
                duration=duration,
                excluded=False,
            )

        for cut in self.timeline.inverted_keep_segments():
            if cut.start_frame <= frame_index < cut.end_frame:
                duration = self.timeline.timecode(cut.duration_frames)
                return HoverPreviewData(
                    frame_index=frame_index,
                    timestamp=timestamp,
                    frame_number=frame_number,
                    pixmap=pixmap,
                    title="Removed region",
                    detail="Excluded from export",
                    duration=duration,
                    excluded=True,
                )

        return HoverPreviewData(
            frame_index=frame_index,
            timestamp=timestamp,
            frame_number=frame_number,
            pixmap=pixmap,
            title="Timeline",
            detail="",
            duration=None,
            excluded=False,
        )

    def _show_hover_preview(self, event_pos: QPoint) -> None:
        data = self._frame_info_for_x(int(event_pos.x()))
        if data is None:
            self._hide_hover_preview()
            return

        self.hover_preview.set_preview(data)
        self.hover_preview.adjustSize()

        global_pos = self.mapToGlobal(event_pos)
        offset = QPoint(24, -self.hover_preview.height() - 18)
        target = global_pos + offset

        # Constrain to screen bounds instead of window bounds, because popup is top-level (None parent)
        screen = QApplication.primaryScreen().geometry()
        target.setX(max(screen.left() + 8, min(target.x(), screen.right() - self.hover_preview.width() - 8)))
        target.setY(max(screen.top() + 8, min(target.y(), screen.bottom() - self.hover_preview.height() - 8)))
        
        self.hover_preview.move(target)
        if not self._hover_visible:
            from PyQt6.QtCore import QPropertyAnimation
            self.hover_preview.setWindowOpacity(0.0)
            self.hover_preview.show()
            self.hover_preview.raise_()
            self._hover_visible = True
            
            self._anim = QPropertyAnimation(self.hover_preview, b"windowOpacity")
            self._anim.setDuration(120)
            self._anim.setStartValue(0.0)
            self._anim.setEndValue(1.0)
            self._anim.start()
        else:
            self.hover_preview.raise_()

    def clear_selection(self) -> None:
        self.resize_controller.clear_selection()
        self.selected_segment_id = None
        self._hide_hover_preview()
        self.selectionChanged.emit()
        self.update()

    def _frame_to_x(self, frame_index: int, width: int) -> int:
        if not self.timeline or self.timeline.total_frames <= 0:
            return 0
        ratio = self.zoom_controller.frame_to_ratio(frame_index, self.timeline.total_frames)
        return int(ratio * width)

    def _x_to_frame(self, x: int, width: int) -> int:
        if not self.timeline or self.timeline.total_frames <= 0:
            return 0
        ratio = x / max(1, width)
        return self.zoom_controller.ratio_to_frame(ratio, self.timeline.total_frames)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect()
        painter.fillRect(rect, QColor("#0F1115"))
        
        MARGIN_X = 12
        MARGIN_Y = 12
        container_rect = rect.adjusted(MARGIN_X, MARGIN_Y, -MARGIN_X, -MARGIN_Y)
        
        # Track background
        width = max(1, container_rect.width())
        height = container_rect.height()
        track_top = container_rect.top()
        track_left = container_rect.left()
        
        painter.setClipRect(track_left, track_top, width, height)
        painter.fillRect(track_left, track_top, width, height, QColor("#171A21"))

        if self.timeline and self.timeline.total_frames > 0:
            mark_in = getattr(self.timeline, "mark_in_frame", None)
            mark_out = getattr(self.timeline, "mark_out_frame", None)

            # Draw thumbnails
            if self.thumb_frames:
                for frame_index, thumb in self.thumb_frames:
                    x = self._frame_to_x(frame_index, width) + track_left
                    thumb_width = max(20, int(thumb.width()))
                    y = track_top + max(2, (height - thumb.height()) // 2)
                    painter.drawPixmap(x - thumb_width // 2, y, thumb)

            # Draw "Cut" regions (dimmed/hatched)
            painter.fillRect(track_left, track_top, width, height, QColor(15, 17, 21, 160))
            
            # Draw "Keep" Segments
            HANDLE_WIDTH = 10
            for i, segment in enumerate(self.timeline.keep_segments):
                x1 = self._frame_to_x(segment.start_frame, width) + track_left
                x2 = self._frame_to_x(segment.end_frame, width) + track_left
                seg_width = max(2, x2 - x1)
                
                is_selected = (segment.id == self.selected_segment_id)
                
                colors = ["#10b981", "#3b82f6", "#f59e0b", "#8b5cf6"]
                base_color = QColor(colors[i % len(colors)])
                
                if is_selected:
                    fill_alpha = 180
                    border_color = QColor("#d4af37")
                    border_width = 2.0
                    
                    # Outer Glow for Selection
                    glow_pen = QPen(QColor(212, 175, 55, 60), 6)
                    painter.setPen(glow_pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRoundedRect(x1 - 1, track_top + 1, seg_width + 2, height - 2, 8, 8)
                else:
                    fill_alpha = 90
                    border_color = QColor(base_color.red(), base_color.green(), base_color.blue(), 160)
                    border_width = 1.0
                
                from PyQt6.QtGui import QLinearGradient
                gradient = QLinearGradient(x1, track_top, x1, track_top + height)
                gradient.setColorAt(0.0, QColor(base_color.red(), base_color.green(), base_color.blue(), fill_alpha))
                gradient.setColorAt(1.0, QColor(base_color.red(), base_color.green(), base_color.blue(), max(0, fill_alpha - 45)))
                
                painter.setBrush(QBrush(gradient))
                painter.setPen(QPen(border_color, border_width))
                painter.drawRoundedRect(x1, track_top + 2, seg_width, height - 4, 6, 6)
                
                # Resize Handles only visible on selected segment
                if is_selected:
                    # Left Handle
                    left_handle_rect = QRect(x1, track_top + 2, HANDLE_WIDTH, height - 4)
                    painter.setBrush(QBrush(QColor("#252932")))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawRoundedRect(left_handle_rect, 6, 6)
                    painter.fillRect(x1 + HANDLE_WIDTH // 2, track_top + 2, HANDLE_WIDTH // 2, height - 4, QColor("#252932"))
                    painter.setPen(QPen(QColor("#ffffff"), 1.5))
                    painter.drawLine(x1 + 3, track_top + height//2 - 6, x1 + 3, track_top + height//2 + 6)
                    painter.drawLine(x1 + 6, track_top + height//2 - 6, x1 + 6, track_top + height//2 + 6)
                    
                    # Right Handle
                    right_handle_rect = QRect(x2 - HANDLE_WIDTH, track_top + 2, HANDLE_WIDTH, height - 4)
                    painter.setBrush(QBrush(QColor("#252932")))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawRoundedRect(right_handle_rect, 6, 6)
                    painter.fillRect(x2 - HANDLE_WIDTH, track_top + 2, HANDLE_WIDTH // 2, height - 4, QColor("#252932"))
                    painter.setPen(QPen(QColor("#ffffff"), 1.5))
                    painter.drawLine(x2 - 4, track_top + height//2 - 6, x2 - 4, track_top + height//2 + 6)
                    painter.drawLine(x2 - 7, track_top + height//2 - 6, x2 - 7, track_top + height//2 + 6)

            # Draw Selection Region (if any)
            sel_bounds = self.resize_controller.get_selection_bounds()
            if sel_bounds:
                start_f, end_f = sel_bounds
                sx1 = self._frame_to_x(start_f, width) + track_left
                sx2 = self._frame_to_x(end_f, width) + track_left
                sel_w = max(2, sx2 - sx1)
                
                painter.setBrush(QBrush(QColor(59, 130, 246, 72)))
                painter.setPen(QPen(QColor("#3b82f6"), 2, Qt.PenStyle.SolidLine))
                painter.drawRoundedRect(sx1, track_top + 2, sel_w, height - 4, 6, 6)

            if mark_in is not None:
                mx = self._frame_to_x(mark_in, width) + track_left
                painter.setPen(QPen(QColor("#ef4444"), 2))
                painter.drawLine(mx, track_top, mx, track_top + height)
            if mark_out is not None:
                mx = self._frame_to_x(mark_out, width) + track_left
                painter.setPen(QPen(QColor("#ef4444"), 2))
                painter.drawLine(mx, track_top, mx, track_top + height)

            # Draw Playhead
            cursor_x = self._frame_to_x(self.cursor_frame, width) + track_left
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.drawLine(cursor_x, track_top, cursor_x, track_top + height)
            
            # Playhead triangle
            cursor_poly = QPolygon([
                QPoint(cursor_x - 6, track_top),
                QPoint(cursor_x + 6, track_top),
                QPoint(cursor_x, track_top + 8)
            ])
            painter.setBrush(QColor("#ffffff"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(cursor_poly)

        painter.end()

    def _hit_test(self, x: int) -> tuple[str, str | None]:
        if not self.timeline:
            return "empty", None
        segment, area = self._segment_at_pos(x)
        if segment is None:
            return "empty", None
        return area, segment.id

    def mousePressEvent(self, event) -> None:
        if not self.timeline:
            return
            
        if event.button() == Qt.MouseButton.LeftButton:
            MARGIN_X = 12
            x = event.position().x() - MARGIN_X
            width = max(1, self.width() - 2 * MARGIN_X)
            frame = self._x_to_frame(x, width)
            
            drag_mode, target_id = self._hit_test(x)
            if drag_mode == "empty":
                self.selected_segment_id = None
                self._drag_create_start = frame
                self._drag_create_end = frame
                self.cursorFrameChanged.emit(frame)
                self.selectionChanged.emit()
                self.grabMouse()
            else:
                self.selected_segment_id = target_id
                self.selectionChanged.emit()
                if drag_mode in ("body", "left_edge", "right_edge"):
                    mapped = {
                        "body": "move_segment",
                        "left_edge": "left_handle",
                        "right_edge": "right_handle",
                    }[drag_mode]
                    self.resize_controller.initiate_drag(self.timeline, frame, mapped, target_id)
                    self._drag_move_original = None
                    if target_id:
                        segment = self.timeline.segment_at_frame(frame)
                        if segment and segment.id == target_id:
                            self._drag_move_original = (segment.start_frame, segment.end_frame)
                    self.grabMouse()
                self.cursorFrameChanged.emit(frame)
            self.update()
            event.accept()
            
        elif event.button() == Qt.MouseButton.MiddleButton:
            self._pan_start_x = event.position().x()
            self.grabMouse()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        MARGIN_X = 12
        width = max(1, self.width() - 2 * MARGIN_X)
        
        if self.resize_controller.is_dragging:
            frame = self._x_to_frame(event.position().x() - MARGIN_X, width)
            emit_frame, altered = self.resize_controller.update_drag(self.timeline, frame)
            self.cursorFrameChanged.emit(emit_frame)
            if altered:
                self.selectionChanged.emit()
                self.update()
            event.accept()
        elif self._drag_create_start is not None:
            frame = self._x_to_frame(event.position().x() - MARGIN_X, width)
            self._drag_create_end = frame
            self.cursorFrameChanged.emit(frame)
            self.update()
            event.accept()
            
        elif event.buttons() & Qt.MouseButton.MiddleButton:
            # Panning
            delta_x = self._pan_start_x - event.position().x()
            delta_ratio = delta_x / width / self.zoom_controller.zoom_level
            self.zoom_controller.pan(delta_ratio)
            self._pan_start_x = event.position().x()
            self.update()
            event.accept()
            
        else:
            # Hover effects
            x = event.position().x() - MARGIN_X
            mode, _ = self._hit_test(x)
            if mode in ("left_handle", "right_handle"):
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            self._show_hover_preview(event.position().toPoint())
            event.accept()

    def leaveEvent(self, event) -> None:
        self._hide_hover_preview()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self.resize_controller.is_dragging:
            self.releaseMouse()
            mode = self.resize_controller.end_drag()
            if mode in {"move_segment", "left_handle", "right_handle"}:
                self.timeline.normalize_layer()
            self._drag_move_original = None
            self.update()
            event.accept()
        elif self._drag_create_start is not None:
            self.releaseMouse()
            start = min(self._drag_create_start, self._drag_create_end or self._drag_create_start)
            end = max(self._drag_create_start, self._drag_create_end or self._drag_create_start)
            if start == end:
                end = min(self.timeline.total_frames, start + 1)
            self.timeline.add_segment(start, end)
            self.timeline.normalize_layer()
            self.selected_segment_id = self.timeline.keep_segments[-1].id if self.timeline.keep_segments else None
            self._drag_create_start = None
            self._drag_create_end = None
            self.selectionChanged.emit()
            self.update()
            event.accept()

    def wheelEvent(self, event) -> None:
        if not self.timeline:
            return
            
        delta = event.angleDelta().y()
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Zoom timeline (future ready zoom support mapped to Ctrl + Wheel)
            MARGIN_X = 12
            width = max(1, self.width() - 2 * MARGIN_X)
            x = event.position().x() - MARGIN_X
            ratio = max(0.0, min(x / width, 1.0))
            self.zoom_controller.zoom_at(ratio, delta)
            self.update()
        elif event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            # Frame step
            step = 1 if delta > 0 else -1
            self.cursorFrameChanged.emit(self.cursor_frame + step)
        else:
            # Default scroll or zoom modifier
            super().wheelEvent(event)
            
        event.accept()

    def set_mark_in_from_cursor(self) -> None:
        if not self.timeline:
            return
        self.timeline.set_mark_in(self.cursor_frame)
        if not self.timeline.keep_segments:
            self.timeline.add_segment(self.cursor_frame, min(self.cursor_frame + 1, self.timeline.total_frames))
            self.selected_segment_id = self.timeline.keep_segments[-1].id
        else:
            segment = self.timeline.segment_at_frame(self.cursor_frame)
            if segment:
                self.selected_segment_id = segment.id
        self.selectionChanged.emit()
        self.update()

    def set_mark_out_from_cursor(self) -> None:
        if not self.timeline:
            return
        if self.timeline.mark_in_frame is None and not self.timeline.keep_segments:
            self.timeline.add_segment(0, max(1, self.cursor_frame))
        elif self.timeline.mark_in_frame is None:
            self.timeline.add_segment(0, max(1, self.cursor_frame))
        else:
            if self.timeline.mark_in_frame is not None:
                start = self.timeline.mark_in_frame
                end = self.cursor_frame
                if start == end:
                    end = min(self.timeline.total_frames, start + 1)
                self.timeline.add_segment(min(start, end), max(start, end))
                self.timeline.clear_mark_in()
        self.timeline.normalize_layer()
        self.selectionChanged.emit()
        self.update()


class TimelineWidget(QWidget):
    cursorFrameChanged = pyqtSignal(int)
    selectionChanged = pyqtSignal()
    
    # Forwarded Toolbar actions
    deleteRequested = pyqtSignal()
    replayRequested = pyqtSignal()
    saveFrameRequested = pyqtSignal()
    splitRequested = pyqtSignal()
    duplicateRequested = pyqtSignal()
    undoRequested = pyqtSignal()
    redoRequested = pyqtSignal()

    def __init__(self, timeline, parent=None):
        super().__init__(parent)
        self.timeline = timeline
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Permanent top header toolbar and inspector
        self.header_widget = TimelineHeaderWidget()
        layout.addWidget(self.header_widget)

        # Canvas
        self.canvas = TimelineCanvas()
        self.canvas.set_timeline(self.timeline)
        layout.addWidget(self.canvas)

        # Forward Canvas signals
        self.canvas.cursorFrameChanged.connect(self.cursorFrameChanged.emit)
        self.canvas.selectionChanged.connect(self._on_canvas_selection_changed)
        
        # Connect toolbar signals
        self.header_widget.deleteRequested.connect(self.deleteRequested.emit)
        self.header_widget.replayRequested.connect(self.replayRequested.emit)
        self.header_widget.saveFrameRequested.connect(self.saveFrameRequested.emit)
        self.header_widget.splitRequested.connect(self.splitRequested.emit)
        self.header_widget.duplicateRequested.connect(self.duplicateRequested.emit)
        self.header_widget.undoRequested.connect(self.undoRequested.emit)
        self.header_widget.redoRequested.connect(self.redoRequested.emit)

    def _on_canvas_selection_changed(self) -> None:
        self.refresh_state()
        self.selectionChanged.emit()

    def set_timeline(self, timeline) -> None:
        self.timeline = timeline
        self.canvas.set_timeline(timeline)
        self.refresh_state()

    def set_preview_source(self, engine) -> None:
        self.canvas.set_preview_source(engine)

    def set_cursor_frame(self, frame_index: int) -> None:
        frame_index = max(0, int(frame_index))
        self.canvas.set_cursor_frame(frame_index)
        self.refresh_state()

    def refresh_state(self) -> None:
        if not self.timeline:
            return
            
        # Verify selected segment still exists
        seg_ids = [s.id for s in self.timeline.keep_segments]
        if self.canvas.selected_segment_id not in seg_ids:
            self.canvas.selected_segment_id = None
            
        header = self.header_widget
        if self.canvas.selected_segment_id:
            # Find the segment
            selected_seg = next(s for s in self.timeline.keep_segments if s.id == self.canvas.selected_segment_id)
            start_tc = timecode_to_hmsf(selected_seg.start_frame, self.timeline.fps)
            end_tc = timecode_to_hmsf(selected_seg.end_frame, self.timeline.fps)
            dur_tc = timecode_to_hmsf(selected_seg.duration_frames, self.timeline.fps)
            header.set_segment_selected(True, start_tc, end_tc, dur_tc)
        else:
            header.set_segment_selected(False)
            
        self.canvas.update()
