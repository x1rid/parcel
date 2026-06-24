from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QRect, QSize
from PyQt6.QtGui import QColor, QPainter, QPen, QPolygon, QBrush, QPainterPath, QCursor, QIcon, QPixmap
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QFrame

from .segment_resize_controller import SegmentResizeController
from .timeline_zoom_controller import TimelineZoomController


class FloatingToolbar(QFrame):
    removeRequested = pyqtSignal()
    segmentRequested = pyqtSignal()
    replayRequested = pyqtSignal()
    cancelRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("FloatingToolbar")
        
        # Make the toolbar float globally without window frame or stealing focus
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        
        # Steam-inspired styling: Background #161B22, Border #21262D, Accent #58A6FF, Radius 10px
        self.setStyleSheet("""
            QFrame#FloatingToolbar {
                background-color: #161B22;
                border: 2px solid #21262D;
                border-radius: 10px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        
        self.btn_remove = self._create_steamy_button("✂", "Remove Region")
        self.btn_segment = self._create_steamy_button("📎", "Keep Segment")
        self.btn_replay = self._create_steamy_button("↺", "Replay Selection")
        self.btn_cancel = self._create_steamy_button("❌", "Cancel Selection")
        
        layout.addWidget(self.btn_remove)
        layout.addWidget(self.btn_segment)
        layout.addWidget(self.btn_replay)
        layout.addWidget(self.btn_cancel)
        
        self.btn_remove.clicked.connect(self.removeRequested.emit)
        self.btn_segment.clicked.connect(self.segmentRequested.emit)
        self.btn_replay.clicked.connect(self.replayRequested.emit)
        self.btn_cancel.clicked.connect(self.cancelRequested.emit)

        # Slight drop shadow for premium depth
        from PyQt6.QtWidgets import QGraphicsDropShadowEffect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

    def _create_steamy_button(self, icon_text: str, tooltip: str) -> QToolButton:
        btn = QToolButton()
        btn.setText(icon_text)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(32, 32)
        btn.setStyleSheet("""
            QToolButton {
                color: #d7dce3;
                background-color: #21262D;
                border: 1px solid #30363D;
                border-radius: 6px;
                font-size: 16px;
            }
            QToolButton:hover {
                background-color: #30363D;
                border-color: #58A6FF;
                color: #58A6FF;
            }
            QToolButton:pressed {
                background-color: #161B22;
                border-color: #58A6FF;
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


class TimelineCanvas(QWidget):
    cursorFrameChanged = pyqtSignal(int)
    selectionChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.timeline = None
        self.cursor_frame = 0
        self.preview_engine = None
        
        # Caching for thumbnails
        self.thumb_frames: list[tuple[int, object]] = []
        self.thumb_cache_height = 40
        
        # Controllers
        self.resize_controller = SegmentResizeController()
        self.zoom_controller = TimelineZoomController()
        
        self.setMinimumHeight(80)
        self.setMouseTracking(True)
        
        # UI Elements
        self.floating_toolbar = FloatingToolbar(self)
        self.floating_toolbar.hide()
        
        # Connect toolbar signals
        self.floating_toolbar.cancelRequested.connect(self.clear_selection)

    def set_timeline(self, timeline) -> None:
        self.timeline = timeline
        self.thumb_frames = []
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
            from PyQt6.QtGui import QImage, QPixmap
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

    def clear_selection(self) -> None:
        self.resize_controller.clear_selection()
        self.floating_toolbar.hide()
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
        painter.fillRect(rect, QColor("#0f1115"))
        
        MARGIN_X = 12
        MARGIN_Y = 12
        container_rect = rect.adjusted(MARGIN_X, MARGIN_Y, -MARGIN_X, -MARGIN_Y)
        
        # Track background
        width = max(1, container_rect.width())
        height = container_rect.height()
        track_top = container_rect.top()
        track_left = container_rect.left()
        
        painter.setClipRect(track_left, track_top, width, height)
        painter.fillRect(track_left, track_top, width, height, QColor("#1c2028"))

        if self.timeline and self.timeline.total_frames > 0:
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
                painter.fillRect(x1, track_top, seg_width, height, QColor(102, 192, 244, 90))
                painter.setPen(QPen(QColor("#66c0f4"), 2))
                painter.drawRect(x1, track_top, seg_width, height)
                
                # Left Handle
                left_handle_rect = QRect(x1, track_top, HANDLE_WIDTH, height)
                painter.fillRect(left_handle_rect, QColor("#3b82f6"))
                painter.setPen(QPen(QColor("#ffffff"), 1))
                painter.drawLine(x1 + 3, track_top + height//2 - 6, x1 + 3, track_top + height//2 + 6)
                painter.drawLine(x1 + 5, track_top + height//2 - 6, x1 + 5, track_top + height//2 + 6)
                
                # Right Handle
                right_handle_rect = QRect(x2 - HANDLE_WIDTH, track_top, HANDLE_WIDTH, height)
                painter.fillRect(right_handle_rect, QColor("#3b82f6"))
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
                painter.fillRect(sx1, track_top, sel_w, height, QColor(245, 185, 66, 70))
                painter.setPen(QPen(QColor("#f5b942"), 2, Qt.PenStyle.DashLine))
                painter.drawRect(sx1, track_top, sel_w, height)

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
            self.floating_toolbar.hide()
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

    def _position_floating_toolbar(self) -> None:
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
            
            # If drag_select finished and spans multiple frames, show toolbar
            if mode == "drag_select":
                sel = self.resize_controller.get_selection_bounds()
                if sel and sel[1] > sel[0]:
                    self._position_floating_toolbar()
                    self.floating_toolbar.raise_()
                    self.floating_toolbar.show_animated()
                else:
                    self.resize_controller.clear_selection()
            
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
        layout.setSpacing(6)

        header = QHBoxLayout()
        self.label_time = QLabel("00:00:00")
        self.label_time.setStyleSheet("color: #d6dce4; font-weight: 600; font-size: 14px;")
        
        self.state_label = QLabel("Ready")
        self.state_label.setStyleSheet("color: #9aa5b1;")
        
        header.addWidget(self.label_time)
        header.addWidget(self.state_label)
        header.addStretch(1)
        layout.addLayout(header)

        self.canvas = TimelineCanvas()
        self.canvas.set_timeline(self.timeline)
        self.canvas.cursorFrameChanged.connect(self.cursorFrameChanged.emit)
        self.canvas.selectionChanged.connect(self.refresh_state)
        
        # Connect canvas toolbar signals
        self.canvas.floating_toolbar.removeRequested.connect(self._on_remove)
        self.canvas.floating_toolbar.segmentRequested.connect(self._on_segment)
        self.canvas.floating_toolbar.replayRequested.connect(self._on_replay)
        
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
            return
            
        segment_count = len(self.timeline.keep_segments)
        if segment_count:
            self.state_label.setText(f"{segment_count} segment(s) ready")
        else:
            self.state_label.setText("Ready")