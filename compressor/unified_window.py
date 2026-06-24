from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import av
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QIcon, QPainter, QPixmap, QColor, QPen, QPainterPath, QBrush
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QCheckBox,
    QDoubleSpinBox,
    QStackedWidget,
    QListWidget,
    QListWidgetItem,
    QSizePolicy
)

from .media_profiles import AUDIO_BITRATES, ENCODERS, FORMATS, FPS_OPTIONS, QUALITIES, RESOLUTIONS, CODEC_MAP, get_resolution_scale
from .settings_manager import SettingsManager
from .home_page import HomePage
from editor.steam_workspace import SteamStyleEditorWidget
from editor.player_widget import PreviewPlayerWidget
from editor.frame_engine import FrameAccurateEngine
from editor.playback_controller import PlaybackController


APP_QSS = """
QWidget {
    background: #0d0e12;
    color: #f3f4f6;
    font-family: "abcNormal", "Segoe UI Variable", "Segoe UI", sans-serif;
    font-size: 16px;
    letter-spacing: -0.16px;
}
QLabel {
    background: transparent;
}
QMainWindow {
    background: #0d0e12;
}
QFrame#Sidebar {
    background: #161920;
    border-right: 1px solid #262b37;
}
QFrame#PageCard {
    background: #161920;
    border: 1px solid #262b37;
    border-radius: 12px;
}
QToolButton#NavButton {
    color: #9ca3af;
    background: transparent;
    border: 1px solid transparent;
    padding: 12px;
    text-align: left;
    border-radius: 8px;
    font-size: 16px;
}
QToolButton#NavButton:hover {
    background: #2b3242;
    color: #f3f4f6;
    border-color: #262b37;
}
QToolButton#NavButton:checked {
    color: #f3f4f6;
    background: #2b3242;
    border-color: #2b3242;
    border-left: 3px solid #6366f1;
}
QPushButton {
    background: #1f242f;
    color: #f3f4f6;
    border: 1px solid #262b37;
    padding: 10px 14px;
    border-radius: 6px;
}
QPushButton:hover {
    background: #2b3242;
    border-color: #6366f1;
}
QPushButton:pressed {
    background: #161920;
    border-color: #6366f1;
}
QPushButton:disabled {
    color: #9ca3af;
    background: #161920;
    border-color: #262b37;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTreeWidget, QListWidget {
    background: #1f242f;
    color: #f3f4f6;
    border: 1px solid #262b37;
    border-radius: 8px;
    padding: 10px 14px;
    selection-background-color: #2b3242;
    selection-color: #f3f4f6;
}
QTreeWidget::item:selected, QListWidget::item:selected {
    background: #2b3242;
}
QHeaderView::section {
    background: transparent;
    color: #9ca3af;
    border: none;
    padding: 0px 12px 6px 12px;
}
QLabel#Muted {
    color: #9ca3af;
}
QProgressBar {
    border: 1px solid #262b37;
    border-radius: 8px;
    background: #1f242f;
    text-align: center;
    color: #f3f4f6;
}
QProgressBar::chunk {
    background: #6366f1;
    border-radius: 8px;
}
QCheckBox {
    spacing: 8px;
    color: #f3f4f6;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
}
QCheckBox::indicator:unchecked {
    border: 1px solid #262b37;
    background: #1f242f;
}
QCheckBox::indicator:checked {
    border: 1px solid #6366f1;
    background: #2b3242;
}
QScrollBar:vertical {
    border: none;
    background: #0d0e12;
    width: 8px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #262b37;
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    border: none;
    background: #0d0e12;
    height: 8px;
    margin: 0px;
}
QScrollBar::handle:horizontal {
    background: #262b37;
    min-width: 20px;
    border-radius: 4px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}
QToolTip {
    background: #161920;
    border: 1px solid #262b37;
    color: #f3f4f6;
    padding: 4px 6px;
}
QMenu {
    background: #161920;
    border: 1px solid #262b37;
}
QMenu::item:selected {
    background: #2b3242;
}
QSplitter::handle {
    background: #262b37;
    width: 2px;
}
"""


def _format_size_mb(path: str) -> str:
    try:
        return f"{os.path.getsize(path) / (1024 * 1024):.2f} MB"
    except OSError:
        return "Unknown"


