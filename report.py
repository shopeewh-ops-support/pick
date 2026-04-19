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


# ==========================================
# LỚP CUSTOM: ComboBox chọn nhiều giá trị
# ==========================================
class CheckableComboBox(QComboBox):
    selectionChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view().pressed.connect(self.handle_item_pressed)
        self.setModel(QStandardItemModel(self))
        self.setLineEdit(QLineEdit())
        self.lineEdit().setReadOnly(True)
        # Cài event filter để dropdown không bị đóng khi click
        self.view().viewport().installEventFilter(self)

    def handle_item_pressed(self, index):
        item = self.model().itemFromIndex(index)
        if item.checkState() == Qt.Checked:
            item.setCheckState(Qt.Unchecked)
        else:
            item.setCheckState(Qt.Checked)
        self.update_display_text()
        self.selectionChanged.emit()

    def eventFilter(self, obj, event):
        if obj == self.view().viewport() and event.type() == QEvent.MouseButtonRelease:
            return True
        return super().eventFilter(obj, event)

    def add_item(self, text, checked=False):
        item = QStandardItem(text)
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.model().appendRow(item)
        self.update_display_text()

    def get_checked_items(self):
        checked = []
        for i in range(self.model().rowCount()):
            item = self.model().item(i)
            if item.checkState() == Qt.Checked:
                checked.append(item.text())
        return checked

    def update_display_text(self):
        checked = self.get_checked_items()
        if self.model().rowCount() == 0:
            self.lineEdit().setText("--- Chạy dữ liệu trước ---")
        elif len(checked) == 0:
            self.lineEdit().setText("Chưa chọn mục nào")
        elif len(checked) == self.model().rowCount():
            self.lineEdit().setText("Tất cả")
        else:
            self.lineEdit().setText(f"Đã chọn {len(checked)} mục")

    def clear(self):
        self.model().clear()
        self.update_display_text()


# ==========================================
# THREAD 1: Khởi tạo Cookies lúc vừa mở App
# ==========================================
class InitCookieThread(QThread):
    cookie_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def run(self):
        try:
            fb_url = "https://cookies-942c0-default-rtdb.firebaseio.com/cookies/vnvl.json"
            fb_res = requests.get(fb_url, timeout=10)
            if fb_res.status_code == 200:
                self.cookie_signal.emit(fb_res.json())
            else:
                self.error_signal.emit(f"HTTP Lỗi: {fb_res.status_code}")
        except Exception as e:
            self.error_signal.emit(str(e))


