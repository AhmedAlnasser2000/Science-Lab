import sys
from pathlib import Path

from PyQt6 import QtWidgets

from . import manager


def main() -> None:
    repo_root = Path("ui_repo/ui_v1")
    store_root = Path("ui_store/ui_v1")

    manager.ensure_config()
    active_id = manager.get_active_pack()
    pack = manager.resolve_pack(active_id, repo_root, store_root, prefer_store=True)
    if pack is None:
        # fallback to default
        pack = manager.resolve_pack(manager.DEFAULT_PACK_ID, repo_root, store_root, prefer_store=True)
        active_id = manager.DEFAULT_PACK_ID

    app = QtWidgets.QApplication(sys.argv)
    window = QtWidgets.QWidget()
    window.setWindowTitle("PhysicsLab UI Demo")
    layout = QtWidgets.QVBoxLayout(window)
    label = QtWidgets.QLabel(f"Applied pack: {active_id}")
    reduced_motion = manager._load_config(manager.CONFIG_PATH).get("reduced_motion", False)
    sublabel = QtWidgets.QLabel(f"Reduced motion: {reduced_motion}")
    button = QtWidgets.QPushButton("Close")
    button.clicked.connect(window.close)
    layout.addWidget(label)
    layout.addWidget(sublabel)
    layout.addWidget(button)
    window.setLayout(layout)

    if pack:
        qss = manager.load_qss(pack)
        manager.apply_qss(app, qss)
        print(f"Applied UI pack: {pack.id} (source={pack.source})")
    else:
        print("No UI pack found; running without custom QSS.")

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
