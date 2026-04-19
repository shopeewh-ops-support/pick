import sys
import os
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon


# Giữ lại hàm này để không bị lỗi nếu đóng gói bằng PyInstaller (pyinstaller --onefile ...)
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AA App")
        self.resize(400, 300)

        # Tạo chữ AA lớn, in đậm và màu đỏ
        label = QLabel("THƯƠNG ANH HONG")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: red; font-size: 150px; font-weight: bold;")

        self.setCentralWidget(label)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(resource_path('emm.ico')))
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
