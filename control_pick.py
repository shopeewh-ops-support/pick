import sys
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class FullscreenDialog(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        # Thiết lập chế độ toàn màn hình
        self.showFullScreen()

        # Tạo nhãn chứa nội dung văn bản
        label = QLabel("SET BẰNG TAY ĐI HIHI", self)
        label.setAlignment(Qt.AlignCenter)

        # Tùy chỉnh font chữ to và rõ ràng
        font = QFont("Arial", 42, QFont.Bold)
        label.setFont(font)

        # Tùy chọn: đổi màu chữ hoặc nền bằng CSS nếu muốn nổi bật hơn
        label.setStyleSheet("color: #d90429;")
        self.setStyleSheet("background-color: #f8f9fa;")

        # Căn layout ra chính giữa màn hình
        layout = QVBoxLayout()
        layout.addWidget(label)
        self.setLayout(layout)

    def keyPressEvent(self, event):
        # Nhấn phím Escape (ESC) để thoát nhanh khỏi chế độ toàn màn hình
        if event.key() == Qt.Key_Escape:
            self.close()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FullscreenDialog()
    sys.exit(app.exec_())