# ==========================================
# THREAD 2: Xử lý Report Logic ngầm
# ==========================================
class WorkerThread(QThread):
    progress_signal = pyqtSignal(str)
    progress_bar_signal = pyqtSignal(int)
    result_signal = pyqtSignal(object)  # Phát tín hiệu trả về pd.DataFrame
    error_signal = pyqtSignal(str)

    def __init__(self, start_time, end_time, status_list, cookie_string):
        super().__init__()
        self.start_time = start_time  # Integer timestamp
        self.end_time = end_time  # Integer timestamp
        self.status_list = [int(s) for s in status_list]  # Dạng mảng Int [0, 9, 2, 3]

        self.headers = {
            "Sec-CH-UA": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            "Referer": "https://wms.ssc.shopee.vn/",
            "Origin": "https://wms.ssc.shopee.vn",
            "Content-Type": "application/json",
            "Cookie": cookie_string
        }

    def run(self):
        try:
            # 1. Tạo Export Task
            self.progress_signal.emit("1. Đang yêu cầu tạo Export Task...")
            self.progress_bar_signal.emit(10)

            create_url = "https://wms.ssc.shopee.vn/api/v2/apps/basic/reportcenter/create_export_task"
            extra_data_dict = {
                "timeRange": 0,
                "module": 2,
                "taskType": 701,
                "status_list": self.status_list,
                "order_type": 0,
                "include_sku_list": 1,
                "date_ref": 0,
                "time_from": self.start_time,
                "time_to": self.end_time
            }

            create_payload = {
                "export_module": 2,
                "task_type": 701,
                "extra_data": json.dumps(extra_data_dict)
            }

            res_create = requests.post(create_url, headers=self.headers, json=create_payload).json()
            if res_create.get("retcode") != 0:
                raise Exception(f"Lỗi tạo Task: {res_create.get('message')}")

            # 2. Polling chờ Task hoàn thành
            search_url = "https://wms.ssc.shopee.vn/api/v2/apps/basic/reportcenter/search_export_task?is_myself=1&pageno=1&count=20"
            download_link = None

            # Khởi tạo tiến trình giả để người dùng biết là app không bị đơ
            wait_percent = 15

            while True:
                self.progress_signal.emit(f"2. Đang chờ hệ thống xử lý Report... ({wait_percent}%)")
                self.progress_bar_signal.emit(wait_percent)

                res_search = requests.get(search_url, headers=self.headers).json()
                if res_search.get("retcode") != 0:
                    raise Exception(f"Lỗi tìm kiếm Task: {res_search.get('message')}")

                tasks = res_search.get("data", {}).get("list", [])

                # Tìm task hợp lệ mới nhất
                target_task = None
                for t in tasks:
                    if t.get("export_module") == 2 and t.get("task_type") == 701:
                        target_task = t
                        break  # Lấy phần tử đầu tiên (vì list đã sort ctime desc)

                if not target_task:
                    raise Exception("Không tìm thấy task báo cáo vừa tạo trên hệ thống!")

                processed_pct = target_task.get("processed_percentage", 0)

                if processed_pct == 100:
                    download_link = target_task.get("download_link")
                    break
                else:
                    # Cập nhật số tiến trình ảo & đợi 2 giây
                    wait_percent = wait_percent + 5 if wait_percent < 80 else wait_percent
                    time.sleep(2)

            if not download_link:
                raise Exception("Không thể lấy được đường dẫn tải file (download_link trống)!")

            self.progress_bar_signal.emit(85)
            self.progress_signal.emit("3. Đang tải file Excel vào bộ nhớ...")

            # 3. Tải và đọc Excel trên RAM
            excel_res = requests.get(download_link, stream=True)
            if excel_res.status_code != 200:
                raise Exception("Tải file Excel thất bại!")

            self.progress_bar_signal.emit(90)
            self.progress_signal.emit("4. Đang phân tích dữ liệu DataFrame...")

            # Đọc bằng Pandas (Header là dòng đầu tiên, index 0)
            df = pd.read_excel(io.BytesIO(excel_res.content), header=0)

            self.result_signal.emit(df)
            self.progress_bar_signal.emit(100)
            self.progress_signal.emit("Hoàn thành!")

        except Exception as e:
            self.error_signal.emit(str(e))


