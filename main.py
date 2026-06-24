import sys

from PyQt6.QtWidgets import QApplication

from compressor import UnifiedVideoSuiteWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = UnifiedVideoSuiteWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

