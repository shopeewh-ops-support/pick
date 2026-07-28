import sys, os, json, time, requests, gspread, queue
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

# --- CẤU HÌNH ---
SET_WAREHOUSE_NAME = "VN - VNVL"
API_URL = "https://wms.ssc.shopee.vn/api/v2/apps/labor/staffrecord/record_attendance"

# --- FIREBASE CẤU HÌNH ---
FIREBASE_USERS_URL = "https://cookies-942c0-default-rtdb.firebaseio.com/users.json"

# Cấu hình danh sách link Cookies tương ứng cho mỗi User
COOKIE_LINKS = {
    "301942": "https://cookies-942c0-default-rtdb.firebaseio.com/cookies/vnvl.json",
    "310942": "https://cookies-942c0-default-rtdb.firebaseio.com/cookies/vnvl.json",
    "669428": "https://cookies-942c0-default-rtdb.firebaseio.com/cookies/dainam.json",
    "366544": "https://cookies-942c0-default-rtdb.firebaseio.com/cookies/ngocnga.json",
    "603319": "https://cookies-942c0-default-rtdb.firebaseio.com/cookies/thuan.json"
}

PT_GSHEET_ID = '1WZVgl1L86F75YVRqP4N8n2E3-K6AJCup6hKnVu3-0rE'
PT_WORKSHEET_NAME = 'PT'
BLACKLIST_SHEET_NAME = 'Blacklist'
GSHEET_KEY_FILE = "googlesheet.json"
SUCCESS_SOUND_FILE = "OK.wav"

# --- SỬA ĐOẠN IMPORT ÂM THANH ---
try:
    import winsound
except ImportError:
    winsound = None
    
