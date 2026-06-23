from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QColor, QPainter, QPen, QPolygon
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class TimelineCanvas(QWidget):
    cursorFrameChanged = pyqtSignal(int)
    selectionChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.timeline = None
        self.cursor_frame = 0
        self.zoom_mode = "overview"
        self.flash_message = ""
        self.preview_engine = None
        self.thumb_frames: list[tuple[int, object]] = []
        self.thumb_cache_height = 30
        self._dragging = False
        self._drag_mode = None
        self._drag_start_frame = 0
        self._drag_start_mark_in = None
        self._drag_start_mark_out = None
        self.setMinimumHeight(56)
        self.setMaximumHeight(90)
        self.setMouseTracking(True)
        self._hover_frame = None

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
        thumb_count = max(1, min(width // 70, total))
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

    def set_zoom_mode(self, mode: str) -> None:
        self.zoom_mode = mode
        self.update()

    def set_flash_message(self, message: str) -> None:
        self.flash_message = message
        self.update()

    def _frame_to_x(self, frame_index: int, width: int) -> int:
        if not self.timeline or self.timeline.total_frames <= 0:
            return 0
        usable_frames = max(1, self.timeline.total_frames - 1)
        ratio = max(0.0, min(frame_index / usable_frames, 1.0))
        return int(ratio * width)

    def _x_to_frame(self, x: int, width: int) -> int:
        if not self.timeline or self.timeline.total_frames <= 0:
            return 0
        ratio = max(0.0, min(x / max(width, 1), 1.0))
        usable_frames = max(1, self.timeline.total_frames - 1)
        return int(round(ratio * usable_frames))

    def _selection_bounds(self):
        mark_in = getattr(self.timeline, "mark_in_frame", None)
        mark_out = getattr(self.timeline, "mark_out_frame", None)
        if mark_in is None or mark_out is None:
            return None
        return min(mark_in, mark_out), max(mark_in, mark_out)

    def _clamp_frame(self, frame: int) -> int:
        if not self.timeline:
            return max(0, int(frame))
        return max(0, min(int(frame), max(0, self.timeline.total_frames - 1)))

    def _set_selection(self, mark_in: int, mark_out: int) -> None:
        if not self.timeline:
            return
        self.timeline.mark_in_frame = self._clamp_frame(mark_in)
        self.timeline.mark_out_frame = self._clamp_frame(mark_out)
        if self.timeline.mark_in_frame > self.timeline.mark_out_frame:
            self.timeline.mark_in_frame, self.timeline.mark_out_frame = self.timeline.mark_out_frame, self.timeline.mark_in_frame
        self.selectionChanged.emit()
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect()
        painter.fillRect(rect, QColor("#0f1115"))
        
        MARGIN_X = 12
        MARGIN_Y = 8

        # Draw container
        container_rect = rect.adjusted(MARGIN_X, MARGIN_Y, -MARGIN_X, -MARGIN_Y)
        painter.setPen(QPen(QColor("#2a3240"), 1))
        painter.setBrush(QColor("#181c24"))
        painter.drawRoundedRect(container_rect, 4, 4)

        width = max(1, container_rect.width())
        height = container_rect.height()
        track_top = container_rect.top()
        track_height = height
        track_left = container_rect.left()

        painter.fillRect(track_left, track_top, width, track_height, QColor("#20242d"))

        if self.timeline and self.timeline.total_frames > 0:
            keep_segments = self.timeline.flatten_layers() if hasattr(self.timeline, "flatten_layers") else list(self.timeline.keep_segments)
            self._paint_gap_regions(painter, keep_segments, width, track_top, track_height, track_left)
            self._paint_thumbnails(painter, width, track_top, track_height, track_left)

            for segment in keep_segments:
                x1 = self._frame_to_x(segment.start_frame, width) + track_left
                x2 = self._frame_to_x(segment.end_frame, width) + track_left
                bar_width = max(2, x2 - x1)
                painter.fillRect(x1, track_top, bar_width, track_height, QColor(102, 192, 244, 56))
                painter.setPen(QPen(QColor("#66c0f4"), 1))
                painter.drawRect(x1, track_top, bar_width, track_height)

            # Draw marks and handles
            if getattr(self.timeline, "mark_in_frame", None) is not None:
                mark_x = self._frame_to_x(self.timeline.mark_in_frame, width) + track_left
                selection_end = self.timeline.mark_out_frame if getattr(self.timeline, "mark_out_frame", None) is not None else self.cursor_frame
                sel_x2 = self._frame_to_x(selection_end, width) + track_left
                left = min(mark_x, sel_x2)
                right = max(mark_x, sel_x2)
                painter.fillRect(left, track_top, max(2, right - left), track_height, QColor(245, 185, 66, 36))
                
                # Mark In Handle
                painter.setPen(QPen(QColor("#f5b942"), 2))
                painter.drawLine(mark_x, track_top, mark_x, track_top + track_height)
                # Triangle handle pointing right
                in_poly = QPolygon([
                    QPoint(mark_x, track_top + track_height),
                    QPoint(mark_x + 8, track_top + track_height),
                    QPoint(mark_x, track_top + track_height - 8)
                ])
                painter.setBrush(QColor("#f5b942"))
                painter.drawPolygon(in_poly)

                if getattr(self.timeline, "mark_out_frame", None) is not None:
                    mark_out_x = self._frame_to_x(self.timeline.mark_out_frame, width) + track_left
                    # Mark Out Handle
                    painter.setPen(QPen(QColor("#4ea1ff"), 2))
                    painter.drawLine(mark_out_x, track_top, mark_out_x, track_top + track_height)
                    # Triangle handle pointing left
                    out_poly = QPolygon([
                        QPoint(mark_out_x, track_top + track_height),
                        QPoint(mark_out_x - 8, track_top + track_height),
                        QPoint(mark_out_x, track_top + track_height - 8)
                    ])
                    painter.setBrush(QColor("#4ea1ff"))
                    painter.drawPolygon(out_poly)

            # Ticks
            painter.setPen(QPen(QColor("#7f8aa3"), 1))
            tick_count = 12 if self.zoom_mode == "overview" else 24 if self.zoom_mode == "seconds" else 48
            for index in range(tick_count + 1):
                frame = int((self.timeline.total_frames / tick_count) * index)
                x = self._frame_to_x(frame, width) + track_left
                tick_height = 8 if index % 2 == 0 else 4
                painter.drawLine(x, track_top, x, track_top + tick_height)
                if self.zoom_mode != "overview" and index % 2 == 0:
                    painter.drawText(x + 2, track_top + 10, str(frame))

            # Cursor
            cursor_x = self._frame_to_x(self.cursor_frame, width) + track_left
            painter.setPen(QPen(QColor("#ffffff"), 1))
            painter.drawLine(cursor_x, track_top, cursor_x, track_top + track_height)
            # Inverted triangle at top
            cursor_poly = QPolygon([
                QPoint(cursor_x - 4, track_top),
                QPoint(cursor_x + 4, track_top),
                QPoint(cursor_x, track_top + 6)
            ])
            painter.setBrush(QColor("#ffffff"))
            painter.drawPolygon(cursor_poly)
            
            painter.setPen(QPen(QColor("#ffffff"), 1))
            painter.drawText(cursor_x + 6, track_top + track_height - 4, f"{self.cursor_frame}")

            if self.flash_message:
                painter.setPen(QPen(QColor("#9fe870"), 1))
                painter.drawText(track_left + 4, track_top + track_height - 4, self.flash_message)

        painter.end()

    def _paint_thumbnails(self, painter, width: int, track_top: int, track_height: int, track_left: int) -> None:
        if not self.thumb_frames:
            return

        for frame_index, thumb in self.thumb_frames:
            if thumb is None:
                continue
            x = self._frame_to_x(frame_index, width) + track_left
            thumb_width = max(20, int(thumb.width()))
            y = track_top + max(2, (track_height - thumb.height()) // 2)
            painter.drawPixmap(x - thumb_width // 2, y, thumb)

    def _paint_gap_regions(self, painter, keep_segments, width: int, track_top: int, track_height: int, track_left: int) -> None:
        if not keep_segments:
            painter.fillRect(track_left, track_top, width, track_height, QColor(169, 68, 66, 46))
            return

        prev_end = 0
        for segment in keep_segments:
            if segment.start_frame > prev_end:
                left = self._frame_to_x(prev_end, width) + track_left
                right = self._frame_to_x(segment.start_frame, width) + track_left
                painter.fillRect(left, track_top, max(1, right - left), track_height, QColor(169, 68, 66, 56))
            prev_end = max(prev_end, segment.end_frame)
        if prev_end < getattr(self.timeline, "total_frames", 0):
            left = self._frame_to_x(prev_end, width) + track_left
            right = track_left + width
            painter.fillRect(left, track_top, max(1, right - left), track_height, QColor(169, 68, 66, 56))

    def mousePressEvent(self, event) -> None:
        if not self.timeline:
            return
        MARGIN_X = 12
        x = event.position().x() - MARGIN_X
        width = max(1, self.width() - 2 * MARGIN_X)
        frame = self._x_to_frame(x, width)
        self._drag_mode = "cursor"
        self._drag_start_frame = frame
        self._drag_start_mark_in = getattr(self.timeline, "mark_in_frame", None)
        self._drag_start_mark_out = getattr(self.timeline, "mark_out_frame", None)

        selection = self._selection_bounds()
        if selection is not None:
            left_frame, right_frame = selection
            left_x = self._frame_to_x(left_frame, width) + MARGIN_X
            right_x = self._frame_to_x(right_frame, width) + MARGIN_X
            if abs(event.position().x() - left_x) <= 7:
                self._drag_mode = "mark_in"
            elif abs(event.position().x() - right_x) <= 7:
                self._drag_mode = "mark_out"
            elif left_x < event.position().x() < right_x:
                self._drag_mode = "selection"

        if self._drag_mode in {"mark_in", "mark_out", "selection"}:
            self._dragging = True
            self.grabMouse()
            event.accept()
            return

        self._dragging = True
        self.grabMouse()
        self.cursorFrameChanged.emit(frame)
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        MARGIN_X = 12
        width = max(1, self.width() - 2 * MARGIN_X)
        
        if (self._dragging or event.buttons() & Qt.MouseButton.LeftButton) and self.timeline:
            frame = self._x_to_frame(event.position().x() - MARGIN_X, width)
            if self._drag_mode == "mark_in" and self._drag_start_mark_out is not None:
                mark_in = self._clamp_frame(frame)
                mark_out = self._clamp_frame(self._drag_start_mark_out)
                self._set_selection(mark_in, mark_out)
                self.cursorFrameChanged.emit(frame)
            elif self._drag_mode == "mark_out" and self._drag_start_mark_in is not None:
                mark_in = self._clamp_frame(self._drag_start_mark_in)
                mark_out = self._clamp_frame(frame)
                self._set_selection(mark_in, mark_out)
                self.cursorFrameChanged.emit(frame)
            elif self._drag_mode == "selection" and self._drag_start_mark_in is not None and self._drag_start_mark_out is not None:
                start = min(self._drag_start_mark_in, self._drag_start_mark_out)
                end = max(self._drag_start_mark_in, self._drag_start_mark_out)
                span = end - start
                new_start = self._clamp_frame(start + (frame - self._drag_start_frame))
                new_end = new_start + span
                if new_end > max(0, self.timeline.total_frames - 1):
                    new_end = max(0, self.timeline.total_frames - 1)
                    new_start = max(0, new_end - span)
                self._set_selection(new_start, new_end)
                self.cursorFrameChanged.emit(frame)
            else:
                self.cursorFrameChanged.emit(frame)
            event.accept()
        else:
            # Hover effects
            if self.timeline:
                frame = self._x_to_frame(event.position().x() - MARGIN_X, width)
                self.setToolTip(f"Frame: {frame}")
                
                # Check cursor icon
                selection = self._selection_bounds()
                is_near_handle = False
                if selection is not None:
                    left_frame, right_frame = selection
                    left_x = self._frame_to_x(left_frame, width) + MARGIN_X
                    right_x = self._frame_to_x(right_frame, width) + MARGIN_X
                    if abs(event.position().x() - left_x) <= 7 or abs(event.position().x() - right_x) <= 7:
                        is_near_handle = True
                
                if is_near_handle:
                    self.setCursor(Qt.CursorShape.SizeHorCursor)
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event) -> None:
        if self._dragging:
            self._dragging = False
            self.releaseMouse()
        if self.timeline:
            MARGIN_X = 12
            frame = self._x_to_frame(event.position().x() - MARGIN_X, max(1, self.width() - 2 * MARGIN_X))
            if self._drag_mode == "cursor":
                self.cursorFrameChanged.emit(frame)
            elif self._drag_mode in {"mark_in", "mark_out", "selection"}:
                self.selectionChanged.emit()
        self._drag_mode = None
        event.accept()


class TimelineWidget(QWidget):
    cursorFrameChanged = pyqtSignal(int)

    def __init__(self, timeline, parent=None):
        super().__init__(parent)
        self.timeline = timeline
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header = QHBoxLayout()
        self.label_time = QLabel("Frame 0 | 00:00:00.00")
        self.label_time.setStyleSheet("color: #d6dce4; font-weight: 600;")
        self.state_label = QLabel("Ready")
        self.state_label.setObjectName("Muted")
        self.state_label.setStyleSheet("color: #9aa5b1;")
        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(["overview", "seconds", "frames"])
        self.zoom_combo.setCurrentText("overview")
        header.addWidget(self.label_time)
        header.addWidget(self.state_label)
        header.addStretch(1)
        header.addWidget(self.zoom_combo)
        layout.addLayout(header)

        self.canvas = TimelineCanvas()
        self.canvas.set_timeline(self.timeline)
        self.canvas.cursorFrameChanged.connect(self.cursorFrameChanged.emit)
        self.canvas.selectionChanged.connect(self.refresh_state)
        layout.addWidget(self.canvas)

        self.zoom_combo.currentTextChanged.connect(self.canvas.set_zoom_mode)
        self.cursorFrameChanged.connect(self.set_cursor_frame)

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
        timestamp = "00:00:00.00"
        fps = getattr(self.timeline, "fps", 0.0) or 0.0
        if fps > 0:
            total_seconds = frame_index / fps
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            seconds = total_seconds % 60
            timestamp = f"{hours:02d}:{minutes:02d}:{seconds:05.2f}"
        self.label_time.setText(f"Frame {frame_index} | {timestamp}")
        self.canvas.update()
        self.refresh_state()

    def refresh_state(self, flash_message: str = "") -> None:
        if flash_message:
            self.state_label.setText(flash_message)
            self.canvas.set_flash_message(flash_message)
            return

        if getattr(self.timeline, "mark_in_frame", None) is not None:
            if getattr(self.timeline, "mark_out_frame", None) is not None:
                self.state_label.setText(
                    f"Selection ready: {self.timeline.mark_in_frame} - {self.timeline.mark_out_frame} | Press Cut"
                )
                self.canvas.set_flash_message("")
            else:
                self.state_label.setText(f"Mark In set at frame {self.timeline.mark_in_frame}")
                self.canvas.set_flash_message("")
            return

        segment_count = len(self.timeline.flatten_layers() if hasattr(self.timeline, "flatten_layers") else getattr(self.timeline, "keep_segments", []))
        if segment_count:
            self.state_label.setText(f"{segment_count} segment(s) ready")
        else:
            self.state_label.setText("Ready")
        self.canvas.set_flash_message("")
