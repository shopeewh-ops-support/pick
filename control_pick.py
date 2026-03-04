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
                             QListWidgetItem, QMessageBox, QGridLayout, QFrame, QMenu, QLineEdit, QSizePolicy)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject, QRunnable, QThreadPool, pyqtSlot
from PyQt5.QtGui import QFont, QColor

import gspread
from google.oauth2.service_account import Credentials


# --- HÀM TÍNH TỶ LỆ MÀN HÌNH (SCALE FACTOR) ---
def get_scale_factor():
    screen = QApplication.primaryScreen().availableGeometry()
    scale_w = screen.width() / 1920.0
    scale_h = screen.height() / 1080.0
    # Lấy tỷ lệ nhỏ hơn để đảm bảo không bị tràn
    return min(scale_w, scale_h, 1.0)


# --- GIAO DIỆN TRUNG TÍNH ĐỘNG DỰA TRÊN TỶ LỆ (ULTRA-COMPACT) ---
def get_dynamic_qss(scale):
    # Cho phép font nhỏ hơn trên các màn hình laptop bé
    f_10 = max(8, int(10 * scale))
    f_11 = max(9, int(11 * scale))
    f_12 = max(10, int(12 * scale))
    f_13 = max(11, int(13 * scale))
    f_14 = max(12, int(14 * scale))

    # Ép padding tối thiểu để tiết kiệm không gian
    pad_xs = max(1, int(2 * scale))
    pad_small = max(2, int(4 * scale))
    pad_med = max(4, int(6 * scale))
    pad_large = max(6, int(8 * scale))

    return f"""
    QMainWindow {{
        background-color: #e2e8f0; 
    }}
    QLabel {{
        color: #2d3436;
    }}
    QListWidget {{
        background-color: transparent;
        color: #2d3436;
        border: none;
        outline: none;
        font-family: "Segoe UI", "Arial";
        font-weight: bold;
        font-size: {f_12}px;
    }}
    QListWidget::item {{
        padding: {pad_small}px {pad_xs}px;
        border-bottom: 1px solid #f1f2f6;
        border-radius: 4px;
        margin-bottom: 2px;
    }}
    QListWidget::item:selected {{
        background-color: #dff9fb; 
        border: 1px solid #c7ecee;
    }}
    QListWidget::item:hover {{
        background-color: #f5f6fa;
    }}
    QTextEdit {{
        border: 2px solid #cbd5e1;
        border-radius: 4px;
        padding: {pad_small}px;
        background-color: #ffffff;
        color: #2d3436;
        font-family: "Segoe UI", "Arial";
        font-size: {f_13}px;
    }}
    QTextEdit:focus {{
        border: 2px solid #74b9ff;
    }}
    QPushButton {{
        background-color: #0984e3;
        color: white;
        border: none;
        border-radius: 4px;
        padding: {pad_med}px {pad_large}px;
        font-family: "Segoe UI", "Arial";
        font-weight: bold;
        font-size: {f_12}px;
    }}
    QPushButton:hover {{
        background-color: #74b9ff;
    }}
    QPushButton:pressed {{
        background-color: #0097e6;
    }}
    QPushButton#btn_delete {{
        background-color: #d63031;
    }}
    QPushButton#btn_delete:hover {{
        background-color: #ff7675;
    }}
    QPushButton#btn_refresh_block {{
        background-color: #e17055;
        padding: {pad_small}px {pad_med}px;
    }}
    QPushButton#btn_refresh_block:hover {{
        background-color: #fab1a0;
    }}
    QProgressBar {{
        border: 1px solid #cbd5e1;
        border-radius: 4px;
        text-align: center;
        color: transparent;
        max-height: 6px;
        background-color: #ffffff;
    }}
    QProgressBar::chunk {{
        background-color: #00b894;
        border-radius: 3px;
    }}
    """


# --- CONSTANTS ---
FLOW_ZONES = ["A1", "A2", "A3", "A4", "B1", "B2", "BC", "SPC", "C1", "C2", "C3", "CA", "CB"]
NORMAL_BLOCKS = ["Block A", "Block B", "Block C", "Block A&B", "Block A&C", "Block B&C", "Block A&B&C"]

FIREBASE_PICKER_URL = "https://ship-8a347-default-rtdb.firebaseio.com/pickers"
FIREBASE_CONFIG_URL = "https://ship-8a347-default-rtdb.firebaseio.com/config"


# --- BẮT LỖI TOÀN CỤC ---
def log_uncaught_exceptions(ex_cls, ex, tb):
    text = '{}: {}:\n'.format(ex_cls.__name__, ex)
    text += ''.join(traceback.format_tb(tb))
    print("[CRITICAL ERROR] Hệ thống gặp lỗi nghiêm trọng:")
    print(text)
    QMessageBox.critical(None, 'Lỗi Hệ Thống', f"Ứng dụng gặp lỗi:\n{text}")


sys.excepthook = log_uncaught_exceptions


# --- WORKERS ---

