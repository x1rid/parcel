from __future__ import annotations

import hashlib
import os
from pathlib import Path

import av
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QImage, QPixmap, QColor, QPainter, QPainterPath, QPen, QBrush
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QMessageBox
)


VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}
PROJECT_ROOT = Path(__file__).resolve().parents[1]
THUMB_CACHE_DIR = PROJECT_ROOT / "temp" / "thumbnails"
THUMB_WIDTH = 320
THUMB_HEIGHT = 180


def _make_icon(kind: str, size: int = 18) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QPen(QColor("#9ca3af"), 1.75, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if kind == "open":
        painter.drawRoundedRect(3, 6, 12, 8, 2, 2)
        painter.drawLine(5, 6, 7, 4)
        painter.drawLine(7, 4, 11, 4)
    elif kind == "refresh":
        painter.drawArc(3, 3, 12, 12, 45 * 16, 270 * 16)
        painter.drawLine(11, 3, 14, 3)
        painter.drawLine(14, 3, 14, 6)
    elif kind == "folder":
        painter.drawRoundedRect(3, 5, 12, 8, 2, 2)
        painter.drawLine(3, 7, 6, 7)
        painter.drawLine(6, 5, 8, 7)
    elif kind == "trash":
        painter.drawRect(5, 6, 8, 8)
        painter.drawLine(4, 6, 14, 6)
        painter.drawLine(7, 4, 11, 4)
    painter.end()
    return QIcon(pixmap)


def _thumbnail_cache_path(video_path: Path) -> Path:
    mtime = int(video_path.stat().st_mtime)
    key = hashlib.sha1(f"{video_path.resolve()}:{mtime}".encode()).hexdigest()
    return THUMB_CACHE_DIR / f"{key}.jpg"


def _load_video_thumbnail(video_path: Path) -> QPixmap:
    THUMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = _thumbnail_cache_path(video_path)
    if cache_file.exists():
        cached = QPixmap(str(cache_file))
        if not cached.isNull():
            return cached

    pixmap = _extract_video_thumbnail(video_path)
    if not pixmap.isNull():
        pixmap.save(str(cache_file), "JPG", 85)
    return pixmap


def _extract_video_thumbnail(video_path: Path) -> QPixmap:
    placeholder = QPixmap(THUMB_WIDTH, THUMB_HEIGHT)
    placeholder.fill(QColor("#1a1f2a"))
    try:
        container = av.open(str(video_path))
        stream = container.streams.video[0]
        if stream.time_base:
            seek_ts = int(1.0 / float(stream.time_base))
            container.seek(seek_ts, backward=True, stream=stream)
        for frame in container.decode(stream):
            rgb = frame.to_ndarray(format="rgb24")
            height, width, _ = rgb.shape
            image = QImage(rgb.data, width, height, width * 3, QImage.Format.Format_RGB888).copy()
            return QPixmap.fromImage(image).scaled(
                THUMB_WIDTH,
                THUMB_HEIGHT,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        container.close()
    except Exception:
        pass
    return placeholder

class DropHeroCard(QFrame):
    dropped = pyqtSignal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setObjectName("PageCard")
        # Subtle gradient border simulation using QSS
        self.setStyleSheet("""
            QFrame#PageCard {
                background-color: #151a22;
                border: 1px solid #2b3442;
                border-radius: 8px;
            }
        """)
        
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()
            
    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path and Path(path).suffix.lower() in VIDEO_EXTENSIONS:
                self.dropped.emit(path)
                return

class HomePage(QWidget):
    openVideoRequested = pyqtSignal(str)

    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self._setup_ui()
        self.refresh_recents()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.hero = DropHeroCard()
        hero_layout = QVBoxLayout(self.hero)
        hero_layout.setContentsMargins(24, 24, 24, 24)
        hero_layout.setSpacing(12)
        title = QLabel("Drop Video Here")
        title.setFont(QFont("abcNormal", 24, QFont.Weight.Medium))
        title.setStyleSheet("color: #f3f4f6;")
        subtitle = QLabel("Open a clip, trim it, and send it straight into compression.")
        subtitle.setObjectName("Muted")
        subtitle.setStyleSheet("color: #9ca3af;")
        hero_layout.addWidget(title)
        hero_layout.addWidget(subtitle)

        button_row = QHBoxLayout()
        self.btn_open = QPushButton("Open Video")
        self.btn_open.setIcon(_make_icon("open"))
        self.btn_refresh = QPushButton("Refresh Recents")
        self.btn_refresh.setIcon(_make_icon("refresh"))
        
        self.scanning_label = QLabel("")
        self.scanning_label.setStyleSheet("color: #9ca3af;")
        
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Date", "Name", "Size", "Duration"])
        self.sort_combo.setCurrentText(self.settings_manager.get("recent_sort_mode", "Date"))
        button_row.addWidget(self.btn_open)
        button_row.addWidget(self.btn_refresh)
        button_row.addWidget(self.scanning_label)
        button_row.addStretch(1)
        
        sort_label = QLabel("Sort")
        sort_label.setStyleSheet("color: #f3f4f6;")
        button_row.addWidget(sort_label)
        button_row.addWidget(self.sort_combo)
        hero_layout.addLayout(button_row)

        self.manual_path = QLineEdit()
        self.manual_path.setPlaceholderText("Paste absolute system file path here")
        self.manual_path.setClearButtonEnabled(True)
        hero_layout.addWidget(self.manual_path)
        layout.addWidget(self.hero)

        # Recents Section
        recent_header = QHBoxLayout()
        recent_label = QLabel("Recent Videos")
        recent_label.setFont(QFont("abcNormal", 14, QFont.Weight.Medium))
        recent_label.setStyleSheet("color: #f3f4f6;")
        recent_header.addWidget(recent_label)
        recent_header.addStretch(1)
        layout.addLayout(recent_header)

        self.recent_list = QListWidget()
        self.recent_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.recent_list.setMovement(QListWidget.Movement.Static)
        self.recent_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.recent_list.setWrapping(True)
        self.recent_list.setSpacing(16)
        self.recent_list.setIconSize(QSize(THUMB_WIDTH, THUMB_HEIGHT))
        self.recent_list.setGridSize(QSize(THUMB_WIDTH + 24, THUMB_HEIGHT + 56))
        self.recent_list.setWordWrap(True)
        self.recent_list.setStyleSheet(
            "QListWidget { background: #161920; border: 1px solid #262b37; color: #f3f4f6; border-radius: 8px; padding: 8px; }"
            "QListWidget::item { padding: 6px; border-radius: 8px; }"
            "QListWidget::item:selected { background: #2b3242; }"
            "QListWidget::item:hover { background: #1f242f; }"
        )
        layout.addWidget(self.recent_list, stretch=1)

        self.btn_open.clicked.connect(self._pick_video)
        self.manual_path.returnPressed.connect(self._open_manual_path)
        self.btn_refresh.clicked.connect(self.refresh_recents)
        self.sort_combo.currentTextChanged.connect(self._sort_changed)
        self.recent_list.itemDoubleClicked.connect(self._open_recent_item)
        self.hero.dropped.connect(self.openVideoRequested.emit)

    def _pick_video(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Video",
            "",
            "Video Files (*.mp4 *.mkv *.mov *.avi *.webm *.m4v);;All Files (*.*)",
        )
        if file_path:
            self.openVideoRequested.emit(file_path)

    def _sort_changed(self, value: str) -> None:
        self.settings_manager.set("recent_sort_mode", value)
        self.refresh_recents()

    def _open_recent_item(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and os.path.exists(path):
            self.openVideoRequested.emit(path)

    def _open_manual_path(self) -> None:
        path = self.manual_path.text().strip()
        if path and os.path.exists(path):
            self.openVideoRequested.emit(path)
        else:
            QMessageBox.information(self, "Path not found", "Please enter a valid absolute file path.")

    def refresh_recents(self) -> None:
        self.scanning_label.setText("Scanning...")
        self.repaint() # Force UI update
        self.recent_list.clear()

        entries = []
        seen_paths = set()
        watch_folders = [Path(folder) for folder in self.settings_manager.get_watch_folders()]
        for folder in watch_folders:
            if folder.exists() and folder.is_dir():
                for item in folder.rglob("*"):
                    if item.is_file() and item.suffix.lower() in VIDEO_EXTENSIONS and str(item) not in seen_paths:
                        seen_paths.add(str(item))
                        entries.append(self._describe_file(item))

        sort_mode = self.settings_manager.get("recent_sort_mode", "Date")
        if sort_mode == "Name":
            entries.sort(key=lambda row: row["name"].lower())
        elif sort_mode == "Size":
            entries.sort(key=lambda row: row["size"], reverse=True)
        elif sort_mode == "Duration":
            entries.sort(key=lambda row: row["duration"], reverse=True)
        else:
            entries.sort(key=lambda row: row["mtime"], reverse=True)

        for entry in entries[:40]:
            thumb = _load_video_thumbnail(Path(entry["path"]))
            item = QListWidgetItem(QIcon(thumb), entry["name"])
            item.setToolTip(
                f"{entry['path']}\n{entry['duration_text']}  ·  {entry['resolution_text']}  ·  {entry['modified_text']}"
            )
            item.setData(Qt.ItemDataRole.UserRole, entry["path"])
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.recent_list.addItem(item)
            
        self.scanning_label.setText("")

    def _describe_file(self, path: Path) -> dict:
        size = path.stat().st_size
        mtime = path.stat().st_mtime
        duration = 0.0
        resolution = "Unknown"
        try:
            container = av.open(str(path))
            if container.streams.video:
                stream = container.streams.video[0]
                width = getattr(stream, "width", 0) or 0
                height = getattr(stream, "height", 0) or 0
                if width and height:
                    resolution = f"{width}x{height}"
                if stream.duration and stream.time_base:
                    duration = float(stream.duration * stream.time_base)
            if container.duration:
                duration = max(duration, float(container.duration / av.time_base))
            container.close()
        except Exception:
            pass

        duration_text = self._format_duration(duration)
        modified_text = self._format_modified(mtime)
        return {
            "path": str(path),
            "name": path.name,
            "size": size,
            "duration": duration,
            "duration_text": duration_text,
            "resolution_text": resolution,
            "modified_text": modified_text,
            "mtime": mtime,
        }

    @staticmethod
    def _format_duration(seconds: float) -> str:
        total = int(max(0, seconds))
        hours = total // 3600
        minutes = (total % 3600) // 60
        secs = total % 60
        if hours:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    @staticmethod
    def _format_modified(timestamp: float) -> str:
        from datetime import datetime

        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%b %d, %Y")
