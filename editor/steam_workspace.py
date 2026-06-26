from __future__ import annotations

import copy
import json
import os
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QObject, QEvent, QThread, QSize
from PyQt6.QtGui import QFont, QImage, QKeySequence, QShortcut, QIcon, QPixmap, QPainter, QColor, QPen, QBrush, QPainterPath
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QMessageBox, 
    QToolButton, QVBoxLayout, QWidget, QToolTip, QDialog, QVBoxLayout as QVLayout,
    QDialogButtonBox, QFormLayout, QComboBox, QCheckBox, QPushButton, QFrame
)

from .ffmpeg_editor_engine import FFmpegEditorEngine
from .frame_engine import FrameAccurateEngine
from .timeline import FrameTimeline
from .player_widget import PreviewPlayerWidget
from .timeline_widget import TimelineWidget, timecode_to_hmsf
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
    """Enforces clean typography design rules by introducing a mandatory 600ms tooltip delay constraint."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(600)  # Polished tooltip delay: 600ms
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


class MetadataPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MetadataPanel")
        self.setFixedWidth(240)
        self.setStyleSheet("""
            QFrame#MetadataPanel {
                background-color: #171A21;
                border: 1px solid #252932;
                border-radius: 12px;
            }
            QLabel {
                font-family: 'Segoe UI', Helvetica, Arial, sans-serif;
                color: #7d848e;
            }
            QLabel#PanelHeader {
                color: #ffffff;
                font-size: 11px;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            QLabel#PlayheadTime {
                color: #ffffff;
                font-size: 22px;
                font-weight: 700;
                font-family: Consolas, Monaco, monospace;
            }
            QLabel#PlayheadFrame {
                color: #d4af37;
                font-size: 13px;
                font-weight: 600;
            }
            QLabel#MetaSectionTitle {
                color: #ffffff;
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            QLabel#MetaVal {
                color: #ffffff;
                font-size: 13px;
                font-family: Consolas, Monaco, monospace;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)
        
        # Cursor Section
        cursor_layout = QVBoxLayout()
        cursor_layout.setSpacing(2)
        lbl_cur_title = QLabel("PLAYHEAD POSITION")
        lbl_cur_title.setObjectName("PanelHeader")
        self.lbl_time = QLabel("00:00:00:00")
        self.lbl_time.setObjectName("PlayheadTime")
        self.lbl_frame = QLabel("Frame 0")
        self.lbl_frame.setObjectName("PlayheadFrame")
        cursor_layout.addWidget(lbl_cur_title)
        cursor_layout.addWidget(self.lbl_time)
        cursor_layout.addWidget(self.lbl_frame)
        layout.addLayout(cursor_layout)
        
        # Divider line
        div1 = QFrame()
        div1.setFrameShape(QFrame.Shape.HLine)
        div1.setStyleSheet("background-color: #252932;")
        layout.addWidget(div1)
        
        # Selection Section
        sel_layout = QVBoxLayout()
        sel_layout.setSpacing(6)
        lbl_sel_title = QLabel("SELECTION RANGE")
        lbl_sel_title.setObjectName("MetaSectionTitle")
        self.lbl_sel_range = QLabel("No Selection")
        self.lbl_sel_range.setObjectName("MetaVal")
        
        lbl_dur_title = QLabel("SELECTION DURATION")
        lbl_dur_title.setObjectName("MetaSectionTitle")
        self.lbl_sel_dur = QLabel("00:00:00:00")
        self.lbl_sel_dur.setObjectName("MetaVal")
        
        sel_layout.addWidget(lbl_sel_title)
        sel_layout.addWidget(self.lbl_sel_range)
        sel_layout.addSpacing(4)
        sel_layout.addWidget(lbl_dur_title)
        sel_layout.addWidget(self.lbl_sel_dur)
        layout.addLayout(sel_layout)
        
        # Divider line
        div2 = QFrame()
        div2.setFrameShape(QFrame.Shape.HLine)
        div2.setStyleSheet("background-color: #252932;")
        layout.addWidget(div2)
        
        # Project Total info
        proj_layout = QVBoxLayout()
        proj_layout.setSpacing(6)
        
        lbl_orig_title = QLabel("ORIGINAL DURATION")
        lbl_orig_title.setObjectName("MetaSectionTitle")
        self.lbl_orig_dur = QLabel("00:00:00:00")
        self.lbl_orig_dur.setObjectName("MetaVal")
        
        lbl_edit_title = QLabel("EDITED EXPORT DURATION")
        lbl_edit_title.setObjectName("MetaSectionTitle")
        self.lbl_edit_dur = QLabel("00:00:00:00")
        self.lbl_edit_dur.setObjectName("MetaVal")
        
        proj_layout.addWidget(lbl_orig_title)
        proj_layout.addWidget(self.lbl_orig_dur)
        proj_layout.addSpacing(4)
        proj_layout.addWidget(lbl_edit_title)
        proj_layout.addWidget(self.lbl_edit_dur)
        layout.addLayout(proj_layout)
        
        layout.addStretch(1)
        
    def update_cursor(self, timecode: str, frame: int) -> None:
        self.lbl_time.setText(timecode)
        self.lbl_frame.setText(f"Frame {frame}")
        
    def update_selection(self, start_tc: str, end_tc: str, dur_tc: str) -> None:
        if start_tc and end_tc:
            self.lbl_sel_range.setText(f"{start_tc}\n→ {end_tc}")
            self.lbl_sel_dur.setText(dur_tc)
        else:
            self.lbl_sel_range.setText("No Selection")
            self.lbl_sel_dur.setText("00:00:00:00")
            
    def update_project(self, orig_tc: str, edit_tc: str) -> None:
        self.lbl_orig_dur.setText(orig_tc)
        self.lbl_edit_dur.setText(edit_tc)


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
        self.setStyleSheet("""
            QWidget#SteamStyleEditorWidget {
                background-color: #0F1115;
                font-family: 'Inter', 'Segoe UI Variable', 'SF Pro', sans-serif;
            }
        """)
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
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # 1. Video Preview & Metadata Panel side-by-side
        preview_row = QHBoxLayout()
        preview_row.setSpacing(16)

        self.player_widget = PreviewPlayerWidget(self.playback_controller)
        self.player_widget.setMinimumHeight(340)
        preview_row.addWidget(self.player_widget, stretch=4)

        self.meta_panel = MetadataPanel()
        preview_row.addWidget(self.meta_panel, stretch=1)
        
        layout.addLayout(preview_row, stretch=4)

        # 2. Playback Controls (Play and Replay have equal 64x64 emphasis)
        playback_row = QHBoxLayout()
        playback_row.setSpacing(24)  # Increased spacing between buttons
        playback_row.addStretch(1)

        self.btn_prev = self._make_icon_button("Previous Frame (Left)", _draw_prev, 48)
        self.btn_play = self._make_icon_button("Play / Pause (Space)", _draw_play_pause, 64)
        self.btn_next = self._make_icon_button("Next Frame (Right)", _draw_next, 48)
        self.btn_replay = self._make_icon_button("Replay Selection", _draw_replay, 64)

        playback_row.addWidget(self.btn_prev)
        playback_row.addWidget(self.btn_play)
        playback_row.addWidget(self.btn_next)
        playback_row.addSpacing(16)
        playback_row.addWidget(self.btn_replay)
        playback_row.addStretch(1)
        layout.addLayout(playback_row)

        # 3. Timeline
        self.timeline_widget = TimelineWidget(self.timeline)
        layout.addWidget(self.timeline_widget, stretch=2)

        # 4. Editing Controls & Project Info
        edit_row = QHBoxLayout()
        edit_row.setSpacing(12)
        
        self.btn_segment = self._make_icon_button("Create Segment", _draw_segment, 48)
        self.btn_mark_in = self._make_icon_button("Mark In", _draw_mark_in, 48)
        self.btn_mark_out = self._make_icon_button("Mark Out", _draw_mark_out, 48)
        self.btn_capture = self._make_icon_button("Save Current Frame", _draw_capture, 48)
        
        edit_row.addWidget(self.btn_segment)
        edit_row.addWidget(self.btn_mark_in)
        edit_row.addWidget(self.btn_mark_out)
        edit_row.addWidget(self.btn_capture)
        edit_row.addStretch(1)
        
        # Project Info labels (dimmed metadata footer)
        self.info_original = QLabel("Original: --")
        self.info_edited = QLabel("Edited: --")
        self.info_original.setStyleSheet("color: #7d848e; font-size: 13px;")
        self.info_edited.setStyleSheet("color: #7d848e; font-size: 13px;")
        
        edit_row.addWidget(self.info_original)
        edit_row.addSpacing(12)
        edit_row.addWidget(self.info_edited)
        
        layout.addLayout(edit_row)

        # 5. Export Button (Hero - reduced height to 48px)
        self.btn_export = QPushButton("  EXPORT")
        self.btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export.setFixedHeight(48)  # Reduced by ~25% from 64
        self.btn_export.setStyleSheet("""
            QPushButton {
                background-color: #d4af37;
                color: #0F1115;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 700;
                letter-spacing: 1px;
            }
            QPushButton:hover {
                background-color: #e5c354;
            }
            QPushButton:pressed {
                background-color: #c29f2e;
            }
            QPushButton:disabled {
                background-color: #252932;
                color: #7d848e;
            }
        """)
        self.btn_export.setIcon(_make_vector_icon(24, _draw_export))
        self.btn_export.setIconSize(QSize(24, 24))
        layout.addWidget(self.btn_export)

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
        self.timeline_widget.selectionChanged.connect(self._on_timeline_selection_changed)
        
        # Connect timeline header toolbar signals
        self.timeline_widget.deleteRequested.connect(self.delete_selected_segment)
        self.timeline_widget.replayRequested.connect(self.replay_selected_segment)
        self.timeline_widget.saveFrameRequested.connect(self.player_widget.save_current_frame)
        self.timeline_widget.splitRequested.connect(self.split_selected_segment)
        self.timeline_widget.duplicateRequested.connect(self.duplicate_selected_segment)
        self.timeline_widget.undoRequested.connect(self.undo)
        self.timeline_widget.redoRequested.connect(self.redo)

    def _make_icon_button(self, tooltip: str, draw_func, size: int = 40) -> QToolButton:
        button = QToolButton()
        icon_size = size // 2 + 4
        button.setIcon(_make_vector_icon(icon_size, draw_func))
        button.setToolTip(tooltip)
        button.installEventFilter(self.tooltip_filter)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setFixedSize(size, size)
        button.setStyleSheet("""
            QToolButton {
                border-radius: 8px;
                background-color: #171A21;
                color: #ffffff;
                border: 1px solid #252932;
            }
            QToolButton:hover {
                background-color: #252932;
                border-color: #3b4252;
            }
            QToolButton:pressed {
                background-color: #000000;
                border-color: #d4af37;
            }
            QToolButton:disabled {
                color: #7d848e;
                background-color: #0F1115;
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
        self._update_meta_panel_playhead(frame_index)

    def scrub_to_frame(self, frame_index: int) -> None:
        if not self.frame_engine:
            return
        self.player_widget.seek_to_frame(frame_index)
        self.timeline.set_cursor(frame_index)
        self._update_meta_panel_playhead(frame_index)

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
        self._refresh_views()
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
        
        # Update info labels
        if self.frame_engine:
            original_duration = max(0, self.frame_engine.total_frames / max(self.frame_engine.fps, 1.0))
            self.info_original.setText(f"Original: {self._fmt_duration(original_duration)}")
        if hasattr(self.timeline, "flatten_layers"):
            edited_duration = sum(seg.duration_seconds for seg in self.timeline.flatten_layers())
            self.info_edited.setText(f"Edited: {self._fmt_duration(edited_duration)}")
            
        self._update_meta_panel_project()
        self._save_session()
        
    def export_trimmed(self) -> None:
        if not self.current_video_path:
            return
        if not self.timeline.flatten_layers():
            QMessageBox.information(self, "No segments", "Create at least one segment before exporting.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Export Summary")
        layout = QVLayout(dialog)
        form = QFormLayout()
        layout.addLayout(form)
        original = max(0, self.frame_engine.total_frames / max(self.frame_engine.fps, 1.0)) if self.frame_engine else 0
        edited = sum(seg.duration_seconds for seg in self.timeline.flatten_layers()) if hasattr(self.timeline, "flatten_layers") else 0
        
        # Estimate size (rough rule of thumb: ~5 MB / minute for 1080p medium quality, or 80kbps per second)
        estimated_mb = edited * (80.0 / 1024.0) 
        
        summary_label = QLabel(f"Original: {self._fmt_duration(original)}  ↓  Edited: {self._fmt_duration(edited)}  ↓  Estimated: ~{estimated_mb:.1f} MB")
        summary_label.setStyleSheet("font-size: 14px; font-weight: bold; margin-bottom: 12px;")
        summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.insertWidget(0, summary_label)
        
        mode = QComboBox()
        mode.addItems(["Send To Parcel", "Direct Export"])
        form.addRow("Mode", mode)
        direct_lossless = QCheckBox("Use lossless direct export naming")
        form.addRow("", direct_lossless)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        if mode.currentText() == "Send To Parcel":
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
        self.info_edited.setText("Exporting...")
        worker = ExportWorker(self.export_engine, input_path, output_path, self.timeline, fast_mode=(mode != "direct"))
        self._export_worker = worker
        worker.finished_ok.connect(self._on_export_finished)
        worker.failed.connect(self._on_export_failed)
        worker.finished.connect(lambda: self.btn_export.setEnabled(True))
        worker.start()

    def _on_export_finished(self, output_path: str) -> None:
        self._refresh_views()
        self.exportedVideo.emit(output_path)

    def _on_export_failed(self, message: str) -> None:
        self._refresh_views()
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
        self.timeline_widget.canvas.set_mark_in_from_cursor()
        self._refresh_views()

    def mark_out(self) -> None:
        self.timeline_widget.canvas.set_mark_out_from_cursor()
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
        self.delete_selected_segment()

    def split_selected_segment(self) -> None:
        seg_id = self.timeline_widget.canvas.selected_segment_id
        if not seg_id:
            return
        target_seg = None
        for seg in self.timeline.keep_segments:
            if seg.id == seg_id:
                target_seg = seg
                break
        if target_seg:
            idx = self.player_widget.current_frame_index
            if target_seg.start_frame < idx < target_seg.end_frame:
                self._snapshot()
                self.timeline.split_at_frame(idx)
                self._refresh_views()

    def duplicate_selected_segment(self) -> None:
        seg_id = self.timeline_widget.canvas.selected_segment_id
        if not seg_id:
            return
        target_seg = None
        for seg in self.timeline.keep_segments:
            if seg.id == seg_id:
                target_seg = seg
                break
        if target_seg:
            self._snapshot()
            dur = target_seg.end_frame - target_seg.start_frame
            new_start = target_seg.end_frame
            new_end = min(new_start + dur, self.timeline.total_frames)
            if new_start < new_end:
                self.timeline.add_segment(new_start, new_end)
                self._refresh_views()

    def delete_selected_segment(self) -> None:
        seg_id = self.timeline_widget.canvas.selected_segment_id
        if not seg_id:
            return
        self._snapshot()
        self.timeline.delete_segment(seg_id)
        self._refresh_views()

    def replay_selected_segment(self) -> None:
        seg_id = self.timeline_widget.canvas.selected_segment_id
        if not seg_id:
            return
        target_seg = None
        for seg in self.timeline.keep_segments:
            if seg.id == seg_id:
                target_seg = seg
                break
        if target_seg:
            self.replay_range(target_seg.start_frame, target_seg.end_frame)

    def _on_timeline_selection_changed(self) -> None:
        sel = self.timeline_widget.canvas.resize_controller.get_selection_bounds()
        if sel and sel[1] > sel[0]:
            start_tc = timecode_to_hmsf(sel[0], self.timeline.fps)
            end_tc = timecode_to_hmsf(sel[1], self.timeline.fps)
            dur_tc = timecode_to_hmsf(sel[1] - sel[0], self.timeline.fps)
            self.meta_panel.update_selection(start_tc, end_tc, dur_tc)
        else:
            self.meta_panel.update_selection("", "", "")

    def _update_meta_panel_playhead(self, frame_index: int) -> None:
        if self.timeline:
            tc = timecode_to_hmsf(frame_index, self.timeline.fps)
            self.meta_panel.update_cursor(tc, frame_index)

    def _update_meta_panel_project(self) -> None:
        if not self.timeline:
            return
        orig_tc = timecode_to_hmsf(self.timeline.total_frames, self.timeline.fps)
        segments = self.timeline.flatten_layers() if hasattr(self.timeline, "flatten_layers") else self.timeline.keep_segments
        total_edited = sum(seg.duration_frames for seg in segments)
        edit_tc = timecode_to_hmsf(total_edited, self.timeline.fps)
        self.meta_panel.update_project(orig_tc, edit_tc)