class WMSUpdateRuleThread(QThread):
    def __init__(self, target_zone, picker_list, config_data, wms_cookie):
        super().__init__()
        self.target_zone = target_zone
        self.picker_list = picker_list
        self.config_data = config_data
        self.wms_cookie = wms_cookie

    def run(self):
        if not self.wms_cookie or not self.picker_list:
            return

        headers = {
            "Sec-CH-UA": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            "Content-Type": "application/json",
            "Cookie": self.wms_cookie
        }
        url = "https://wms.ssc.shopee.vn/api/v2/apps/process/outbound/pickingrule/mass_adjust_staff_picking_rule"

        # Phân loại Hỏa tốc và Thường để gửi request có channel_id khác nhau
        urgent_pickers = [p["user_id"] for p in self.picker_list if p.get("urgent") == "Y"]
        normal_pickers = [p["user_id"] for p in self.picker_list if p.get("urgent") != "Y"]

        is_flow = self.target_zone in FLOW_ZONES
        is_none = self.target_zone == ""

        # Lọc danh sách zone cho Pick Normal dựa trên cấu hình Config
        normal_zones = set()
        if not is_flow and not is_none:
            cfg_a = [z.strip() for z in self.config_data.get("Block A", "").split(",") if z.strip()]
            cfg_b = [z.strip() for z in self.config_data.get("Block B", "").split(",") if z.strip()]
            cfg_c = [z.strip() for z in self.config_data.get("Block C", "").split(",") if z.strip()]

            if self.target_zone == "Block A":
                normal_zones.update(cfg_a)
            elif self.target_zone == "Block B":
                normal_zones.update(cfg_b)
            elif self.target_zone == "Block C":
                normal_zones.update(cfg_c)
            elif self.target_zone == "Block A&B":
                normal_zones.update(cfg_a + cfg_b)
            elif self.target_zone == "Block A&C":
                normal_zones.update(cfg_a + cfg_c)
            elif self.target_zone == "Block B&C":
                normal_zones.update(cfg_b + cfg_c)
            elif self.target_zone == "Block A&B&C":
                normal_zones.update(cfg_a + cfg_b + cfg_c)

        def send_req(staff_ids, is_urg):
            if not staff_ids: return

            payload = {
                "checkbox_bit_set": 13,
                "zone_hard_restrict": 1,
                "zone_hard_restrict_apply_urgent": 1,
                "channel_hard_restrict": 1,
                "channel_hard_restrict_apply_urgent": 1,
                "shop_id_list": [],
                "shop_hard_restrict": 0,
                "shop_hard_restrict_apply_urgent": 0,
                "cross_zone_level": 0,
                "cross_zone_control": 0,
                "staff_id_list": staff_ids
            }

            if is_none:
                payload["zone_id_list"] = ["SA4"]
                payload["flow_pick_working_zone_list"] = ["SA4"]
                payload["channel_id_list"] = ["50011", "50021", "50032"]
            elif is_flow:
                payload["zone_id_list"] = ["SA4"]
                payload["flow_pick_working_zone_list"] = [self.target_zone]
                payload["channel_id_list"] = ["50011", "50021", "50032"]
            else:  # Normal
                payload["zone_id_list"] = list(normal_zones) if normal_zones else ["SA4"]
                payload["flow_pick_working_zone_list"] = ["SA4"]
                payload["channel_id_list"] = ["50033", "50051"] if is_urg else ["50011", "50021", "50032"]

            print(f"\n[DEBUG][WMS Update Rule] Đang Set Rule cho Zone: '{self.target_zone}', Urgent: {is_urg}")
            print(f"[DEBUG][WMS Update Rule] Payload gửi đi: {json.dumps(payload, ensure_ascii=False)}")

            try:
                res = requests.post(url, json=payload, headers=headers, timeout=10)
                print(f"[DEBUG][WMS Update Rule] Status Code: {res.status_code}")
                print(f"[DEBUG][WMS Update Rule] Response Text: {res.text}")
            except Exception as e:
                print(f"[DEBUG][WMS Update Rule] Lỗi API Request: {e}")

        # Execute
        send_req(urgent_pickers, True)
        send_req(normal_pickers, False)


class FetchTasksThread(QThread):
    tasks_fetched = pyqtSignal(dict)

    def __init__(self, wms_cookie, config_data):
        super().__init__()
        self.wms_cookie = wms_cookie
        self.config_data = config_data

    def run(self):
        if not self.wms_cookie:
            print("[DEBUG][WMS Tasks] Lỗi: Chưa có WMS Cookie để gọi Task!")
            self.tasks_fetched.emit({})
            return

        counts = {block: 0 for block in NORMAL_BLOCKS}

        cfg_a = set([z.strip() for z in self.config_data.get("Block A", "").split(",") if z.strip()])
        cfg_b = set([z.strip() for z in self.config_data.get("Block B", "").split(",") if z.strip()])
        cfg_c = set([z.strip() for z in self.config_data.get("Block C", "").split(",") if z.strip()])

        print(f"\n[DEBUG][WMS Tasks] Cấu hình đang check Task -> Block A: {cfg_a}, Block B: {cfg_b}, Block C: {cfg_c}")

        # Tính time
        now = datetime.datetime.now()
        start_date = now - datetime.timedelta(days=6)
        start_dt = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = now.replace(hour=23, minute=59, second=59, microsecond=0)
        start_ts = int(start_dt.timestamp())
        end_ts = int(end_dt.timestamp())

        # BỔ SUNG ĐẦY ĐỦ HEADERS CỦA BROWSER ĐỂ VƯỢT QUA WMS SECURITY
        headers = {
            "Sec-CH-UA": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            "Content-Type": "application/json",
            "Cookie": self.wms_cookie
        }
        url = "https://wms.ssc.shopee.vn/api/v2/apps/process/taskcenter/pickingtask/search_sales_sub_picking_task"

        all_tasks = []
        pageno = 1

        try:
            while True:
                # Cập nhật Payload: Thêm paperless và is_add_picking
                payload = {
                    "start_time": start_ts,
                    "end_time": end_ts,
                    "status": 0,
                    "paperless": 1,
                    "is_add_picking": 0,
                    "fulfillment_chain_dest_zone_list": [],
                    "pageno": pageno,
                    "count": 200
                }

                print(f"[DEBUG][WMS Tasks] Lấy Page {pageno} - Payload: {json.dumps(payload)}")
                res = requests.post(url, json=payload, headers=headers, timeout=10)

                if pageno == 1:
                    print(f"[DEBUG][WMS Tasks] API Response (Mẫu Page 1): {res.text[:500]}...")

                if res.status_code != 200:
                    print(f"[DEBUG][WMS Tasks] Lỗi HTTP: {res.status_code}")
                    break

                data = res.json().get("data", {})
                batch_list = data.get("list", [])
                total = data.get("total", 0)

                if batch_list:
                    all_tasks.extend(batch_list)

                if not batch_list or (pageno * 200) >= total:
                    break
                pageno += 1

            print(f"[DEBUG][WMS Tasks] TỔNG SỐ TASK THỰC TẾ TRẢ VỀ: {len(all_tasks)}")
            if all_tasks:
                print(f"[DEBUG][WMS Tasks] Dữ liệu mẫu 1 Task đầu tiên: {json.dumps(all_tasks[0], ensure_ascii=False)}")

            # Phân loại Task
            for task in all_tasks:
                z_str = task.get("zone_list", "")
                t_zones = set([z.strip() for z in z_str.split(",") if z.strip()])

                has_a = bool(t_zones & cfg_a)
                has_b = bool(t_zones & cfg_b)
                has_c = bool(t_zones & cfg_c)

                if has_a and has_b and has_c:
                    counts["Block A&B&C"] += 1
                elif has_a and has_b:
                    counts["Block A&B"] += 1
                elif has_a and has_c:
                    counts["Block A&C"] += 1
                elif has_b and has_c:
                    counts["Block B&C"] += 1
                elif has_a:
                    counts["Block A"] += 1
                elif has_b:
                    counts["Block B"] += 1
                elif has_c:
                    counts["Block C"] += 1

            print(f"[DEBUG][WMS Tasks] TỔNG TASKS GOM ĐƯỢC: {len(all_tasks)}")
            print(f"[DEBUG][WMS Tasks] KẾT QUẢ ĐẾM TỪNG BLOCK: {counts}")
            self.tasks_fetched.emit(counts)

        except Exception as e:
            print(f"[DEBUG][WMS Tasks] Exception Lỗi Code: {e}")
            self.tasks_fetched.emit({})