def resource_path(relative_path):
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def play_sound(stype):
    if sys.platform != 'win32' or not winsound: return
    try:
        # Tìm file ở thư mục hiện tại
        p = os.path.join(os.getcwd(), SUCCESS_SOUND_FILE)
        if not os.path.exists(p):
            p = resource_path(SUCCESS_SOUND_FILE)

        if stype == "success":
            if os.path.exists(p):
                # SND_FILENAME: Báo cho hệ thống biết p là đường dẫn file
                # SND_ASYNC: Phát âm thanh chạy ngầm, không làm đơ (lag) giao diện
                winsound.PlaySound(p, winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                winsound.Beep(1000, 150)
        elif stype == "error":
            winsound.Beep(400, 600)
    except Exception as e:
        print(f"Lỗi phát âm thanh: {e}")

# --- LUỒNG GHI GOOGLE SHEET TỨC THÌ ---
class GSheetWriterWorker(QThread):
    log_signal = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        self.queue = queue.Queue()
        self.running = True

    def add_to_queue(self, row_data):
        self.queue.put(row_data)

    def run(self):
        while self.running:
            try:
                data = self.queue.get(timeout=1)
                sid, task, p_type = data

                gc = gspread.service_account(filename=resource_path(GSHEET_KEY_FILE))
                ws = gc.open_by_key(PT_GSHEET_ID).worksheet(PT_WORKSHEET_NAME)

                row_idx = len(ws.col_values(3)) + 1
                sheet_id = ws.id
                source_row_idx = row_idx - 1

                requests = [
                    {
                        "copyPaste": {
                            "source": {
                                "sheetId": sheet_id,
                                "startRowIndex": source_row_idx - 1,
                                "endRowIndex": source_row_idx,
                                "startColumnIndex": 3,
                                "endColumnIndex": 5
                            },
                            "destination": {
                                "sheetId": sheet_id,
                                "startRowIndex": row_idx - 1,
                                "endRowIndex": row_idx,
                                "startColumnIndex": 3,
                                "endColumnIndex": 5
                            },
                            "pasteType": "PASTE_NORMAL",
                            "pasteOrientation": "NORMAL"
                        }
                    }
                ]
                ws.spreadsheet.batch_update({"requests": requests})
                ws.update(values=[[sid, p_type, task]], range_name=f'C{row_idx}:E{row_idx}',
                          value_input_option='USER_ENTERED')
                self.log_signal.emit(f"☁️ Đã lưu lên Sheet thành công!", "success")

            except queue.Empty:
                continue
            except Exception as e:
                self.log_signal.emit(f"❌ Lỗi Sheet: {str(e)}", "error")


# --- LUỒNG KHỞI TẠO HỆ THỐNG BAN ĐẦU (CHIA 2 GIAI ĐOẠN) ---
class InitSystemWorker(QThread):
    log_signal = pyqtSignal(str, str)
    # Tín hiệu 1: Ưu tiên tải Users trước để mở UI đăng nhập
    users_ready_signal = pyqtSignal(bool, dict)
    # Tín hiệu 2: Tải ngầm xong Cookies và Blacklist
    finished_signal = pyqtSignal(bool, dict, dict)

    def run(self):
        blacklist = {}
        users_data = {}
        user_cookies = {}
        try:
            # GIAI ĐOẠN 1: Tải dữ liệu Users trước
            self.log_signal.emit("Đang tải dữ liệu Users...", "#60A5FA")
            res_users = requests.get(FIREBASE_USERS_URL, timeout=10)
            if res_users.status_code == 200:
                users_data = res_users.json() or {}
                self.users_ready_signal.emit(True, users_data)
            else:
                self.users_ready_signal.emit(False, {})
                return  # Lỗi Users thì không thể đăng nhập, dừng tại đây.

            # GIAI ĐOẠN 2: Chạy ngầm tải Cookies và Blacklist (Dù user đang đăng nhập)
            self.log_signal.emit("Đang đồng bộ Cookies ngầm...", "#60A5FA")
            for uid, link in COOKIE_LINKS.items():
                try:
                    c_res = requests.get(link, timeout=5)
                    if c_res.status_code == 200:
                        raw_cookie = c_res.json()
                        if raw_cookie:
                            c_str = str(raw_cookie).strip()
                            csrf = ""
                            for c in c_str.split(";"):
                                if "csrftoken=" in c.strip():
                                    csrf = c.split("csrftoken=")[1].split(";")[0].strip()
                                    break
                            user_cookies[uid] = {"cookie": c_str, "csrf": csrf}
                except Exception:
                    self.log_signal.emit(f"Cảnh báo: Lỗi lấy cookie cho ID {uid}", "#D97706")
                    continue

            self.log_signal.emit("Đang đồng bộ Blacklist từ Google Sheet...", "#60A5FA")
            key_path = resource_path(GSHEET_KEY_FILE)
            if os.path.exists(key_path):
                gc = gspread.service_account(filename=key_path)
                bl_ws = gc.open_by_key(PT_GSHEET_ID).worksheet(BLACKLIST_SHEET_NAME)
                bl_data = bl_ws.get_all_values()

                for row in bl_data[1:]:
                    if len(row) >= 3 and str(row[2]).strip():
                        msn = str(row[2]).strip().upper()
                        task = str(row[4]).strip().upper() if len(row) >= 5 else ""
                        blacklist[msn] = task
            else:
                self.log_signal.emit(f"LỖI: Không tìm thấy file {GSHEET_KEY_FILE}", "#F87171")

            self.finished_signal.emit(True, blacklist, user_cookies)
        except Exception as e:
            self.log_signal.emit(f"Lỗi khởi tạo ngầm: {str(e)}", "#F87171")
            self.finished_signal.emit(False, {}, {})


# --- GIAO DIỆN HỘP THOẠI ĐỔI MẬT KHẨU ---
class ChangePasswordDialog(QDialog):
    def __init__(self, parent=None, current_uid="", is_admin=False, users_data=None):
        super().__init__(parent)
        self.current_uid = current_uid
        self.is_admin = is_admin
        self.users_data = users_data or {}

        self.setWindowTitle("🔑 Đổi Mật Khẩu")
        self.setFixedSize(380, 480)  # Tăng thêm chiều cao tổng thể của hộp thoại
        self.setStyleSheet("""
            QDialog { background-color: #F8FAFC; }
            QLabel { color: #334155; font-weight: bold; font-family: 'Segoe UI'; font-size: 13px; margin-top: 5px; }
            QLineEdit { padding: 12px; border-radius: 8px; font-size: 14px; background: white; border: 1px solid #CBD5E1; color: #0F172A; }
            QLineEdit:focus { border: 2px solid #3B82F6; }
            QLineEdit:disabled { background: #E2E8F0; color: #64748B; }
            QComboBox { padding: 12px; border-radius: 8px; font-size: 14px; border: 1px solid #CBD5E1; background: white; }
            QPushButton { 
                font-family: 'Segoe UI'; 
                font-size: 15px; 
                font-weight: bold; 
                border-radius: 8px; 
                min-height: 45px; /* Ép cứng chiều cao tối thiểu cho nút */
                padding: 10px; /* Thêm khoảng trống bên trong nút */
                color: white; 
                background-color: #3B82F6; 
                border: none; 
                margin-top: 15px;
            }
            QPushButton:hover { background-color: #2563EB; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 20, 25, 20)

        title = QLabel("CẬP NHẬT MẬT KHẨU")
        title.setStyleSheet("font-size: 16px; color: #0F172A; margin-bottom: 10px;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        layout.addWidget(QLabel("Tài khoản cần đổi:"))
        if self.is_admin:
            self.target_combo = QComboBox()
            for uid, info in self.users_data.items():
                self.target_combo.addItem(f"{uid} - {info.get('name', '')}", uid)

            idx = self.target_combo.findData(self.current_uid)
            if idx >= 0: self.target_combo.setCurrentIndex(idx)
            layout.addWidget(self.target_combo)
        else:
            self.target_input = QLineEdit(
                f"{self.current_uid} - {self.users_data.get(self.current_uid, {}).get('name', '')}")
            self.target_input.setEnabled(False)
            layout.addWidget(self.target_input)

        layout.addWidget(QLabel("Mật khẩu cũ (Xác minh quyền):"))
        self.old_pass = QLineEdit()
        self.old_pass.setEchoMode(QLineEdit.Password)
        self.old_pass.setPlaceholderText("Nhập mật khẩu đang dùng...")
        layout.addWidget(self.old_pass)

        layout.addWidget(QLabel("Mật khẩu mới:"))
        self.new_pass = QLineEdit()
        self.new_pass.setEchoMode(QLineEdit.Password)
        self.new_pass.setPlaceholderText("Nhập mật khẩu mới...")
        layout.addWidget(self.new_pass)

        layout.addWidget(QLabel("Xác nhận mật khẩu mới:"))
        self.confirm_pass = QLineEdit()
        self.confirm_pass.setEchoMode(QLineEdit.Password)
        self.confirm_pass.setPlaceholderText("Nhập lại mật khẩu mới...")
        layout.addWidget(self.confirm_pass)

        self.error_lbl = QLabel("")
        self.error_lbl.setStyleSheet("color: #DC2626; font-size: 12px; font-weight: normal;")
        self.error_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.error_lbl)

        self.btn_submit = QPushButton("LƯU THAY ĐỔI")
        self.btn_submit.clicked.connect(self.process_update)
        layout.addWidget(self.btn_submit)

    def process_update(self):
        target_uid = self.target_combo.currentData() if self.is_admin else self.current_uid
        op = self.old_pass.text().strip()
        np = self.new_pass.text().strip()
        cp = self.confirm_pass.text().strip()

        if not op or not np or not cp:
            self.error_lbl.setText("Vui lòng điền đầy đủ các trường!")
            return

        if op != self.users_data.get(self.current_uid, {}).get("pass"):
            self.error_lbl.setText("Mật khẩu cũ không chính xác!")
            return

        if np != cp:
            self.error_lbl.setText("Mật khẩu xác nhận không khớp!")
            return

        if len(np) < 5:
            self.error_lbl.setText("Mật khẩu mới phải từ 5 ký tự trở lên!")
            return

        self.btn_submit.setText("Đang xử lý...")
        self.btn_submit.setEnabled(False)
        QApplication.processEvents()

        try:
            url = f"https://cookies-942c0-default-rtdb.firebaseio.com/users/{target_uid}.json"
            res = requests.patch(url, json={"pass": np}, timeout=5)
            if res.status_code == 200:
                QMessageBox.information(self, "Thành công", f"Đã đổi mật khẩu thành công cho tài khoản {target_uid}!")
                self.users_data[target_uid]["pass"] = np
                self.accept()
            else:
                self.error_lbl.setText(f"Lỗi hệ thống: {res.status_code}")
        except Exception:
            self.error_lbl.setText("Lỗi mạng! Không thể kết nối máy chủ.")
        finally:
            self.btn_submit.setText("LƯU THAY ĐỔI")
            self.btn_submit.setEnabled(True)


# --- LUỒNG QUÉT MÃ CHÍNH ---
class MasterScanWorker(QThread):
    finished_signal = pyqtSignal(str, str, bool)

    def __init__(self, get_headers_func):
        super().__init__()
        self.get_headers = get_headers_func
        self.queue = queue.Queue()
        self.running = True

    def add_to_queue(self, sid):
        self.queue.put(sid)

    def run(self):
        while self.running:
            try:
                sid = self.queue.get(timeout=0.1)
                headers = self.get_headers()
                try:
                    r = requests.post(API_URL, json={"type": 1, "staff_no": sid}, headers=headers, timeout=10)
                    res_j = r.json()
                    msg_resp = str(res_j.get("message", res_j.get("msg", ""))).lower()

                    if r.status_code == 200 and (res_j.get("retcode") == 0 or msg_resp == "success"):
                        data_obj = res_j.get("data", {})
                        name = data_obj.get("staff_name", f"NV {sid}")
                        self.finished_signal.emit(sid, name, True)
                    else:
                        msg = res_j.get("msg", res_j.get("message", "Lỗi quét"))
                        self.finished_signal.emit(sid, msg, False)
                except Exception:
                    self.finished_signal.emit(sid, f"Lỗi kết nối", False)
                self.queue.task_done()
            except queue.Empty:
                continue


# --- GIAO DIỆN CHÍNH ---
class ShopeeScannerTactile(QMainWindow):
    def __init__(self):
        super().__init__()
        self.scanned_list = []

        # Biến trạng thái
        self.is_fully_loaded = False  # Bật lên khi Cookies & Blacklist đã tải xong

        self.blacklist = {}
        self.users_data = {}
        self.all_user_cookies = {}

        self.current_uid = ""
        self.current_is_admin = False
        self.active_cookie = ""
        self.active_csrf = ""

        self.modern_font = QFont("Segoe UI", 10)
        self.setFont(self.modern_font)

        self.worker = MasterScanWorker(self.get_headers)
        self.worker.finished_signal.connect(self.on_scan_done)
        self.worker.start()

        self.sheet_worker = GSheetWriterWorker()
        self.sheet_worker.log_signal.connect(self.log)
        self.sheet_worker.start()

        self.init_ui()
        QTimer.singleShot(500, self.check_auth_at_startup)

    def get_headers(self):
        return {
            "X-CSRFToken": self.active_csrf,
            "Referer": "https://wms.ssc.shopee.vn/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Cookie": self.active_cookie,
            "Content-Type": "application/json",
            "Accept-Language": "en-US,en;q=0.9,vi;q=0.8"
        }

    def init_ui(self):
        self.setWindowTitle("WMS Scanner Pro - VNVL")
        self.setFixedSize(650, 850)

        # --- Set App Icon ---
        icon_path = resource_path("logo.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.setStyleSheet("""
            QMainWindow { background-color: #F1F5F9; }
            QStackedWidget { background-color: #F1F5F9; }
            QFrame#MainCard, QFrame#LoginCard { background: white; border-radius: 16px; border: 1px solid #CBD5E1; }
            QLabel { color: #334155; font-weight: bold; font-family: 'Segoe UI'; font-size: 13px; }
            QLabel#HeaderLabel { color: #0F172A; font-size: 14px; font-weight: 900; }
            QLabel#TitleLabel { color: #0F172A; font-size: 20px; font-weight: 900; }

            QLineEdit { padding: 12px 15px; border-radius: 10px; font-size: 16px; background: #F8FAFC; border: 2px solid #E2E8F0; color: #0F172A; font-weight: bold; }
            QLineEdit:focus { border: 2px solid #3B82F6; background: white; }
            QLineEdit:disabled { background: #E2E8F0; color: #94A3B8; }

            QPushButton#ConfirmBtn, QPushButton#LoginBtn { font-family: 'Segoe UI'; font-size: 15px; font-weight: bold; border-radius: 10px; padding: 12px; color: white; background-color: #3B82F6; border: none;}
            QPushButton#ConfirmBtn:hover, QPushButton#LoginBtn:hover { background-color: #2563EB; }
            QPushButton#ConfirmBtn:disabled, QPushButton#LoginBtn:disabled { background-color: #94A3B8; }

            QPushButton#ExitBtn { font-family: 'Segoe UI'; font-size: 15px; font-weight: bold; border-radius: 10px; padding: 12px; color: white; border: none; background-color: #EF4444; }
            QPushButton#ExitBtn:hover { background-color: #DC2626; }

            QComboBox { padding: 10px; border-radius: 10px; border: 2px solid #E2E8F0; background: #F8FAFC; font-size: 14px; font-weight: bold; color: #334155;}
            QComboBox:focus { border: 2px solid #3B82F6; }

            QTextEdit#SuccessView { background: white; border-radius: 12px; border: 1px solid #CBD5E1; font-family: 'Segoe UI'; font-size: 14px; padding: 10px; }
            QTextEdit#LogConsole { background: #F8FAFC; border-radius: 12px; border: 1px solid #CBD5E1; font-family: 'Consolas'; font-size: 12px; padding: 10px; color: #1E293B; }
        """)

        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)

        # ----------------------------------------------------
        # WIDGET 1: MÀN HÌNH ĐĂNG NHẬP
        # ----------------------------------------------------
        self.login_widget = QWidget()
        login_layout = QVBoxLayout(self.login_widget)
        login_layout.setAlignment(Qt.AlignCenter)

        login_card = QFrame()
        login_card.setObjectName("LoginCard")
        login_card.setFixedSize(400, 420)
        card_layout_login = QVBoxLayout(login_card)
        card_layout_login.setContentsMargins(30, 40, 30, 40)
        card_layout_login.setSpacing(15)

        title_lbl = QLabel("ĐĂNG NHẬP HỆ THỐNG")
        title_lbl.setObjectName("TitleLabel")
        title_lbl.setAlignment(Qt.AlignCenter)
        card_layout_login.addWidget(title_lbl)
        card_layout_login.addSpacing(10)

        card_layout_login.addWidget(QLabel("MÃ NHÂN VIÊN (User ID):"))
        self.userid_input = QLineEdit()
        self.userid_input.setPlaceholderText("Ví dụ: 301942")
        self.userid_input.setEnabled(False)  # Khóa lúc khởi chạy
        card_layout_login.addWidget(self.userid_input)

        card_layout_login.addWidget(QLabel("MẬT KHẨU:"))
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Nhập mật khẩu...")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setEnabled(False)  # Khóa lúc khởi chạy
        card_layout_login.addWidget(self.password_input)

        card_layout_login.addSpacing(15)

        self.btn_login = QPushButton("ĐĂNG NHẬP")
        self.btn_login.setObjectName("LoginBtn")
        self.btn_login.setEnabled(False)  # Khóa lúc khởi chạy
        self.btn_login.clicked.connect(self.handle_login)
        card_layout_login.addWidget(self.btn_login)

        self.login_status_lbl = QLabel("Hệ thống đang đồng bộ dữ liệu ngầm...")
        self.login_status_lbl.setStyleSheet("color: #D97706; font-size: 13px; font-weight: normal;")
        self.login_status_lbl.setAlignment(Qt.AlignCenter)
        card_layout_login.addWidget(self.login_status_lbl)

        login_layout.addWidget(login_card)
        self.stacked_widget.addWidget(self.login_widget)

        self.userid_input.returnPressed.connect(self.password_input.setFocus)
        self.password_input.returnPressed.connect(self.handle_login)

        # ----------------------------------------------------
        # WIDGET 2: MÀN HÌNH CHÍNH (SCANNER)
        # ----------------------------------------------------
        self.main_widget = QWidget()
        layout = QVBoxLayout(self.main_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        top_bar = QHBoxLayout()
        top_bar.addStretch()

        user_panel = QVBoxLayout()
        user_panel.setAlignment(Qt.AlignRight)

        self.user_info_lbl = QLabel("👤 Khách")
        self.user_info_lbl.setStyleSheet(
            "color: #0F172A; font-size: 15px; font-weight: 900; background: white; padding: 6px 15px; border-radius: 10px; border: 1px solid #CBD5E1;")
        user_panel.addWidget(self.user_info_lbl)

        self.btn_change_pass = QPushButton("Đổi mật khẩu")
        self.btn_change_pass.setCursor(Qt.PointingHandCursor)
        self.btn_change_pass.setStyleSheet(
            "color: #3B82F6; font-size: 12px; font-weight: bold; background: transparent; border: none; text-align: right; text-decoration: underline;")
        self.btn_change_pass.clicked.connect(self.open_change_pass_dialog)
        user_panel.addWidget(self.btn_change_pass)

        top_bar.addLayout(user_panel)
        layout.addLayout(top_bar)

        card = QFrame()
        card.setObjectName("MainCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(15)

        row_drop = QHBoxLayout()
        v_type = QVBoxLayout()
        v_type.addWidget(QLabel("📅 LOẠI CA:"))
        v_type.setSpacing(5)
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Shift 1", "Shift 2"])
        v_type.addWidget(self.type_combo)

        v_task = QVBoxLayout()
        v_task.addWidget(QLabel("⚙️ CÔNG VIỆC:"))
        v_task.setSpacing(5)
        self.task_combo = QComboBox()
        self.task_combo.addItems([" Pick", " Pack", " Check", " DP", "Wis", " TBS", " Mover"])
        v_task.addWidget(self.task_combo)

        row_drop.addLayout(v_type)
        row_drop.addLayout(v_task)
        card_layout.addLayout(row_drop)

        v_input = QVBoxLayout()
        v_input.setSpacing(5)
        v_input.addWidget(QLabel("ĐỊNH DANH NHÂN VIÊN (SCAN):"))
        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Nhấp vào đây và quét mã...")
        self.input_box.setEnabled(False)  # Khóa đến khi is_fully_loaded = True
        v_input.addWidget(self.input_box)
        card_layout.addLayout(v_input)

        self.btn_confirm = QPushButton("XÁC NHẬN")
        self.btn_confirm.setObjectName("ConfirmBtn")
        self.btn_confirm.setEnabled(False)  # Khóa đến khi is_fully_loaded = True
        self.btn_confirm.clicked.connect(self.handle_scan)
        card_layout.addWidget(self.btn_confirm)
        layout.addWidget(card)

        split_layout = QHBoxLayout()

        v_success = QVBoxLayout()
        v_success.setSpacing(5)
        lbl_success = QLabel("📋 DANH SÁCH THÀNH CÔNG")
        lbl_success.setObjectName("HeaderLabel")
        v_success.addWidget(lbl_success)
        self.success_view = QTextEdit()
        self.success_view.setObjectName("SuccessView")
        self.success_view.setReadOnly(True)
        v_success.addWidget(self.success_view)

        v_log = QVBoxLayout()
        v_log.setSpacing(5)
        lbl_log = QLabel("⚡ SYSTEM LOGS")
        lbl_log.setObjectName("HeaderLabel")
        v_log.addWidget(lbl_log)
        self.log_view = QTextEdit()
        self.log_view.setObjectName("LogConsole")
        self.log_view.setReadOnly(True)
        v_log.addWidget(self.log_view)

        split_layout.addLayout(v_success, 6)
        split_layout.addLayout(v_log, 4)
        layout.addLayout(split_layout)

        footer = QHBoxLayout()
        self.status_lbl = QLabel("● ĐANG KHỞI TẠO...")
        self.status_lbl.setStyleSheet("color: #64748B; font-size: 13px;")
        footer.addWidget(self.status_lbl, 1)

        self.btn_exit = QPushButton("THOÁT")
        self.btn_exit.setObjectName("ExitBtn")
        self.btn_exit.setFixedSize(120, 40)
        self.btn_exit.clicked.connect(self.close)
        footer.addWidget(self.btn_exit)
        layout.addLayout(footer)

        self.input_box.returnPressed.connect(self.handle_scan)
        self.stacked_widget.addWidget(self.main_widget)
        self.stacked_widget.setCurrentIndex(0)

    def check_auth_at_startup(self):
        self.init_worker = InitSystemWorker()
        self.init_worker.log_signal.connect(self.log)

        # Kết nối 2 sự kiện riêng biệt
        self.init_worker.users_ready_signal.connect(self.on_users_ready)
        self.init_worker.finished_signal.connect(self.on_init_done)

        self.init_worker.start()

    # Sự kiện 1: Tải xong Users -> Cho phép đăng nhập
    def on_users_ready(self, success, users_data):
        if success:
            self.users_data = users_data
            self.log(f"Đã tải thông tin Users. Sẵn sàng đăng nhập.", "#34D399")

            # Bật ô đăng nhập
            self.userid_input.setEnabled(True)
            self.password_input.setEnabled(True)
            self.btn_login.setEnabled(True)

            self.login_status_lbl.setStyleSheet("color: #059669;")
            self.login_status_lbl.setText("Mời đăng nhập! (Hệ thống đang tiếp tục tải nền...)")
            self.userid_input.setFocus()
        else:
            self.login_status_lbl.setStyleSheet("color: #DC2626;")
            self.login_status_lbl.setText("Lỗi mạng! Không thể kết nối tới cơ sở dữ liệu User.")

    # Sự kiện 2: Tải xong Cookies và Blacklist -> Cho phép Quét
    def on_init_done(self, success, blacklist, user_cookies):
        self.is_fully_loaded = True
        if success:
            self.blacklist = blacklist
            self.all_user_cookies = user_cookies

            self.log(f"Đã tải {len(self.blacklist)} mã Blacklist.", "#60A5FA")
            self.log("Toàn bộ dữ liệu ngầm đã tải xong!", "#34D399")

            # Nếu người dùng đã vào màn hình Scanner trước đó, mở khóa ngay
            if self.stacked_widget.currentIndex() == 1:
                self.setup_active_user_cookie()
                self.input_box.setEnabled(True)
                self.btn_confirm.setEnabled(True)
                self.input_box.setFocus()
                self.status_lbl.setText("● HỆ THỐNG SẴN SÀNG")
            else:
                self.login_status_lbl.setText("Hệ thống đã tải xong toàn bộ. Mời đăng nhập!")
        else:
            self.log("Khởi tạo ngầm thất bại. Vui lòng kiểm tra mạng.", "#F87171")
            if self.stacked_widget.currentIndex() == 1:
                self.status_lbl.setText("● LỖI TẢI DỮ LIỆU NỀN")

    def handle_login(self):
        uid = self.userid_input.text().strip()
        pwd = self.password_input.text().strip()

        if not uid or not pwd:
            self.login_status_lbl.setStyleSheet("color: #DC2626;")
            self.login_status_lbl.setText("Vui lòng nhập đầy đủ thông tin!")
            return

        if uid in self.users_data and self.users_data[uid].get("pass") == pwd:
            user_info = self.users_data[uid]
            name = user_info.get("name", "Unknown User")

            self.current_uid = uid
            self.current_is_admin = user_info.get("admin", False)

            badge = "👑 Admin" if self.current_is_admin else "👤"
            self.user_info_lbl.setText(f"{badge} {name}")
            self.log(f"User {name} ({uid}) đã đăng nhập.", "#34D399")

            self.stacked_widget.setCurrentIndex(1)

            # Nếu tiến trình nền đã hoàn tất trước đó
            if self.is_fully_loaded:
                self.setup_active_user_cookie()
                self.input_box.setEnabled(True)
                self.btn_confirm.setEnabled(True)
                self.input_box.setFocus()
                self.status_lbl.setText("● HỆ THỐNG SẴN SÀNG")
            else:
                # Nếu chưa tải xong Cookie/Blacklist, bắt đợi
                self.log("Đang chờ tải xong Cookie và Blacklist...", "#D97706")
                self.status_lbl.setText("● ĐANG TẢI DỮ LIỆU NỀN, VUI LÒNG ĐỢI...")
        else:
            self.login_status_lbl.setStyleSheet("color: #DC2626;")
            self.login_status_lbl.setText("Sai tài khoản hoặc mật khẩu!")

    def setup_active_user_cookie(self):
        u_cookie = self.all_user_cookies.get(self.current_uid, {})
        self.active_cookie = u_cookie.get("cookie", "")
        self.active_csrf = u_cookie.get("csrf", "")

        if not self.active_cookie:
            self.log(f"Cảnh báo: Không có Cookie cấu hình sẵn cho ID {self.current_uid}", "#D97706")

    def open_change_pass_dialog(self):
        dialog = ChangePasswordDialog(self, self.current_uid, self.current_is_admin, self.users_data)
        dialog.exec_()

    def handle_scan(self):
        sid = self.input_box.text().strip().upper()
        self.input_box.clear()
        if not sid: return

        self.input_box.setEnabled(False)
        self.btn_confirm.setEnabled(False)

        if sid in [x[0] for x in self.scanned_list]:
            self.log(f"TRÙNG: {sid}", "#F59E0B")
            play_sound("error")
            self.input_box.setEnabled(True)
            self.btn_confirm.setEnabled(True)
            self.input_box.setFocus()
            return

        if sid in self.blacklist:
            bl_task = self.blacklist[sid]
            current_task = self.task_combo.currentText().strip().upper()
            is_blocked, block_reason = False, ""

            if bl_task == "" or bl_task == "OUTBOUND":
                is_blocked = True
                block_reason = "Tất cả công việc (Outbound)" if bl_task == "OUTBOUND" else "Tất cả công việc"
            elif bl_task in ["DP", "WIS"] and current_task in ["DP", "WIS"]:
                is_blocked = True
                block_reason = f"Nhóm DP/Wis (bị cấm gốc: {bl_task})"
            elif bl_task == current_task:
                is_blocked = True
                block_reason = bl_task

            if is_blocked:
                self.log(f"🛑 BLACKLIST: {sid} - {block_reason}", "#EF4444")
                play_sound("error")
                self.input_box.setEnabled(True)
                self.btn_confirm.setEnabled(True)
                self.input_box.setFocus()
                return
            else:
                self.log(f"⚠️ Chú ý: {sid} bị Blacklist '{bl_task}' nhưng vẫn quét '{current_task}'", "#D97706")

        self.log(f"🔍 Đang quét: {sid}...", "#94A3B8")
        self.worker.add_to_queue(sid)

    def on_scan_done(self, sid, name, success):
        if success:
            play_sound("success")
            p_type = self.type_combo.currentText()
            task = self.task_combo.currentText()
            self.scanned_list.append([sid, task, p_type])

            success_text = f"<b style='color: #0F172A; font-size: 15px;'>{sid}</b> - <span style='color: #334155;'>{name}</span> <span style='color: #94A3B8; font-size: 12px;'>({task.strip()})</span>"
            self.success_view.append(success_text)

            self.sheet_worker.add_to_queue([sid, task, p_type])
            self.log(f"✅ OK: {sid}", "#34D399")
            self.status_lbl.setText(f"● TỔNG ĐÃ QUÉT THÀNH CÔNG: {len(self.scanned_list)}")
        else:
            self.log(f"❌ LỖI: {sid} - {name}", "#F87171")
            play_sound("error")

        self.input_box.setEnabled(True)
        self.btn_confirm.setEnabled(True)
        self.input_box.setFocus()

    def log(self, msg, color=None):
        if color is None: color = "#1E293B"

        color_map = {
            "blue": "#2563EB", "#60A5FA": "#2563EB",
            "red": "#DC2626", "#F87171": "#DC2626",
            "green": "#059669", "#34D399": "#059669", "#10B981": "#059669",
            "#F59E0B": "#D97706", "#FBBF24": "#D97706", "#EF4444": "#DC2626",
            "#64748B": "#475569", "#9CA3AF": "#475569", "#E2E8F0": "#1E293B"
        }
        final_color = color_map.get(color, color)
        t = time.strftime("%H:%M:%S")
        self.log_view.append(
            f"<span style='color: #64748B;'>[{t}]</span> <span style='color: {final_color};'><b>{msg}</b></span>")


if __name__ == '__main__':
    # Giúp Windows nhận diện icon đúng dưới Taskbar thay vì icon mặc định của Python
    try:
        import ctypes

        myappid = 'shopee.wms.scanner.pro'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass

    app = QApplication(sys.argv)

    # Gán icon cho toàn bộ Application (áp dụng cho cả hộp thoại đổi mật khẩu)
    icon_path = resource_path("logo.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    win = ShopeeScannerTactile()
    win.show()
    sys.exit(app.exec_())