def _probe_duration_seconds(path: str) -> float:
    try:
        container = av.open(path)
        if container.duration:
            duration = float(container.duration / av.time_base)
            container.close()
            return duration
        if container.streams.video:
            stream = container.streams.video[0]
            if stream.duration and stream.time_base:
                duration = float(stream.duration * stream.time_base)
                container.close()
                return duration
        container.close()
    except Exception:
        return 0.0
    return 0.0


def _codec_for_selection(codec_label: str, encoder_label: str) -> str:
    codec_key = codec_label.replace(" ", "")
    encoder_label = encoder_label
    mapping = CODEC_MAP.get(codec_key, {})
    return mapping.get(encoder_label, mapping.get("x264", "libx264"))


def _quality_to_preset(quality: str) -> str:
    return {
        "Fastest": "ultrafast",
        "Fast": "veryfast",
        "Balanced": "medium",
        "Quality": "slow",
        "Best Quality": "veryslow",
        "Lossless": "veryslow",
    }.get(quality, "medium")


def _build_output_name(input_path: str, settings: dict) -> str:
    source = Path(input_path)
    name = source.stem
    if settings.get("handoff_mode"):
        stem = f"{name}_EditedForCompressor"
    elif settings.get("export_mode") == "direct":
        stem = f"{name}_DirectExport"
    else:
        parts = [name]
        resolution = settings.get("resolution", "Original")
        codec = settings.get("codec", "H264")
        fps = settings.get("fps", "Original")
        quality = settings.get("quality", "")
        if resolution and resolution != "Original":
            parts.append(resolution)
        parts.append(codec)
        if quality == "Lossless":
            parts.append("Lossless")
        if fps and fps != "Original":
            parts.append(f"{fps}FPS")
        stem = "_".join(parts)
    ext = {
        "MP4": ".mp4",
        "MKV": ".mkv",
        "MOV": ".mov",
        "AVI": ".avi",
        "WEBM": ".webm",
    }.get(settings.get("output_format", "MP4"), ".mp4")
    return f"{stem}{ext}"


class CompressionWorker(QThread):
    item_started = pyqtSignal(int, str)
    item_progress = pyqtSignal(int, int)
    item_finished = pyqtSignal(int, str)
    log_message = pyqtSignal(str)
    all_finished = pyqtSignal()

    def __init__(self, jobs: list[str], settings: dict):
        super().__init__()
        self.jobs = jobs
        self.settings = settings

    def _build_command(self, input_file: str, output_file: str) -> list[str]:
        output_format = self.settings.get("output_format", "MP4")
        codec_label = self.settings.get("codec", "H264")
        encoder_label = self.settings.get("encoder", "x264")
        resolution = self.settings.get("resolution", "Original")
        fps_value = self.settings.get("fps", "Original")
        quality = self.settings.get("quality", "Balanced")
        audio_bitrate = int(self.settings.get("audio_bitrate", 128))
        target_size_mb = float(self.settings.get("target_size_mb", 25))
        ffmpeg_bin = self.settings.get("ffmpeg_path") or "ffmpeg"
        codec = _codec_for_selection(codec_label, encoder_label)
        duration = max(1.0, _probe_duration_seconds(input_file))
        target_total_kbps = max(300, int((target_size_mb * 8192) / duration))
        video_bitrate = max(180, target_total_kbps - audio_bitrate)

        cmd = [ffmpeg_bin, "-y", "-i", input_file]
        filters = []
        scale_filter = get_resolution_scale(resolution)
        if scale_filter:
            filters.append(scale_filter)
        if fps_value not in ("Original", "Custom"):
            try:
                target_fps = int(fps_value)
                filters.append(f"fps={target_fps}")
            except ValueError:
                pass
        if filters:
            cmd.extend(["-vf", ",".join(filters)])

        cmd.extend(["-c:v", codec])

        if quality == "Lossless":
            if codec == "libx265":
                cmd.extend(["-x265-params", "lossless=1"])
            elif codec == "libaom-av1":
                cmd.extend(["-crf", "0", "-b:v", "0"])
            else:
                cmd.extend(["-crf", "0"])
        elif codec.startswith("lib"):
            cmd.extend(["-preset", _quality_to_preset(quality)])
            cmd.extend(["-b:v", f"{video_bitrate}k", "-maxrate", f"{int(video_bitrate * 1.2)}k", "-bufsize", f"{int(video_bitrate * 2)}k"])
        else:
            cmd.extend(["-b:v", f"{video_bitrate}k"])

        cmd.extend(["-c:a", "aac", "-b:a", f"{audio_bitrate}k"])
        cmd.extend(["-movflags", "+faststart", "-progress", "pipe:1", "-nostats", output_file])
        return cmd

    def run(self) -> None:
        for index, input_file in enumerate(self.jobs):
            output_file = self._resolve_output_path(input_file)
            self.item_started.emit(index, input_file)
            cmd = self._build_command(input_file, output_file)
            self.log_message.emit(" ".join(cmd))
            try:
                duration = max(1.0, _probe_duration_seconds(input_file))
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                last_percent = 0
                if process.stdout:
                    for line in process.stdout:
                        line = line.strip()
                        if line.startswith("out_time_ms="):
                            try:
                                out_time_ms = int(line.split("=", 1)[1])
                                percent = min(99, int((out_time_ms / 1_000_000) / duration * 100))
                                if percent != last_percent:
                                    last_percent = percent
                                    self.item_progress.emit(index, percent)
                            except ValueError:
                                pass
                        elif line:
                            self.log_message.emit(line)
                return_code = process.wait()
                if return_code != 0:
                    raise subprocess.CalledProcessError(return_code, cmd)
                self.item_progress.emit(index, 100)
                self.item_finished.emit(index, output_file)
            except Exception as exc:
                self.item_finished.emit(index, f"ERROR: {exc}")
        self.all_finished.emit()

    def _resolve_output_path(self, input_file: str) -> str:
        settings = self.settings
        output_mode = settings.get("output_mode", "same_folder")
        if output_mode == "custom_folder" and settings.get("custom_output_folder"):
            output_dir = Path(settings["custom_output_folder"])
        else:
            output_dir = Path(input_file).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        return str(output_dir / _build_output_name(input_file, settings))


