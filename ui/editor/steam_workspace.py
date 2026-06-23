from __future__ import annotations

import copy
import json
import os
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QFont, QImage, QKeySequence, QShortcut, QIcon, QPixmap, QPainter, QColor, QPen, QBrush, QPainterPath
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QStyle,
)

from core.video_editor.ffmpeg_editor_engine import FFmpegEditorEngine
from core.video_editor.frame_engine import FrameAccurateEngine
from core.video_editor.timeline import FrameTimeline
from ui.editor.player_widget import PreviewPlayerWidget
from ui.editor.timeline_widget import TimelineWidget

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPORT_TEMP_DIR = PROJECT_ROOT / "temp" / "exports"

def _make_vector_icon(size: int, draw_func) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor('#e0e4ea'), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    draw_func(painter, size)
    painter.end()
    return QIcon(pixmap)

def _draw_open(painter, size):
    painter.drawRect(4, 8, size-8, size-12)
    painter.drawLine(4, 8, 10, 8)
    painter.drawLine(10, 8, 14, 4)
    painter.drawLine(14, 4, size-4, 4)
    painter.drawLine(size-4, 4, size-4, 8)

def _draw_prev(painter, size):
    painter.drawLine(6, 6, 6, size-6)
    path = QPainterPath()
    path.moveTo(size-6, 6)
    path.lineTo(8, size//2)
    path.lineTo(size-6, size-6)
    path.closeSubpath()
    painter.setBrush(QBrush(QColor('#e0e4ea')))
    painter.drawPath(path)

def _draw_next(painter, size):
    painter.drawLine(size-6, 6, size-6, size-6)
    path = QPainterPath()
    path.moveTo(6, 6)
    path.lineTo(size-8, size//2)
    path.lineTo(6, size-6)
    path.closeSubpath()
    painter.setBrush(QBrush(QColor('#e0e4ea')))
    painter.drawPath(path)

def _draw_play_pause(painter, size):
    path = QPainterPath()
    path.moveTo(4, 6)
    path.lineTo(12, size//2)
    path.lineTo(4, size-6)
    path.closeSubpath()
    painter.setBrush(QBrush(QColor('#e0e4ea')))
    painter.drawPath(path)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawLine(16, 6, 16, size-6)
    painter.drawLine(20, 6, 20, size-6)

def _draw_replay(painter, size):
    painter.drawArc(4, 4, size-8, size-8, 45 * 16, 270 * 16)
    path = QPainterPath()
    path.moveTo(14, 4)
    path.lineTo(18, 8)
    path.lineTo(14, 12)
    path.closeSubpath()
    painter.setBrush(QBrush(QColor('#e0e4ea')))
    painter.drawPath(path)

def _draw_capture(painter, size):
    painter.drawRoundedRect(4, 8, size-8, size-12, 2, 2)
    painter.drawEllipse(size//2 - 3, size//2, 6, 6)
    painter.drawLine(8, 8, 10, 4)
    painter.drawLine(10, 4, size-10, 4)
    painter.drawLine(size-10, 4, size-8, 8)

def _draw_mark_in(painter, size):
    painter.drawLine(8, 4, 8, size-4)
    painter.drawLine(8, 4, 12, 4)
    painter.drawLine(8, size-4, 12, size-4)
    painter.drawLine(10, size//2, size-4, size//2)
    painter.drawLine(size-8, size//2 - 4, size-4, size//2)
    painter.drawLine(size-8, size//2 + 4, size-4, size//2)

def _draw_mark_out(painter, size):
    painter.drawLine(size-8, 4, size-8, size-4)
    painter.drawLine(size-8, 4, size-12, 4)
    painter.drawLine(size-8, size-4, size-12, size-4)
    painter.drawLine(4, size//2, size-10, size//2)
    painter.drawLine(4, size//2, 8, size//2 - 4)
    painter.drawLine(4, size//2, 8, size//2 + 4)

def _draw_cut(painter, size):
    painter.drawEllipse(2, size-10, 6, 6)
    painter.drawEllipse(size-8, size-10, 6, 6)
    painter.drawLine(6, size-8, size-4, 4)
    painter.drawLine(size-4, size-8, 6, 4)

def _draw_undo(painter, size):
    painter.drawArc(8, 8, size-12, size-12, -90 * 16, 180 * 16)
    path = QPainterPath()
    path.moveTo(12, 4)
    path.lineTo(4, 8)
    path.lineTo(12, 12)
    path.closeSubpath()
    painter.setBrush(QBrush(QColor('#e0e4ea')))
    painter.drawPath(path)

def _draw_redo(painter, size):
    painter.drawArc(4, 8, size-12, size-12, 90 * 16, 180 * 16)
    path = QPainterPath()
    path.moveTo(12, 4)
    path.lineTo(20, 8)
    path.lineTo(12, 12)
    path.closeSubpath()
    painter.setBrush(QBrush(QColor('#e0e4ea')))
    painter.drawPath(path)

def _draw_export(painter, size):
    painter.drawRect(4, size//2, size-8, size//2 - 2)
    painter.drawLine(size//2, 4, size//2, size-6)
    painter.drawLine(size//2, 4, size//2 - 4, 8)
    painter.drawLine(size//2, 4, size//2 + 4, 8)

class SteamStyleEditorWidget(QWidget):
    exportedVideo = pyqtSignal(str)

    def __init__(self, parent=None, on_export_complete_callback=None):
        super().__init__(parent)
        self.on_export_complete_callback = on_export_complete_callback
        self.timeline = FrameTimeline(total_frames=0, fps=25.0)
        self.frame_engine = None
        self.current_video_path = None
        self.export_engine = FFmpegEditorEngine()
        self._undo_stack: list[dict] = []
        self._redo_stack: list[dict] = []
        self._state_path = Path("config") / "editor_state.json"
        self._shortcuts = []
        self._scrub_timer = QTimer(self)
        self._scrub_timer.setSingleShot(True)
        self._scrub_timer.setInterval(25)
        self._pending_scrub_frame = None
        self._scrub_timer.timeout.connect(self._commit_scrub_frame)
        self._setup_ui()
        self._install_shortcuts()
        self._restore_state()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        header = QHBoxLayout()
        self.title_label = QLabel("Clip Editor")
        self.title_label.setFont(QFont("Segoe UI Variable", 18, QFont.Weight.Bold))
        self.status_label = QLabel("Open a video to start trimming.")
        self.status_label.setObjectName("Muted")
        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.status_label)
        layout.addLayout(header)

        self.player_widget = PreviewPlayerWidget()
        self.player_widget.setMinimumHeight(340)
        layout.addWidget(self.player_widget, stretch=5)

        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        action_row.addStretch(1) # Center align

        self.btn_open = self._make_icon_button("Open video", _draw_open)
        action_row.addWidget(self.btn_open)
        
        self._add_separator(action_row)

        self.btn_prev = self._make_icon_button("Previous frame", _draw_prev)
        self.btn_play = self._make_icon_button("Play / Pause", _draw_play_pause)
        self.btn_next = self._make_icon_button("Next frame", _draw_next)
        self.btn_replay = self._make_icon_button("Replay edited video", _draw_replay)
        action_row.addWidget(self.btn_prev)
        action_row.addWidget(self.btn_play)
        action_row.addWidget(self.btn_next)
        action_row.addWidget(self.btn_replay)
        
        self._add_separator(action_row)

        self.btn_mark_in = self._make_icon_button("Mark In", _draw_mark_in)
        self.btn_mark_out = self._make_icon_button("Mark Out", _draw_mark_out)
        self.btn_cut = self._make_icon_button("Cut selection", _draw_cut)
        action_row.addWidget(self.btn_mark_in)
        action_row.addWidget(self.btn_mark_out)
        action_row.addWidget(self.btn_cut)
        
        self._add_separator(action_row)

        self.btn_undo = self._make_icon_button("Undo", _draw_undo)
        self.btn_redo = self._make_icon_button("Redo", _draw_redo)
        action_row.addWidget(self.btn_undo)
        action_row.addWidget(self.btn_redo)
        
        self._add_separator(action_row)

        self.btn_capture = self._make_icon_button("Save current frame", _draw_capture)
        self.btn_export = self._make_icon_button("Export video", _draw_export)
        action_row.addWidget(self.btn_capture)
        action_row.addWidget(self.btn_export)

        action_row.addStretch(1) # Center align
        layout.addLayout(action_row)

        self.timeline_widget = TimelineWidget(self.timeline)
        layout.addWidget(self.timeline_widget, stretch=1)

        self.btn_open.clicked.connect(self.open_video)
        self.btn_prev.clicked.connect(lambda: self.step_frame(-1))
        self.btn_next.clicked.connect(lambda: self.step_frame(1))
        self.btn_play.clicked.connect(self.toggle_playback)
        self.btn_replay.clicked.connect(self.replay_edited)
        self.btn_capture.clicked.connect(self.save_current_frame)
        self.btn_mark_in.clicked.connect(self.mark_in)
        self.btn_mark_out.clicked.connect(self.mark_out)
        self.btn_cut.clicked.connect(self.cut_selection)
        self.btn_undo.clicked.connect(self.undo)
        self.btn_redo.clicked.connect(self.redo)
        self.btn_export.clicked.connect(self.export_trimmed)

        self.player_widget.frameChanged.connect(self._sync_frame)
        self.timeline_widget.cursorFrameChanged.connect(self.scrub_to_frame)

    def _add_separator(self, layout) -> None:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setStyleSheet("color: #2b3442;")
        sep.setFixedSize(1, 20)
        layout.addWidget(sep)

    def _make_icon_button(self, tooltip: str, draw_func) -> QToolButton:
        button = QToolButton()
        button.setIcon(_make_vector_icon(24, draw_func))
        button.setToolTip(tooltip)
        button.setAutoRaise(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setFixedSize(36, 36)
        button.setStyleSheet("""
            QToolButton {
                border-radius: 4px;
                background-color: transparent;
            }
            QToolButton:hover {
                background-color: #1d2430;
            }
            QToolButton:pressed {
                background-color: #11151c;
            }
        """)
        return button

    def open_video(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Video",
            "",
            "Video Files (*.mp4 *.mkv *.mov *.avi *.webm *.m4v);;All Files (*.*)",
        )
        if file_path:
            self.load_video(file_path)

    def load_video(self, file_path: str) -> None:
        if self.frame_engine:
            self.frame_engine.release()

        self.current_video_path = file_path
        self.frame_engine = FrameAccurateEngine(file_path)
        self.timeline = FrameTimeline(total_frames=self.frame_engine.total_frames, fps=self.frame_engine.fps)
        self._undo_stack.clear()

        self.timeline_widget.set_timeline(self.timeline)
        self.timeline_widget.set_preview_source(self.frame_engine)
        self.player_widget.set_engine(self.frame_engine)
        self.player_widget.set_media_source(file_path)
        self.scrub_to_frame(0)
        self._set_status(
            f"{os.path.basename(file_path)} | {self.frame_engine.total_frames} frames @ {self.frame_engine.fps:.2f} fps"
        )
        self._save_state()

    def _snapshot(self) -> None:
        self._undo_stack.append(
            {
                "layers": copy.deepcopy(self.timeline.layers),
                "mark_in_frame": self.timeline.mark_in_frame,
                "mark_out_frame": self.timeline.mark_out_frame,
                "cursor_frame": self.timeline.cursor_frame,
            }
        )
        self._redo_stack.clear()

    def undo(self) -> None:
        if not self._undo_stack:
            self._set_status("Nothing to undo")
            return
        self._redo_stack.append(
            {
                "layers": copy.deepcopy(self.timeline.layers),
                "mark_in_frame": self.timeline.mark_in_frame,
                "mark_out_frame": self.timeline.mark_out_frame,
                "cursor_frame": self.timeline.cursor_frame,
            }
        )
        state = self._undo_stack.pop()
        self.timeline.layers = state["layers"]
        self.timeline.mark_in_frame = state["mark_in_frame"]
        self.timeline.mark_out_frame = state["mark_out_frame"]
        self.timeline.cursor_frame = state["cursor_frame"]
        self._refresh_views()
        self._set_status("Undo")

    def redo(self) -> None:
        if not self._redo_stack:
            self._set_status("Nothing to redo")
            return
        self._undo_stack.append(
            {
                "layers": copy.deepcopy(self.timeline.layers),
                "mark_in_frame": self.timeline.mark_in_frame,
                "mark_out_frame": self.timeline.mark_out_frame,
                "cursor_frame": self.timeline.cursor_frame,
            }
        )
        state = self._redo_stack.pop()
        self.timeline.layers = state["layers"]
        self.timeline.mark_in_frame = state["mark_in_frame"]
        self.timeline.mark_out_frame = state["mark_out_frame"]
        self.timeline.cursor_frame = state["cursor_frame"]
        self._refresh_views()
        self._set_status("Redo")

    def _sync_frame(self, frame_index: int) -> None:
        self.timeline.set_cursor(frame_index)
        self.timeline_widget.set_cursor_frame(frame_index)

    def scrub_to_frame(self, frame_index: int) -> None:
        if not self.frame_engine:
            return
        self._pending_scrub_frame = max(0, int(frame_index))
        if self.player_widget.timer.isActive():
            self.timeline.set_cursor(self._pending_scrub_frame)
            self.timeline_widget.set_cursor_frame(self._pending_scrub_frame)
            self._scrub_timer.stop()
            self._scrub_timer.start()
            return
        self._commit_scrub_frame()

    def _commit_scrub_frame(self) -> None:
        if self._pending_scrub_frame is None or not self.frame_engine:
            return
        was_playing = self.player_widget.timer.isActive()
        frame_index = self._pending_scrub_frame
        self._pending_scrub_frame = None
        self.player_widget.seek_to_frame(frame_index, play_audio=False)
        if was_playing:
            self.player_widget.play()
        self.timeline.set_cursor(frame_index)
        self.timeline_widget.set_cursor_frame(frame_index)

    def step_frame(self, delta: int) -> None:
        if not self.frame_engine:
            return
        self.player_widget.step(delta)
        self._sync_frame(self.player_widget.current_frame_index)

    def toggle_playback(self) -> None:
        if not self.frame_engine:
            return
        if self.player_widget.timer.isActive():
            self.player_widget.pause()
            self._set_status("Paused")
        else:
            self.player_widget.play()
            self._set_status("Playing")

    def replay_edited(self) -> None:
        if not self.frame_engine:
            return
        self.player_widget.pause()
        segments = self.timeline.flatten_layers() if hasattr(self.timeline, "flatten_layers") else list(self.timeline.keep_segments)
        ranges = [(segment.start_frame, segment.end_frame) for segment in segments if segment.end_frame > segment.start_frame]
        if ranges:
            self.player_widget.play_segment_ranges(ranges)
            self._set_status(f"Replaying {len(ranges)} segment(s)")
        else:
            self.scrub_to_frame(0)
            self.player_widget.play()
            self._set_status("Replaying from start")

    def mark_in(self) -> None:
        if not self.frame_engine:
            return
        self._snapshot()
        self.timeline.set_mark_in(self.timeline.cursor_frame)
        self.timeline_widget.refresh_state(f"Mark In at frame {self.timeline.cursor_frame}")
        self._set_status(f"Mark In set at frame {self.timeline.cursor_frame}")
        self._save_state()

    def mark_out(self) -> None:
        if not self.frame_engine or self.timeline.mark_in_frame is None:
            return
        self._snapshot()
        segment = self.timeline.commit_mark_out(self.timeline.cursor_frame)
        if segment:
            self._refresh_views()
            self._set_status(f"Segment created: {segment.start_frame} - {segment.end_frame}")
        else:
            self.timeline_widget.refresh_state(
                f"Selection ready: {self.timeline.mark_in_frame} - {self.timeline.mark_out_frame} | Press Cut"
            )
            self._set_status(f"Mark Out set at frame {self.timeline.cursor_frame}")
        self._save_state()

    def cut_selection(self) -> None:
        if not self.frame_engine:
            return
        if self.timeline.mark_in_frame is None or self.timeline.mark_out_frame is None:
            QMessageBox.information(self, "Selection Needed", "Set Mark In and Mark Out first.")
            return
        self._snapshot()
        segment = self.timeline.create_segment_from_marks()
        if segment:
            self._refresh_views()
            self._set_status(f"Cut added: {segment.start_frame} - {segment.end_frame}")
            self._save_state()

    def split_at_cursor(self) -> None:
        if not self.frame_engine:
            return
        self._snapshot()
        result = self.timeline.split_at_frame(self.timeline.cursor_frame)
        if result:
            self._refresh_views()
            self._set_status("Segment split")
            self._save_state()

    def merge_segments(self) -> None:
        if not self.frame_engine:
            return
        self._snapshot()
        self.timeline.merge_adjacent()
        self._refresh_views()
        self._set_status("Merged adjacent segments")
        self._save_state()

    def clear_all(self) -> None:
        if not self.frame_engine:
            return
        self._snapshot()
        self.timeline.layers = {"base": []}
        self.timeline.clear_mark_in()
        self._refresh_views()
        self._set_status("Cleared cuts")
        self._save_state()

    def remove_selected_segment(self) -> None:
        self._set_status("Segments panel removed")

    def invert_segments(self) -> None:
        if not self.frame_engine:
            return
        self._snapshot()
        keep_segments = self.timeline.inverted_keep_segments()
        self.timeline.layers = {"base": keep_segments}
        self.timeline.clear_mark_in()
        self._refresh_views()
        self._set_status("Inverted timeline")
        self._save_state()

    def export_trimmed(self) -> None:
        if not self.current_video_path:
            return
        if not self.timeline.flatten_layers():
            self.timeline.add_segment(0, self.timeline.total_frames)
        save_path = self._default_export_path()
        if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
            chosen_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Trimmed Video",
                str(save_path),
                "Video Files (*.mp4 *.mkv *.mov *.avi *.webm)",
            )
            if chosen_path:
                save_path = Path(chosen_path)

        try:
            output_path = self.export_engine.export_timeline(
                self.current_video_path,
                str(save_path),
                self.timeline,
                fast_mode=True,
            )
            self.exportedVideo.emit(output_path)
            if self.on_export_complete_callback:
                self.on_export_complete_callback(output_path)
            self._set_status(f"Exported to temp — sent to compressor")
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", f"Export failed:\n{exc}")

    def _default_export_path(self) -> Path:
        source = Path(self.current_video_path) if self.current_video_path else Path("export.mp4")
        EXPORT_TEMP_DIR.mkdir(parents=True, exist_ok=True)
        suffix = source.suffix if source.suffix else ".mp4"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return EXPORT_TEMP_DIR / f"{source.stem}_{stamp}{suffix}"

    def save_current_frame(self) -> None:
        if not self.frame_engine:
            return
        target_dir = Path.home() / "Pictures" / "Compressor" / "Frames"
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"frame_{self.timeline.cursor_frame:06d}.png"
        frame_rgb = self.frame_engine.get_exact_frame(self.timeline.cursor_frame)
        if frame_rgb is None:
            return
        height, width, channel = frame_rgb.shape
        bytes_per_line = channel * width
        image = QImage(frame_rgb.data, width, height, bytes_per_line, QImage.Format.Format_RGB888).copy()
        image.save(str(target_path))
        self._set_status(f"Saved frame to {target_path.name}")

    def _install_shortcuts(self) -> None:
        self._shortcuts = [
            QShortcut(QKeySequence("Space"), self, activated=self.toggle_playback),
            QShortcut(QKeySequence("Ctrl+Z"), self, activated=self.undo),
            QShortcut(QKeySequence("Ctrl+Y"), self, activated=self.redo),
            QShortcut(QKeySequence("Ctrl+Shift+Z"), self, activated=self.redo),
            QShortcut(QKeySequence("Left"), self, activated=lambda: self.step_frame(-1)),
            QShortcut(QKeySequence("Right"), self, activated=lambda: self.step_frame(1)),
            QShortcut(QKeySequence("I"), self, activated=self.mark_in),
            QShortcut(QKeySequence("O"), self, activated=self.mark_out),
            QShortcut(QKeySequence("X"), self, activated=self.cut_selection),
            QShortcut(QKeySequence("C"), self, activated=self.cut_selection),
            QShortcut(QKeySequence("Delete"), self, activated=self.remove_selected_segment),
            QShortcut(QKeySequence("S"), self, activated=self.split_at_cursor),
            QShortcut(QKeySequence("M"), self, activated=self.merge_segments),
            QShortcut(QKeySequence("Home"), self, activated=lambda: self.scrub_to_frame(0)),
            QShortcut(QKeySequence("End"), self, activated=lambda: self.scrub_to_frame(self.timeline.total_frames - 1 if self.timeline else 0)),
            QShortcut(QKeySequence("J"), self, activated=lambda: self.step_frame(-10)),
            QShortcut(QKeySequence("K"), self, activated=self.toggle_playback),
            QShortcut(QKeySequence("L"), self, activated=lambda: self.step_frame(10)),
            QShortcut(QKeySequence("Ctrl+E"), self, activated=self.export_trimmed),
            QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save_current_frame),
        ]

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Space:
            self.toggle_playback()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Left:
            self.step_frame(-1)
            event.accept()
            return
        if event.key() == Qt.Key.Key_Right:
            self.step_frame(1)
            event.accept()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            delta = 1 if event.angleDelta().y() > 0 else -1
            self.step_frame(delta)
            event.accept()
            return
        super().wheelEvent(event)

    def _refresh_views(self) -> None:
        self.timeline_widget.set_cursor_frame(self.timeline.cursor_frame)
        self.timeline_widget.refresh_state()
        self.timeline_widget.canvas.update()
        self._save_state()

    def closeEvent(self, event) -> None:
        self._save_state()
        super().closeEvent(event)

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _save_state(self) -> None:
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "video_path": self.current_video_path,
                "timeline": {
                    "layers": {
                        layer: [segment.to_dict() for segment in segments]
                        for layer, segments in self.timeline.layers.items()
                    },
                    "mark_in_frame": self.timeline.mark_in_frame,
                    "mark_out_frame": self.timeline.mark_out_frame,
                    "cursor_frame": self.timeline.cursor_frame,
                    "fps": self.timeline.fps,
                    "total_frames": self.timeline.total_frames,
                },
            }
            self._state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _restore_state(self) -> None:
        if not self._state_path.exists():
            return
        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
            video_path = payload.get("video_path")
            if video_path and os.path.exists(video_path):
                self.load_video(video_path)
                timeline = payload.get("timeline", {})
                from core.video_editor.segment import Segment

                self.timeline.layers = {
                    layer: [Segment.from_dict(item) for item in items]
                    for layer, items in timeline.get("layers", {}).items()
                }
                self.timeline.mark_in_frame = timeline.get("mark_in_frame")
                self.timeline.mark_out_frame = timeline.get("mark_out_frame")
                self.timeline.cursor_frame = timeline.get("cursor_frame", 0)
                self.timeline.set_cursor(self.timeline.cursor_frame)
                self._refresh_views()
        except Exception:
            pass
