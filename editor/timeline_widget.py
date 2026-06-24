from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QRect, QSize, QEvent
from PyQt6.QtGui import QColor, QPainter, QPen, QPolygon, QBrush, QPainterPath, QCursor, QIcon, QPixmap, QImage
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QFrame, QGridLayout

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


class SelectionActionBar(QFrame):
    removeRequested = pyqtSignal()
    segmentRequested = pyqtSignal()
    replayRequested = pyqtSignal()
    cancelRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SelectionActionBar")
        self.setStyleSheet("""
            QFrame#SelectionActionBar {
                background-color: #161920;
                border: 1px solid #262b37;
                border-radius: 12px;
            }
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        self.btn_remove = self._create_button(_make_icon("trash"), "Remove Region")
        self.btn_segment = self._create_button(_make_icon("segment"), "Keep Segment")
        self.btn_replay = self._create_button(_make_icon("replay"), "Replay Selection")
        self.btn_cancel = self._create_button(_make_icon("close"), "Cancel Selection")

        layout.addWidget(self.btn_remove)
        layout.addWidget(self.btn_segment)
        layout.addWidget(self.btn_replay)
        layout.addWidget(self.btn_cancel)
        layout.addStretch(1)
        
        self.btn_remove.clicked.connect(self.removeRequested.emit)
        self.btn_segment.clicked.connect(self.segmentRequested.emit)
        self.btn_replay.clicked.connect(self.replayRequested.emit)
        self.btn_cancel.clicked.connect(self.cancelRequested.emit)

    def _create_button(self, icon: QIcon, tooltip: str) -> QToolButton:
        btn = QToolButton()
        btn.setIcon(icon)
        btn.setIconSize(QSize(18, 18))
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(36, 36)
        btn.setStyleSheet("""
            QToolButton {
                color: #f3f4f6;
                background-color: #1f242f;
                border: 1px solid #262b37;
                border-radius: 8px;
            }
            QToolButton:hover {
                background-color: #2b3242;
                border-color: #6366f1;
            }
            QToolButton:pressed {
                background-color: #161920;
                border-color: #6366f1;
            }
        """)
        return btn

    def show_animated(self) -> None:
        from PyQt6.QtCore import QPropertyAnimation
        if hasattr(self, "_anim") and self._anim.state() == QPropertyAnimation.State.Running:
            self._anim.stop()
        
        self.setWindowOpacity(0.0)
        self.show()
        
        self._anim = QPropertyAnimation(self, b"windowOpacity")
        self._anim.setDuration(120)  # 100-150ms fade-in
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()


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
        self.setStyleSheet("""
            QFrame#HoverPreviewPopup {
                background-color: #1a1a1a;
                border: 1px solid #27272a;
                border-radius: 12px;
            }
            QLabel {
                color: #ffffff;
            }
            QLabel#HoverPreviewTitle {
                font-size: 13px;
                font-weight: 700;
            }
            QLabel#HoverPreviewMeta {
                color: #7d848e;
                font-size: 11px;
            }
        """)

        self.preview_label = QLabel()
        self.preview_label.setFixedSize(180, 102)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("""
            QLabel {
                background-color: #030303;
                border: 1px solid #27272a;
                border-radius: 8px;
            }
        """)

        self.title_label = QLabel("")
        self.title_label.setObjectName("HoverPreviewTitle")
        self.detail_label = QLabel("")
        self.detail_label.setObjectName("HoverPreviewMeta")
        self.meta_label = QLabel("")
        self.meta_label.setObjectName("HoverPreviewMeta")
        self.meta_label.setWordWrap(True)

        layout = QGridLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(6)
        layout.addWidget(self.preview_label, 0, 0, 3, 1)
        layout.addWidget(self.title_label, 0, 1)
        layout.addWidget(self.detail_label, 1, 1)
        layout.addWidget(self.meta_label, 2, 1)

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

        self.title_label.setText(data.title)
        self.detail_label.setText(data.detail)
        lines = [
            f"Timestamp: {data.timestamp}",
            f"Frame: {data.frame_number}",
        ]
        if data.duration:
            lines.append(f"Duration: {data.duration}")
        if data.excluded:
            lines.append("Excluded from export")
        self.meta_label.setText("\n".join(lines))


class TimelineCanvas(QWidget):
    cursorFrameChanged = pyqtSignal(int)
    selectionChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.timeline = None
        self.cursor_frame = 0
        self.preview_engine = None
        self.hover_preview = HoverPreviewPopup(self.window())
        self.hover_preview.hide()
        self._hover_visible = False
        
        # Caching for thumbnails
        self.thumb_frames: list[tuple[int, object]] = []
        self.thumb_cache_height = 40
        
        # Controllers
        self.resize_controller = SegmentResizeController()
        self.zoom_controller = TimelineZoomController()
        
        self.setMinimumHeight(80)
        self.setMouseTracking(True)
        self.selection_actions = None

    def set_timeline(self, timeline) -> None:
        self.timeline = timeline
        self.thumb_frames = []
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
        thumb_count = max(1, min(width // 80, total))
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

        window = self.window().geometry()
        target.setX(max(window.left() + 8, min(target.x(), window.right() - self.hover_preview.width() - 8)))
        target.setY(max(window.top() + 8, min(target.y(), window.bottom() - self.hover_preview.height() - 8)))
        self.hover_preview.move(target)
        if not self._hover_visible:
            self.hover_preview.show()
            self.hover_preview.raise_()
            self._hover_visible = True
        else:
            self.hover_preview.raise_()

    def clear_selection(self) -> None:
        self.resize_controller.clear_selection()
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
        painter.fillRect(rect, QColor("#000000"))
        
        MARGIN_X = 12
        MARGIN_Y = 12
        container_rect = rect.adjusted(MARGIN_X, MARGIN_Y, -MARGIN_X, -MARGIN_Y)
        
        # Track background
        width = max(1, container_rect.width())
        height = container_rect.height()
        track_top = container_rect.top()
        track_left = container_rect.left()
        
        painter.setClipRect(track_left, track_top, width, height)
        painter.fillRect(track_left, track_top, width, height, QColor("#1a1a1a"))

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
            painter.fillRect(track_left, track_top, width, height, QColor(0, 0, 0, 150))
            
            # Draw "Keep" Segments
            HANDLE_WIDTH = 8
            for segment in self.timeline.keep_segments:
                x1 = self._frame_to_x(segment.start_frame, width) + track_left
                x2 = self._frame_to_x(segment.end_frame, width) + track_left
                seg_width = max(2, x2 - x1)
                
                # Segment Body
                painter.fillRect(x1, track_top, seg_width, height, QColor(16, 185, 129, 80))
                painter.setPen(QPen(QColor("#10b981"), 1))
                painter.drawRect(x1, track_top, seg_width, height)
                
                # Left Handle
                left_handle_rect = QRect(x1, track_top, HANDLE_WIDTH, height)
                painter.fillRect(left_handle_rect, QColor("#27272a"))
                painter.setPen(QPen(QColor("#ffffff"), 1))
                painter.drawLine(x1 + 3, track_top + height//2 - 6, x1 + 3, track_top + height//2 + 6)
                painter.drawLine(x1 + 5, track_top + height//2 - 6, x1 + 5, track_top + height//2 + 6)
                
                # Right Handle
                right_handle_rect = QRect(x2 - HANDLE_WIDTH, track_top, HANDLE_WIDTH, height)
                painter.fillRect(right_handle_rect, QColor("#27272a"))
                painter.setPen(QPen(QColor("#ffffff"), 1))
                painter.drawLine(x2 - 5, track_top + height//2 - 6, x2 - 5, track_top + height//2 + 6)
                painter.drawLine(x2 - 3, track_top + height//2 - 6, x2 - 3, track_top + height//2 + 6)

            # Draw Selection Region (if any)
            sel_bounds = self.resize_controller.get_selection_bounds()
            if sel_bounds:
                start_f, end_f = sel_bounds
                sx1 = self._frame_to_x(start_f, width) + track_left
                sx2 = self._frame_to_x(end_f, width) + track_left
                sel_w = max(2, sx2 - sx1)
                painter.fillRect(sx1, track_top, sel_w, height, QColor(59, 130, 246, 72))
                painter.setPen(QPen(QColor("#3b82f6"), 1, Qt.PenStyle.DashLine))
                painter.drawRect(sx1, track_top, sel_w, height)

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
        """Returns (drag_mode, segment_id)."""
        if not self.timeline:
            return "drag_select", None
            
        MARGIN_X = 12
        width = max(1, self.width() - 2 * MARGIN_X)
        HANDLE_PX = 8
        
        # Check handles first (they have priority)
        for segment in self.timeline.keep_segments:
            x1 = self._frame_to_x(segment.start_frame, width)
            x2 = self._frame_to_x(segment.end_frame, width)
            
            if abs(x - x1) <= HANDLE_PX:
                return "left_handle", segment.id
            if abs(x - x2) <= HANDLE_PX:
                return "right_handle", segment.id

        # Empty space means playhead/select
        return "drag_select", None

    def mousePressEvent(self, event) -> None:
        if not self.timeline:
            return
            
        if event.button() == Qt.MouseButton.LeftButton:
            if self.selection_actions:
                self.selection_actions.setVisible(False)
            MARGIN_X = 12
            x = event.position().x() - MARGIN_X
            width = max(1, self.width() - 2 * MARGIN_X)
            frame = self._x_to_frame(x, width)
            
            drag_mode, target_id = self._hit_test(x)
            
            self.resize_controller.initiate_drag(self.timeline, frame, drag_mode, target_id)
            self.grabMouse()
            
            if drag_mode == "drag_select":
                self.cursorFrameChanged.emit(frame)
            
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
            
            if self.resize_controller.drag_mode == "drag_select":
                self.cursorFrameChanged.emit(emit_frame)
                
            if altered:
                self.selectionChanged.emit()
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

    def _position_floating_toolbar(self) -> None:
        if not hasattr(self, "floating_toolbar") or self.floating_toolbar is None:
            return
        sel = self.resize_controller.get_selection_bounds()
        if not sel or sel[1] <= sel[0]:
            return

        self.floating_toolbar.adjustSize()
        tw = self.floating_toolbar.width()
        th = self.floating_toolbar.height()

        MARGIN_X = 12
        width = max(1, self.width() - 2 * MARGIN_X)
        sx1 = self._frame_to_x(sel[0], width) + MARGIN_X
        sx2 = self._frame_to_x(sel[1], width) + MARGIN_X
        
        # Calculate track rectangle relative to canvas
        track_top = 12
        track_height = self.height() - 24

        # Map bounds to global coordinates
        top_left = self.mapToGlobal(QPoint(sx1, track_top))
        bottom_right = self.mapToGlobal(QPoint(sx2, track_top + track_height))
        sel_rect_global = QRect(top_left, bottom_right)

        # Get top-level window bounds
        window = self.window()
        window_rect = window.geometry()

        gap = 8
        sel_center_x = (sel_rect_global.left() + sel_rect_global.right()) // 2

        # 1. Above Selection
        x_above = sel_center_x - tw // 2
        x_above = max(window_rect.left() + gap, min(x_above, window_rect.right() - gap - tw))
        y_above = sel_rect_global.top() - th - gap
        if y_above >= window_rect.top() + gap:
            self.floating_toolbar.move(x_above, y_above)
            return

        # 2. Left of Selection
        x_left = sel_rect_global.left() - tw - gap
        y_left = (sel_rect_global.top() + sel_rect_global.bottom()) // 2 - th // 2
        y_left = max(window_rect.top() + gap, min(y_left, window_rect.bottom() - gap - th))
        if x_left >= window_rect.left() + gap:
            self.floating_toolbar.move(x_left, y_left)
            return

        # 3. Right of Selection
        x_right = sel_rect_global.right() + gap
        y_right = (sel_rect_global.top() + sel_rect_global.bottom()) // 2 - th // 2
        y_right = max(window_rect.top() + gap, min(y_right, window_rect.bottom() - gap - th))
        if x_right + tw <= window_rect.right() - gap:
            self.floating_toolbar.move(x_right, y_right)
            return

        # 4. Below Selection (or fallback to viewport bounds)
        x_below = sel_center_x - tw // 2
        x_below = max(window_rect.left() + gap, min(x_below, window_rect.right() - gap - tw))
        y_below = sel_rect_global.bottom() + gap
        y_below = max(window_rect.top() + gap, min(y_below, window_rect.bottom() - gap - th))
        self.floating_toolbar.move(x_below, y_below)

    def mouseReleaseEvent(self, event) -> None:
        self.releaseMouse()
        if self.resize_controller.is_dragging:
            mode = self.resize_controller.end_drag()
            if mode == "drag_select" and self.selection_actions:
                sel = self.resize_controller.get_selection_bounds()
                if sel and sel[1] > sel[0]:
                    self.selection_actions.setVisible(True)
                else:
                    self.resize_controller.clear_selection()
                    self.selection_actions.setVisible(False)
            self.update()
            event.accept()

    def wheelEvent(self, event) -> None:
        if not self.timeline:
            return
            
        delta = event.angleDelta().y()
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            # Frame step
            step = 1 if delta > 0 else -1
            self.cursorFrameChanged.emit(self.cursor_frame + step)
        else:
            # Zoom
            MARGIN_X = 12
            width = max(1, self.width() - 2 * MARGIN_X)
            x = event.position().x() - MARGIN_X
            ratio = max(0.0, min(x / width, 1.0))
            self.zoom_controller.zoom_at(ratio, delta)
            self.update()
            
        event.accept()


class TimelineWidget(QWidget):
    cursorFrameChanged = pyqtSignal(int)
    # Forward toolbar signals
    removeRequested = pyqtSignal(int, int)
    segmentRequested = pyqtSignal(int, int)
    replayRequested = pyqtSignal(int, int)

    def __init__(self, timeline, parent=None):
        super().__init__(parent)
        self.timeline = timeline
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        header = QHBoxLayout()
        self.label_time = QLabel("00:00:00")
        self.label_time.setStyleSheet("color: #f3f4f6; font-weight: 600; font-size: 14px;")
        
        self.state_label = QLabel("Ready")
        self.state_label.setStyleSheet("color: #9ca3af;")
        
        header.addWidget(self.label_time)
        header.addWidget(self.state_label)
        header.addStretch(1)
        layout.addLayout(header)

        self.selection_actions = SelectionActionBar()
        self.selection_actions.setVisible(False)
        self.canvas = TimelineCanvas()
        self.canvas.selection_actions = self.selection_actions
        self.selection_actions.removeRequested.connect(self._on_remove)
        self.selection_actions.segmentRequested.connect(self._on_segment)
        self.selection_actions.replayRequested.connect(self._on_replay)
        self.selection_actions.cancelRequested.connect(self.canvas.clear_selection)
        layout.addWidget(self.selection_actions)

        self.canvas.set_timeline(self.timeline)
        self.canvas.cursorFrameChanged.connect(self.cursorFrameChanged.emit)
        self.canvas.selectionChanged.connect(self.refresh_state)
        layout.addWidget(self.canvas)
        self.cursorFrameChanged.connect(self.set_cursor_frame)

    def _on_remove(self):
        sel = self.canvas.resize_controller.get_selection_bounds()
        if sel:
            self.removeRequested.emit(sel[0], sel[1])
            self.canvas.clear_selection()

    def _on_segment(self):
        sel = self.canvas.resize_controller.get_selection_bounds()
        if sel:
            self.segmentRequested.emit(sel[0], sel[1])
            self.canvas.clear_selection()
            
    def _on_replay(self):
        sel = self.canvas.resize_controller.get_selection_bounds()
        if sel:
            self.replayRequested.emit(sel[0], sel[1])

    def set_timeline(self, timeline) -> None:
        self.timeline = timeline
        self.canvas.set_timeline(timeline)
        self.set_cursor_frame(0)
        self.refresh_state()

    def set_preview_source(self, engine) -> None:
        self.canvas.set_preview_source(engine)

    def set_cursor_frame(self, frame_index: int) -> None:
        frame_index = max(0, int(frame_index))
        self.canvas.set_cursor_frame(frame_index)
        
        timecode = "00:00:00"
        if self.timeline:
            timecode = self.timeline.timecode(frame_index)
            
        self.label_time.setText(f"{timecode} | Frame {frame_index}")
        self.refresh_state()

    def refresh_state(self) -> None:
        if not self.timeline:
            return
            
        sel = self.canvas.resize_controller.get_selection_bounds()
        if sel:
            self.state_label.setText(f"Selected: {sel[0]} - {sel[1]}")
            self.selection_actions.setVisible(True)
            return
            
        segment_count = len(self.timeline.keep_segments)
        self.selection_actions.setVisible(False)
        if segment_count:
            self.state_label.setText(f"{segment_count} segment(s) ready")
        else:
            self.state_label.setText("Ready")