class FirebaseUpdateThread(QThread):
    finished_signal = pyqtSignal()

    def __init__(self, action, data=None, user_id=None):
        super().__init__()
        self.action = action
        self.data = data
        self.user_id = user_id

    def run(self):
        try:
            if self.action == "PUT" and self.data:
                uid = self.data.get("user_id")
                if not uid: return
                safe_uid = urllib.parse.quote(str(uid), safe='')
                payload = {
                    "wms_id": self.data.get("wms_id", ""),
                    "name": self.data.get("name", ""),
                    "sex": self.data.get("sex", ""),
                    "block": self.data.get("block", ""),
                    "color": self.data.get("color", "black"),
                    "urgent": self.data.get("urgent", "N")
                }
                url = f"{FIREBASE_PICKER_URL}/{safe_uid}.json"
                res = requests.put(url, json=payload, timeout=10)
                if res.status_code == 200:
                    print(f"[DEBUG][Firebase] PUT thành công cho {uid} vào Block: {payload['block']}")
            elif self.action == "PUT_CONFIG" and self.data:
                url = f"{FIREBASE_CONFIG_URL}.json"
                res = requests.put(url, json=self.data, timeout=10)
                if res.status_code == 200:
                    print("[DEBUG][Firebase] PUT_CONFIG thành công")
            elif self.action == "DELETE" and self.user_id:
                safe_uid = urllib.parse.quote(str(self.user_id), safe='')
                url = f"{FIREBASE_PICKER_URL}/{safe_uid}.json"
                res = requests.delete(url, timeout=10)
                if res.status_code == 200:
                    print(f"[DEBUG][Firebase] DELETE thành công cho {self.user_id}")
        except Exception as e:
            print(f"[DEBUG][Firebase] Lỗi Update: {e}")
        finally:
            self.finished_signal.emit()


class InitDataThread(QThread):
    finished_signal = pyqtSignal(object, str, str)
    error_signal = pyqtSignal(str)

    def run(self):
        print("[DEBUG] Bắt đầu tải Cookies và Google Sheet Data...")
        cached_data = []
        wfm_cookie = ""
        wms_cookie = ""

        # 1. Lấy Cookies
        try:
            url = "https://cookies-942c0-default-rtdb.firebaseio.com/cookies.json"
            response = requests.get(url, timeout=10)
            data = response.json()
            if isinstance(data, dict):
                w_data = data.get("wfm") or data.get("WFM")
                if w_data:
                    if isinstance(w_data, str):
                        wfm_cookie = w_data
                    elif isinstance(w_data, list):
                        wfm_cookie = "; ".join(w_data)
                    elif isinstance(w_data, dict) and "cookie" in w_data:
                        wfm_cookie = "; ".join(w_data["cookie"]) if isinstance(w_data["cookie"], list) else w_data[
                            "cookie"]
                v_data = data.get("vnvl") or data.get("VNVL")
                if v_data:
                    if isinstance(v_data, str):
                        wms_cookie = v_data
                    elif isinstance(v_data, list):
                        wms_cookie = "; ".join(v_data)
                    elif isinstance(v_data, dict) and "cookie" in v_data:
                        wms_cookie = "; ".join(v_data["cookie"]) if isinstance(v_data["cookie"], list) else v_data[
                            "cookie"]
            if not wfm_cookie: wfm_cookie = str(data)
            wfm_cookie = wfm_cookie.strip()
            wms_cookie = wms_cookie.strip()
            print(f"[DEBUG] Cookies loaded. WFM: {bool(wfm_cookie)}, WMS: {bool(wms_cookie)}")
        except Exception as e:
            print(f"[DEBUG] Lỗi tải cookies: {e}")

        # 2. Lấy Google Sheet
        try:
            scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
            creds = Credentials.from_service_account_file("JSON4.json", scopes=scopes)
            client = gspread.authorize(creds)
            SHEET_ID = '1WZVgl1L86F75YVRqP4N8n2E3-K6AJCup6hKnVu3-0rE'
            worksheet = client.open_by_key(SHEET_ID).worksheet('Infomation_laborer/employee')
            all_data = worksheet.get_all_values()
            if len(all_data) > 1:
                for row in all_data[1:]:
                    if len(row) >= 8:
                        cached_data.append({
                            "UserID": row[0], "WMSID": row[1], "Email": row[2],
                            "Name": row[6], "Sex": row[7]
                        })
            print(f"[DEBUG] Đã tải {len(cached_data)} dòng dữ liệu từ Google Sheet.")
            self.finished_signal.emit(cached_data, wfm_cookie, wms_cookie)
        except Exception as e:
            print(f"[DEBUG] Lỗi Google Sheet: {e}")
            self.error_signal.emit(str(e))


