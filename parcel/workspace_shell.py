from __future__ import annotations

import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from compressor.home_page import HomePage
from editor.steam_workspace import SteamStyleEditorWidget
from compressor.settings_manager import SettingsManager


APP_ICON_PATH = Path(__file__).resolve().parents[1] / "assets" / "icons" / "icon.png"


def _make_icon(kind: str, size: int = 18) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QPen(QColor("#9ca3af"), 1.7))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if kind == "home":
        painter.drawRect(4, 8, 10, 7)
        painter.drawLine(3, 9, 9, 3)
        painter.drawLine(9, 3, 15, 9)
    elif kind == "plus":
        painter.drawLine(9, 3, 9, 15)
        painter.drawLine(3, 9, 15, 9)
    elif kind == "video":
        painter.drawRect(3, 5, 10, 8)
        painter.drawLine(13, 7, 16, 5)
        painter.drawLine(13, 11, 16, 13)
    elif kind == "image":
        painter.drawRect(3, 4, 12, 10)
        painter.drawLine(5, 11, 8, 8)
        painter.drawLine(8, 8, 12, 12)
    elif kind == "pdf":
        painter.drawRect(4, 3, 10, 12)
        painter.drawLine(6, 6, 12, 6)
        painter.drawLine(6, 9, 12, 9)
    elif kind == "audio":
        painter.drawLine(6, 4, 6, 13)
        painter.drawEllipse(4, 12, 4, 4)
        painter.drawLine(6, 4, 12, 6)
    elif kind == "unknown":
        painter.drawEllipse(4, 4, 10, 10)
        painter.drawLine(9, 7, 9, 11)
        painter.drawPoint(9, 5)
    elif kind == "settings":
        painter.drawEllipse(6, 6, 6, 6)
    painter.end()
    return QIcon(pixmap)


def _file_kind(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}:
        return "video"
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}:
        return "image"
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"}:
        return "audio"
    if suffix in {".zip", ".rar", ".7z", ".tar", ".gz"}:
        return "archive"
    if suffix in {".exe", ".msi", ".bat", ".cmd"}:
        return "executable"
    return "unknown"


@dataclass
class WorkspaceRecord:
    path: str
    kind: str
    title: str
    widget: QWidget


