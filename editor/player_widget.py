from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, QElapsedTimer, pyqtSignal, QUrl, QPoint
from PyQt6.QtGui import QImage, QPixmap, QColor, QPalette
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QWidget, QComboBox, QMenu, QToolButton

from .replay_engine import ReplayEngine
from .playback_controller import PlaybackController, PlaybackMode

class PreviewPlayerWidget(QWidget):
    frameChanged = pyqtSignal(int)
    playbackFinished = pyqtSignal()

    def __init__(self, playback_controller: PlaybackController, parent=None):
        super().__init__(parent)
        self.engine = None
        self.current_frame_index = 0
        self._current_pixmap = None
        self._media_path = None
        
        self.playback_controller = playback_controller
        self.replay_engine = ReplayEngine()
        
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
        layout.setSpacing(0)

        # Main video container
        self.video_container = QWidget()
        self.video_container.setStyleSheet("background: #000000; border-radius: 8px;")
        video_layout = QVBoxLayout(self.video_container)
        video_layout.setContentsMargins(0, 0, 0, 0)
        
        self.video_frame_label = QLabel("Drop a video to begin")
        self.video_frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_frame_label.setMinimumSize(640, 360)
        self.video_frame_label.setStyleSheet("color: #d7dce3; font-size: 16px;")
        
        video_layout.addWidget(self.video_frame_label)
        
        # HUD Overlays (positioned absolutely in resizeEvent)
        # Quality button remains floating over video
        self.quality_btn = QToolButton(self.video_container)
        self.quality_btn.setText("⚙")
        self.quality_btn.setToolTip("Preview Quality")
        self.quality_btn.setStyleSheet("""
            QToolButton {
                background-color: rgba(0, 0, 0, 160);
                color: white;
                border-radius: 4px;
                padding: 4px;
                font-size: 16px;
            }
            QToolButton:hover {
                background-color: rgba(60, 60, 60, 160);
            }
        """)
        self.quality_btn.hide()
        
        self.quality_menu = QMenu(self)
        self.quality_menu.setStyleSheet("""
            QMenu {
                background-color: #1c2028;
                color: white;
                border: 1px solid #3a4150;
            }
            QMenu::item:selected {
                background-color: #2a2f3a;
            }
        """)
        for q in ["Full", "1/2", "1/4", "1/8"]:
            action = self.quality_menu.addAction(q)
            action.triggered.connect(lambda checked, text=q: self._on_quality_changed(text))
            
        self.quality_btn.setMenu(self.quality_menu)
        self.quality_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        layout.addWidget(self.video_container, stretch=1)
        
        # Info bar below video
        self.hud_label = QLabel("00:00:00 / 00:00:00  |  -- FPS")
        self.hud_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hud_label.setStyleSheet("""
            color: #7d848e;
            font-size: 13px;
            font-weight: 600;
            margin-top: 8px;
        """)
        self.hud_label.hide()
        layout.addWidget(self.hud_label)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_scaled_pixmap()
        
        # Reposition overlays
        if hasattr(self, 'quality_btn'):
            self.quality_btn.move(self.video_container.width() - self.quality_btn.width() - 12, 12)

    def _on_quality_changed(self, text: str) -> None:
        self._quality_manual_override = True
        mapping = {"Full": 1.0, "1/2": 0.5, "1/4": 0.25, "1/8": 0.125}
        self._preview_scale_factor = mapping.get(text, 1.0)
        self.quality_btn.setText(f"⚙ {text}")
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
            
        self.quality_btn.setText(f"⚙ {default_quality}")
        self._preview_scale_factor = {"Full": 1.0, "1/2": 0.5, "1/4": 0.25, "1/8": 0.125}[default_quality]

    def set_engine(self, engine) -> None:
        self.engine = engine
        if not engine:
            self.hud_label.hide()
            self.quality_btn.hide()
            return
            
        self.hud_label.show()
        self.quality_btn.show()
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

    def play(self) -> None:
        if self.engine:
            self.replay_engine.clear()
            self._playback_start_frame = self.current_frame_index
            self._playback_clock.restart()
            if self._media_path:
                self.media_player.play()
            self.timer.start()

    def play_segment_ranges(self, ranges: list[tuple[int, int]]) -> None:
        if not self.engine:
            return
            
        has_ranges = self.replay_engine.configure_ranges(ranges)
        if not has_ranges:
            self.seek_to_frame(0)
            self.play()
            return

        start_frame = self.replay_engine.segment_ranges[0][0]
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
        self.playback_controller.pause()
        next_frame = self.current_frame_index + int(direction)
        self.show_frame(next_frame)
        if self._media_path:
            self.media_player.setPosition(int((self.current_frame_index / max(self.engine.fps, 1.0)) * 1000))

    def save_current_frame(self) -> None:
        if not self.engine:
            return
        frame_rgb = self.engine.get_exact_frame(self.current_frame_index)
        if frame_rgb is None:
            return

        from PyQt6.QtWidgets import QFileDialog
        height, width, channel = frame_rgb.shape
        bytes_per_line = channel * width
        q_img = QImage(frame_rgb.tobytes(), width, height, bytes_per_line, QImage.Format.Format_RGB888)

        file_path, _ = QFileDialog.getSaveFileName(
            self, 
            "Save Current Frame", 
            f"frame_{self.current_frame_index}.png", 
            "PNG Image (*.png);;JPEG Image (*.jpg *.jpeg)"
        )
        if file_path:
            q_img.save(file_path)

    def next_frame(self) -> None:
        if not self.engine:
            return
        fps = max(self.engine.fps, 1.0)
        elapsed_ms = self._playback_clock.elapsed() if self._playback_clock.isValid() else 0
        target_frame = self._playback_start_frame + int((elapsed_ms / 1000.0) * fps)
        target_frame = max(0, min(target_frame, self.engine.total_frames - 1))
        
        if self.replay_engine.is_active:
            current_start, current_end = self.replay_engine.get_current_bounds()
            if target_frame < current_start:
                target_frame = current_start
                
            if target_frame >= current_end:
                next_start, force_seek, finished = self.replay_engine.step_to_next_segment(self.engine.total_frames)
                if finished:
                    self.playback_controller.stop()
                    self.playbackFinished.emit()
                    return
                if next_start is not None:
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
                self.playback_controller.stop()
                self.replay_engine.clear()
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
                self.playback_controller.stop()
                self.playbackFinished.emit()
                return
            self._display_frame_array(frame_rgb, self.engine.current_frame_index)
            return

        next_frame = target_frame if target_frame > self.current_frame_index else self.current_frame_index + 1
        if next_frame >= self.engine.total_frames:
            self.playback_controller.stop()
            self.playbackFinished.emit()
            return
        self.show_frame(next_frame)

    def seek_to_frame(self, frame_index: int, play_audio: bool = False) -> None:
        if not self.engine:
            return
        frame_index = max(0, min(int(frame_index), max(0, self.engine.total_frames - 1)))
        
        # Don't pause if we are just dragging playhead while paused, but update engine
        self.engine.seek_to_frame(frame_index)
        self._playback_start_frame = frame_index
        self._playback_clock.restart()
        self.show_frame(frame_index)
        if self._media_path:
            self.media_player.setPosition(int((frame_index / max(self.engine.fps, 1.0)) * 1000))
            if play_audio and self.playback_controller.is_playing:
                self.media_player.play()

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
        
        # Update HUD
        timecode = "00:00:00"
        total_timecode = "00:00:00"
        fps_display = "-- FPS"
        
        if self.engine:
            fps = self.engine.fps
            if fps > 0:
                fps_display = f"{fps:.2f} FPS" if fps % 1 != 0 else f"{int(fps)} FPS"
                # Current Time
                total_seconds = self.current_frame_index / fps
                minutes = int(total_seconds // 60)
                seconds = int(total_seconds % 60)
                frame_remainder = int(round((total_seconds - int(total_seconds)) * fps))
                timecode = f"{minutes:02d}:{seconds:02d}:{frame_remainder:02d}"
                
                # Total Time
                dur_seconds = self.engine.total_frames / fps
                t_minutes = int(dur_seconds // 60)
                t_seconds = int(dur_seconds % 60)
                t_frame_rem = int(round((dur_seconds - int(dur_seconds)) * fps))
                total_timecode = f"{t_minutes:02d}:{t_seconds:02d}:{t_frame_rem:02d}"
                
        self.hud_label.setText(f"{timecode} / {total_timecode}   |   {fps_display}")
        
        self.frameChanged.emit(self.current_frame_index)

    def _on_playback_state_changed(self, state) -> None:
        pass # state changes are now driven by PlaybackController

    def _downscale_for_preview(self, frame_rgb):
        if self._preview_scale_factor >= 1.0:
            return frame_rgb
        step = int(1.0 / self._preview_scale_factor)
        return frame_rgb[::step, ::step].copy()