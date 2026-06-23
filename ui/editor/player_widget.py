from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, QElapsedTimer, pyqtSignal, QUrl, QCoreApplication
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen, QColor
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QWidget, QComboBox


class LoadingSpinner(QWidget):
    """A self-contained, smooth vector-drawn loading animation."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(50, 50)
        # Prevent blocking clicks through the overlay loader
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._rotate)
        self.timer.setInterval(30)
        self.hide()

    def _rotate(self):
        self.angle = (self.angle + 12) % 360
        self.update()

    def showEvent(self, event):
        self.timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw a beautiful dark translucent circular background backing
        painter.setBrush(QColor(15, 17, 21, 220))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 12, 12)
        
        # Setup an elegant accent blue arc pen
        pen = QPen(QColor("#3b82f6"))
        pen.setWidth(4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        
        rect = self.rect().adjusted(10, 10, -10, -10)
        painter.drawArc(rect, -self.angle * 16, 100 * 16)


class PreviewPlayerWidget(QWidget):
    frameChanged = pyqtSignal(int)
    playbackFinished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.engine = None
        self.current_frame_index = 0
        self._current_pixmap = None
        self._media_path = None
        self._segment_ranges: list[tuple[int, int]] | None = None
        self._segment_index = 0
        self._preview_scale_factor = 0.25
        self._quality_manual_override = False
        self._playback_clock = QElapsedTimer()
        self._playback_start_frame = 0
        self._last_frame_rgb = None
        self._setup_ui()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.next_frame)
        self.audio_output = QAudioOutput(self)
        self.media_player = QMediaPlayer(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.playbackStateChanged.connect(self._on_playback_state_changed)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.video_frame_label = QLabel("Drop a video to begin")
        self.video_frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_frame_label.setMinimumSize(640, 360)
        self.video_frame_label.setStyleSheet(
            "background: #0f1115; color: #d7dce3; border: 1px solid #2a2f3a; border-radius: 8px;"
        )
        layout.addWidget(self.video_frame_label, stretch=1)

        # Initialize and position our custom loader overlay centered inside video label container
        self.loading_spinner = LoadingSpinner(self.video_frame_label)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)
        self.frame_label = QLabel("Frame: 0")
        self.time_label = QLabel("00:00:00.00")
        self.fps_label = QLabel("0.00 fps")
        for label in (self.frame_label, self.time_label, self.fps_label):
            label.setStyleSheet("color: #aeb7c2;")
            meta_row.addWidget(label)
            
        meta_row.addStretch(1)
        
        preview_qual_label = QLabel("Preview Quality:")
        preview_qual_label.setStyleSheet("color: #aeb7c2;")
        meta_row.addWidget(preview_qual_label)
        
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Full", "1/2", "1/4", "1/8"])
        self.quality_combo.setCurrentText("1/4")
        self.quality_combo.currentTextChanged.connect(self._on_quality_changed)
        meta_row.addWidget(self.quality_combo)
        
        self.quality_label = QLabel("")
        self.quality_label.setStyleSheet("color: #aeb7c2;")
        meta_row.addWidget(self.quality_label)
        
        layout.addLayout(meta_row)

    def _on_quality_changed(self, text: str) -> None:
        self._quality_manual_override = True
        mapping = {"Full": 1.0, "1/2": 0.5, "1/4": 0.25, "1/8": 0.125}
        self._preview_scale_factor = mapping.get(text, 1.0)
        if self._last_frame_rgb is not None:
            self._display_frame_array(self._last_frame_rgb, self.current_frame_index)

    def _apply_default_preview_quality(self) -> None:
        if self._quality_manual_override or not self.engine:
            return
        max_dim = max(int(getattr(self.engine, "source_width", 0) or 0), int(getattr(self.engine, "source_height", 0) or 0))
        if max_dim >= 3840:
            default_quality = "1/8"
        elif max_dim >= 1920:
            default_quality = "1/4"
        elif max_dim >= 1280:
            default_quality = "1/2"
        else:
            default_quality = "Full"
        self.quality_combo.blockSignals(True)
        self.quality_combo.setCurrentText(default_quality)
        self.quality_combo.blockSignals(False)
        self._preview_scale_factor = {"Full": 1.0, "1/2": 0.5, "1/4": 0.25, "1/8": 0.125}[default_quality]

    def set_engine(self, engine) -> None:
        self.engine = engine
        if not engine:
            return
        self._apply_default_preview_quality()
        interval_ms = max(1, int(round(1000 / max(engine.fps, 1.0))))
        self.timer.setInterval(interval_ms)
        self.show_frame(0)

    def set_media_source(self, media_path: str) -> None:
        self._media_path = media_path
        if media_path:
            self.media_player.setSource(QUrl.fromLocalFile(media_path))

    def show_frame(self, frame_index: int) -> None:
        if not self.engine or self.engine.total_frames <= 0:
            return
        safe_index = max(0, min(int(frame_index), self.engine.total_frames - 1))
        frame_rgb = self.engine.get_exact_frame(safe_index)
        if frame_rgb is None:
            return
        self._display_frame_array(frame_rgb, safe_index)

    def _update_metadata(self) -> None:
        if not self.engine:
            return
        self.frame_label.setText(f"Frame: {self.current_frame_index}")
        self.time_label.setText(self.engine.frame_timecode(self.current_frame_index))
        self.fps_label.setText(f"{self.engine.fps:.2f} fps")

    def play(self) -> None:
        if self.engine:
            self._segment_ranges = None
            self._playback_start_frame = self.current_frame_index
            self._playback_clock.restart()
            if self._media_path:
                self.media_player.play()
            self.timer.start()

    def play_segment_ranges(self, ranges: list[tuple[int, int]]) -> None:
        if not self.engine:
            return
        normalized = []
        for start, end in ranges:
            start = max(0, int(start))
            end = max(0, int(end))
            if end > start:
                normalized.append((start, end))
        normalized.sort(key=lambda item: (item[0], item[1]))
        if not normalized:
            self.seek_to_frame(0)
            self.play()
            return

        self._segment_ranges = normalized
        self._segment_index = 0
        start_frame = normalized[0][0]
        self.seek_to_frame(start_frame)
        self._playback_start_frame = start_frame
        self._playback_clock.restart()
        if self._media_path:
            self.media_player.play()
        self.timer.start()

    def pause(self) -> None:
        self.timer.stop()
        if self._media_path:
            self.media_player.pause()
        self._apply_scaled_pixmap()

    def step(self, direction: int) -> None:
        if not self.engine:
            return
        self.pause()
        next_frame = self.current_frame_index + int(direction)
        self.show_frame(next_frame)
        if self._media_path:
            self.media_player.setPosition(int((self.current_frame_index / max(self.engine.fps, 1.0)) * 1000))

    def next_frame(self) -> None:
        if not self.engine:
            return
        fps = max(self.engine.fps, 1.0)
        elapsed_ms = self._playback_clock.elapsed() if self._playback_clock.isValid() else 0
        target_frame = self._playback_start_frame + int((elapsed_ms / 1000.0) * fps)
        target_frame = max(0, min(target_frame, self.engine.total_frames - 1))
        if self._segment_ranges:
            current_start, current_end = self._segment_ranges[min(self._segment_index, len(self._segment_ranges) - 1)]
            if target_frame < current_start:
                target_frame = current_start
            if target_frame >= current_end:
                self._segment_index += 1
                if self._segment_index >= len(self._segment_ranges):
                    self.pause()
                    self._segment_ranges = None
                    self.playbackFinished.emit()
                    return
                next_start = self._segment_ranges[self._segment_index][0]
                self.show_frame(next_start)
                self._playback_start_frame = next_start
                self._playback_clock.restart()
                if self._media_path:
                    self.media_player.setPosition(int((next_start / fps) * 1000))
                return
            if target_frame > self.current_frame_index + 1:
                self.show_frame(target_frame)
                self._playback_start_frame = target_frame
                self._playback_clock.restart()
                if self._media_path:
                    self.media_player.setPosition(int((target_frame / fps) * 1000))
                return
            frame_rgb = self.engine.read_next_playback_frame()
            if frame_rgb is None:
                self.pause()
                self._segment_ranges = None
                self.playbackFinished.emit()
                return
            self._display_frame_array(frame_rgb, self.engine.current_frame_index)
            return
        if self._media_path:
            if target_frame > self.current_frame_index + 1:
                self.show_frame(target_frame)
                self._playback_start_frame = target_frame
                self._playback_clock.restart()
                self.media_player.setPosition(int((target_frame / fps) * 1000))
                return
            frame_rgb = self.engine.read_next_playback_frame()
            if frame_rgb is None:
                self.pause()
                self.playbackFinished.emit()
                return
            self._display_frame_array(frame_rgb, self.engine.current_frame_index)
            return

        next_frame = target_frame if target_frame > self.current_frame_index else self.current_frame_index + 1
        if next_frame >= self.engine.total_frames:
            self.pause()
            self.playbackFinished.emit()
            return
        self.show_frame(next_frame)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_scaled_pixmap()
        # Ensure loading spinner stays precisely centered on window resizing
        if hasattr(self, "loading_spinner"):
            self.loading_spinner.move(
                (self.video_frame_label.width() - self.loading_spinner.width()) // 2,
                (self.video_frame_label.height() - self.loading_spinner.height()) // 2
            )

    def seek_to_frame(self, frame_index: int, play_audio: bool = False) -> None:
        if not self.engine:
            return
        frame_index = max(0, min(int(frame_index), max(0, self.engine.total_frames - 1)))
        self.pause()
        
        # CONDITIONAL LOADING: Check if the frame is already in memory cache.
        is_cached = hasattr(self.engine, "_frame_cache") and frame_index in self.engine._frame_cache
        
        if not is_cached:
            # Re-center and trigger immediate visual paint event before blocking for decoding
            self.loading_spinner.move(
                (self.video_frame_label.width() - self.loading_spinner.width()) // 2,
                (self.video_frame_label.height() - self.loading_spinner.height()) // 2
            )
            self.loading_spinner.show()
            QCoreApplication.processEvents()

        self.engine.seek_to_frame(frame_index)
        self._playback_start_frame = frame_index
        self._playback_clock.restart()
        self.show_frame(frame_index)
        
        if self._media_path:
            self.media_player.setPosition(int((frame_index / max(self.engine.fps, 1.0)) * 1000))
            if play_audio:
                self.play()
                
        if not is_cached:
            self.loading_spinner.hide()

    def _apply_scaled_pixmap(self) -> None:
        if self._current_pixmap is None or self._current_pixmap.isNull():
            return
        transform_mode = Qt.TransformationMode.FastTransformation if self.timer.isActive() else Qt.TransformationMode.SmoothTransformation
        scaled_pixmap = self._current_pixmap.scaled(
            self.video_frame_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            transform_mode,
        )
        self.video_frame_label.setPixmap(scaled_pixmap)

    def _display_frame_array(self, frame_rgb, frame_index: int) -> None:
        self._last_frame_rgb = frame_rgb
        downscaled_rgb = self._downscale_for_preview(frame_rgb)
        self.current_frame_index = max(0, int(frame_index))
        height, width, channel = downscaled_rgb.shape
        bytes_per_line = channel * width
        q_img = QImage(downscaled_rgb.tobytes(), width, height, bytes_per_line, QImage.Format.Format_RGB888).copy()
        self._current_pixmap = QPixmap.fromImage(q_img)
        self._apply_scaled_pixmap()
        self._update_metadata()
        self.quality_label.setText(f"{width}x{height}")
        self.frameChanged.emit(self.current_frame_index)

    def _on_playback_state_changed(self, state) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.timer.start()
        else:
            self.timer.stop()

    def _downscale_for_preview(self, frame_rgb):
        if self._preview_scale_factor >= 1.0:
            return frame_rgb
        step = int(1.0 / self._preview_scale_factor)
        return frame_rgb[::step, ::step].copy()