class HomeWorkspace(QWidget):
    openFileRequested = pyqtSignal(str)

    def __init__(self, settings_manager: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        hero = QFrame()
        hero.setStyleSheet("QFrame { background: #161920; border: 1px solid #242936; border-radius: 16px; }")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(24, 24, 24, 24)
        hero_layout.setSpacing(14)

        title = QLabel("Parcel")
        title.setStyleSheet("font-size: 34px; font-weight: 700;")
        subtitle = QLabel("Open a file and Parcel will choose the right workspace.")
        subtitle.setStyleSheet("color: #9ca3af;")
        hero_layout.addWidget(title)
        hero_layout.addWidget(subtitle)

        self.btn_open = QPushButton("Open File")
        self.btn_open.setIcon(_make_icon("home"))
        self.btn_open.clicked.connect(self._pick_file)
        hero_layout.addWidget(self.btn_open)
        layout.addWidget(hero)

        recent_label = QLabel("Recent Files")
        recent_label.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(recent_label)

        self.recent_list = QListWidget()
        self.recent_list.itemDoubleClicked.connect(self._open_recent)
        self.recent_list.setStyleSheet("QListWidget { background: #161920; border: 1px solid #242936; border-radius: 12px; }")
        layout.addWidget(self.recent_list, stretch=1)
        self.refresh_recent([])

    def _pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open File", "", "All Files (*.*)")
        if path:
            self.openFileRequested.emit(path)

    def _open_recent(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and os.path.exists(path):
            self.openFileRequested.emit(path)

    def refresh_recent(self, entries: list[dict]) -> None:
        self.recent_list.clear()
        for entry in entries[:40]:
            item = QListWidgetItem(_make_icon(entry.get("kind", "unknown")), entry.get("title", Path(entry["path"]).name))
            item.setData(Qt.ItemDataRole.UserRole, entry["path"])
            self.recent_list.addItem(item)


class PlaceholderWorkspace(QWidget):
    def __init__(self, path: str, kind: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        box = QFrame()
        box.setStyleSheet("QFrame { background: #161920; border: 1px solid #242936; border-radius: 16px; }")
        box_layout = QVBoxLayout(box)
        title = QLabel(f"{kind.title()} Workspace")
        title.setStyleSheet("font-size: 28px; font-weight: 700;")
        desc = QLabel(f"Opened {Path(path).name}")
        desc.setStyleSheet("color: #9ca3af;")
        box_layout.addWidget(title)
        box_layout.addWidget(desc)
        layout.addWidget(box)


class ParcelWorkspaceShell(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings_manager = SettingsManager()
        self.setWindowTitle("Parcel")
        self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.resize(1600, 960)
        self._recent_files: list[dict] = []
        self._workspaces: dict[str, WorkspaceRecord] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.tab_strip = QFrame()
        self.tab_strip.setFixedWidth(78)
        self.tab_strip.setStyleSheet("QFrame { background: #161920; border-right: 1px solid #242936; }")
        strip_layout = QVBoxLayout(self.tab_strip)
        strip_layout.setContentsMargins(10, 10, 10, 10)
        strip_layout.setSpacing(8)

        self.btn_new_home = QToolButton()
        self.btn_new_home.setIcon(_make_icon("plus"))
        self.btn_new_home.setFixedSize(48, 48)
        self.btn_new_home.clicked.connect(self.open_home_tab)
        strip_layout.addWidget(self.btn_new_home)

        self.tab_list = QListWidget()
        self.tab_list.setStyleSheet(
            "QListWidget { background: transparent; border: none; }"
            "QListWidget::item { padding: 10px; margin-bottom: 6px; border-radius: 12px; color: #f3f4f6; }"
            "QListWidget::item:selected { background: #2b3242; }"
        )
        self.tab_list.itemClicked.connect(self._on_tab_clicked)
        strip_layout.addWidget(self.tab_list, stretch=1)
        layout.addWidget(self.tab_strip)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack, stretch=1)

        self.home_widget = HomeWorkspace(self.settings_manager)
        self.home_widget.openFileRequested.connect(self.open_file)
        self.stack.addWidget(self.home_widget)
        self._home_item = self._add_tab("Home", "home")
        self.stack.setCurrentWidget(self.home_widget)
        self._select_tab(self._home_item)
        self.statusBar().showMessage("Ready")

    def _add_tab(self, title: str, kind: str, path: str | None = None) -> QListWidgetItem:
        item = QListWidgetItem(_make_icon(kind), title)
        item.setData(Qt.ItemDataRole.UserRole, path or title)
        item.setSizeHint(QSize(58, 58))
        self.tab_list.addItem(item)
        return item

    def _select_tab(self, item: QListWidgetItem) -> None:
        row = self.tab_list.row(item)
        if row >= 0:
            self.tab_list.setCurrentRow(row)

    def _on_tab_clicked(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path == "Home":
            self.stack.setCurrentWidget(self.home_widget)
            return
        workspace = self._workspaces.get(path)
        if workspace:
            self.stack.setCurrentWidget(workspace.widget)

    def open_home_tab(self) -> None:
        for idx in range(self.tab_list.count()):
            if self.tab_list.item(idx).data(Qt.ItemDataRole.UserRole) == "Home":
                self._select_tab(self.tab_list.item(idx))
                self.stack.setCurrentWidget(self.home_widget)
                return
        item = self._add_tab("Home", "home", "Home")
        self._home_item = item
        self._select_tab(item)
        self.stack.setCurrentWidget(self.home_widget)

    def open_editor_page(self) -> None:
        key = "__editor__"
        if key in self._workspaces:
            self._select_existing_workspace(self._workspaces[key])
            return
        widget = SteamStyleEditorWidget()
        record = WorkspaceRecord(path=key, kind="video", title="Editor", widget=widget)
        self._workspaces[key] = record
        self.stack.addWidget(widget)
        item = self._add_tab("Editor", "video", key)
        self._select_tab(item)
        self.stack.setCurrentWidget(widget)

    def open_file(self, path: str) -> None:
        path = os.path.abspath(path)
        kind = _file_kind(path)
        title = Path(path).name
        if path in self._workspaces:
            workspace = self._workspaces[path]
            self._select_existing_workspace(workspace)
            return
        if kind == "video":
            widget = SteamStyleEditorWidget()
            widget.load_video(path)
        else:
            widget = PlaceholderWorkspace(path, kind)
        record = WorkspaceRecord(path=path, kind=kind, title=title, widget=widget)
        self._workspaces[path] = record
        self.stack.addWidget(widget)
        item = self._add_tab(title, kind if kind in {"home", "video", "image", "pdf", "audio", "unknown"} else "unknown", path)
        item.setData(Qt.ItemDataRole.UserRole, path)
        self._select_tab(item)
        self.stack.setCurrentWidget(widget)
        self._remember_recent(path, kind, title)
        self.home_widget.refresh_recent(self._recent_files)

    def _select_existing_workspace(self, workspace: WorkspaceRecord) -> None:
        for idx in range(self.tab_list.count()):
            if self.tab_list.item(idx).data(Qt.ItemDataRole.UserRole) == workspace.path:
                self._select_tab(self.tab_list.item(idx))
                self.stack.setCurrentWidget(workspace.widget)
                return

    def _remember_recent(self, path: str, kind: str, title: str) -> None:
        self._recent_files = [entry for entry in self._recent_files if entry["path"] != path]
        self._recent_files.insert(0, {"path": path, "kind": kind, "title": title})
        self._recent_files = self._recent_files[:40]

