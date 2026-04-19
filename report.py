import sys
import time
import traceback
import json
import requests
import re
import urllib.parse
import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QProgressBar, QTextEdit,
                             QPushButton, QListWidget, QAbstractItemView,
                             QListWidgetItem, QMessageBox, QGridLayout, QFrame, QMenu, QLineEdit)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject, QRunnable, QThreadPool, pyqtSlot
from PyQt5.QtGui import QFont, QColor
import gspread
import sys
import json
import time
import requests
import io
import pandas as pd
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QPushButton, QDateTimeEdit,
                             QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView,
                             QProgressBar, QMessageBox, QGroupBox, QComboBox, QLineEdit)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QDateTime, QTime, QEvent
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QIcon

# --- QUAN TRỌNG: Import tất cả thư viện mà file GitHub cần ở đây ---
# Ví dụ file trên GitHub dùng PyQt5, hãy import hết vào để PyInstaller thấy
try:
    from PyQt5 import QtWidgets, QtCore, QtGui
    from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton  # Liệt kê cụ thể
    # Nếu file GitHub dùng thư viện khác (ví dụ: pandas, selenium), hãy import vào đây luôn
    # import pandas
    # import selenium
except ImportError:
    pass


def run_code_from_github():
    url = "https://raw.githubusercontent.com/shopeewh-ops-support/pick/main/report.py"
    try:
        print("Đang tải dữ liệu từ GitHub...")
        response = requests.get(url)
        if response.status_code == 200:
            source_code = response.text
            print("--- Đang khởi chạy chương trình ---")

            # Sử dụng globals() để code chạy có đầy đủ các thư viện đã import ở trên
            exec(source_code, globals())
        else:
            print(f"Lỗi: Status code {response.status_code}")
    except Exception as e:
        print(f"Lỗi hệ thống: {e}")
        input("Nhấn Enter để thoát...")  # Giữ màn hình CMD để đọc lỗi


if __name__ == "__main__":
    run_code_from_github()