class ProcessApiThread(QThread):
    result_ready = pyqtSignal(object)

    def __init__(self, raw_text, cached_data, wfm_cookie, wms_cookie):
        super().__init__()
        self.raw_text = raw_text
        self.cached_data = cached_data
        self.wfm_cookie = wfm_cookie
        self.wms_cookie = wms_cookie

    def run(self):
        print(f"[DEBUG] Bắt đầu luồng ProcessApiThread cho text: {self.raw_text[:30]}...")
        id_list = [x.strip() for x in re.split(r'[\s,]+', self.raw_text) if x.strip()]
        if not id_list:
            print("[DEBUG] Không tìm thấy ID hợp lệ để xử lý.")
            return

        headers_common = {
            "Sec-CH-UA": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            "Content-Type": "application/json"
        }

        headers_wfm = headers_common.copy()
        headers_wfm["Cookie"] = self.wfm_cookie
        headers_wms = headers_common.copy()
        headers_wms["Cookie"] = self.wms_cookie

        for scanned_id in id_list:
            print(f"\n[DEBUG] Đang xử lý ID: {scanned_id}")
            id_type = ""
            if re.match(r'^\d{6}$', scanned_id):
                id_type = "wms"
            elif re.match(r'^[Ss]\d{6}$', scanned_id):
                id_type = "user"
                scanned_id = scanned_id.upper()
            else:
                print(f"[DEBUG] ID '{scanned_id}' sai định dạng - BỎ QUA")
                continue

            emp_name, emp_sex, emp_wmsid, emp_userid, emp_email = "Không xác định", "", scanned_id, scanned_id, ""

            # --- Bước 1: Ánh xạ từ Google Sheet Cache ---
            for emp in self.cached_data:
                if (id_type == "wms" and emp["WMSID"] == scanned_id) or \
                        (id_type == "user" and emp["UserID"].upper() == scanned_id):
                    emp_name, emp_sex, emp_wmsid, emp_userid, emp_email = emp["Name"], str(emp["Sex"]).strip().lower(), \
                        emp["WMSID"], emp["UserID"].upper(), emp.get("Email", "")
                    print(f"[DEBUG] Đã tìm thấy {scanned_id} trong Google Sheet Cache.")
                    break

            wfm_success = wms_success = False

            # --- Bước 2: Gọi WFM ---
            if self.wfm_cookie:
                try:
                    url_search = "https://wfm.ssc.shopee.com/api/apps/labor/staff/search_staff_v2"
                    payload_search = {"order_by_ctime": 2, "pageno": 1, "count": 20}
                    if id_type == "wms":
                        payload_search["wms_user_id_list_str"] = scanned_id
                    else:
                        payload_search["staff_no_list_str"] = scanned_id

                    res_search = requests.post(url_search, json=payload_search, headers=headers_wfm).json()
                    if res_search.get("retcode") == 0 and res_search.get("data") and res_search["data"].get("list"):
                        staff_info = res_search["data"]["list"][0]
                        print(f"[DEBUG] WFM tìm thấy staff: {staff_info.get('staff_name')}")
                        if emp_name == "Không xác định": emp_name = staff_info.get("staff_name", "Không xác định")
                        if "wms_user_id" in staff_info: emp_wmsid = str(staff_info["wms_user_id"])
                        if "staff_no" in staff_info and emp_userid == scanned_id: emp_userid = staff_info[
                            "staff_no"].upper()
                        if not emp_email and "staff_email" in staff_info: emp_email = staff_info.get("staff_email", "")

                        if staff_info.get("reporting_warehouse") == "VNVL":
                            wfm_success = True
                        else:
                            print(f"[DEBUG] WFM: Nhân sự {scanned_id} không thuộc VNVL, bỏ qua (giữ màu đen).")
                            wfm_success = False
                except Exception as e:
                    print(f"[DEBUG] Lỗi WFM: {e}")

            # --- Bước 3: Gọi WMS ---
            if self.wms_cookie and emp_wmsid.isdigit():
                try:
                    url_rule = f"https://wms.ssc.shopee.vn/api/v2/apps/process/outbound/pickingrule/get_picking_rule_detail?rule_id=Pick0024&user_id={emp_wmsid}"
                    res_rule = requests.get(url_rule, headers=headers_wms).json()
                    if res_rule.get("retcode") == 0 and res_rule.get("data"):
                        payload_wms = dict(res_rule["data"])
                        for k in ["id", "whs_id", "min_item_qty_per_mix_task", "simplified_checking",
                                  "hide_close_device"]: payload_wms.pop(k, None)
                        payload_wms.update({"user_id": int(emp_wmsid), "rule_id": "Pick0024", "user_email": emp_email,
                                            "email": emp_email, "working_zone_list": []})
                        res_create = requests.post(
                            "https://wms.ssc.shopee.vn/api/v2/apps/process/outbound/pickerskill/create_picker_skill",
                            json=payload_wms, headers=headers_wms).json()
                        if res_create.get("retcode") == 0: wms_success = True
                except Exception as e:
                    print(f"[DEBUG] Lỗi WMS: {e}")

            # Đánh giá màu
            color_tag = "#2d3436"
            if wfm_success and wms_success:
                if emp_sex in ["nam", "m", "male"]:
                    color_tag = "#0984e3"
                elif emp_sex in ["nữ", "nu", "f", "female"]:
                    color_tag = "#d63031"

            result = {"name": emp_name, "wms_id": emp_wmsid, "user_id": emp_userid, "sex": emp_sex, "color": color_tag,
                      "block": "", "urgent": "N"}
            print(f"[DEBUG] Hoàn tất xử lý {scanned_id}. Emitting signal...")
            self.result_ready.emit(result)


class FetchFirebaseThread(QThread):
    data_fetched = pyqtSignal(object, object)

    def run(self):
        try:
            res_p = requests.get(f"{FIREBASE_PICKER_URL}.json", timeout=10)
            pickers_data = res_p.json() if res_p.status_code == 200 else None

            res_c = requests.get(f"{FIREBASE_CONFIG_URL}.json", timeout=10)
            config_data = res_c.json() if res_c.status_code == 200 else {}

            self.data_fetched.emit(pickers_data, config_data)
        except Exception:
            self.data_fetched.emit(None, None)


# --- UI COMPONENTS ---

class ScanTextEdit(QTextEdit):
    enter_pressed = pyqtSignal(str)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (event.modifiers() & Qt.ShiftModifier):
            txt = self.toPlainText()
            print(f"[DEBUG] Enter detected in QTextEdit. Content length: {len(txt)}")
            self.enter_pressed.emit(txt)
            return
        super().keyPressEvent(event)