class QueuePage(QWidget):
    queueChanged = pyqtSignal()
    compressRequested = pyqtSignal()

    def __init__(self, settings_manager: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.current_asset_path = ""
        self._asset_engine = None
        self._preview_controller = PlaybackController()
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Compressor")
        title.setFont(QFont("abcNormal", 16, QFont.Weight.Medium))
        subtitle = QLabel("Load one asset, tune output settings, and compress it directly.")
        subtitle.setObjectName("Muted")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(subtitle)
        root.addLayout(header)

        body = QVBoxLayout()
        body.setSpacing(12)
        root.addLayout(body, stretch=1)

        card = QFrame(objectName="PageCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 12, 12, 12)
        card_layout.setSpacing(12)
        body.addWidget(card)

        toolbar = QHBoxLayout()
        self.btn_add = QPushButton("Add File")
        self.btn_open_path = QPushButton("Load Path")
        self.btn_clear = QPushButton("Clear")
        self.btn_add.setIcon(_make_nav_icon("open"))
        self.btn_open_path.setIcon(_make_nav_icon("open"))
        self.btn_clear.setIcon(_make_nav_icon("reset"))
        for button in (self.btn_add, self.btn_open_path, self.btn_clear):
            button.setIconSize(QSize(18, 18))
            toolbar.addWidget(button)
        toolbar.addStretch(1)
        card_layout.addLayout(toolbar)

        self.asset_path = QLineEdit()
        self.asset_path.setPlaceholderText("Paste or type a single video file path")
        card_layout.addWidget(self.asset_path)

        self.preview_card = QFrame(objectName="PageCard")
        self.preview_card.setStyleSheet("background: #161920; border: 1px solid #262b37; border-radius: 12px;")
        preview_layout = QVBoxLayout(self.preview_card)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_layout.setSpacing(12)
        self.preview_empty = QLabel("No asset loaded")
        self.preview_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_empty.setStyleSheet("color: #9ca3af; background: transparent; padding: 56px 0;")
        self.preview_player = PreviewPlayerWidget(self._preview_controller)
        self.preview_player.hide()
        preview_layout.addWidget(self.preview_empty)
        preview_layout.addWidget(self.preview_player)
        card_layout.addWidget(self.preview_card)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)
        body.addLayout(form)

        self.target_size = QDoubleSpinBox()
        self.target_size.setRange(1, 10000)
        self.target_size.setSuffix(" MB")
        self.target_size.setDecimals(1)

        self.output_format = QComboBox()
        self.output_format.addItems(FORMATS)

        self.encoder = QComboBox()
        self.encoder.addItems(ENCODERS)

        self.codec = QComboBox()
        self.codec.addItems(["H264", "H265", "AV1", "VP9"])

        self.resolution = QComboBox()
        self.resolution.addItems(RESOLUTIONS)

        self.fps = QComboBox()
        self.fps.addItems(FPS_OPTIONS)

        self.quality = QComboBox()
        self.quality.addItems(QUALITIES + ["Lossless"])

        self.audio_bitrate = QComboBox()
        self.audio_bitrate.addItems(AUDIO_BITRATES)

        self.output_mode = QComboBox()
        self.output_mode.addItems(["Same folder", "Custom folder"])

        self.output_folder = QLineEdit()
        self.output_folder.setPlaceholderText("Leave blank for same folder")

        widgets = [
            ("Target size", self.target_size),
            ("Format", self.output_format),
            ("Encoder", self.encoder),
            ("Codec", self.codec),
            ("Resolution", self.resolution),
            ("FPS", self.fps),
            ("Quality", self.quality),
            ("Audio", self.audio_bitrate),
            ("Output", self.output_mode),
            ("Folder", self.output_folder),
        ]
        for row, (label, widget) in enumerate(widgets):
            form.addWidget(QLabel(label), row, 0)
            form.addWidget(widget, row, 1)

        self.auto_open = QCheckBox("Auto-open output folder")
        self.verify_output = QCheckBox("Verify output exists")
        body.addWidget(self.auto_open)
        body.addWidget(self.verify_output)

        self.btn_compress = QPushButton("Compress Queue")
        self.btn_compress.setStyleSheet("""
            QPushButton {
                background: #6366f1;
                color: #f3f4f6;
                border: 1px solid #6366f1;
                padding: 12px 14px;
                border-radius: 8px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #4f46e5;
                border-color: #4f46e5;
            }
            QPushButton:pressed {
                background: #4338ca;
                border-color: #4338ca;
            }
            QPushButton:disabled {
                background: #2b3242;
                color: #9ca3af;
                border-color: #262b37;
            }
        """)
        body.addWidget(self.btn_compress)

        self.progress = QProgressBar()
        self.status = QLabel("Idle")
        self.status.setObjectName("Muted")
        body.addWidget(self.progress)
        body.addWidget(self.status)

        self.btn_add.clicked.connect(self._add_files)
        self.btn_open_path.clicked.connect(self._load_from_path)
        self.btn_clear.clicked.connect(self.clear)
        self.btn_compress.clicked.connect(self.compressRequested.emit)

        for widget in (self.target_size, self.output_format, self.encoder, self.codec, self.resolution, self.fps, self.quality, self.audio_bitrate, self.output_mode, self.output_folder, self.auto_open, self.verify_output):
            if isinstance(widget, QComboBox):
                widget.currentTextChanged.connect(self.save_settings)
            elif isinstance(widget, QDoubleSpinBox):
                widget.valueChanged.connect(self.save_settings)
            elif isinstance(widget, QLineEdit):
                widget.editingFinished.connect(self.save_settings)
            else:
                widget.toggled.connect(self.save_settings)

    def _load_settings(self) -> None:
        self.target_size.setValue(float(self.settings_manager.get("target_size_mb", 25)))
        self.output_format.setCurrentText(self.settings_manager.get("output_format", "MP4"))
        self.encoder.setCurrentText(self.settings_manager.get("encoder", "x264"))
        self.codec.setCurrentText(self.settings_manager.get("codec", "H264"))
        self.resolution.setCurrentText(self.settings_manager.get("resolution", "Original"))
        self.fps.setCurrentText(self.settings_manager.get("fps", "Original"))
        self.quality.setCurrentText(self.settings_manager.get("quality", "Balanced"))
        self.audio_bitrate.setCurrentText(str(self.settings_manager.get("audio_bitrate", "128")))
        self.output_mode.setCurrentText("Custom folder" if self.settings_manager.get("output_mode", "same_folder") == "custom_folder" else "Same folder")
        self.output_folder.setText(self.settings_manager.get("custom_output_folder", ""))
        self.auto_open.setChecked(bool(self.settings_manager.get("auto_open", True)))
        self.verify_output.setChecked(bool(self.settings_manager.get("verify_output", True)))

    def save_settings(self) -> None:
        self.settings_manager.set("target_size_mb", str(self.target_size.value()))
        self.settings_manager.set("output_format", self.output_format.currentText())
        self.settings_manager.set("encoder", self.encoder.currentText())
        self.settings_manager.set("codec", self.codec.currentText())
        self.settings_manager.set("resolution", self.resolution.currentText())
        self.settings_manager.set("fps", self.fps.currentText())
        self.settings_manager.set("quality", self.quality.currentText())
        self.settings_manager.set("audio_bitrate", self.audio_bitrate.currentText())
        self.settings_manager.set("output_mode", "custom_folder" if self.output_mode.currentText() == "Custom folder" else "same_folder")
        self.settings_manager.set("custom_output_folder", self.output_folder.text().strip())
        self.settings_manager.set("auto_open", self.auto_open.isChecked())
        self.settings_manager.set("verify_output", self.verify_output.isChecked())

    def current_settings(self) -> dict:
        self.save_settings()
        return dict(self.settings_manager.settings)

    def add_files(self, paths: list[str]) -> None:
        for path in paths:
            if path and os.path.isfile(path):
                self.load_asset(path)
                break
        self.queueChanged.emit()

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Add Videos", "", "Video Files (*.mp4 *.mkv *.mov *.avi *.webm);;All Files (*.*)")
        if paths:
            self.add_files(paths)

    def clear(self) -> None:
        self.current_asset_path = ""
        self.asset_path.clear()
        self.preview_player.hide()
        self.preview_empty.show()
        self._preview_controller.stop()
        self._asset_engine = None
        self.queueChanged.emit()

    def queue_paths(self) -> list[str]:
        return [self.current_asset_path] if self.current_asset_path else []

    def update_row(self, index: int, status: str, percent: int | None = None) -> None:
        if percent is None:
            self.status.setText(status)
        else:
            self.status.setText(f"{status} ({percent}%)")

    def _load_from_path(self) -> None:
        path = self.asset_path.text().strip()
        if path:
            self.load_asset(path)

    def load_asset(self, path: str) -> None:
        if not path or not os.path.isfile(path):
            self.status.setText("Invalid asset path")
            return
        self.current_asset_path = path
        self.asset_path.setText(path)
        try:
            self._asset_engine = FrameAccurateEngine(path)
            self.preview_player.set_engine(self._asset_engine)
            self.preview_player.set_media_source(path)
            self.preview_player.show_frame(0)
            self.preview_player.show()
            self.preview_empty.hide()
            self.status.setText("Asset loaded")
        except Exception as exc:
            self.preview_player.hide()
            self.preview_empty.show()
            self._asset_engine = None
            self.status.setText(f"Load failed: {exc}")


class SettingsPage(QWidget):
    def __init__(self, settings_manager: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        title = QLabel("Settings")
        title.setFont(QFont("Segoe UI Variable", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        card = QFrame(objectName="PageCard")
        grid = QGridLayout(card)
        grid.setSpacing(10)
        layout.addWidget(card)

        self.ffmpeg_path = QLineEdit()
        self.ffprobe_path = QLineEdit()
        self.naming_pattern = QLineEdit()
        self.preview_quality = QComboBox()
        self.preview_quality.addItems(["Full", "1/2", "1/4", "1/8"])
        self.auto_open = QCheckBox("Auto-open output folder")
        self.verify_output = QCheckBox("Verify output exists")
        self.always_on_top = QCheckBox("Always on top")

        self.ffmpeg_path.setText(self.settings_manager.get("ffmpeg_path", ""))
        self.ffprobe_path.setText(self.settings_manager.get("ffprobe_path", ""))
        self.naming_pattern.setText(self.settings_manager.get("naming_pattern", "{name}_compressed"))
        self.preview_quality.setCurrentText(self.settings_manager.get("preview_quality", "1/2"))
        self.auto_open.setChecked(bool(self.settings_manager.get("auto_open", True)))
        self.verify_output.setChecked(bool(self.settings_manager.get("verify_output", True)))
        self.always_on_top.setChecked(bool(self.settings_manager.get("always_on_top", False)))

        rows = [
            ("FFmpeg path", self.ffmpeg_path),
            ("FFprobe path", self.ffprobe_path),
            ("Naming pattern", self.naming_pattern),
            ("Default Preview Quality", self.preview_quality)
        ]
        for row, (label, widget) in enumerate(rows):
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(widget, row, 1)
            
        grid.addWidget(self.auto_open, len(rows), 0, 1, 2)
        grid.addWidget(self.verify_output, len(rows) + 1, 0, 1, 2)
        grid.addWidget(self.always_on_top, len(rows) + 2, 0, 1, 2)

        folders_label = QLabel("Watch Folders")
        folders_label.setFont(QFont("abcNormal", 12, QFont.Weight.Medium))
        folders_label.setStyleSheet("background: transparent; color: #f3f4f6;")
        grid.addWidget(folders_label, len(rows) + 3, 0, 1, 2)

        self.watch_folder_path = QLineEdit()
        self.watch_folder_path.setPlaceholderText("Paste a folder path to add it")
        self.btn_add_folder = QPushButton("Add Folder")
        self.btn_remove_folder = QPushButton("Remove Folder")
        add_row = QHBoxLayout()
        add_row.addWidget(self.watch_folder_path, stretch=1)
        add_row.addWidget(self.btn_add_folder)
        add_row.addWidget(self.btn_remove_folder)
        grid.addLayout(add_row, len(rows) + 4, 0, 1, 2)

        self.folders_list = QListWidget()
        self.folders_list.setFixedHeight(120)
        self._refresh_folders_list()
        grid.addWidget(self.folders_list, len(rows) + 5, 0, 1, 2)

        self.btn_add_folder.clicked.connect(self._add_folder)
        self.btn_remove_folder.clicked.connect(self._remove_folder)

        self.btn_save = QPushButton("Save Settings")
        layout.addWidget(self.btn_save)
        self.btn_save.clicked.connect(self.save)
        
    def _refresh_folders_list(self):
        self.folders_list.clear()
        for f in self.settings_manager.get_watch_folders():
            item = QListWidgetItem(f)
            item.setData(Qt.ItemDataRole.UserRole, f)
            self.folders_list.addItem(item)
            
    def _add_folder(self):
        folder = self.watch_folder_path.text().strip() or QFileDialog.getExistingDirectory(self, "Add Watch Folder")
        if folder:
            self.settings_manager.add_watch_folder(folder)
            self.watch_folder_path.clear()
            self._refresh_folders_list()
            
    def _remove_folder(self):
        item = self.folders_list.currentItem()
        if item:
            self.settings_manager.remove_watch_folder(item.data(Qt.ItemDataRole.UserRole))
            self._refresh_folders_list()

    def save(self) -> None:
        self.settings_manager.set("ffmpeg_path", self.ffmpeg_path.text().strip())
        self.settings_manager.set("ffprobe_path", self.ffprobe_path.text().strip())
        self.settings_manager.set("naming_pattern", self.naming_pattern.text().strip() or "{name}_compressed")
        self.settings_manager.set("preview_quality", self.preview_quality.currentText())
        self.settings_manager.set("auto_open", self.auto_open.isChecked())
        self.settings_manager.set("verify_output", self.verify_output.isChecked())
        self.settings_manager.set("always_on_top", self.always_on_top.isChecked())


class UnifiedVideoSuiteWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings_manager = SettingsManager()
        self.setWindowTitle("Video Compressor + Editor")
        self.resize(1600, 950)
        self.setAcceptDrops(True)
        self._worker = None
        self._sidebar_expanded = True
        self._setup_ui()
        self._apply_theme()

    def _apply_theme(self) -> None:
        self.setStyleSheet(APP_QSS)
        if self.settings_manager.get("always_on_top", False):
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path and Path(path).suffix.lower() in [".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"]:
                self._open_video_in_editor(path)
                return

    def _setup_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar = QFrame(objectName="Sidebar")
        sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(16, 16, 16, 16)
        sidebar_layout.setSpacing(12)

        self.btn_sidebar_toggle = QToolButton()
        self.btn_sidebar_toggle.setText("⟨")
        self.btn_sidebar_toggle.setToolTip("Collapse sidebar")
        self.btn_sidebar_toggle.setFixedSize(32, 32)
        self.btn_sidebar_toggle.clicked.connect(self.toggle_sidebar)
        sidebar_layout.addWidget(self.btn_sidebar_toggle, alignment=Qt.AlignmentFlag.AlignRight)

        self.sidebar_brand = QLabel("Compressor")
        self.sidebar_brand.setFont(QFont("abcNormal", 16, QFont.Weight.Medium))
        self.sidebar_brand_sub = QLabel("Editor + Compressor")
        self.sidebar_brand_sub.setObjectName("Muted")
        self.sidebar_brand.setStyleSheet("background: transparent;")
        self.sidebar_brand_sub.setStyleSheet("background: transparent;")
        sidebar_layout.addWidget(self.sidebar_brand)
        sidebar_layout.addWidget(self.sidebar_brand_sub)

        self.nav_buttons = {}
        self.nav_labels = {}
        for name, icon, page, tooltip in [
            ("Home", _make_nav_icon("home"), 0, "Dashboard & Recent Files"),
            ("Editor", _make_nav_icon("editor"), 1, "Clip Editor"),
            ("Compressor", _make_nav_icon("compressor"), 2, "Compression Queue"),
            ("Settings", _make_nav_icon("settings"), 3, "App Settings"),
        ]:
            button = QToolButton()
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setIcon(icon)
            button.setText(name)
            button.setToolTip(tooltip)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setIconSize(QSize(18, 18))
            button.setMinimumHeight(42)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.setStyleSheet(button.styleSheet() + "padding-left: 16px; padding-right: 16px; background: transparent;")
            button.clicked.connect(lambda checked=False, index=page, n=name: self._switch_page(index, n))
            sidebar_layout.addWidget(button)
            self.nav_buttons[name] = button
            self.nav_labels[name] = name

        sidebar_layout.addStretch(1)
        self.sidebar_footer = QLabel("v4 editor")
        self.sidebar_footer.setObjectName("Muted")
        self.sidebar_footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sidebar_footer.setStyleSheet("background: transparent;")
        sidebar_layout.addWidget(self.sidebar_footer)
        root_layout.addWidget(sidebar)

        self.pages = QStackedWidget()
        root_layout.addWidget(self.pages, stretch=1)

        self.home_page = HomePage(self.settings_manager)
        self.queue_page = QueuePage(self.settings_manager)
        self.editor_page = SteamStyleEditorWidget()
        self.settings_page = SettingsPage(self.settings_manager)
        
        self.pages.addWidget(self.home_page)
        self.pages.addWidget(self.editor_page)
        self.pages.addWidget(self.queue_page)
        self.pages.addWidget(self.settings_page)

        self.home_page.openVideoRequested.connect(self._open_video_in_editor)
        self.queue_page.compressRequested.connect(self.start_queue_compression)
        self.editor_page.exportedVideo.connect(self._on_editor_exported)
        self.queue_page.queueChanged.connect(self._sync_status)

        self.nav_buttons["Home"].setChecked(True)
        self.pages.setCurrentIndex(0)
        self.statusBar().showMessage("Ready")
        self._sync_sidebar_state()

    def _switch_page(self, index, name):
        self.pages.setCurrentIndex(index)
        self.statusBar().showMessage(f"Navigated to {name}")
        if index == 0:
            self.home_page.refresh_recents()

    def toggle_sidebar(self) -> None:
        self._sidebar_expanded = not self._sidebar_expanded
        self._sync_sidebar_state()

    def _sync_sidebar_state(self) -> None:
        sidebar = self.findChild(QFrame, "Sidebar")
        if sidebar:
            sidebar.setFixedWidth(220 if self._sidebar_expanded else 64)
        self.sidebar_brand.setVisible(self._sidebar_expanded)
        self.sidebar_brand_sub.setVisible(self._sidebar_expanded)
        self.sidebar_footer.setVisible(self._sidebar_expanded)
        self.btn_sidebar_toggle.setText("⟨" if self._sidebar_expanded else "⟩")
        self.btn_sidebar_toggle.setToolTip("Collapse sidebar" if self._sidebar_expanded else "Expand sidebar")
        for name, button in self.nav_buttons.items():
            if self._sidebar_expanded:
                button.setText(self.nav_labels[name])
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                button.setIconSize(QSize(18, 18))
                button.setMinimumHeight(42)
                button.setToolTip(button.toolTip())
            else:
                button.setText("")
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                button.setIconSize(QSize(18, 18))
                button.setMinimumHeight(42)

    def _sync_status(self) -> None:
        asset = self.queue_page.queue_paths()
        if asset:
            self.statusBar().showMessage(f"Loaded asset: {os.path.basename(asset[0])}")
        else:
            self.statusBar().showMessage("Ready")

    def start_queue_compression(self) -> None:
        jobs = self.queue_page.queue_paths()
        if not jobs:
            QMessageBox.information(self, "No asset loaded", "Load a single video first.")
            return
        self.queue_page.save_settings()
        self._worker = CompressionWorker(jobs, self.queue_page.current_settings())
        self._worker.item_started.connect(self._on_item_started)
        self._worker.item_progress.connect(self._on_item_progress)
        self._worker.item_finished.connect(self._on_item_finished)
        self._worker.log_message.connect(self._on_worker_log)
        self._worker.all_finished.connect(self._on_worker_done)
        self.queue_page.btn_compress.setEnabled(False)
        self._worker.start()

    def _on_item_started(self, index: int, path: str) -> None:
        self.queue_page.update_row(index, "Processing", 0)
        self.queue_page.progress.setValue(0)
        self.statusBar().showMessage(f"Processing {os.path.basename(path)}")

    def _on_item_progress(self, index: int, percent: int) -> None:
        self.queue_page.update_row(index, "Processing", percent)
        self.queue_page.progress.setValue(percent)

    def _on_item_finished(self, index: int, message: str) -> None:
        if message.startswith("ERROR:"):
            self.queue_page.update_row(index, message, None)
        else:
            self.queue_page.update_row(index, "Completed", 100)
            self.queue_page.progress.setValue(100)
        if self.queue_page.auto_open.isChecked() and not message.startswith("ERROR:"):
            try:
                os.startfile(str(Path(message).parent))
            except Exception:
                pass

    def _on_worker_log(self, text: str) -> None:
        pass

    def _on_worker_done(self) -> None:
        self.queue_page.btn_compress.setEnabled(True)
        self.queue_page.progress.setValue(0)
        self.statusBar().showMessage("Compression complete")

    def open_editor_page(self) -> None:
        self.nav_buttons["Editor"].setChecked(True)
        self._switch_page(1, "Editor")

    def open_queue_page(self) -> None:
        self.nav_buttons["Compressor"].setChecked(True)
        self._switch_page(2, "Compressor")

    def open_home_page(self) -> None:
        self.nav_buttons["Home"].setChecked(True)
        self._switch_page(0, "Home")

    def open_settings_page(self) -> None:
        self.nav_buttons["Settings"].setChecked(True)
        self._switch_page(3, "Settings")

    def _open_video_in_editor(self, path: str) -> None:
        if not path:
            return
        self.editor_page.load_video(path)
        self.open_editor_page()

    def _on_editor_exported(self, path: str) -> None:
        if not path:
            return
        self.queue_page.add_files([path])
        self.open_queue_page()
        self.statusBar().showMessage(
            f"Export saved to temp — added to compressor queue: {os.path.basename(path)}"
        )
def _make_nav_icon(kind: str, size: int = 18) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QPen(QColor("#9ca3af"), 1.75, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if kind == "home":
        path = QPainterPath()
        path.moveTo(3, 9)
        path.lineTo(9, 4)
        path.lineTo(15, 9)
        path.lineTo(15, 15)
        path.lineTo(9, 15)
        path.lineTo(9, 11)
        path.lineTo(7, 11)
        path.lineTo(7, 15)
        path.lineTo(3, 15)
        path.closeSubpath()
        painter.drawPath(path)
    elif kind == "editor":
        painter.drawRoundedRect(3, 4, 12, 10, 2, 2)
        painter.drawLine(6, 4, 6, 14)
        painter.drawLine(9, 7, 13, 7)
    elif kind == "compressor":
        painter.drawRect(4, 4, 10, 10)
        painter.drawLine(4, 7, 14, 7)
        painter.drawLine(4, 10, 14, 10)
    elif kind == "settings":
        painter.drawEllipse(6, 6, 6, 6)
        painter.drawLine(9, 3, 9, 5)
        painter.drawLine(9, 13, 9, 15)
        painter.drawLine(3, 9, 5, 9)
        painter.drawLine(13, 9, 15, 9)
    elif kind == "open":
        painter.drawRoundedRect(3, 6, 12, 8, 2, 2)
        painter.drawLine(5, 6, 7, 4)
        painter.drawLine(7, 4, 11, 4)
    elif kind == "refresh":
        painter.drawArc(3, 3, 12, 12, 30 * 16, 280 * 16)
        painter.drawLine(12, 4, 14, 6)
        painter.drawLine(12, 4, 11, 7)
    elif kind == "folder":
        painter.drawRoundedRect(3, 5, 12, 8, 2, 2)
        painter.drawLine(3, 7, 6, 7)
        painter.drawLine(6, 5, 8, 7)
    elif kind == "trash":
        painter.drawRect(5, 6, 8, 8)
        painter.drawLine(4, 6, 14, 6)
        painter.drawLine(7, 4, 11, 4)
    elif kind == "reset":
        painter.drawArc(3, 3, 12, 12, 45 * 16, 270 * 16)
        painter.drawLine(11, 3, 14, 3)
        painter.drawLine(14, 3, 14, 6)
    painter.end()
    return QIcon(pixmap)
