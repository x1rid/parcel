import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from parcel import UnifiedVideoSuiteWindow


APP_ICON = Path(__file__).resolve().parent / "assets" / "icons" / "icon.png"


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("Parcel")
    app.setWindowIcon(QIcon(str(APP_ICON)))
    window = UnifiedVideoSuiteWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
