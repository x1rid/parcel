from __future__ import annotations

import copy
import json
import os
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QObject, QEvent, QThread
from PyQt6.QtGui import QFont, QImage, QKeySequence, QShortcut, QIcon, QPixmap, QPainter, QColor, QPen, QBrush, QPainterPath
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QMessageBox, 
    QToolButton, QVBoxLayout, QWidget, QToolTip, QDialog, QVBoxLayout as QVLayout,
    QDialogButtonBox, QFormLayout, QComboBox, QCheckBox
)

from .ffmpeg_editor_engine import FFmpegEditorEngine
from .frame_engine import FrameAccurateEngine
from .timeline import FrameTimeline
from .player_widget import PreviewPlayerWidget
from .timeline_widget import TimelineWidget
from .playback_controller import PlaybackController, PlaybackMode

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPORT_TEMP_DIR = PROJECT_ROOT / "temp" / "exports"
SESSION_RECOVERY_PATH = PROJECT_ROOT / "config" / "editor_session.json"


class ExportWorker(QThread):
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, engine: FFmpegEditorEngine, input_path: str, output_path: str, timeline, fast_mode: bool):
        super().__init__()
        self.engine = engine
        self.input_path = input_path
        self.output_path = output_path
        self.timeline = timeline
        self.fast_mode = fast_mode

    def run(self) -> None:
        try:
            result = self.engine.export_timeline(self.input_path, self.output_path, self.timeline, fast_mode=self.fast_mode)
            self.finished_ok.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class ThreeSecondTooltipFilter(QObject):
    """Enforces clean typography design rules by introducing a mandatory 2500ms tooltip delay constraint."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(2500)
        self.timer.timeout.connect(self._show_tooltip)
        self.current_widget = None
        self.tooltip_text = ""
        self.global_pos = None

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ToolTip:
            return True 
        elif event.type() == QEvent.Type.Enter:
            text = watched.toolTip()
            if text:
                self.current_widget = watched
                self.tooltip_text = text
                self.global_pos = watched.mapToGlobal(watched.rect().center())
                self.timer.start()
        elif event.type() in (QEvent.Type.Leave, QEvent.Type.MouseButtonPress, QEvent.Type.WindowDeactivate):
            if self.current_widget == watched:
                self.timer.stop()
                QToolTip.hideText()
                self.current_widget = None
        return super().eventFilter(watched, event)

    def _show_tooltip(self):
        if self.current_widget and self.tooltip_text:
            QToolTip.showText(self.global_pos, self.tooltip_text, self.current_widget)


# Vector Painters
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

def _draw_prev(p, s):
    p.drawLine(6, 6, 6, s-6)
    path = QPainterPath()
    path.moveTo(s-6, 6)
    path.lineTo(8, s//2)
    path.lineTo(s-6, s-6)
    path.closeSubpath()
    p.setBrush(QBrush(QColor('#e0e4ea')))
    p.drawPath(path)

def _draw_next(p, s):
    p.drawLine(s-6, 6, s-6, s-6)
    path = QPainterPath()
    path.moveTo(6, 6)
    path.lineTo(s-8, s//2)
    path.lineTo(6, s-6)
    path.closeSubpath()
    p.setBrush(QBrush(QColor('#e0e4ea')))
    p.drawPath(path)

def _draw_play_pause(p, s):
    path = QPainterPath()
    path.moveTo(4, 6)
    path.lineTo(12, s//2)
    path.lineTo(4, s-6)
    path.closeSubpath()
    p.setBrush(QBrush(QColor('#e0e4ea')))
    p.drawPath(path)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(16, 6, 16, s-6)
    p.drawLine(20, 6, 20, s-6)

def _draw_replay(p, s):
    p.drawArc(4, 4, s-8, s-8, 45 * 16, 270 * 16)
    path = QPainterPath()
    path.moveTo(14, 4)
    path.lineTo(18, 8)
    path.lineTo(14, 12)
    path.closeSubpath()
    p.setBrush(QBrush(QColor('#e0e4ea')))
    p.drawPath(path)

def _draw_segment(p, s):
    p.drawEllipse(s//2 - 4, 4, 8, 8)
    p.drawLine(s//2, 12, s//2, s-4)

def _draw_mark_in(p, s):
    p.drawLine(5, 4, 5, s-4)
    p.drawLine(5, 4, 11, 4)
    p.drawLine(5, s-4, 11, s-4)

def _draw_mark_out(p, s):
    p.drawLine(s-5, 4, s-5, s-4)
    p.drawLine(s-11, 4, s-5, 4)
    p.drawLine(s-11, s-4, s-5, s-4)

def _draw_capture(p, s):
    p.drawRoundedRect(3, 6, s-6, s-10, 2, 2)
    p.drawEllipse(s//2 - 3, s//2 - 1, 6, 6)

def _draw_export(p, s):
    p.drawRect(4, s//2 + 2, s-8, s//2 - 6)
    p.drawLine(s//2, 3, s//2, s//2 + 2)


class SteamStyleEditorWidget(QWidget):
    exportedVideo = pyqtSignal(str)

    def __init__(self, parent=None, on_export_complete_callback=None):
        super().__init__(parent)
        self.setObjectName("SteamStyleEditorWidget")
        self.on_export_complete_callback = on_export_complete_callback
        
        self.timeline = FrameTimeline(total_frames=0, fps=25.0)
        self.frame_engine = None
        self.current_video_path = None
        self.export_engine = FFmpegEditorEngine()
        self.playback_controller = PlaybackController()
        
        self._undo_stack: list[dict] = []
        self._redo_stack: list[dict] = []
        self._state_path = Path("config") / "editor_state.json"
        self._export_worker = None
        
        self.tooltip_filter = ThreeSecondTooltipFilter(self)
        
        self._setup_ui()
        self._install_shortcuts()
        self._try_restore_session()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 1. Main Player
        self.player_widget = PreviewPlayerWidget(self.playback_controller)
        self.player_widget.setMinimumHeight(340)
        layout.addWidget(self.player_widget, stretch=5)

        # 2. Toolbar Frame
        action_row = QHBoxLayout()
        action_row.setSpacing(12)
        action_row.addStretch(1)

        self.btn_prev = self._make_icon_button("Previous Frame (Left)", _draw_prev)
        self.btn_play = self._make_icon_button("Play / Pause (Space)", _draw_play_pause)
        self.btn_next = self._make_icon_button("Next Frame (Right)", _draw_next)
        self.btn_replay = self._make_icon_button("Replay Edited Timeline", _draw_replay)
        
        self.btn_segment = self._make_icon_button("Create Segment", _draw_segment)
        self.btn_mark_in = self._make_icon_button("Mark In", _draw_mark_in)
        self.btn_mark_out = self._make_icon_button("Mark Out", _draw_mark_out)
        self.btn_capture = self._make_icon_button("Save Current Frame", _draw_capture)
        self.btn_export = self._make_icon_button("Export Video", _draw_export)

        action_row.addWidget(self.btn_prev)
        action_row.addWidget(self.btn_play)
        action_row.addWidget(self.btn_next)
        action_row.addSpacing(15)
        action_row.addWidget(self.btn_replay)
        action_row.addSpacing(15)
        action_row.addWidget(self.btn_segment)
        action_row.addWidget(self.btn_mark_in)
        action_row.addWidget(self.btn_mark_out)
        action_row.addWidget(self.btn_capture)
        action_row.addSpacing(15)
        action_row.addWidget(self.btn_export)
        
        action_row.addStretch(1)
        layout.addLayout(action_row)

        # 3. Timeline
        self.timeline_widget = TimelineWidget(self.timeline)
        layout.addWidget(self.timeline_widget, stretch=1)

        # Connections
        self.btn_prev.clicked.connect(lambda: self.step_frame(-1))
        self.btn_next.clicked.connect(lambda: self.step_frame(1))
        self.btn_play.clicked.connect(self.toggle_playback)
        self.btn_replay.clicked.connect(self.replay_edited_timeline)
        self.btn_segment.clicked.connect(self.create_segment_at_cursor)
        self.btn_mark_in.clicked.connect(self.mark_in)
        self.btn_mark_out.clicked.connect(self.mark_out)
        self.btn_capture.clicked.connect(self.player_widget.save_current_frame)
        self.btn_export.clicked.connect(self.export_trimmed)

        self.player_widget.frameChanged.connect(self._sync_frame)
        self.player_widget.playbackFinished.connect(self._on_playback_finished)
        self.timeline_widget.cursorFrameChanged.connect(self.scrub_to_frame)
        
        # Connect timeline widget signals
        self.timeline_widget.removeRequested.connect(self.remove_timeline_range)
        self.timeline_widget.segmentRequested.connect(self.create_segment_range)
        self.timeline_widget.replayRequested.connect(self.replay_range)

    def _make_icon_button(self, tooltip: str, draw_func) -> QToolButton:
        button = QToolButton()
        button.setIcon(_make_vector_icon(24, draw_func))
        button.setToolTip(tooltip)
        button.installEventFilter(self.tooltip_filter)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setFixedSize(40, 40)
        button.setStyleSheet("""
            QToolButton {
                border-radius: 6px;
                background-color: transparent;
                color: #ffffff;
                border: 1px solid transparent;
            }
            QToolButton:hover {
                background-color: #1a1a1a;
                border-color: #27272a;
            }
            QToolButton:pressed {
                background-color: #000000;
                border-color: #ffffff;
            }
            QToolButton:disabled {
                color: #7d848e;
                background-color: #030303;
            }
        """)
        return button

    def _install_shortcuts(self) -> None:
        """Frame accurate jumping constraints mapped directly to keyboard."""
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, self.toggle_playback)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, lambda: self.step_frame(-1))
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, lambda: self.step_frame(1))
        QShortcut(QKeySequence("Shift+Left"), self, lambda: self.step_frame(-10))
        QShortcut(QKeySequence("Shift+Right"), self, lambda: self.step_frame(10))
        QShortcut(QKeySequence("Ctrl+Z"), self, self.undo)
        QShortcut(QKeySequence("Ctrl+Y"), self, self.redo)
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self, self._delete_selection_or_segment)

    def step_frame(self, delta: int) -> None:
        if not self.frame_engine:
            return
        self.player_widget.step(delta)
        self._sync_frame(self.player_widget.current_frame_index)

    def _sync_frame(self, frame_index: int) -> None:
        self.timeline.set_cursor(frame_index)
        self.timeline_widget.set_cursor_frame(frame_index)

    def scrub_to_frame(self, frame_index: int) -> None:
        if not self.frame_engine:
            return
        self.player_widget.seek_to_frame(frame_index)
        self.timeline.set_cursor(frame_index)

    def toggle_playback(self) -> None:
        if not self.frame_engine:
            return
        if self.playback_controller.is_playing:
            self.playback_controller.pause()
            self.player_widget.pause()
        else:
            self.playback_controller.play()
            self.player_widget.play()

    def _on_playback_finished(self):
        self.playback_controller.stop()

    def load_video(self, file_path: str) -> None:
        self.current_video_path = file_path
        self.frame_engine = FrameAccurateEngine(file_path)
        self.timeline = FrameTimeline(total_frames=self.frame_engine.total_frames, fps=self.frame_engine.fps)
        self.timeline_widget.set_timeline(self.timeline)
        self.timeline_widget.set_preview_source(self.frame_engine)
        self.player_widget.set_engine(self.frame_engine)
        self.player_widget.set_media_source(file_path)
        self.scrub_to_frame(0)
        self._save_session()

    # Core logic hooks (Snapshots, Undo, Export) mirror previous configuration
    def _snapshot(self) -> None:
        self._undo_stack.append({"layers": copy.deepcopy(self.timeline.layers)})
        self._redo_stack.clear()

    def undo(self) -> None:
        if self._undo_stack:
            self._redo_stack.append({"layers": copy.deepcopy(self.timeline.layers)})
            self.timeline.layers = self._undo_stack.pop()["layers"]
            self._refresh_views()

    def redo(self) -> None:
        if self._redo_stack:
            self._undo_stack.append({"layers": copy.deepcopy(self.timeline.layers)})
            self.timeline.layers = self._redo_stack.pop()["layers"]
            self._refresh_views()

    def _refresh_views(self) -> None:
        self.timeline_widget.canvas.update()
        self.timeline_widget.refresh_state()
        self._save_session()
        
    def export_trimmed(self) -> None:
        if not self.current_video_path:
            return
        if not self.timeline.flatten_layers():
            QMessageBox.information(self, "No segments", "Create at least one segment before exporting.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Export")
        layout = QVLayout(dialog)
        form = QFormLayout()
        layout.addLayout(form)
        original = max(0, self.frame_engine.total_frames / max(self.frame_engine.fps, 1.0)) if self.frame_engine else 0
        edited = sum(seg.duration_seconds for seg in self.timeline.flatten_layers()) if hasattr(self.timeline, "flatten_layers") else 0
        removed = max(0, original - edited)
        form.addRow("Edited Duration", QLabel(self._fmt_duration(edited)))
        form.addRow("Original Duration", QLabel(self._fmt_duration(original)))
        form.addRow("Removed", QLabel(self._fmt_duration(removed)))
        mode = QComboBox()
        mode.addItems(["Send To Compressor", "Direct Export"])
        form.addRow("Mode", mode)
        direct_lossless = QCheckBox("Use lossless direct export naming")
        form.addRow("", direct_lossless)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        if mode.currentText() == "Send To Compressor":
            output_name = self.export_engine.build_export_name(self.current_video_path, mode="handoff")
            handoff_path = str(EXPORT_TEMP_DIR / output_name)
            EXPORT_TEMP_DIR.mkdir(parents=True, exist_ok=True)
            self._run_export_job(self.current_video_path, handoff_path, mode="handoff")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Direct Export",
            str(Path.home() / "Desktop" / self.export_engine.build_export_name(self.current_video_path, mode="direct")),
            "MP4 Video (*.mp4);;Matroska Video (*.mkv);;All Files (*.*)"
        )
        if not file_path:
            return
        self._run_export_job(self.current_video_path, file_path, mode="direct")

    def _fmt_duration(self, seconds: float) -> str:
        seconds = max(0, int(round(seconds)))
        minutes, sec = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{sec:02d}"
        return f"{minutes:02d}:{sec:02d}"

    def _run_export_job(self, input_path: str, output_path: str, mode: str) -> None:
        self.btn_export.setEnabled(False)
        self.timeline_widget.state_label.setText("Exporting...")
        worker = ExportWorker(self.export_engine, input_path, output_path, self.timeline, fast_mode=(mode != "direct"))
        self._export_worker = worker
        worker.finished_ok.connect(self._on_export_finished)
        worker.failed.connect(self._on_export_failed)
        worker.finished.connect(lambda: self.btn_export.setEnabled(True))
        worker.start()

    def _on_export_finished(self, output_path: str) -> None:
        self.timeline_widget.state_label.setText("Ready")
        self.exportedVideo.emit(output_path)

    def _on_export_failed(self, message: str) -> None:
        self.timeline_widget.state_label.setText("Ready")
        QMessageBox.critical(self, "Export failed", f"Export failed:\n{message}")

    def _save_session(self) -> None:
        try:
            SESSION_RECOVERY_PATH.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "video_path": self.current_video_path,
                "timeline": self.timeline.layers if self.timeline else {},
                "total_frames": self.timeline.total_frames if self.timeline else 0,
                "fps": self.timeline.fps if self.timeline else 0.0,
                "cursor_frame": self.player_widget.current_frame_index if hasattr(self, "player_widget") else 0,
            }
            SESSION_RECOVERY_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _try_restore_session(self) -> None:
        try:
            if not SESSION_RECOVERY_PATH.exists():
                return
            payload = json.loads(SESSION_RECOVERY_PATH.read_text(encoding="utf-8"))
            video_path = payload.get("video_path")
            if not video_path or not Path(video_path).exists():
                return
            if QMessageBox.question(
                self,
                "Restore previous session?",
                f"Restore the previous editing session for:\n{video_path}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            ) != QMessageBox.StandardButton.Yes:
                return
            self.load_video(video_path)
            if self.timeline and isinstance(payload.get("timeline"), dict):
                self.timeline.layers = payload["timeline"]
                self._refresh_views()
            self.scrub_to_frame(int(payload.get("cursor_frame", 0)))
        except Exception:
            pass

    def create_segment_at_cursor(self) -> None:
        self._snapshot()
        idx = self.player_widget.current_frame_index
        if self.timeline.has_markers():
            self.timeline.create_segment_from_marks()
        else:
            end = min(idx + 50, self.timeline.total_frames)
            self.timeline.add_segment(idx, end)
        self._refresh_views()

    def mark_in(self) -> None:
        self.timeline.set_mark_in(self.player_widget.current_frame_index)
        self._refresh_views()

    def mark_out(self) -> None:
        self.timeline.set_mark_out(self.player_widget.current_frame_index)
        self._refresh_views()

    def remove_timeline_range(self, start_frame: int, end_frame: int) -> None:
        self._snapshot()
        if self.timeline.remove_range(start_frame, end_frame):
            self._refresh_views()
        else:
            self.undo() # Revert snapshot if nothing changed

    def create_segment_range(self, start_frame: int, end_frame: int) -> None:
        self._snapshot()
        self.timeline.add_segment(start_frame, end_frame)
        self._refresh_views()

    def replay_range(self, start_frame: int, end_frame: int) -> None:
        if not self.frame_engine or not self.timeline:
            return
        self.playback_controller.play(PlaybackMode.REPLAY)
        self.player_widget.play_segment_ranges([(start_frame, end_frame)])

    def replay_edited_timeline(self) -> None:
        if not self.frame_engine or not self.timeline:
            return
        
        segments = self.timeline.flatten_layers() if hasattr(self.timeline, "flatten_layers") else self.timeline.keep_segments
        ranges = [(seg.start_frame, seg.end_frame) for seg in segments]
        
        self.playback_controller.play(PlaybackMode.REPLAY)
        self.player_widget.play_segment_ranges(ranges)

    def _delete_selection_or_segment(self) -> None:
        # Check for active drag selection
        sel = self.timeline_widget.canvas.resize_controller.get_selection_bounds()
        if sel:
            self.timeline_widget.selection_actions.removeRequested.emit()
            return
            
        # Otherwise cut at current playhead segment
        seg = self.timeline.segment_at_frame(self.player_widget.current_frame_index)
        if seg:
            self._snapshot()
            self.timeline.delete_segment(seg.id)
            self._refresh_views()