class ZoneListWidget(QListWidget):
    items_dropped_signal = pyqtSignal(str, list)

    def __init__(self, zone_name, parent=None):
        super().__init__(parent)
        self.zone_name = zone_name
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        # Cho phép Widget nén hết cỡ nếu không có không gian
        self.setMinimumHeight(0)

    def dropEvent(self, event):
        source = event.source()
        if source == self or not isinstance(source, QListWidget):
            super().dropEvent(event)
            return

        row = self.indexAt(event.pos()).row()
        if row == -1: row = self.count()

        dropped_data = []
        for item in source.selectedItems():
            taken_item = source.takeItem(source.row(item))
            if taken_item:
                data = taken_item.data(Qt.UserRole)
                if isinstance(data, dict):
                    data["block"] = self.zone_name

                    if self.zone_name in FLOW_ZONES or self.zone_name == "":
                        data["urgent"] = "N"

                    prefix = "🔥 " if data.get("urgent") == "Y" else ""
                    taken_item.setText(f'{prefix}{data.get("name", "N/A")} - {data.get("wms_id", "")}')
                    taken_item.setData(Qt.UserRole, data)

                    self.insertItem(row, taken_item)
                    row += 1
                    dropped_data.append(data)

        event.accept()
        if dropped_data:
            self.items_dropped_signal.emit(self.zone_name, dropped_data)