# ==========================================
# MAIN GUI WINDOW
# ==========================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ngọc Yến's Report Tool")
        self.setWindowIcon(QIcon('emm.ico'))
        self.resize(1000, 700)

        self.cookie_string = ""
        self.df = None  # Chứa raw dataframe gốc

        self.setup_ui()
        self.apply_styles()

        # Bắt đầu lấy Cookie ngay khi mở app
        self.lbl_status.setText("Loading...")
        self.btn_run.setEnabled(False)
        self.init_cookie_thread = InitCookieThread()
        self.init_cookie_thread.cookie_signal.connect(self.on_cookie_loaded)
        self.init_cookie_thread.error_signal.connect(self.on_cookie_error)
        self.init_cookie_thread.start()

    def setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setSpacing(15)

        # 1. Group Box Ngày Giờ (HH:mm:ss)
        time_group = QGroupBox("Chọn Create Time")
        time_layout = QHBoxLayout()

        # Định nghĩa thời gian mặc định
        now = QDateTime.currentDateTime()
        yesterday = now.addDays(-1)

        # Từ: 00:00:00 hôm qua
        self.dt_begin = QDateTimeEdit(self)
        self.dt_begin.setDisplayFormat("dd/MM/yyyy HH:mm:ss")
        self.dt_begin.setCalendarPopup(True)
        begin_dt = QDateTime(yesterday.date(), QTime(0, 0, 0))
        self.dt_begin.setDateTime(begin_dt)

        # Đến: 23:59:59 hôm nay
        self.dt_end = QDateTimeEdit(self)
        self.dt_end.setDisplayFormat("dd/MM/yyyy HH:mm:ss")
        self.dt_end.setCalendarPopup(True)
        end_dt = QDateTime(now.date(), QTime(23, 59, 59))
        self.dt_end.setDateTime(end_dt)

        time_layout.addWidget(QLabel("Star Time:"))
        time_layout.addWidget(self.dt_begin)
        time_layout.addWidget(QLabel("End Time:"))
        time_layout.addWidget(self.dt_end)
        time_group.setLayout(time_layout)
        main_layout.addWidget(time_group)

        # 2. Group Box Trạng thái
        status_group = QGroupBox("Chọn Order Status")
        status_layout = QHBoxLayout()

        self.cb_created = QCheckBox("Created")
        self.cb_created.setProperty("val", "0")

        self.cb_pending = QCheckBox("Pending Pick")
        self.cb_pending.setProperty("val", "9")
        self.cb_pending.setChecked(True)

        self.cb_picking = QCheckBox("Picking")
        self.cb_picking.setProperty("val", "2")
        self.cb_picking.setChecked(True)

        self.cb_picked = QCheckBox("Picked")
        self.cb_picked.setProperty("val", "3")
        self.cb_picked.setChecked(True)

        self.status_checkboxes = [self.cb_created, self.cb_pending, self.cb_picking, self.cb_picked]
        for cb in self.status_checkboxes:
            status_layout.addWidget(cb)

        status_group.setLayout(status_layout)
        main_layout.addWidget(status_group)

        # 3. Filter Khu vực & Nút Chạy
        action_layout = QHBoxLayout()

        # Filter Dropdown
        filter_box = QGroupBox("Filter")
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filter by 3PL:"))
        self.combo_3pl = CheckableComboBox()
        self.combo_3pl.setEnabled(False)
        self.combo_3pl.update_display_text()
        self.combo_3pl.selectionChanged.connect(self.update_pivot_table)
        filter_layout.addWidget(self.combo_3pl)
        filter_box.setLayout(filter_layout)

        # Nút Chạy (chiếm bên phải)
        run_box = QVBoxLayout()
        self.btn_run = QPushButton("Bắt đầu lấy Report")
        self.btn_run.clicked.connect(self.start_processing)
        run_box.addWidget(self.btn_run)

        action_layout.addWidget(filter_box, stretch=2)
        action_layout.addLayout(run_box, stretch=1)
        main_layout.addLayout(action_layout)

        # 4. Process Bar & Trạng thái
        self.lbl_status = QLabel("Trạng thái: Đang khởi tạo...")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.lbl_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        main_layout.addWidget(self.progress_bar)

        # 5. Table Result Pivot
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        main_layout.addWidget(self.table)

    def apply_styles(self):
        style = """
            QMainWindow {
                background-color: #f4f6f9;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #dcdde1;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 15px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                color: #2f3640;
            }
            QLabel {
                font-size: 13px;
                color: #2f3640;
            }
            QDateTimeEdit {
                padding: 6px;
                border: 1px solid #dcdde1;
                border-radius: 4px;
                background: white;
                min-width: 150px;
            }
            QCheckBox {
                font-size: 13px;
                color: #2f3640;
                padding: 5px;
            }
            QComboBox {
                padding: 5px;
                border: 1px solid #dcdde1;
                border-radius: 4px;
                background: white;
                min-width: 200px;
            }
            QPushButton {
                background-color: #ee4d2d;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 12px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #d74325;
            }
            QPushButton:disabled {
                background-color: #fab4a5;
            }
            QTableWidget {
                background-color: white;
                border: 1px solid #dcdde1;
                border-radius: 6px;
                gridline-color: #f1f2f6;
            }
            QHeaderView::section {
                background-color: #f8f9fa;
                padding: 8px;
                border: none;
                border-bottom: 1px solid #dcdde1;
                font-weight: bold;
                color: #2f3640;
            }
            QProgressBar {
                border: 1px solid #dcdde1;
                border-radius: 4px;
                text-align: center;
                height: 10px;
            }
            QProgressBar::chunk {
                background-color: #2ecc71;
                border-radius: 3px;
            }
        """
        self.setStyleSheet(style)

    # --- Callbacks Firebase Cookie ---
    def on_cookie_loaded(self, cookie):
        self.cookie_string = cookie
        self.lbl_status.setText("Trạng thái: Sẵn sàng")
        self.btn_run.setEnabled(True)

    def on_cookie_error(self, err_msg):
        QMessageBox.critical(self, "Lỗi kết nối", f"Không thể lấy Cookies từ Firebase.\n{err_msg}")
        self.lbl_status.setText("Trạng thái: Lỗi Cookies")

    # --- Worker Thread ---
    def start_processing(self):
        beg_ctime = self.dt_begin.dateTime().toSecsSinceEpoch()
        end_ctime = self.dt_end.dateTime().toSecsSinceEpoch()

        if beg_ctime >= end_ctime:
            QMessageBox.warning(self, "Lỗi", "Thời gian 'Từ' phải nhỏ hơn thời gian 'Đến'")
            return

        selected_statuses = [cb.property("val") for cb in self.status_checkboxes if cb.isChecked()]
        if not selected_statuses:
            QMessageBox.warning(self, "Lỗi", "Vui lòng chọn ít nhất 1 Order Status")
            return

        # Reset UI
        self.table.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self.btn_run.setEnabled(False)
        self.combo_3pl.setEnabled(False)
        self.combo_3pl.clear()
        self.combo_3pl.lineEdit().setText("--- Đang xử lý ---")

        self.progress_bar.setValue(0)
        self.df = None  # Xóa cache dataframe

        # Chạy Worker
        self.worker = WorkerThread(beg_ctime, end_ctime, selected_statuses, self.cookie_string)
        self.worker.progress_signal.connect(self.update_status)
        self.worker.progress_bar_signal.connect(self.progress_bar.setValue)
        self.worker.result_signal.connect(self.on_data_received)
        self.worker.error_signal.connect(self.handle_error)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def update_status(self, text):
        self.lbl_status.setText(text)

    def on_data_received(self, df):
        self.df = df

        # Kiểm tra sự tồn tại của các cột cần thiết
        required_cols = ["New 3PL", "Status", "Device ID", "SKU ID"]
        missing_cols = [c for c in required_cols if c not in df.columns]
        if missing_cols:
            QMessageBox.warning(self, "Lỗi Cấu trúc Excel",
                                f"File báo cáo không chứa các cột: {', '.join(missing_cols)}")
            return

        # Đổ dữ liệu vào ComboBox (Lọc New 3PL)
        unique_3pl = df["New 3PL"].dropna().unique().tolist()
        unique_3pl.sort(key=str)

        self.combo_3pl.blockSignals(True)  # Block signal tạm thời để không trigger pivot khi đang add
        self.combo_3pl.clear()
        for item in unique_3pl:
            self.combo_3pl.add_item(str(item), checked=True)
        self.combo_3pl.blockSignals(False)

        self.combo_3pl.setEnabled(True)
        self.combo_3pl.update_display_text()

        # Tạo pivot lần đầu
        self.update_pivot_table()

    def update_pivot_table(self):
        if self.df is None:
            return

        selected_3pls = self.combo_3pl.get_checked_items()

        # 1. Filter
        if not selected_3pls:
            filtered_df = self.df.iloc[0:0]  # Rỗng nếu không có ô nào được đánh dấu
        else:
            filtered_df = self.df[self.df["New 3PL"].isin(selected_3pls)]

        # 2. Pivot
        try:
            # Columns = Status, Rows = Device ID, Values = SKU ID (Count)
            pivot_df = pd.pivot_table(
                filtered_df,
                values="SKU ID",
                index="Device ID",
                columns="Status",
                aggfunc="count",
                fill_value=0
            )

            # Reset index để Device ID thành cột bình thường thay vì index
            pivot_df = pivot_df.reset_index()

            # 3. Đổ dữ liệu Pivot vào QTableWidget
            self.render_dataframe(pivot_df)

        except Exception as e:
            QMessageBox.warning(self, "Lỗi Pivot", f"Lỗi khi xoay dữ liệu:\n{str(e)}")

    def render_dataframe(self, df):
        self.table.clear()

        # Cấu hình Số hàng & Số cột
        self.table.setRowCount(df.shape[0])
        self.table.setColumnCount(df.shape[1])

        # Cấu hình Header
        headers = [str(col) for col in df.columns]
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        # Fill Dữ liệu
        for row in range(df.shape[0]):
            for col in range(df.shape[1]):
                val = df.iloc[row, col]
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col, item)

    def handle_error(self, err_msg):
        QMessageBox.critical(self, "Lỗi", f"Có lỗi xảy ra:\n{err_msg}")
        self.lbl_status.setText("Trạng thái: Xử lý thất bại.")

        self.combo_3pl.clear()
        self.combo_3pl.update_display_text()
        self.combo_3pl.setEnabled(False)

    def on_finished(self):
        self.btn_run.setEnabled(True)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon('emm.ico'))
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
