"""Application startup."""

from __future__ import annotations

import argparse
import sys

from PySide6.QtWidgets import QApplication

from denon_controller.settings import load_settings
from denon_controller.ui.main_window import MainWindow


def main() -> int:
    parser = argparse.ArgumentParser(description="Denon AVR desktop controller")
    parser.add_argument("--simulate", action="store_true", help="Run against a simulated receiver")
    args = parser.parse_args()
    application = QApplication(sys.argv[:1])
    window = MainWindow(load_settings(), simulated=args.simulate)
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