# --- MAIN WINDOW ---

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.scale = get_scale_factor()
        self.setWindowTitle("Hệ Thống Quản Lý Zone Picker")
        self.setStyleSheet(get_dynamic_qss(self.scale))

        self.active_threads = []
        self.cached_data = []
        self.wfm_cookie = self.wms_cookie = ""
        self.current_firebase_data = {}
        self.task_counts = {}

        self.badges = {}

        self.init_ui()
        self.setWindowState(Qt.WindowMaximized)
        self.start_initialization()

    def start_thread(self, thread_obj):
        self.active_threads.append(thread_obj)
        thread_obj.finished.connect(lambda: self.cleanup_thread(thread_obj))
        thread_obj.start()

    def cleanup_thread(self, thread_obj):
        if thread_obj in self.active_threads:
            self.active_threads.remove(thread_obj)

    def get_current_config(self):
        return {
            "Block A": self.txt_cfg_a.text().strip(),
            "Block B": self.txt_cfg_b.text().strip(),
            "Block C": self.txt_cfg_c.text().strip()
        }

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # GIẢM LỀ TỐI ĐA (Margins siêu nhỏ để nhường không gian cho nội dung chính)
        pad_main = int(5 * self.scale)
        main_layout.setContentsMargins(pad_main, pad_main, pad_main, pad_main)
        main_layout.setSpacing(pad_main)

        # --- Header Nén ---
        header_widget = QWidget()
        header_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(int(5 * self.scale))

        scan_frame = QFrame()
        scan_frame.setStyleSheet("QFrame { background-color: white; border: 2px solid #cbd5e1; border-radius: 6px; }")
        scan_box_layout = QHBoxLayout(scan_frame)
        scan_box_layout.setContentsMargins(int(5 * self.scale), int(5 * self.scale), int(5 * self.scale),
                                           int(5 * self.scale))

        # Cột trái Header (Nhập liệu và Trạng thái)
        input_vbox = QVBoxLayout()
        input_vbox.setSpacing(int(2 * self.scale))

        lbl_scan_title = QLabel("Cổng Nhập Dữ Liệu (Quét/Paste ID)")
        lbl_scan_title.setStyleSheet(
            f"font-weight: bold; font-size: {max(10, int(13 * self.scale))}px; color: #636e72; border: none;")
        input_vbox.addWidget(lbl_scan_title)

        self.txt_scan = ScanTextEdit()
        self.txt_scan.setPlaceholderText("Paste ID và Enter...")
        # ÉP TEXT BOX CHỈ CÒN ĐỦ CHIỀU CAO CHO 1-2 DÒNG
        self.txt_scan.setMaximumHeight(int(35 * self.scale))
        self.txt_scan.enter_pressed.connect(self.on_scan_triggered)
        input_vbox.addWidget(self.txt_scan)

        status_layout = QHBoxLayout()
        self.lbl_status = QLabel("Đang khởi động hệ thống...")
        self.lbl_status.setStyleSheet(
            f"font-weight: bold; color: #2d3436; border: none; font-size: {max(9, int(11 * self.scale))}px;")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        status_layout.addWidget(self.lbl_status, stretch=8)
        status_layout.addWidget(self.progress_bar, stretch=2)
        input_vbox.addLayout(status_layout)

        scan_box_layout.addLayout(input_vbox, stretch=8)

        # Cột phải Header (Nút chức năng)
        btn_vbox = QVBoxLayout()
        btn_vbox.setSpacing(int(4 * self.scale))
        btn_refresh = QPushButton("🔄 Tải lại dữ liệu")
        btn_refresh.clicked.connect(self.refresh_firebase)
        self.btn_delete = QPushButton("❌ Xóa chọn")
        self.btn_delete.setObjectName("btn_delete")
        self.btn_delete.clicked.connect(self.delete_selected_items)
        btn_vbox.addWidget(btn_refresh)
        btn_vbox.addWidget(self.btn_delete)
        scan_box_layout.addLayout(btn_vbox, stretch=2)

        header_layout.addWidget(scan_frame)
        main_layout.addWidget(header_widget)

        # --- Main Workspace ---
        self.listboxes = {}
        workspace_layout = QHBoxLayout()
        workspace_layout.setSpacing(pad_main)

        # Panel Trái (Danh sách xử lý) ép stretch siêu nhỏ
        left_panel_container = QWidget()
        left_layout = QVBoxLayout(left_panel_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.create_zone_box(left_layout, "Danh sách xử lý", "#636e72", 0, 0, is_grid=False, show_badge=True,
                             is_left_panel=True)
        # Bóp Panel Trái xuống 1.5 phần (15%) thay vì 2 phần (20%)
        workspace_layout.addWidget(left_panel_container, stretch=15)

        # Panel Phải
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(pad_main)

        # 1. Khu vực NORMAL
        normal_container = QWidget()
        normal_layout_main = QVBoxLayout(normal_container)
        normal_layout_main.setContentsMargins(0, 0, 0, 0)
        normal_layout_main.setSpacing(int(2 * self.scale))

        lbl_normal = QLabel("Khu vực: PICK NORMAL")
        lbl_normal.setStyleSheet(f"font-weight: bold; font-size: {max(11, int(14 * self.scale))}px; color: #0984e3;")
        btn_refresh_block = QPushButton("🔄 Refresh Block")
        btn_refresh_block.setObjectName("btn_refresh_block")
        btn_refresh_block.clicked.connect(self.refresh_wms_tasks)
        h_header = QHBoxLayout()
        h_header.addWidget(lbl_normal)
        h_header.addStretch()
        h_header.addWidget(btn_refresh_block)
        normal_layout_main.addLayout(h_header)

        normal_grid = QGridLayout()
        # GIẢM KHOẢNG CÁCH GRID XUỐNG CỰC TIỂU
        normal_grid.setSpacing(int(4 * self.scale))

        self.create_zone_box(normal_grid, "Block A", "#00b894", 0, 0, True)
        self.create_zone_box(normal_grid, "Block B", "#e17055", 0, 1, True)
        self.create_zone_box(normal_grid, "Block C", "#6c5ce7", 0, 2, True)

        # --- Ô CONFIG NÉN VÀO LƯỚI ---
        config_frame = QFrame()
        config_frame.setStyleSheet(
            "QFrame { border: 2px solid #b2bec3; border-radius: 6px; background-color: #ffffff; }")

        # Chuyển layout config thành Grid để tiết kiệm chiều cao
        config_layout = QGridLayout(config_frame)
        config_layout.setContentsMargins(int(4 * self.scale), int(4 * self.scale), int(4 * self.scale),
                                         int(4 * self.scale))
        config_layout.setSpacing(int(2 * self.scale))

        lbl_cfg_title = QLabel("⚙️ Config Zone")
        lbl_cfg_title.setStyleSheet(
            f"font-weight: bold; font-size: {max(10, int(12 * self.scale))}px; color: #636e72; border: none;")
        config_layout.addWidget(lbl_cfg_title, 0, 0, 1, 2)

        self.txt_cfg_a = QLineEdit()
        self.txt_cfg_b = QLineEdit()
        self.txt_cfg_c = QLineEdit()

        font_size_cfg = max(9, int(11 * self.scale))
        input_style = f"QLineEdit {{ border: 1px solid #cbd5e1; border-radius: 2px; padding: 2px; color: #2d3436; font-size: {font_size_cfg}px;}}"

        for idx, (lbl_text, txt_widget) in enumerate(
                [("Bl. A:", self.txt_cfg_a), ("Bl. B:", self.txt_cfg_b), ("Bl. C:", self.txt_cfg_c)]):
            lbl = QLabel(lbl_text)
            lbl.setStyleSheet(f"font-weight: bold; color: #2d3436; border: none; font-size: {font_size_cfg}px;")
            txt_widget.setStyleSheet(input_style)
            txt_widget.setReadOnly(True)
            config_layout.addWidget(lbl, idx + 1, 0)
            config_layout.addWidget(txt_widget, idx + 1, 1)

        self.btn_edit_config = QPushButton("Edit")
        self.btn_edit_config.setStyleSheet(
            f"QPushButton {{ background-color: #0984e3; padding: {int(3 * self.scale)}px; border-radius: 2px; color: white; font-weight: bold; font-size: {font_size_cfg}px;}} QPushButton:hover {{ background-color: #74b9ff; }}")
        self.btn_edit_config.clicked.connect(self.toggle_config_edit)
        config_layout.addWidget(self.btn_edit_config, 4, 0, 1, 2)

        normal_grid.addWidget(config_frame, 0, 3, 2, 1)  # Cho Config chiếm 2 dòng để vuông vức
        # ---------------------

        self.create_zone_box(normal_grid, "Block A&B", "#0984e3", 1, 0, True)
        self.create_zone_box(normal_grid, "Block A&C", "#0984e3", 1, 1, True)
        self.create_zone_box(normal_grid, "Block B&C", "#0984e3", 1, 2, True)

        # Row 3 để Block tổng
        self.create_zone_box(normal_grid, "Block A&B&C", "#d63031", 2, 0, True, colspan=4)

        normal_layout_main.addLayout(normal_grid)
        right_layout.addWidget(normal_container, stretch=4)

        # 2. Khu vực FLOW PICK
        flow_container = QWidget()
        flow_layout_main = QVBoxLayout(flow_container)
        flow_layout_main.setContentsMargins(0, 0, 0, 0)
        flow_layout_main.setSpacing(int(2 * self.scale))

        lbl_flow = QLabel("Khu vực: FLOW PICK")
        lbl_flow.setStyleSheet(f"font-weight: bold; font-size: {max(11, int(14 * self.scale))}px; color: #e17055;")
        flow_layout_main.addWidget(lbl_flow)

        flow_grid = QGridLayout()
        # GIẢM KHOẢNG CÁCH GRID XUỐNG CỰC TIỂU
        flow_grid.setSpacing(int(4 * self.scale))

        self.create_zone_box(flow_grid, "A1", "#00cec9", 0, 0, True, True)
        self.create_zone_box(flow_grid, "A2", "#00cec9", 0, 1, True, True)
        self.create_zone_box(flow_grid, "A3", "#00cec9", 0, 2, True, True)
        self.create_zone_box(flow_grid, "A4", "#00cec9", 0, 3, True, True, colspan=2)

        self.create_zone_box(flow_grid, "B1", "#e17055", 1, 0, True, True)
        self.create_zone_box(flow_grid, "B2", "#e17055", 1, 1, True, True)
        self.create_zone_box(flow_grid, "BC", "#e17055", 1, 2, True, True)
        self.create_zone_box(flow_grid, "SPC", "#e17055", 1, 3, True, True, colspan=2)

        self.create_zone_box(flow_grid, "C1", "#6c5ce7", 2, 0, True, True)
        self.create_zone_box(flow_grid, "C2", "#6c5ce7", 2, 1, True, True)
        self.create_zone_box(flow_grid, "C3", "#6c5ce7", 2, 2, True, True)
        self.create_zone_box(flow_grid, "CA", "#6c5ce7", 2, 3, True, True)
        self.create_zone_box(flow_grid, "CB", "#6c5ce7", 2, 4, True, True)

        flow_layout_main.addLayout(flow_grid)
        right_layout.addWidget(flow_container, stretch=6)

        # Trả Right Panel lên 85% diện tích ngang
        workspace_layout.addWidget(right_panel, stretch=85)

        main_layout.addLayout(workspace_layout)

    def create_zone_box(self, parent_layout, title, border_color, row, col, is_grid=False, show_badge=True, colspan=1,
                        is_left_panel=False):
        box_frame = QFrame()
        box_frame.setObjectName("zone_box_frame")
        box_frame.setStyleSheet(
            f"#zone_box_frame {{ border: 2px solid {border_color}; border-radius: 4px; background-color: #ffffff; }}")

        box_layout = QVBoxLayout(box_frame)
        # NÉN MARGIN BÊN TRONG FRAME CỦA TỪNG BLOCK XUỐNG MỨC SIÊU NHỎ
        box_layout.setContentsMargins(int(3 * self.scale), int(3 * self.scale), int(3 * self.scale),
                                      int(3 * self.scale))
        box_layout.setSpacing(int(1 * self.scale))

        h_layout = QHBoxLayout()
        h_layout.setContentsMargins(0, 0, 0, 0)
        lbl_title = QLabel(title)

        font_size_title = max(10, int(13 * self.scale))
        lbl_title.setStyleSheet(f"font-weight: bold; font-size: {font_size_title}px; color: {border_color};")
        h_layout.addWidget(lbl_title)
        h_layout.addStretch()

        lw_title = title if title != "Danh sách xử lý" else ""

        if show_badge:
            badge = QLabel("0")
            font_size_badge = max(9, int(11 * self.scale))
            badge.setStyleSheet(
                f"background-color: white; color: {border_color}; font-weight: bold; border: 1px solid {border_color}; border-radius: 3px; padding: 1px 4px; font-size: {font_size_badge}px;")
            h_layout.addWidget(badge)
            self.badges[lw_title] = badge

        box_layout.addLayout(h_layout)

        lw = ZoneListWidget(lw_title)
        lw.setStyleSheet("QListWidget { border: none; background-color: transparent; }")
        lw.items_dropped_signal.connect(self.on_items_dropped_to_zone)
        lw.itemDoubleClicked.connect(self.on_item_double_clicked)
        lw.setContextMenuPolicy(Qt.CustomContextMenu)
        lw.customContextMenuRequested.connect(lambda pos, lw_ref=lw: self.on_context_menu(pos, lw_ref))
        box_layout.addWidget(lw)

        if is_left_panel:
            parent_layout.addWidget(box_frame)
        elif is_grid:
            parent_layout.addWidget(box_frame, row, col, 1, colspan)

        self.listboxes[lw_title] = lw

    def update_all_badges(self):
        if not hasattr(self, 'badges'): return
        for title, lb in self.listboxes.items():
            if title in self.badges:
                if title in NORMAL_BLOCKS:
                    task_count = self.task_counts.get(title, 0)
                    self.badges[title].setText(f"📦 {task_count}")
                else:
                    self.badges[title].setText(f"👤 {lb.count()}")

    def start_initialization(self):
        init_thread = InitDataThread()
        init_thread.finished_signal.connect(self.on_init_finished)
        init_thread.error_signal.connect(self.on_init_error)
        self.start_thread(init_thread)

    @pyqtSlot(object, str, str)
    def on_init_finished(self, cached_data, wfm_cookie, wms_cookie):
        self.cached_data, self.wfm_cookie, self.wms_cookie = cached_data, wfm_cookie, wms_cookie
        self.progress_bar.setRange(0, 100);
        self.progress_bar.setValue(100)
        self.lbl_status.setText(f"✅ Sẵn sàng! Đã tải {len(self.cached_data)} nhân sự.")
        self.lbl_status.setStyleSheet("color: #00b894;")
        self.refresh_firebase()

    @pyqtSlot(str)
    def on_init_error(self, err):
        self.lbl_status.setText(f"❌ Lỗi: {err}")
        self.lbl_status.setStyleSheet("color: #d63031;")

    def on_scan_triggered(self, text):
        print(f"[DEBUG] on_scan_triggered nhận text: {text}")
        self.txt_scan.clear()
        if not text.strip(): return
        self.lbl_status.setText("Đang xử lý dữ liệu nhập vào...")
        self.lbl_status.setStyleSheet("color: #0984e3;")
        api_thread = ProcessApiThread(text, self.cached_data, self.wfm_cookie, self.wms_cookie)
        api_thread.result_ready.connect(self.add_item_to_ui_and_firebase)
        self.start_thread(api_thread)

    @pyqtSlot(object)
    def add_item_to_ui_and_firebase(self, data):
        uid = data.get("user_id", "")
        if not uid: return
        print(f"[DEBUG] UI đang thêm user: {data['name']} ({uid})")
        if uid in self.current_firebase_data:
            data["block"] = self.current_firebase_data[uid].get("block", "")
            data["urgent"] = self.current_firebase_data[uid].get("urgent", "N")
        self.current_firebase_data[uid] = data
        for lb in self.listboxes.values():
            for i in range(lb.count()):
                existing_item = lb.item(i)
                if existing_item and isinstance(existing_item.data(Qt.UserRole), dict) and existing_item.data(
                        Qt.UserRole).get("user_id") == uid:
                    lb.takeItem(i)
                    break

        block_name = str(data.get("block", "")).strip()
        target_lb = self.listboxes.get(block_name, self.listboxes[""])

        prefix = "🔥 " if data.get("urgent") == "Y" else ""
        item = QListWidgetItem(f'{prefix}{data.get("name", "N/A")} - {data.get("wms_id", "")}')
        item.setForeground(QColor(data.get("color", "#2d3436")))
        item.setFlags(item.flags() | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled | Qt.ItemIsEnabled)
        item.setData(Qt.UserRole, data)

        target_lb.addItem(item)
        target_lb.scrollToBottom()

        self.start_thread(FirebaseUpdateThread("PUT", data=data))
        self.lbl_status.setText(f"✅ Đã thêm {data['name']}")
        self.lbl_status.setStyleSheet("color: #00b894;")
        self.update_all_badges()

    @pyqtSlot(str, list)
    def on_items_dropped_to_zone(self, zone_name, dropped_data):
        for data in dropped_data:
            self.current_firebase_data[data["user_id"]] = data
            self.start_thread(FirebaseUpdateThread("PUT", data=data))

        wms_thread = WMSUpdateRuleThread(zone_name, dropped_data, self.get_current_config(), self.wms_cookie)
        self.start_thread(wms_thread)
        self.update_all_badges()

    @pyqtSlot(QListWidgetItem)
    def on_item_double_clicked(self, item):
        data = item.data(Qt.UserRole)
        if not isinstance(data, dict): return
        if not data.get("block") or data.get("block") in FLOW_ZONES:
            QMessageBox.warning(self, "Cảnh báo", "Không thể gán Hỏa Tốc trong Danh sách xử lý hoặc Flow Pick!")
            return

        data["urgent"] = "Y" if data.get("urgent", "N") == "N" else "N"
        prefix = "🔥 " if data["urgent"] == "Y" else ""
        item.setText(f'{prefix}{data.get("name", "N/A")} - {data.get("wms_id", "")}')

        self.current_firebase_data[data["user_id"]] = data
        self.start_thread(FirebaseUpdateThread("PUT", data=data))

        wms_thread = WMSUpdateRuleThread(data.get("block"), [data], self.get_current_config(), self.wms_cookie)
        self.start_thread(wms_thread)

    def on_context_menu(self, pos, list_widget):
        item = list_widget.itemAt(pos)
        if not item: return
        data = item.data(Qt.UserRole)
        menu = QMenu(self)

        if data.get("block") and data.get("block") not in FLOW_ZONES:
            act_y = menu.addAction("🔥 Gán Đơn Hỏa Tốc")
            act_n = menu.addAction("👤 Gán Đơn Bình Thường")
            menu.addSeparator()

        act_del = menu.addAction("❌ Xóa nhân sự")
        action = menu.exec_(list_widget.mapToGlobal(pos))

        if action == act_del:
            self.start_thread(FirebaseUpdateThread("DELETE", user_id=data["user_id"]))
            list_widget.takeItem(list_widget.row(item))
            self.update_all_badges()
        elif 'act_y' in locals() and action in [act_y, act_n]:
            data["urgent"] = "Y" if action == act_y else "N"
            prefix = "🔥 " if data["urgent"] == "Y" else ""
            item.setText(f'{prefix}{data.get("name", "N/A")} - {data.get("wms_id", "")}')

            self.start_thread(FirebaseUpdateThread("PUT", data=data))

            wms_thread = WMSUpdateRuleThread(data.get("block"), [data], self.get_current_config(), self.wms_cookie)
            self.start_thread(wms_thread)

    def delete_selected_items(self):
        for lb in self.listboxes.values():
            for item in list(lb.selectedItems()):
                data = item.data(Qt.UserRole)
                self.start_thread(FirebaseUpdateThread("DELETE", user_id=data["user_id"]))
                lb.takeItem(lb.row(item))
        self.update_all_badges()

    def refresh_firebase(self):
        self.lbl_status.setText("🔄 Đang đồng bộ dữ liệu Picker...")
        self.progress_bar.setRange(0, 0)
        fetch_thread = FetchFirebaseThread()
        fetch_thread.data_fetched.connect(self.on_firebase_fetched)
        self.start_thread(fetch_thread)

    def refresh_wms_tasks(self):
        self.lbl_status.setText("🔄 Đang lấy danh sách Sub-Tasks WMS...")
        task_thread = FetchTasksThread(self.wms_cookie, self.get_current_config())
        task_thread.tasks_fetched.connect(self.on_wms_tasks_fetched)
        self.start_thread(task_thread)

    @pyqtSlot(dict)
    def on_wms_tasks_fetched(self, counts):
        self.task_counts = counts
        self.update_all_badges()
        self.lbl_status.setText("✅ Đã làm mới số liệu Task WMS.")
        self.lbl_status.setStyleSheet("color: #00b894;")

    @pyqtSlot(object, object)
    def on_firebase_fetched(self, pickers_dict, config_dict):
        self.progress_bar.setRange(0, 100);
        self.progress_bar.setValue(100)

        if config_dict is not None:
            self.txt_cfg_a.setText(config_dict.get("Block A", ""))
            self.txt_cfg_b.setText(config_dict.get("Block B", ""))
            self.txt_cfg_c.setText(config_dict.get("Block C", ""))

        if pickers_dict is None:
            self.lbl_status.setText("❌ Lỗi đồng bộ Firebase!")
            return
        for lb in self.listboxes.values(): lb.clear()
        self.current_firebase_data = {}
        if not pickers_dict:
            self.update_all_badges()
            self.refresh_wms_tasks()
            return
        if isinstance(pickers_dict, list):
            pickers_dict = {str(i): v for i, v in enumerate(pickers_dict) if v is not None}

        for k, v in pickers_dict.items():
            if isinstance(v, dict):
                v["user_id"] = str(k)
                self.current_firebase_data[str(k)] = v

                block_name = str(v.get("block", "")).strip()
                target_lb = self.listboxes.get(block_name, self.listboxes[""])

                prefix = "🔥 " if v.get("urgent") == "Y" else ""
                item = QListWidgetItem(f'{prefix}{v.get("name", "N/A")} - {v.get("wms_id", "")}')
                saved_color = v.get("color", "#2d3436")
                item.setForeground(QColor("#2d3436" if saved_color in ["white", "#ffffff"] else saved_color))
                item.setFlags(item.flags() | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled | Qt.ItemIsEnabled)
                item.setData(Qt.UserRole, v)

                target_lb.addItem(item)

        self.update_all_badges()
        self.lbl_status.setText("✅ Đã đồng bộ Firebase thành công!")
        self.lbl_status.setStyleSheet("color: #00b894;")

        self.refresh_wms_tasks()

    def toggle_config_edit(self):
        font_size_cfg = max(9, int(11 * self.scale))
        if self.btn_edit_config.text() == "Edit":
            self.btn_edit_config.setText("Submit")
            self.btn_edit_config.setStyleSheet(
                f"QPushButton {{ background-color: #00b894; padding: {int(3 * self.scale)}px; border-radius: 2px; color: white; font-weight: bold; font-size: {font_size_cfg}px;}} QPushButton:hover {{ background-color: #55efc4; }}")
            self.txt_cfg_a.setReadOnly(False)
            self.txt_cfg_b.setReadOnly(False)
            self.txt_cfg_c.setReadOnly(False)
        else:
            self.btn_edit_config.setText("Edit")
            self.btn_edit_config.setStyleSheet(
                f"QPushButton {{ background-color: #0984e3; padding: {int(3 * self.scale)}px; border-radius: 2px; color: white; font-weight: bold; font-size: {font_size_cfg}px;}} QPushButton:hover {{ background-color: #74b9ff; }}")
            self.txt_cfg_a.setReadOnly(True)
            self.txt_cfg_b.setReadOnly(True)
            self.txt_cfg_c.setReadOnly(True)

            config_data = self.get_current_config()
            self.start_thread(FirebaseUpdateThread("PUT_CONFIG", data=config_data))

            self.refresh_wms_tasks()


if __name__ == "__main__":
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
