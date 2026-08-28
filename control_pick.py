# STREAMING_CHUNK: Cập nhật import và khởi tạo giao diện
import sys
import time
import traceback
import json
import requests
import re
import urllib.parse
import datetime
import unicodedata
import concurrent.futures
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QProgressBar, QTextEdit,
                             QPushButton, QListWidget, QAbstractItemView,
                             QListWidgetItem, QMessageBox, QGridLayout, QFrame, QMenu, QLineEdit, QSizePolicy,
                             QStackedWidget, QShortcut)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject, QRunnable, QThreadPool, pyqtSlot, QRect
from PyQt5.QtGui import QFont, QColor, QKeySequence, QPainter, QCursor

import gspread
from google.oauth2.service_account import Credentials

# =========================================================================
# WAVE RULE GROUPS
# =========================================================================
WAVE_RULE_GROUPS = {
    "SDD": ["VNVLDWR0200", "VNVLDWR0213", "VNVLDWR0214"],
    "AHM": ["VNVLDWR0215", "VNVLDWR0216", "VNVLDWR0217"],
    "NDD normal": ["VNVLDWR0157"],
    "NDD Phú Thái": ["VNVLDWR0194"],
    "D-": ["VNVLDWR0196", "VNVLDWR0195"]
}

# --- CONSTANTS ---
FLOW_ZONES = ["A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4", "B5", "HV", "FD", "C1", "C2", "C3", "KHO_E", "TOP"]
NORMAL_BLOCKS = ["Block A", "Block B", "Block C", "Block E", "Block A&B", "Block A&C", "Block B&C", "Block A&B&C"]

FIREBASE_PICKER_URL = "https://ship-8a347-default-rtdb.firebaseio.com/pickers"
FIREBASE_CONFIG_URL = "https://ship-8a347-default-rtdb.firebaseio.com/config"


def remove_accents(input_str):
    s = str(input_str)
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return s.replace('đ', 'd').replace('Đ', 'D')


def get_scale_factor():
    screen = QApplication.primaryScreen().availableGeometry()
    scale_w = screen.width() / 1920.0
    scale_h = screen.height() / 1080.0
    return min(scale_w, scale_h, 1.0)


def get_dynamic_qss(scale):
    f_list = max(10, int(12 * scale))
    f_btn = max(10, int(12 * scale))
    f_input = max(11, int(13 * scale))

    pad_xs = max(2, int(4 * scale))
    pad_small = max(4, int(6 * scale))
    pad_med = max(6, int(10 * scale))

    bg_main = "#CDB7B5"
    bg_card = "#F5F5F5"
    bg_input = "#FFFFFF"
    text_main = "#1E293B"
    text_sub = "#64748B"
    border_color = "#FCE7F3"
    primary = "#3B82F6"
    primary_hover = "#2563EB"
    danger = "#EF4444"
    success = "#10B981"

    return f"""
    QMainWindow {{
        background-color: {bg_main};
        font-family: "Segoe UI", "-apple-system", "BlinkMacSystemFont", "Roboto", "Arial", sans-serif;
    }}
    QLabel {{
        color: {text_main};
    }}

    QScrollBar:vertical {{
        border: none;
        background: transparent;
        width: 8px;
        margin: 0px 0px 0px 0px;
    }}
    QScrollBar::handle:vertical {{
        background: #F9A8D4;
        min-height: 20px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: #F472B6;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        border: none; background: none; height: 0px;
    }}
    QScrollBar:horizontal {{
        border: none; background: transparent; height: 8px; margin: 0px 0px 0px 0px;
    }}
    QScrollBar::handle:horizontal {{
        background: #F9A8D4; min-width: 20px; border-radius: 4px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: #F472B6;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        border: none; background: none; width: 0px;
    }}

    QListWidget {{
        background-color: transparent; color: {text_main}; border: none; outline: none; font-weight: 500; font-size: {f_list}px;
    }}
    QListWidget::item {{
        padding: {pad_small}px {pad_xs}px; border-bottom: 1px solid {border_color}; border-radius: 4px; margin-bottom: 2px; background-color: {bg_card};
    }}
    QListWidget::item:selected {{
        background-color: #FCE7F3; border: 1px solid #FBCFE8; color: #BE185D;
    }}
    QListWidget::item:hover:!selected {{
        background-color: #FFF5F9;
    }}

    QTextEdit, QLineEdit {{
        border: 1px solid #CBD5E1; border-radius: 6px; padding: {pad_small}px; background-color: {bg_input}; color: {text_main}; font-size: {f_input}px;
    }}
    QTextEdit:focus, QLineEdit:focus {{
        border: 1px solid #F472B6; background-color: #FFFFFF;
    }}

    QPushButton {{
        background-color: {bg_input}; color: {text_main}; border: 1px solid #CBD5E1; border-radius: 6px; padding: {pad_med}px {pad_med * 2}px; font-weight: 600; font-size: {f_btn}px;
    }}
    QPushButton:hover {{
        background-color: #FCE7F3; border-color: #FBCFE8; color: #BE185D;
    }}
    QPushButton:pressed {{
        background-color: #FBCFE8;
    }}

    QPushButton#btn_primary {{
        background-color: {primary}; color: white; border: none;
    }}
    QPushButton#btn_primary:hover {{
        background-color: {primary_hover}; color: white;
    }}

    QPushButton#tab_active {{
        background-color: {primary}; color: white; border: none; border-radius: 8px; font-size: {max(11, int(13 * scale))}px; padding: {pad_med}px {pad_med * 3}px;
    }}
    QPushButton#tab_inactive {{
        background-color: transparent; color: {text_sub}; border: 1px solid transparent; border-radius: 8px; font-size: {max(10, int(12 * scale))}px; padding: {pad_med}px {pad_med * 3}px;
    }}
    QPushButton#tab_inactive:hover {{
        background-color: #FCE7F3; color: #BE185D;
    }}

    QPushButton#btn_delete {{
        background-color: #FEF2F2; color: {danger}; border: 1px solid #FECACA;
    }}
    QPushButton#btn_delete:hover {{
        background-color: {danger}; color: white;
    }}

    QProgressBar {{
        border: none; border-radius: 4px; text-align: center; color: transparent; max-height: 6px; background-color: #E2E8F0;
    }}
    QProgressBar::chunk {{
        background-color: {success}; border-radius: 4px;
    }}
    """


# STREAMING_CHUNK: Cập nhật hàm logic cập nhật skill
def log_uncaught_exceptions(ex_cls, ex, tb):
    text = '{}: {}:\n'.format(ex_cls.__name__, ex)
    text += ''.join(traceback.format_tb(tb))
    print("[CRITICAL ERROR] Hệ thống gặp lỗi nghiêm trọng:")
    print(text)
    QMessageBox.critical(None, 'Lỗi Hệ Thống', f"Ứng dụng gặp lỗi:\n{text}")


sys.excepthook = log_uncaught_exceptions


class ToggleSwitch(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setMinimumSize(44, 24)
        self.setMaximumSize(44, 24)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        rect = QRect(0, 0, self.width(), self.height())
        if self.isChecked():
            painter.setBrush(QColor("#4ADE80"))
        else:
            painter.setBrush(QColor("#E2E8F0"))

        painter.drawRoundedRect(0, 0, rect.width(), rect.height(), 12, 12)

        painter.setBrush(QColor("#FFFFFF"))
        if self.isChecked():
            painter.drawEllipse(self.width() - 22, 2, 20, 20)
        else:
            painter.drawEllipse(2, 2, 20, 20)
        painter.end()


class WMSUpdateWaveRuleThread(QThread):
    finished_update = pyqtSignal(int, int)

    def __init__(self, wms_cookie, rules_to_update):
        super().__init__()
        self.wms_cookie = wms_cookie
        self.rules_to_update = rules_to_update

    def run(self):
        if not self.wms_cookie or not self.rules_to_update:
            self.finished_update.emit(0, 0)
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
        url = "https://wms.ssc.shopee.vn/api/v2/apps/config/waverule/set_dynamic_wave_rule_switch"

        success_count = 0
        total_count = len(self.rules_to_update)

        def send_req(rule_id, status):
            payload = {
                "rule_id": rule_id,
                "switch_status": status
            }
            try:
                res = requests.post(url, json=payload, headers=headers, timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    if data.get("retcode") == 0 and data.get("message") == "success":
                        return True
            except Exception as e:
                print(f"[WMS Wave Rule] Lỗi API Request ({rule_id}): {e}")
            return False

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, total_count)) as executor:
            futures = [executor.submit(send_req, rule_id, status) for rule_id, status in self.rules_to_update.items()]
            for future in concurrent.futures.as_completed(futures):
                if future.result():
                    success_count += 1

        self.finished_update.emit(success_count, total_count)


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

        def do_set_skill(wms_id, rule_id):
            try:
                url_rule = f"https://wms.ssc.shopee.vn/api/v2/apps/process/outbound/pickingrule/get_picking_rule_detail?rule_id={rule_id}&user_id={wms_id}"
                res_rule = requests.get(url_rule, headers=headers, timeout=10).json()
                if res_rule.get("retcode") == 0 and res_rule.get("data"):
                    payload_wms = dict(res_rule["data"])
                    for k in ["id", "whs_id", "min_item_qty_per_mix_task", "simplified_checking", "hide_close_device"]:
                        payload_wms.pop(k, None)
                    payload_wms.update({
                        "user_id": int(wms_id),
                        "rule_id": rule_id,
                        "working_zone_list": []
                    })
                    res_create = requests.post(
                        "https://wms.ssc.shopee.vn/api/v2/apps/process/outbound/pickerskill/create_picker_skill",
                        json=payload_wms, headers=headers, timeout=10).json()
                    print(f"[Skill Update] Rule {rule_id} cho user {wms_id} -> Result: {res_create.get('message')}")
            except Exception as e:
                print(f"[DEBUG][Skill Update] Lỗi API Request: {e}")

        skills_to_set = []
        for p in self.picker_list:
            wms_id = p.get("wms_id")
            if not wms_id or not str(wms_id).isdigit():
                continue
            is_flow_zone = self.target_zone in FLOW_ZONES
            target_rule = "Pick0025" if (is_flow_zone and p.get("urgent") == "Q") else "Pick0024"
            skills_to_set.append((wms_id, target_rule))

        if skills_to_set:
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(skills_to_set))) as executor:
                futures = [executor.submit(do_set_skill, wid, rid) for wid, rid in skills_to_set]
                concurrent.futures.wait(futures)

        url_mass_adjust = "https://wms.ssc.shopee.vn/api/v2/apps/process/outbound/pickingrule/mass_adjust_staff_picking_rule"
        is_flow = self.target_zone in FLOW_ZONES
        is_none = self.target_zone == ""

        # Lấy trạng thái Ca Ngày / Ca Đêm từ config để điều chỉnh channel 50057 cho normal
        is_day_shift = self.config_data.get("DayShift", True)
        normal_channels = ["50011", "50021", "50032", "50057"] if is_day_shift else ["50011", "50021", "50032"]

        if self.target_zone == "KHO_E":
            groups = {}
            for p in self.picker_list:
                grp = p.get("kho_e_group", "VNVLFPOG0211")
                if grp not in groups:
                    groups[grp] = []
                groups[grp].append(p["user_id"])

            for grp, staff_ids in groups.items():
                if not staff_ids: continue
                payload = {
                    "checkbox_bit_set": 61,
                    "zone_id_list": ["SA4"],
                    "zone_hard_restrict": 1,
                    "zone_hard_restrict_apply_urgent": 1,
                    "channel_id_list": normal_channels,
                    "channel_hard_restrict": 1,
                    "channel_hard_restrict_apply_urgent": 1,
                    "shop_id_list": [],
                    "shop_hard_restrict": 0,
                    "shop_hard_restrict_apply_urgent": 0,
                    "cross_zone_level": 0,
                    "cross_zone_control": 0,
                    "preferred_area_level": 0,
                    "staff_id_list": staff_ids,
                    "flow_pick_working_zone_list": ["E1", "E2", "E3", "E4", "REP"],
                    "flow_pick_order_group_id_list": [grp],
                    "dynamic_wave_order_group_id_list": [-1]
                }
                try:
                    print(f"\n--- [API POST Request - KHO E] ---")
                    print(f"URL: {url_mass_adjust}")
                    print(f"Payload: {json.dumps(payload, indent=2, ensure_ascii=False)}")
                    res = requests.post(url_mass_adjust, json=payload, headers=headers, timeout=10)
                    print(f"Response Status: {res.status_code}")
                    print(f"Response Text: {res.text}")
                    print(f"-----------------------------------\n")
                except Exception as e:
                    print(f"[DEBUG] Lỗi API KHO_E: {e}")
            return

        normal_zones = set()
        if not is_flow and not is_none:
            cfg_a = [z.strip() for z in self.config_data.get("Block A", "").split(",") if z.strip()]
            cfg_b = [z.strip() for z in self.config_data.get("Block B", "").split(",") if z.strip()]
            cfg_c = [z.strip() for z in self.config_data.get("Block C", "").split(",") if z.strip()]
            cfg_e = [z.strip() for z in self.config_data.get("Block E", "").split(",") if z.strip()]

            if self.target_zone == "Block A":
                normal_zones.update(cfg_a)
            elif self.target_zone == "Block B":
                normal_zones.update(cfg_b)
            elif self.target_zone == "Block C":
                normal_zones.update(cfg_c)
            elif self.target_zone == "Block E":
                normal_zones.update(cfg_e)
            elif self.target_zone == "Block A&B":
                normal_zones.update(cfg_a + cfg_b)
            elif self.target_zone == "Block A&C":
                normal_zones.update(cfg_a + cfg_c)
            elif self.target_zone == "Block B&C":
                normal_zones.update(cfg_b + cfg_c)
            elif self.target_zone == "Block A&B&C":
                normal_zones.update(cfg_a + cfg_b + cfg_c)

        def do_post(staff_ids, zone_ids, flow_work_zones, channel_ids, group_ids, role_name=""):
            if not staff_ids: return
            payload = {
                "checkbox_bit_set": 29,
                "zone_hard_restrict": 1,
                "zone_hard_restrict_apply_urgent": 1,
                "channel_hard_restrict": 1,
                "channel_hard_restrict_apply_urgent": 1,
                "shop_id_list": [],
                "shop_hard_restrict": 0,
                "shop_hard_restrict_apply_urgent": 0,
                "cross_zone_level": 0,
                "cross_zone_control": 0,
                "preferred_area_level": 0,
                "staff_id_list": staff_ids,
                "zone_id_list": zone_ids,
                "flow_pick_working_zone_list": flow_work_zones,
                "channel_id_list": channel_ids,
                "flow_pick_order_group_id_list": group_ids
            }
            try:
                print(f"\n--- [API POST Request - {role_name}] ---")
                print(f"URL: {url_mass_adjust}")
                print(f"Payload: {json.dumps(payload, indent=2, ensure_ascii=False)}")
                res = requests.post(url_mass_adjust, json=payload, headers=headers, timeout=10)
                print(f"Response Status: {res.status_code}")
                print(f"Response Text: {res.text}")
                print(f"-----------------------------------\n")
            except Exception as e:
                print(f"[DEBUG] Lỗi Exception mass_adjust_staff_picking_rule: {e}")

        urgent_all_staff = [p["user_id"] for p in self.picker_list if p.get("urgent") == "Y"]
        urgent_ahm_staff = [p["user_id"] for p in self.picker_list if p.get("urgent") == "A"]
        urgent_sdd_staff = [p["user_id"] for p in self.picker_list if p.get("urgent") == "S"]
        urgent_ndd_staff = [p["user_id"] for p in self.picker_list if p.get("urgent") == "V"]
        normal_staff = [p["user_id"] for p in self.picker_list if p.get("urgent") in ["N", "", None]]

        if is_none:
            all_staff = urgent_all_staff + urgent_ahm_staff + urgent_sdd_staff + urgent_ndd_staff + normal_staff
            do_post(all_staff, ["SA4"], ["SA4"], normal_channels, ["VNVLFPOG0053"], "Unassigned Staff")
        elif is_flow:
            flow_ssaq_staff = [p["user_id"] for p in self.picker_list if p.get("urgent") == "Q"]
            flow_normal_staff = [p["user_id"] for p in self.picker_list if p.get("urgent") != "Q"]
            do_post(flow_normal_staff, ["SA4"], [self.target_zone], normal_channels, ["VNVLFPOG0134"], "Flow Normal")
            do_post(flow_ssaq_staff, ["SA4"], [self.target_zone], ["50011", "50021", "50032"], ["VNVLFPOG0189"],
                    "Flow SSAQ")
        else:
            target_z_list = list(normal_zones) if normal_zones else ["SA4"]

            # Gán đơn bình thường (Normal pickers sẽ mất hoặc nhận thêm 50057 theo ca)
            do_post(normal_staff, target_z_list, ["SA4"], normal_channels, ["VNVLFPOG0053"], "Normal Staff")

            # Hỏa Tốc Chung
            do_post(urgent_all_staff, target_z_list, ["SA4"], ["50033", "50044", "50051"], ["VNVLFPOG0053"],
                    "Express All")
            do_post(urgent_ahm_staff, target_z_list, ["SA4"], ["50033", "50044"], ["VNVLFPOG0053"], "AHM Staff")
            do_post(urgent_sdd_staff, target_z_list, ["SA4"], ["50051"], ["VNVLFPOG0053"], "SDD Staff")

            # Gán đơn NDD (Chỉ 50057)
            do_post(urgent_ndd_staff, target_z_list, ["SA4"], ["50057"], ["VNVLFPOG0053"], "NDD Staff")


# STREAMING_CHUNK: Cập nhật hàm logic đếm tác vụ (Loại bỏ DMX)
class FetchTasksThread(QThread):
    tasks_fetched = pyqtSignal(dict)

    def __init__(self, wms_cookie, config_data):
        super().__init__()
        self.wms_cookie = wms_cookie
        self.config_data = config_data

    def run(self):
        if not self.wms_cookie:
            self.tasks_fetched.emit({})
            return

        counts = {block: {"normal": 0, "ahm": 0, "sdd": 0, "ndd": 0, "oth": 0} for block in NORMAL_BLOCKS}

        cfg_a = set([z.strip() for z in self.config_data.get("Block A", "").split(",") if z.strip()])
        cfg_b = set([z.strip() for z in self.config_data.get("Block B", "").split(",") if z.strip()])
        cfg_c = set([z.strip() for z in self.config_data.get("Block C", "").split(",") if z.strip()])
        cfg_e = set([z.strip() for z in self.config_data.get("Block E", "").split(",") if z.strip()])

        is_day_shift = self.config_data.get("DayShift", True)

        now = datetime.datetime.now()
        start_date = now - datetime.timedelta(days=6)
        start_dt = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = now.replace(hour=23, minute=59, second=59, microsecond=0)
        start_ts = int(start_dt.timestamp())
        end_ts = int(end_dt.timestamp())

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

                res = requests.post(url, json=payload, headers=headers, timeout=10)
                if res.status_code != 200: break

                data = res.json().get("data", {})
                batch_list = data.get("list", [])
                total = data.get("total", 0)

                if batch_list:
                    all_tasks.extend(batch_list)

                if not batch_list or (pageno * 200) >= total:
                    break
                pageno += 1

            for task in all_tasks:
                channels = set(str(c) for c in task.get("channel_id_list", []))
                has_ahm = bool(channels & {"50033", "50044"})
                has_sdd = bool(channels & {"50051"})
                has_ndd = bool(channels & {"50057"})
                has_normal = bool(channels - {"50033", "50044", "50051", "50057"})

                other_special = sum([has_ahm, has_sdd])

                # Logic đặc biệt cho 50057
                if has_ndd:
                    if not has_ahm and not has_sdd and not has_normal:
                        task_type = "ndd"
                    elif is_day_shift and not has_ahm and not has_sdd and has_normal:
                        task_type = "normal"
                    else:
                        task_type = "oth"
                else:
                    if other_special > 1:
                        task_type = "oth"
                    elif has_ahm:
                        task_type = "ahm"
                    elif has_sdd:
                        task_type = "sdd"
                    else:
                        task_type = "normal"

                z_str = task.get("zone_list", "")
                t_zones = set([z.strip() for z in z_str.split(",") if z.strip()])

                has_a = bool(t_zones & cfg_a)
                has_b = bool(t_zones & cfg_b)
                has_c = bool(t_zones & cfg_c)
                has_e = bool(t_zones & cfg_e)

                if has_a and has_b and has_c:
                    counts["Block A&B&C"][task_type] += 1
                elif has_a and has_b:
                    counts["Block A&B"][task_type] += 1
                elif has_a and has_c:
                    counts["Block A&C"][task_type] += 1
                elif has_b and has_c:
                    counts["Block B&C"][task_type] += 1
                elif has_a:
                    counts["Block A"][task_type] += 1
                elif has_b:
                    counts["Block B"][task_type] += 1
                elif has_c:
                    counts["Block C"][task_type] += 1
                elif has_e:
                    counts["Block E"][task_type] += 1

            self.tasks_fetched.emit(counts)
        except Exception as e:
            print(f"[DEBUG][WMS Tasks] Exception: {e}")
            self.tasks_fetched.emit({})


class FetchDynamicTasksThread(QThread):
    tasks_fetched = pyqtSignal(dict)

    def __init__(self, wms_cookie, config_data):
        super().__init__()
        self.wms_cookie = wms_cookie
        self.config_data = config_data

    def run(self):
        if not self.wms_cookie:
            self.tasks_fetched.emit({})
            return

        counts = {block: {"normal": set(), "ahm": 0, "sdd": 0, "ndd": 0, "oth": 0} for block in NORMAL_BLOCKS}

        cfg_a = set([z.strip() for z in self.config_data.get("Block A", "").split(",") if z.strip()])
        cfg_b = set([z.strip() for z in self.config_data.get("Block B", "").split(",") if z.strip()])
        cfg_c = set([z.strip() for z in self.config_data.get("Block C", "").split(",") if z.strip()])
        cfg_e = set([z.strip() for z in self.config_data.get("Block E", "").split(",") if z.strip()])

        is_day_shift = self.config_data.get("DayShift", True)

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
        url = "https://wms.ssc.shopee.vn/api/v2/apps/process/taskcenter/virtual_pickingtask/search_sales_sub_picking_task"

        pageno = 1
        try:
            while True:
                payload = {
                    "fulfillment_chain_dest_zone_list": [],
                    "pageno": pageno,
                    "count": 200
                }

                res = requests.post(url, json=payload, headers=headers, timeout=10)
                if res.status_code != 200: break

                data = res.json().get("data", {})
                batch_list = data.get("list", [])
                total = data.get("total", 0)

                for task in batch_list:
                    channels = set(str(c) for c in task.get("channel_id_list", []))
                    has_ahm = bool(channels & {"50033", "50044"})
                    has_sdd = bool(channels & {"50051"})
                    has_ndd = bool(channels & {"50057"})
                    has_normal = bool(channels - {"50033", "50044", "50051", "50057"})

                    other_special = sum([has_ahm, has_sdd])

                    # Logic đặc biệt cho 50057
                    if has_ndd:
                        if not has_ahm and not has_sdd and not has_normal:
                            task_type = "ndd"
                        elif is_day_shift and not has_ahm and not has_sdd and has_normal:
                            task_type = "normal"
                        else:
                            task_type = "oth"
                    else:
                        if other_special > 1:
                            task_type = "oth"
                        elif has_ahm:
                            task_type = "ahm"
                        elif has_sdd:
                            task_type = "sdd"
                        else:
                            task_type = "normal"

                    pickup_id = task.get("pickup_id")

                    if task_type == "normal" and not pickup_id:
                        continue

                    z_str = task.get("zone_list", "")
                    t_zones = set([z.strip() for z in z_str.split(",") if z.strip()])

                    has_a = bool(t_zones & cfg_a)
                    has_b = bool(t_zones & cfg_b)
                    has_c = bool(t_zones & cfg_c)
                    has_e = bool(t_zones & cfg_e)

                    def record_task(block_key):
                        if task_type == "normal":
                            counts[block_key]["normal"].add(pickup_id)
                        else:
                            counts[block_key][task_type] += 1

                    if has_a and has_b and has_c:
                        record_task("Block A&B&C")
                    elif has_a and has_b:
                        record_task("Block A&B")
                    elif has_a and has_c:
                        record_task("Block A&C")
                    elif has_b and has_c:
                        record_task("Block B&C")
                    elif has_a:
                        record_task("Block A")
                    elif has_b:
                        record_task("Block B")
                    elif has_c:
                        record_task("Block C")
                    elif has_e:
                        record_task("Block E")

                if not batch_list or (pageno * 200) >= total:
                    break
                pageno += 1

            final_counts = {
                k: {
                    "normal": len(v["normal"]),
                    "ahm": v["ahm"],
                    "sdd": v["sdd"],
                    "ndd": v["ndd"],
                    "oth": v["oth"]
                } for k, v in counts.items()
            }
            self.tasks_fetched.emit(final_counts)

        except Exception as e:
            print(f"[DEBUG][Dynamic Tasks] Exception: {e}")
            self.tasks_fetched.emit({})


# STREAMING_CHUNK: Các logic kết nối dữ liệu Firebase, Threads, Update
class FetchFlowTasksThread(QThread):
    tasks_fetched = pyqtSignal(dict)

    def __init__(self, wms_cookie, config_data):
        super().__init__()
        self.wms_cookie = wms_cookie
        self.config_data = config_data

    def run(self):
        if not self.wms_cookie:
            self.tasks_fetched.emit({})
            return

        headers = {
            "Sec-CH-UA": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            "Cookie": self.wms_cookie
        }

        flow_counts = {zone: 0 for zone in FLOW_ZONES}
        ssaq_counts = {zone: 0 for zone in FLOW_ZONES}
        kho_e_counts = {"PT_N": 0, "PT_Q": 0, "TV": 0, "MGTL": 0, "GD": 0}

        def fetch_group(group_id, target_dict):
            url = f"https://wms.ssc.shopee.vn/api/v2/apps/process/flowpicking/get_progress_monitoring_stats?group_id={group_id}&area_dimension_type=1&efficiency_ratio=2"
            try:
                res = requests.get(url, headers=headers, timeout=10)
                if res.status_code == 200:
                    data = res.json().get("data", {}).get("area_stat_list", [])
                    for item in data:
                        if item.get("is_total") == 0 and item.get("area_name"):
                            area_name = item.get("area_name")
                            order_qty = item.get("order_qty", 0)
                            if area_name in target_dict:
                                target_dict[area_name] += order_qty
            except Exception:
                pass

        def fetch_group_total(group_id, key):
            url = f"https://wms.ssc.shopee.vn/api/v2/apps/process/flowpicking/get_progress_monitoring_stats?group_id={group_id}&area_dimension_type=1&efficiency_ratio=2"
            try:
                res = requests.get(url, headers=headers, timeout=10)
                if res.status_code == 200:
                    data = res.json().get("data", {}).get("area_stat_list", [])
                    for item in data:
                        if item.get("is_total") == 1:
                            kho_e_counts[key] = item.get("order_qty", 0)
                            break
            except Exception:
                pass

        with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
            f1 = executor.submit(fetch_group, "VNVLFPOG0134", flow_counts)
            f2 = executor.submit(fetch_group, "VNVLFPOG0189", ssaq_counts)
            f3 = executor.submit(fetch_group_total, "VNVLFPOG0211", "PT_N")
            f4 = executor.submit(fetch_group_total, "VNVLFPOG0219", "PT_Q")
            f5 = executor.submit(fetch_group_total, "VNVLFPOG0220", "TV")
            f6 = executor.submit(fetch_group_total, "VNVLFPOG0221", "MGTL")
            f7 = executor.submit(fetch_group_total, "VNVLFPOG0222", "GD")

            concurrent.futures.wait([f1, f2, f3, f4, f5, f6, f7])

        self.tasks_fetched.emit({"normal": flow_counts, "ssaq": ssaq_counts, "kho_e": kho_e_counts})


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
                    "urgent": self.data.get("urgent", "N"),
                    "kho_e_group": self.data.get("kho_e_group", ""),
                    "kho_e_label": self.data.get("kho_e_label", "")
                }
                url = f"{FIREBASE_PICKER_URL}/{safe_uid}.json"
                requests.put(url, json=payload, timeout=10)
            elif self.action == "PUT_CONFIG" and self.data:
                url = f"{FIREBASE_CONFIG_URL}.json"
                requests.put(url, json=self.data, timeout=10)
            elif self.action == "DELETE" and self.user_id:
                safe_uid = urllib.parse.quote(str(self.user_id), safe='')
                url = f"{FIREBASE_PICKER_URL}/{safe_uid}.json"
                requests.delete(url, timeout=10)
        except Exception as e:
            print(f"[DEBUG][Firebase] Lỗi Update: {e}")
        finally:
            self.finished_signal.emit()


class InitDataThread(QThread):
    finished_signal = pyqtSignal(object, str, str)
    error_signal = pyqtSignal(str)

    def run(self):
        cached_data = []
        wfm_cookie = ""
        wms_cookie = ""

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
        except Exception as e:
            print(f"[DEBUG] Lỗi tải cookies: {e}")

        try:
            scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
            creds = Credentials.from_service_account_file("JSON4.json", scopes=scopes)
            client = gspread.authorize(creds)
            SHEET_ID = '1WZVgl1L86F75YVRqP4N8n2E3-K6AJCup6hKnVu3-0rE'
            worksheet = client.open_by_key(SHEET_ID).worksheet('Infomation_laborer/employee')
            all_data = worksheet.get_all_values()

            if len(all_data) > 1:
                for row in all_data[1:]:
                    while len(row) < 6: row.append("")
                    user_id = str(row[0]).strip()
                    wms_id = str(row[1]).strip()
                    if not user_id and not wms_id: continue
                    cached_data.append({
                        "UserID": user_id,
                        "WMSID": wms_id,
                        "Email": str(row[2]).strip(),
                        "Name": str(row[4]).strip(),
                        "Sex": str(row[5]).strip()
                    })

            self.finished_signal.emit(cached_data, wfm_cookie, wms_cookie)
        except Exception as e:
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
        id_list = [x.strip() for x in re.split(r'[\s,]+', self.raw_text) if x.strip()]
        if not id_list: return

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
            id_type = ""
            if re.match(r'^\d{6}$', scanned_id):
                id_type = "wms"
            elif re.match(r'^[Ss]\d{6}$', scanned_id):
                id_type = "user"
                scanned_id = scanned_id.upper()
            else:
                continue

            emp_name, emp_sex, emp_wmsid, emp_userid, emp_email = "Không xác định", "", scanned_id, scanned_id, ""

            for emp in self.cached_data:
                if (id_type == "wms" and emp["WMSID"] == scanned_id) or (
                        id_type == "user" and emp["UserID"].upper() == scanned_id):
                    emp_name = emp["Name"]
                    emp_sex = emp["Sex"]
                    emp_wmsid = emp["WMSID"]
                    emp_userid = emp["UserID"].upper()
                    emp_email = emp.get("Email", "")
                    break

            wfm_success = wms_success = False

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
                        if emp_name == "Không xác định":
                            raw_name = staff_info.get("staff_name", "Không xác định")
                            if raw_name and raw_name.startswith("********"):
                                match = re.search(r'\*\*\*\*\*\*\*\*(?:&|\\u0026).*?(?:&|\\u0026)(.*)', raw_name)
                                if match:
                                    encrypt_data = match.group(1)
                                    pii_url = "https://wfm.ssc.shopee.com/api/apps/pii/get_pii_data"
                                    try:
                                        pii_res = requests.post(pii_url, json={"encrypt_data": encrypt_data},
                                                                headers=headers_wfm).json()
                                        if pii_res.get("retcode") == 0 and pii_res.get("data"):
                                            emp_name = pii_res["data"].get("decrypt_data", raw_name)
                                        else:
                                            emp_name = raw_name
                                    except Exception:
                                        emp_name = raw_name
                                else:
                                    emp_name = raw_name
                            else:
                                emp_name = raw_name

                        if "wms_user_id" in staff_info: emp_wmsid = str(staff_info["wms_user_id"])
                        if "staff_no" in staff_info and emp_userid == scanned_id: emp_userid = staff_info[
                            "staff_no"].upper()
                        if not emp_email and "staff_email" in staff_info: emp_email = staff_info.get("staff_email", "")
                except Exception:
                    pass

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
                except Exception:
                    pass

            safe_sex = remove_accents(str(emp_sex)).strip().lower()
            color_tag = "#1E293B"
            if safe_sex in ["nam", "m", "male"]:
                color_tag = "#2563EB"
            elif safe_sex in ["nu", "f", "female"]:
                color_tag = "#DB2777"

            result = {"name": emp_name, "wms_id": emp_wmsid, "user_id": emp_userid, "sex": emp_sex, "color": color_tag,
                      "block": "", "urgent": "N"}
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


# STREAMING_CHUNK: Giao diện kéo thả và hiển thị Picker
class ScanTextEdit(QTextEdit):
    enter_pressed = pyqtSignal(str)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (event.modifiers() & Qt.ShiftModifier):
            txt = self.toPlainText()
            self.enter_pressed.emit(txt)
            return
        super().keyPressEvent(event)


class ZoneListWidget(QListWidget):
    items_dropped_signal = pyqtSignal(str, list)

    def __init__(self, zone_id, scale=1.0, watermark_text=None, parent=None):
        super().__init__(parent)
        self.zone_id = zone_id
        self.scale = scale
        display_title = zone_id
        self.watermark_text = watermark_text if watermark_text else (display_title if display_title else "CHỜ XỬ LÝ")

        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setMinimumHeight(0)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing)

        font_size = max(50, int(100 * self.scale))
        if len(self.watermark_text) > 5:
            font_size = max(30, int(60 * self.scale))

        font = QFont("Segoe UI", font_size, QFont.Bold)
        painter.setFont(font)
        color = QColor(148, 163, 184, 50)
        painter.setPen(color)
        text = self.watermark_text
        painter.drawText(self.viewport().rect(), Qt.AlignCenter | Qt.TextWordWrap, text)
        painter.end()

    def dropEvent(self, event):
        source = event.source()
        if source == self or not isinstance(source, QListWidget):
            super().dropEvent(event)
            return

        row = self.indexAt(event.pos()).row()
        if row == -1: row = self.count()

        kho_e_grp = None
        kho_e_urg = "N"
        kho_e_lbl = ""

        if self.zone_id == "KHO_E":
            menu = QMenu(self)
            a1 = menu.addAction("📦 Phú Thái - Normal")
            a2 = menu.addAction("⚧️ Phú Thái - SSAQ")
            a3 = menu.addAction("📦 Tivi")
            a4 = menu.addAction("📦 MGTL")
            a5 = menu.addAction("📦 Gia Dụng")

            act = menu.exec_(QCursor.pos())
            if not act:
                event.ignore()
                return

            if act == a1:
                kho_e_grp, kho_e_urg, kho_e_lbl = "VNVLFPOG0211", "N", "PT-N"
            elif act == a2:
                kho_e_grp, kho_e_urg, kho_e_lbl = "VNVLFPOG0219", "Q", "PT-Q"
            elif act == a3:
                kho_e_grp, kho_e_urg, kho_e_lbl = "VNVLFPOG0220", "N", "TV"
            elif act == a4:
                kho_e_grp, kho_e_urg, kho_e_lbl = "VNVLFPOG0221", "N", "MGTL"
            elif act == a5:
                kho_e_grp, kho_e_urg, kho_e_lbl = "VNVLFPOG0222", "N", "GD"

        dropped_data = []
        for item in source.selectedItems():
            taken_item = source.takeItem(source.row(item))
            if taken_item:
                data = taken_item.data(Qt.UserRole)
                if isinstance(data, dict):
                    data["block"] = self.zone_id

                    if self.zone_id == "KHO_E":
                        data["kho_e_group"], data["urgent"], data["kho_e_label"] = kho_e_grp, kho_e_urg, kho_e_lbl
                    elif self.zone_id in FLOW_ZONES:
                        pass
                    elif self.zone_id == "":
                        data["urgent"] = "N"

                    prefix = ""
                    if self.zone_id == "KHO_E":
                        prefix = f"[{data.get('kho_e_label', 'PT-N')}] "
                    elif self.zone_id != "":
                        urg = data.get("urgent", "N")
                        if urg == "Y":
                            prefix = "🔥 "
                        elif urg == "A":
                            prefix = "🅰️ "
                        elif urg == "S":
                            prefix = "🪼 "
                        elif urg == "V":
                            prefix = "🚀 "
                        elif urg == "Q":
                            prefix = "⚧️ "

                    taken_item.setText(f'{prefix}{data.get("name", "N/A")} - {data.get("wms_id", "")}')
                    taken_item.setData(Qt.UserRole, data)

                    self.insertItem(row, taken_item)
                    row += 1
                    dropped_data.append(data)

        event.accept()
        if dropped_data:
            self.items_dropped_signal.emit(self.zone_id, dropped_data)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.scale = get_scale_factor()
        self.setWindowTitle("Đa Vũ Trụ Tâm Linh - Xuyên Á Đại Đạo")
        self.setStyleSheet(get_dynamic_qss(self.scale))

        self.active_threads = []
        self.cached_data = []
        self.wfm_cookie = self.wms_cookie = ""
        self.current_firebase_data = {}

        self.task_counts = {}
        self.dynamic_task_counts = {}
        self.flow_task_counts = {}
        self.flow_ssaq_counts = {}
        self.kho_e_task_counts = {}  # Lưu đếm task của kho E

        self.badges = {}

        self.current_toggle_states = {
            "SDD": False,
            "AHM": False,
            "NDD normal": False,
            "NDD Phú Thái": False,
            "D-": False
        }

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
            "Block C": self.txt_cfg_c.text().strip(),
            "Block E": self.txt_cfg_e.text().strip(),
            "SDD": self.toggle_sdd.isChecked(),
            "AHM": self.toggle_ahm.isChecked(),
            "NDD normal": self.toggle_ndd_normal.isChecked(),
            "NDD Phú Thái": self.toggle_ndd_phu_thai.isChecked(),
            "D-": self.toggle_dminus.isChecked(),
            "DayShift": self.btn_shift_toggle.isChecked()
        }

    # STREAMING_CHUNK: Setup Layout Main
    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        pad_main = max(6, int(12 * self.scale))
        main_layout.setContentsMargins(pad_main, pad_main, pad_main, pad_main)
        main_layout.setSpacing(pad_main)

        header_widget = QWidget()
        header_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(int(8 * self.scale))

        scan_frame = QFrame()
        scan_frame.setStyleSheet("QFrame { background-color: #F5F5F5; border: 1px solid #E2E8F0; border-radius: 8px; }")
        scan_box_layout = QHBoxLayout(scan_frame)
        scan_box_layout.setContentsMargins(pad_main, pad_main, pad_main, pad_main)

        input_vbox = QVBoxLayout()
        input_vbox.setSpacing(int(6 * self.scale))

        title_search_layout = QHBoxLayout()
        lbl_scan_title = QLabel("Quỷ Môn Quan")
        lbl_scan_title.setStyleSheet(
            f"font-weight: 600; font-size: {max(11, int(14 * self.scale))}px; color: #475569; border: none;")

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("🔍 Gọi Vong...")
        self.txt_search.setMinimumWidth(int(220 * self.scale))
        self.txt_search.textChanged.connect(self.on_search_text_changed)

        self.lbl_search_count = QLabel("")
        self.lbl_search_count.setStyleSheet(
            f"color: #64748B; font-weight: 600; font-size: {max(10, int(12 * self.scale))}px; margin-left: 6px;")

        title_search_layout.addWidget(lbl_scan_title)
        title_search_layout.addStretch()
        title_search_layout.addWidget(self.txt_search)
        title_search_layout.addWidget(self.lbl_search_count)

        input_vbox.addLayout(title_search_layout)

        shortcut_search = QShortcut(QKeySequence("Ctrl+F"), self)
        shortcut_search.activated.connect(self.txt_search.selectAll)
        shortcut_search.activated.connect(self.txt_search.setFocus)

        shortcut_esc = QShortcut(QKeySequence("Esc"), self.txt_search)
        shortcut_esc.activated.connect(self.txt_search.clear)
        shortcut_esc.activated.connect(self.txt_search.clearFocus)

        self.txt_scan = ScanTextEdit()
        self.txt_scan.setPlaceholderText("Paste ID và Enter...")
        self.txt_scan.setMaximumHeight(int(40 * self.scale))
        self.txt_scan.enter_pressed.connect(self.on_scan_triggered)
        input_vbox.addWidget(self.txt_scan)

        status_layout = QHBoxLayout()
        self.lbl_status = QLabel("Đang khởi động hệ thống...")
        self.lbl_status.setStyleSheet(
            f"font-weight: 500; color: #64748B; border: none; font-size: {max(10, int(12 * self.scale))}px;")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        status_layout.addWidget(self.lbl_status, stretch=8)
        status_layout.addWidget(self.progress_bar, stretch=2)
        input_vbox.addLayout(status_layout)

        scan_box_layout.addLayout(input_vbox, stretch=8)

        btn_vbox = QVBoxLayout()
        btn_vbox.setSpacing(int(6 * self.scale))
        btn_vbox.setAlignment(Qt.AlignBottom)

        btn_refresh = QPushButton("🔄 Luân Hồi")
        btn_refresh.clicked.connect(self.refresh_all_data)

        self.btn_delete = QPushButton("❌ Đầu Thai")
        self.btn_delete.setObjectName("btn_delete")
        self.btn_delete.clicked.connect(self.delete_selected_items)

        self.btn_shift_toggle = QPushButton("☀️ Ca Ngày")
        self.btn_shift_toggle.setCheckable(True)
        self.btn_shift_toggle.setChecked(True)
        self.btn_shift_toggle.setStyleSheet(
            "background-color: #10B981; color: white; border-radius: 6px; padding: 6px; font-weight: bold;")
        self.btn_shift_toggle.clicked.connect(self.on_shift_toggle_changed)

        btn_vbox.addWidget(btn_refresh)
        btn_vbox.addWidget(self.btn_delete)
        btn_vbox.addWidget(self.btn_shift_toggle)
        scan_box_layout.addLayout(btn_vbox, stretch=2)

        header_layout.addWidget(scan_frame)
        main_layout.addWidget(header_widget)

        self.listboxes = {}
        workspace_layout = QHBoxLayout()
        workspace_layout.setSpacing(pad_main)

        left_panel_container = QWidget()
        left_layout = QVBoxLayout(left_panel_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.create_zone_box(left_layout, "Cõi Tạm", "#64748B", 0, 0, is_grid=False, show_badge=True,
                             is_left_panel=True, watermark_text="<3")
        workspace_layout.addWidget(left_panel_container, stretch=1)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(pad_main)

        tab_layout = QHBoxLayout()
        tab_layout.setSpacing(int(8 * self.scale))

        self.btn_tab_normal = QPushButton("🎯 PICK NORMAL")
        self.btn_tab_normal.setObjectName("tab_active")
        self.btn_tab_flow = QPushButton("🌊 FLOW PICK")
        self.btn_tab_flow.setObjectName("tab_inactive")

        self.btn_tab_normal.clicked.connect(lambda: self.switch_tab(0))
        self.btn_tab_flow.clicked.connect(lambda: self.switch_tab(1))

        tab_layout.addWidget(self.btn_tab_normal)
        tab_layout.addWidget(self.btn_tab_flow)
        tab_layout.addStretch()

        right_layout.addLayout(tab_layout)
        self.stacked_widget = QStackedWidget()

        # Normal Pick Tab
        normal_container = QWidget()
        normal_layout_main = QVBoxLayout(normal_container)
        normal_layout_main.setContentsMargins(0, 0, 0, 0)

        normal_grid = QGridLayout()
        normal_grid.setSpacing(int(6 * self.scale))

        self.create_zone_box(normal_grid, "Block A", "#10B981", 0, 0, True, watermark_text="A")
        self.create_zone_box(normal_grid, "Block B", "#F59E0B", 0, 1, True, watermark_text="B")
        self.create_zone_box(normal_grid, "Block C", "#8B5CF6", 0, 2, True, watermark_text="C")
        self.create_zone_box(normal_grid, "Block A&B", "#3B82F6", 0, 3, True, watermark_text="AB")

        config_frame = QFrame()
        config_frame.setStyleSheet(
            "QFrame { border: 1px solid #E2E8F0; border-top: 4px solid #475569; border-radius: 8px; background-color: #F5F5F5; }")

        config_layout = QGridLayout(config_frame)
        config_layout.setContentsMargins(pad_main, pad_main, pad_main, pad_main)
        config_layout.setSpacing(int(4 * self.scale))

        lbl_cfg_title = QLabel("⚙️ Configuration")
        lbl_cfg_title.setStyleSheet(
            f"font-weight: 600; font-size: {max(11, int(13 * self.scale))}px; color: #334155; border: none;")
        config_layout.addWidget(lbl_cfg_title, 0, 0, 1, 2)

        self.txt_cfg_a = QLineEdit()
        self.txt_cfg_b = QLineEdit()
        self.txt_cfg_c = QLineEdit()
        self.txt_cfg_e = QLineEdit()

        font_size_cfg = max(9, int(11 * self.scale))

        for idx, (lbl_text, txt_widget) in enumerate(
                [("A:", self.txt_cfg_a), ("B:", self.txt_cfg_b), ("C:", self.txt_cfg_c), ("E:", self.txt_cfg_e)]):
            lbl = QLabel(lbl_text)
            lbl.setStyleSheet(f"font-weight: 500; color: #475569; border: none; font-size: {font_size_cfg}px;")
            txt_widget.setReadOnly(True)
            config_layout.addWidget(lbl, idx + 1, 0)
            config_layout.addWidget(txt_widget, idx + 1, 1)

        lbl_dynamic_title = QLabel("⚡ Dynamic Wave Config")
        lbl_dynamic_title.setStyleSheet(
            f"font-weight: 600; font-size: {max(10, int(12 * self.scale))}px; color: #9333EA; border: none; margin-top: 4px;")
        config_layout.addWidget(lbl_dynamic_title, 5, 0, 1, 2)

        self.toggle_sdd = ToggleSwitch()
        self.toggle_ahm = ToggleSwitch()
        self.toggle_ndd_normal = ToggleSwitch()
        self.toggle_ndd_phu_thai = ToggleSwitch()
        self.toggle_dminus = ToggleSwitch()

        self.toggle_sdd.clicked.connect(lambda checked, name="SDD": self.on_toggle_changed(name))
        self.toggle_ahm.clicked.connect(lambda checked, name="AHM": self.on_toggle_changed(name))
        self.toggle_ndd_normal.clicked.connect(lambda checked, name="NDD normal": self.on_toggle_changed(name))
        self.toggle_ndd_phu_thai.clicked.connect(lambda checked, name="NDD Phú Thái": self.on_toggle_changed(name))
        self.toggle_dminus.clicked.connect(lambda checked, name="D-": self.on_toggle_changed(name))

        for idx, (lbl_text, toggle_widget) in enumerate(
                [("SDD:", self.toggle_sdd),
                 ("AHM:", self.toggle_ahm),
                 ("NDD normal:", self.toggle_ndd_normal),
                 ("NDD Phú Thái:", self.toggle_ndd_phu_thai),
                 ("D-:", self.toggle_dminus)]):
            lbl = QLabel(lbl_text)
            lbl.setStyleSheet(f"font-weight: 500; color: #475569; border: none; font-size: {font_size_cfg}px;")
            config_layout.addWidget(lbl, 6 + idx, 0)
            config_layout.addWidget(toggle_widget, 6 + idx, 1)

        self.btn_edit_config = QPushButton("Chỉnh sửa")
        self.btn_edit_config.setStyleSheet("margin-top: 8px;")
        self.btn_edit_config.clicked.connect(self.toggle_config_edit)
        config_layout.addWidget(self.btn_edit_config, 12, 0, 1, 2)

        normal_grid.addWidget(config_frame, 0, 4, 2, 1)

        self.create_zone_box(normal_grid, "Block A&C", "#3B82F6", 1, 0, True, watermark_text="AC")
        self.create_zone_box(normal_grid, "Block B&C", "#3B82F6", 1, 1, True, watermark_text="BC")
        self.create_zone_box(normal_grid, "Block A&B&C", "#EF4444", 1, 2, True, watermark_text="ABC")
        self.create_zone_box(normal_grid, "Block E", "#EC4899", 1, 3, True, watermark_text="E")

        normal_layout_main.addLayout(normal_grid)
        self.stacked_widget.addWidget(normal_container)

        # Flow Pick Tab
        flow_container = QWidget()
        flow_layout_main = QVBoxLayout(flow_container)
        flow_layout_main.setContentsMargins(0, 0, 0, 0)

        flow_grid = QGridLayout()
        flow_grid.setSpacing(int(6 * self.scale))

        flow_color_a = "#06B6D4"
        flow_color_b = "#F97316"
        flow_color_c = "#8B5CF6"
        flow_color_d = "#10B981"

        self.create_zone_box(flow_grid, "A1", flow_color_a, 0, 0, True, watermark_text="A1")
        self.create_zone_box(flow_grid, "A2", flow_color_a, 0, 1, True, watermark_text="A2")
        self.create_zone_box(flow_grid, "A3", flow_color_a, 0, 2, True, watermark_text="A3")
        self.create_zone_box(flow_grid, "A4", flow_color_a, 0, 3, True, watermark_text="A4")
        self.create_zone_box(flow_grid, "B1", flow_color_b, 0, 4, True, watermark_text="B1")
        self.create_zone_box(flow_grid, "B2", flow_color_b, 0, 5, True, watermark_text="B2")
        self.create_zone_box(flow_grid, "B3", flow_color_b, 0, 6, True, watermark_text="B3")
        self.create_zone_box(flow_grid, "B4", flow_color_b, 0, 7, True, watermark_text="B4")
        self.create_zone_box(flow_grid, "B5", flow_color_b, 0, 8, True, watermark_text="B5")

        self.create_zone_box(flow_grid, "HV", flow_color_b, 1, 0, True, watermark_text="HV")
        self.create_zone_box(flow_grid, "FD", flow_color_b, 1, 1, True, watermark_text="FD")
        self.create_zone_box(flow_grid, "C1", flow_color_c, 1, 2, True, watermark_text="C1")
        self.create_zone_box(flow_grid, "C2", flow_color_c, 1, 3, True, watermark_text="C2")
        self.create_zone_box(flow_grid, "C3", flow_color_c, 1, 4, True, watermark_text="C3")

        self.create_zone_box(flow_grid, "KHO_E", flow_color_d, 1, 6, is_grid=True, colspan=3, watermark_text="KHO E")
        self.create_zone_box(flow_grid, "TOP", flow_color_d, 1, 5, True, watermark_text="TOP")

        flow_layout_main.addLayout(flow_grid)
        self.stacked_widget.addWidget(flow_container)

        right_layout.addWidget(self.stacked_widget, stretch=1)
        workspace_layout.addWidget(right_panel, stretch=7)

        main_layout.addLayout(workspace_layout)

    def on_shift_toggle_changed(self):
        if self.btn_shift_toggle.isChecked():
            self.btn_shift_toggle.setText("☀️ Ca Ngày")
            self.btn_shift_toggle.setStyleSheet(
                "background-color: #10B981; color: white; border-radius: 6px; padding: 6px; font-weight: bold;")
        else:
            self.btn_shift_toggle.setText("🌙 Ca Đêm")
            self.btn_shift_toggle.setStyleSheet(
                "background-color: #EF4444; color: white; border-radius: 6px; padding: 6px; font-weight: bold;")

        self.refresh_wms_tasks()

        # Cập nhật quyền cho tất cả nhân viên ngay khi đổi ca
        block_users = {}
        for uid, data in self.current_firebase_data.items():
            block = data.get("block", "")
            if block not in block_users:
                block_users[block] = []
            block_users[block].append(data)

        for block, users in block_users.items():
            wms_thread = WMSUpdateRuleThread(block, users, self.get_current_config(), self.wms_cookie)
            self.start_thread(wms_thread)

    def on_search_text_changed(self, text):
        search_term = remove_accents(text.strip().lower())
        match_count = 0

        for lw in self.listboxes.values():
            for i in range(lw.count()):
                item = lw.item(i)
                data = item.data(Qt.UserRole)
                if not isinstance(data, dict):
                    continue

                name_raw = data.get("name", "")
                wms_id = str(data.get("wms_id", ""))
                user_id = str(data.get("user_id", ""))

                name_search = remove_accents(name_raw.lower())
                wms_id_search = wms_id.lower()
                user_id_search = user_id.lower()

                block = data.get("block", "")

                prefix = ""
                if block == "KHO_E":
                    prefix = f"[{data.get('kho_e_label', 'PT-N')}] "
                elif block != "":
                    urg = data.get("urgent", "N")
                    if urg == "Y":
                        prefix = "🔥 "
                    elif urg == "A":
                        prefix = "🅰️ "
                    elif urg == "S":
                        prefix = "🪼 "
                    elif urg == "V":
                        prefix = "🚀 "
                    elif urg == "Q":
                        prefix = "⚧️ "

                base_text = f'{prefix}{name_raw} - {wms_id}'

                if search_term and (
                        search_term in name_search or search_term in wms_id_search or search_term in user_id_search):
                    item.setText(f"⭐ {base_text}")
                    item.setBackground(QColor("#FEF08A"))
                    item.setForeground(QColor("#C2410C"))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    match_count += 1
                else:
                    item.setText(base_text)
                    item.setBackground(QColor("#F5F5F5"))
                    saved_color = data.get("color", "#1E293B")
                    item.setForeground(
                        QColor("#1E293B" if saved_color in ["white", "#ffffff", "#2d3436", "black"] else saved_color))
                    font = item.font()
                    font.setBold(False)
                    item.setFont(font)

        if search_term:
            if match_count > 0:
                self.lbl_search_count.setText(f"({match_count} kết quả)")
                self.lbl_search_count.setStyleSheet(
                    f"color: #D97706; font-weight: 600; font-size: {max(10, int(12 * self.scale))}px; margin-left: 6px;")
            else:
                self.lbl_search_count.setText("(0 kết quả)")
                self.lbl_search_count.setStyleSheet(
                    f"color: #EF4444; font-weight: 600; font-size: {max(10, int(12 * self.scale))}px; margin-left: 6px;")
        else:
            self.lbl_search_count.setText("")

    def trigger_search_update(self):
        if hasattr(self, 'txt_search'):
            self.on_search_text_changed(self.txt_search.text())

    def on_toggle_changed(self, changed_toggle_name):
        new_states = {
            "SDD": self.toggle_sdd.isChecked(),
            "AHM": self.toggle_ahm.isChecked(),
            "NDD normal": self.toggle_ndd_normal.isChecked(),
            "NDD Phú Thái": self.toggle_ndd_phu_thai.isChecked(),
            "D-": self.toggle_dminus.isChecked()
        }

        rules_to_update = {}
        for k, v in new_states.items():
            if v != self.current_toggle_states.get(k, False):
                status_int = 1 if v else 0
                for rule_id in WAVE_RULE_GROUPS.get(k, []):
                    rules_to_update[rule_id] = status_int

        self.current_toggle_states = new_states.copy()
        config_data = self.get_current_config()
        self.start_thread(FirebaseUpdateThread("PUT_CONFIG", data=config_data))

        if rules_to_update:
            api_thread = WMSUpdateWaveRuleThread(self.wms_cookie, rules_to_update)
            api_thread.finished_update.connect(self.on_wave_rules_updated)
            self.start_thread(api_thread)
            self.lbl_status.setText(f"⚡ Đang cấu hình {len(rules_to_update)} Wave Rules song song...")
            self.lbl_status.setStyleSheet("color: #9333EA;")

    @pyqtSlot(int, int)
    def on_wave_rules_updated(self, success_count, total_count):
        if success_count == total_count and total_count > 0:
            self.lbl_status.setText(f"✅ Đã cấu hình xong {success_count}/{total_count} Wave Rules!")
            self.lbl_status.setStyleSheet("color: #10B981;")
        elif total_count > 0:
            self.lbl_status.setText(f"⚠️ Đã cấu hình {success_count}/{total_count} Wave Rules. Có lỗi xảy ra!")
            self.lbl_status.setStyleSheet("color: #F59E0B;")

    def switch_tab(self, index):
        self.stacked_widget.setCurrentIndex(index)
        if index == 0:
            self.btn_tab_normal.setObjectName("tab_active")
            self.btn_tab_flow.setObjectName("tab_inactive")
        else:
            self.btn_tab_normal.setObjectName("tab_inactive")
            self.btn_tab_flow.setObjectName("tab_active")

        self.btn_tab_normal.style().unpolish(self.btn_tab_normal)
        self.btn_tab_normal.style().polish(self.btn_tab_normal)
        self.btn_tab_flow.style().unpolish(self.btn_tab_flow)
        self.btn_tab_flow.style().polish(self.btn_tab_flow)

    # STREAMING_CHUNK: Setup UI từng khung trong Normal và Flow
    def create_zone_box(self, parent_layout, zone_id, top_border_color, row, col, is_grid=False, show_badge=True,
                        colspan=1, is_left_panel=False, watermark_text=None):
        box_frame = QFrame()
        box_frame.setObjectName("zone_box_frame")

        box_style = f"""
        #zone_box_frame {{
            border: 1px solid #E2E8F0;
            border-top: 4px solid {top_border_color};
            border-radius: 8px;
            background-color: #F5F5F5;
        }}
        """
        box_frame.setStyleSheet(box_style)

        box_layout = QVBoxLayout(box_frame)
        pad_box = max(4, int(6 * self.scale))
        box_layout.setContentsMargins(pad_box, pad_box, pad_box, pad_box)
        box_layout.setSpacing(int(4 * self.scale))

        h_layout = QHBoxLayout()
        h_layout.setContentsMargins(0, 0, 0, 0)

        lw_id = "" if is_left_panel else zone_id

        if is_left_panel:
            lbl_title = QLabel(zone_id)
            font_size_title = max(10, int(13 * self.scale))
            lbl_title.setStyleSheet(f"font-weight: 600; font-size: {font_size_title}px; color: #1E293B;")
            h_layout.addWidget(lbl_title)
            h_layout.addStretch()

        if show_badge:
            font_size_badge = max(9, int(11 * self.scale))

            lbl_people = QLabel("👤 0")
            lbl_people.setStyleSheet(
                f"background-color: #FFFFFF; color: {top_border_color}; font-weight: 600; border: 1px solid #E2E8F0; border-radius: 4px; padding: 4px 6px; font-size: {font_size_badge}px;")
            lbl_people.setAlignment(Qt.AlignCenter)
            badges_dict = {"people": lbl_people}

            if lw_id == "KHO_E":
                lbl_pt = QLabel("Phú Thái\n📦 0 | ⚧️ 0")
                lbl_pt.setStyleSheet(
                    f"background-color: #FFFFFF; color: #06B6D4; font-weight: 600; border: 1px solid #A5F3FC; border-radius: 4px; padding: 4px 6px; font-size: {font_size_badge}px;")
                lbl_tv = QLabel("Tivi\n📦 0")
                lbl_tv.setStyleSheet(
                    f"background-color: #FFFFFF; color: #F97316; font-weight: 600; border: 1px solid #FDBA74; border-radius: 4px; padding: 4px 6px; font-size: {font_size_badge}px;")
                lbl_mgtl = QLabel("MGTL\n📦 0")
                lbl_mgtl.setStyleSheet(
                    f"background-color: #FFFFFF; color: #8B5CF6; font-weight: 600; border: 1px solid #C4B5FD; border-radius: 4px; padding: 4px 6px; font-size: {font_size_badge}px;")
                lbl_gd = QLabel("Gia Dụng\n📦 0")
                lbl_gd.setStyleSheet(
                    f"background-color: #FFFFFF; color: #10B981; font-weight: 600; border: 1px solid #6EE7B7; border-radius: 4px; padding: 4px 6px; font-size: {font_size_badge}px;")

                h_layout.addWidget(lbl_people)
                h_layout.addWidget(lbl_pt)
                h_layout.addWidget(lbl_tv)
                h_layout.addWidget(lbl_mgtl)
                h_layout.addWidget(lbl_gd)
                h_layout.addStretch()

                badges_dict.update({"pt": lbl_pt, "tv": lbl_tv, "mgtl": lbl_mgtl, "gd": lbl_gd})

            elif lw_id in NORMAL_BLOCKS:
                lbl_normal = QLabel("Normal\n📦 Wave: 0\n⚡ Auto: 0")
                lbl_normal.setStyleSheet(
                    f"background-color: #FFFFFF; color: #3B82F6; font-weight: 600; border: 1px solid #BFDBFE; border-radius: 4px; padding: 4px 6px; font-size: {font_size_badge}px;")
                lbl_normal.setAlignment(Qt.AlignCenter)

                lbl_urgent = QLabel("Hỏa Tốc\n🅰️ AHM: 0\n🪼 SDD: 0\n🚀 NDD: 0\n📦 Mix: 0")
                lbl_urgent.setStyleSheet(
                    f"background-color: #FFFFFF; color: #EF4444; font-weight: 600; border: 1px solid #FECACA; border-radius: 4px; padding: 4px 6px; font-size: {font_size_badge}px;")
                lbl_urgent.setAlignment(Qt.AlignCenter)

                h_layout.addWidget(lbl_normal)
                h_layout.addStretch()
                h_layout.addWidget(lbl_people)
                h_layout.addStretch()
                h_layout.addWidget(lbl_urgent)

                badges_dict["normal"] = lbl_normal
                badges_dict["urgent"] = lbl_urgent
            elif lw_id in FLOW_ZONES:
                lbl_flow = QLabel("📦 0")
                lbl_flow.setStyleSheet(
                    f"background-color: #FFFFFF; color: #06B6D4; font-weight: 600; border: 1px solid #A5F3FC; border-radius: 4px; padding: 4px 6px; font-size: {font_size_badge}px;")
                lbl_flow.setAlignment(Qt.AlignCenter)

                lbl_ssaq = QLabel("⚧️ 0")
                lbl_ssaq.setStyleSheet(
                    f"background-color: #FFFFFF; color: #9333EA; font-weight: 600; border: 1px solid #D8B4FE; border-radius: 4px; padding: 4px 6px; font-size: {font_size_badge}px;")
                lbl_ssaq.setAlignment(Qt.AlignCenter)

                h_layout.addWidget(lbl_people)
                h_layout.addWidget(lbl_flow)
                h_layout.addWidget(lbl_ssaq)
                h_layout.addStretch()
                badges_dict["flow"] = lbl_flow
                badges_dict["ssaq"] = lbl_ssaq
            else:
                h_layout.addWidget(lbl_people)

            self.badges[lw_id] = badges_dict

        box_layout.addLayout(h_layout)

        lw = ZoneListWidget(lw_id, self.scale, watermark_text=watermark_text)
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
        else:
            parent_layout.addWidget(box_frame)

        self.listboxes[lw_id] = lw

    def update_all_badges(self):
        if not hasattr(self, 'badges'): return
        total_normal = 0
        total_flow = 0

        for z_id, lb in self.listboxes.items():
            people_count = lb.count()

            if z_id in NORMAL_BLOCKS:
                total_normal += people_count
            elif z_id in FLOW_ZONES:
                total_flow += people_count

            if z_id in self.badges:
                b_dict = self.badges[z_id]
                b_dict["people"].setText(f"👤 {people_count}")

                if z_id == "KHO_E":
                    counts = self.kho_e_task_counts
                    if "pt" in b_dict: b_dict["pt"].setText(
                        f"Phú Thái\n📦 {counts.get('PT_N', 0)} | ⚧️ {counts.get('PT_Q', 0)}")
                    if "tv" in b_dict: b_dict["tv"].setText(f"Tivi\n📦 {counts.get('TV', 0)}")
                    if "mgtl" in b_dict: b_dict["mgtl"].setText(f"MGTL\n📦 {counts.get('MGTL', 0)}")
                    if "gd" in b_dict: b_dict["gd"].setText(f"Gia Dụng\n📦 {counts.get('GD', 0)}")
                elif z_id in NORMAL_BLOCKS:
                    task_data = self.task_counts.get(z_id, {"normal": 0, "ahm": 0, "sdd": 0, "ndd": 0, "oth": 0})
                    dyn_data = self.dynamic_task_counts.get(z_id, {"normal": 0, "ahm": 0, "sdd": 0, "ndd": 0, "oth": 0})

                    t_norm = task_data.get("normal", 0) + dyn_data.get("normal", 0)
                    d_norm = dyn_data.get("normal", 0)

                    t_ahm = task_data.get("ahm", 0) + dyn_data.get("ahm", 0)
                    t_sdd = task_data.get("sdd", 0) + dyn_data.get("sdd", 0)
                    t_ndd = task_data.get("ndd", 0) + dyn_data.get("ndd", 0)
                    t_oth = task_data.get("oth", 0) + dyn_data.get("oth", 0)

                    b_dict["normal"].setText(f"Normal\n📦 Wave: {task_data.get('normal', 0)}\n⚡ Auto: {d_norm}")
                    b_dict["urgent"].setText(
                        f"Hỏa Tốc\n🅰️ AHM: {t_ahm}\n🪼 SDD: {t_sdd}\n🚀 NDD: {t_ndd}\n📦 Mix: {t_oth}")
                elif z_id in FLOW_ZONES:
                    f_qty = self.flow_task_counts.get(z_id, 0)
                    q_qty = self.flow_ssaq_counts.get(z_id, 0)
                    if "flow" in b_dict: b_dict["flow"].setText(f"📦 {f_qty}")
                    if "ssaq" in b_dict: b_dict["ssaq"].setText(f"⚧️ {q_qty}")

        if hasattr(self, 'btn_tab_normal'):
            self.btn_tab_normal.setText(f"🎯 PICK NORMAL (👤 Tổng: {total_normal})")
            self.btn_tab_flow.setText(f"🌊 FLOW PICK (👤 Tổng: {total_flow})")

    def start_initialization(self):
        init_thread = InitDataThread()
        init_thread.finished_signal.connect(self.on_init_finished)
        init_thread.error_signal.connect(self.on_init_error)
        self.start_thread(init_thread)

    @pyqtSlot(object, str, str)
    def on_init_finished(self, cached_data, wfm_cookie, wms_cookie):
        self.cached_data, wfm_cookie, wms_cookie = cached_data, wfm_cookie, wms_cookie
        self.wfm_cookie, self.wms_cookie = wfm_cookie, wms_cookie
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.lbl_status.setText(f"✅ Sẵn sàng! Đã tải {len(self.cached_data)} nhân sự.")
        self.lbl_status.setStyleSheet("color: #10B981;")
        self.refresh_all_data()

    @pyqtSlot(str)
    def on_init_error(self, err):
        self.lbl_status.setText(f"❌ Lỗi: {err}")
        self.lbl_status.setStyleSheet("color: #EF4444;")

    # STREAMING_CHUNK: Menu Tùy Chọn và Xử Lý Thao Tác Kéo Thả
    def on_scan_triggered(self, text):
        self.txt_scan.clear()
        if not text.strip(): return
        self.lbl_status.setText("Đang xử lý dữ liệu nhập vào...")
        self.lbl_status.setStyleSheet("color: #3B82F6;")
        api_thread = ProcessApiThread(text, self.cached_data, self.wfm_cookie, self.wms_cookie)
        api_thread.result_ready.connect(self.add_item_to_ui_and_firebase)
        self.start_thread(api_thread)

    @pyqtSlot(object)
    def add_item_to_ui_and_firebase(self, data):
        uid = data.get("user_id", "")
        if not uid: return

        if uid in self.current_firebase_data:
            data["block"] = self.current_firebase_data[uid].get("block", "")
            data["urgent"] = self.current_firebase_data[uid].get("urgent", "N")
            if "kho_e_group" in self.current_firebase_data[uid]:
                data["kho_e_group"] = self.current_firebase_data[uid].get("kho_e_group")
                data["kho_e_label"] = self.current_firebase_data[uid].get("kho_e_label")

        self.current_firebase_data[uid] = data

        for lb in self.listboxes.values():
            for i in range(lb.count()):
                existing_item = lb.item(i)
                if existing_item and isinstance(existing_item.data(Qt.UserRole), dict) and existing_item.data(
                        Qt.UserRole).get("user_id") == uid:
                    lb.takeItem(i)
                    break

        block_name = str(data.get("block", "")).strip()
        fallback_lb = self.listboxes.get("", list(self.listboxes.values())[0])
        target_lb = self.listboxes.get(block_name, fallback_lb)

        item = QListWidgetItem("")

        prefix = ""
        if block_name == "KHO_E":
            prefix = f"[{data.get('kho_e_label', 'PT-N')}] "
        elif block_name != "":
            urg = data.get("urgent", "N")
            if urg == "Y":
                prefix = "🔥 "
            elif urg == "A":
                prefix = "🅰️ "
            elif urg == "S":
                prefix = "🪼 "
            elif urg == "V":
                prefix = "🚀 "
            elif urg == "Q":
                prefix = "⚧️ "

        item.setText(f'{prefix}{data.get("name", "N/A")} - {data.get("wms_id", "")}')
        item.setData(Qt.UserRole, data)
        item.setFlags(item.flags() | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled | Qt.ItemIsEnabled)

        target_lb.addItem(item)
        target_lb.scrollToBottom()

        self.start_thread(FirebaseUpdateThread("PUT", data=data))
        self.lbl_status.setText(f"✅ Đã thêm {data['name']}")
        self.lbl_status.setStyleSheet("color: #10B981;")
        self.update_all_badges()
        self.trigger_search_update()

    @pyqtSlot(str, list)
    def on_items_dropped_to_zone(self, zone_id, dropped_data):
        for data in dropped_data:
            self.current_firebase_data[data["user_id"]] = data
            self.start_thread(FirebaseUpdateThread("PUT", data=data))

        wms_thread = WMSUpdateRuleThread(zone_id, dropped_data, self.get_current_config(), self.wms_cookie)
        self.start_thread(wms_thread)
        self.update_all_badges()
        self.trigger_search_update()

    @pyqtSlot(QListWidgetItem)
    def on_item_double_clicked(self, item):
        data = item.data(Qt.UserRole)
        if not isinstance(data, dict): return

        if not data.get("block"): return

        if data.get("block") == "KHO_E":
            self.on_context_menu(self.listboxes["KHO_E"].mapFromGlobal(QCursor.pos()), self.listboxes["KHO_E"])
            return

        urgent_state = data.get("urgent", "N")

        if data.get("block") in FLOW_ZONES:
            if urgent_state == "N":
                data["urgent"] = "Q"
            else:
                data["urgent"] = "N"
        else:
            if urgent_state == "N":
                data["urgent"] = "Y"
            elif urgent_state == "Y":
                data["urgent"] = "A"
            elif urgent_state == "A":
                data["urgent"] = "S"
            elif urgent_state == "S":
                data["urgent"] = "V"
            else:
                data["urgent"] = "N"

        prefix = ""
        if data.get("block") != "":
            urg = data.get("urgent", "N")
            if urg == "Y":
                prefix = "🔥 "
            elif urg == "A":
                prefix = "🅰️ "
            elif urg == "S":
                prefix = "🪼 "
            elif urg == "V":
                prefix = "🚀 "
            elif urg == "Q":
                prefix = "⚧️ "
        item.setText(f'{prefix}{data.get("name", "N/A")} - {data.get("wms_id", "")}')
        item.setData(Qt.UserRole, data)

        self.current_firebase_data[data["user_id"]] = data
        self.start_thread(FirebaseUpdateThread("PUT", data=data))

        wms_thread = WMSUpdateRuleThread(data.get("block"), [data], self.get_current_config(), self.wms_cookie)
        self.start_thread(wms_thread)
        self.trigger_search_update()

    def on_context_menu(self, pos, list_widget):
        item = list_widget.itemAt(pos)
        if not item: return
        data = item.data(Qt.UserRole)
        menu = QMenu(self)

        act_y = act_a = act_s = act_v = act_n = act_q = None
        actions_kho_e = {}

        if not data.get("block"):
            pass
        elif data.get("block") == "KHO_E":
            actions_kho_e["PT_N"] = menu.addAction("📦 Gán Phú Thái Normal")
            actions_kho_e["PT_Q"] = menu.addAction("⚧️ Gán Phú Thái SSAQ")
            actions_kho_e["TV"] = menu.addAction("📦 Gán Tivi")
            actions_kho_e["MGTL"] = menu.addAction("📦 Gán MGTL")
            actions_kho_e["GD"] = menu.addAction("📦 Gán Gia Dụng")
            menu.addSeparator()
        elif data.get("block") in FLOW_ZONES:
            act_n = menu.addAction("📦 Gán Flow Thường")
            act_q = menu.addAction("⚧️ Gán Flow SSAQ")
            menu.addSeparator()
        elif data.get("block") not in FLOW_ZONES:
            act_n = menu.addAction("👤 Gán Đơn Bình Thường")
            menu.addSeparator()
            act_y = menu.addAction("🔥 Gán Tất Cả Express")
            act_a = menu.addAction("🅰️ Gán Tất Cả AHM")
            act_s = menu.addAction("🪼 Gán SDD")
            act_v = menu.addAction("🚀 Gán NDD")

        menu.addSeparator()
        act_del = menu.addAction("❌ Xóa nhân sự")

        action = menu.exec_(list_widget.mapToGlobal(pos))
        if not action: return

        if action == act_del:
            self.start_thread(FirebaseUpdateThread("DELETE", user_id=data["user_id"]))
            list_widget.takeItem(list_widget.row(item))
            self.update_all_badges()

            data_to_reset = data.copy()
            data_to_reset["urgent"] = "N"
            wms_thread = WMSUpdateRuleThread("", [data_to_reset], self.get_current_config(), self.wms_cookie)
            self.start_thread(wms_thread)
            self.trigger_search_update()

        elif data.get("block") == "KHO_E" and action in actions_kho_e.values():
            if action == actions_kho_e["PT_N"]:
                data["kho_e_group"], data["urgent"], data["kho_e_label"] = "VNVLFPOG0211", "N", "PT-N"
            elif action == actions_kho_e["PT_Q"]:
                data["kho_e_group"], data["urgent"], data["kho_e_label"] = "VNVLFPOG0219", "Q", "PT-Q"
            elif action == actions_kho_e["TV"]:
                data["kho_e_group"], data["urgent"], data["kho_e_label"] = "VNVLFPOG0220", "N", "TV"
            elif action == actions_kho_e["MGTL"]:
                data["kho_e_group"], data["urgent"], data["kho_e_label"] = "VNVLFPOG0221", "N", "MGTL"
            elif action == actions_kho_e["GD"]:
                data["kho_e_group"], data["urgent"], data["kho_e_label"] = "VNVLFPOG0222", "N", "GD"

            item.setText(f'[{data["kho_e_label"]}] {data.get("name", "N/A")} - {data.get("wms_id", "")}')
            item.setData(Qt.UserRole, data)

            self.current_firebase_data[data["user_id"]] = data
            self.start_thread(FirebaseUpdateThread("PUT", data=data))
            wms_thread = WMSUpdateRuleThread(data.get("block"), [data], self.get_current_config(), self.wms_cookie)
            self.start_thread(wms_thread)
            self.trigger_search_update()

        elif act_y and action == act_y:
            data["urgent"] = "Y"
            item.setText(f'🔥 {data.get("name", "N/A")} - {data.get("wms_id", "")}')
            item.setData(Qt.UserRole, data)
            self.start_thread(FirebaseUpdateThread("PUT", data=data))
            wms_thread = WMSUpdateRuleThread(data.get("block"), [data], self.get_current_config(), self.wms_cookie)
            self.start_thread(wms_thread)
            self.trigger_search_update()

        elif act_a and action == act_a:
            data["urgent"] = "A"
            item.setText(f'🅰️ {data.get("name", "N/A")} - {data.get("wms_id", "")}')
            item.setData(Qt.UserRole, data)
            self.start_thread(FirebaseUpdateThread("PUT", data=data))
            wms_thread = WMSUpdateRuleThread(data.get("block"), [data], self.get_current_config(), self.wms_cookie)
            self.start_thread(wms_thread)
            self.trigger_search_update()

        elif act_s and action == act_s:
            data["urgent"] = "S"
            item.setText(f'🪼 {data.get("name", "N/A")} - {data.get("wms_id", "")}')
            item.setData(Qt.UserRole, data)
            self.start_thread(FirebaseUpdateThread("PUT", data=data))
            wms_thread = WMSUpdateRuleThread(data.get("block"), [data], self.get_current_config(), self.wms_cookie)
            self.start_thread(wms_thread)
            self.trigger_search_update()

        elif act_v and action == act_v:
            data["urgent"] = "V"
            item.setText(f'🚀 {data.get("name", "N/A")} - {data.get("wms_id", "")}')
            item.setData(Qt.UserRole, data)
            self.start_thread(FirebaseUpdateThread("PUT", data=data))
            wms_thread = WMSUpdateRuleThread(data.get("block"), [data], self.get_current_config(), self.wms_cookie)
            self.start_thread(wms_thread)
            self.trigger_search_update()

        elif act_q and action == act_q:
            data["urgent"] = "Q"
            item.setText(f'⚧️ {data.get("name", "N/A")} - {data.get("wms_id", "")}')
            item.setData(Qt.UserRole, data)
            self.start_thread(FirebaseUpdateThread("PUT", data=data))
            wms_thread = WMSUpdateRuleThread(data.get("block"), [data], self.get_current_config(), self.wms_cookie)
            self.start_thread(wms_thread)
            self.trigger_search_update()

        elif act_n and action == act_n:
            data["urgent"] = "N"
            item.setText(f'{data.get("name", "N/A")} - {data.get("wms_id", "")}')
            item.setData(Qt.UserRole, data)
            self.start_thread(FirebaseUpdateThread("PUT", data=data))
            wms_thread = WMSUpdateRuleThread(data.get("block"), [data], self.get_current_config(), self.wms_cookie)
            self.start_thread(wms_thread)
            self.trigger_search_update()

    def delete_selected_items(self):
        deleted_pickers = []
        for lb in self.listboxes.values():
            for item in list(lb.selectedItems()):
                data = item.data(Qt.UserRole)
                deleted_pickers.append(data)
                self.start_thread(FirebaseUpdateThread("DELETE", user_id=data["user_id"]))
                lb.takeItem(lb.row(item))

        self.update_all_badges()

        if deleted_pickers:
            for p in deleted_pickers: p["urgent"] = "N"
            wms_thread = WMSUpdateRuleThread("", deleted_pickers, self.get_current_config(), self.wms_cookie)
            self.start_thread(wms_thread)
        self.trigger_search_update()

    def refresh_all_data(self):
        self.lbl_status.setText("🔄 Đang đồng bộ dữ liệu Picker và Config...")
        self.progress_bar.setRange(0, 0)
        fetch_thread = FetchFirebaseThread()
        fetch_thread.data_fetched.connect(self.on_firebase_fetched)
        self.start_thread(fetch_thread)

    def refresh_wms_tasks(self):
        self.lbl_status.setText("🔄 Đang lấy danh sách Tasks WMS...")

        task_thread = FetchTasksThread(self.wms_cookie, self.get_current_config())
        task_thread.tasks_fetched.connect(self.on_wms_tasks_fetched)
        self.start_thread(task_thread)

        dynamic_thread = FetchDynamicTasksThread(self.wms_cookie, self.get_current_config())
        dynamic_thread.tasks_fetched.connect(self.on_dynamic_tasks_fetched)
        self.start_thread(dynamic_thread)

        flow_thread = FetchFlowTasksThread(self.wms_cookie, self.get_current_config())
        flow_thread.tasks_fetched.connect(self.on_flow_tasks_fetched)
        self.start_thread(flow_thread)

    @pyqtSlot(dict)
    def on_wms_tasks_fetched(self, counts):
        self.task_counts = counts
        self.update_all_badges()
        self.lbl_status.setText("✅ Đã làm mới số liệu Task WMS.")
        self.lbl_status.setStyleSheet("color: #10B981;")

    @pyqtSlot(dict)
    def on_dynamic_tasks_fetched(self, counts):
        self.dynamic_task_counts = counts
        self.update_all_badges()

    @pyqtSlot(dict)
    def on_flow_tasks_fetched(self, counts):
        self.flow_task_counts = counts.get("normal", {})
        self.flow_ssaq_counts = counts.get("ssaq", {})
        self.kho_e_task_counts = counts.get("kho_e", {})
        self.update_all_badges()

    @pyqtSlot(object, object)
    def on_firebase_fetched(self, pickers_dict, config_dict):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)

        def _parse_bool(val):
            if isinstance(val, bool): return val
            if isinstance(val, str): return val.lower() == 'true'
            return bool(val)

        if config_dict is not None:
            self.txt_cfg_a.setText(config_dict.get("Block A", ""))
            self.txt_cfg_b.setText(config_dict.get("Block B", ""))
            self.txt_cfg_c.setText(config_dict.get("Block C", ""))
            self.txt_cfg_e.setText(config_dict.get("Block E", ""))

            self.toggle_sdd.blockSignals(True)
            self.toggle_ahm.blockSignals(True)
            self.toggle_ndd_normal.blockSignals(True)
            self.toggle_ndd_phu_thai.blockSignals(True)
            self.toggle_dminus.blockSignals(True)

            is_sdd = _parse_bool(config_dict.get("SDD", False))
            is_ahm = _parse_bool(config_dict.get("AHM", False))
            is_ndd_normal = _parse_bool(config_dict.get("NDD normal", False))
            is_ndd_phu_thai = _parse_bool(config_dict.get("NDD Phú Thái", False))
            is_dminus = _parse_bool(config_dict.get("D-", False))

            # Khôi phục trạng thái ca
            is_day_shift = _parse_bool(config_dict.get("DayShift", True))
            self.btn_shift_toggle.blockSignals(True)
            self.btn_shift_toggle.setChecked(is_day_shift)
            if is_day_shift:
                self.btn_shift_toggle.setText("☀️ Ca Ngày")
                self.btn_shift_toggle.setStyleSheet(
                    "background-color: #10B981; color: white; border-radius: 6px; padding: 6px; font-weight: bold;")
            else:
                self.btn_shift_toggle.setText("🌙 Ca Đêm")
                self.btn_shift_toggle.setStyleSheet(
                    "background-color: #EF4444; color: white; border-radius: 6px; padding: 6px; font-weight: bold;")
            self.btn_shift_toggle.blockSignals(False)

            self.toggle_sdd.setChecked(is_sdd)
            self.toggle_ahm.setChecked(is_ahm)
            self.toggle_ndd_normal.setChecked(is_ndd_normal)
            self.toggle_ndd_phu_thai.setChecked(is_ndd_phu_thai)
            self.toggle_dminus.setChecked(is_dminus)

            self.current_toggle_states = {
                "SDD": is_sdd,
                "AHM": is_ahm,
                "NDD normal": is_ndd_normal,
                "NDD Phú Thái": is_ndd_phu_thai,
                "D-": is_dminus
            }

            self.toggle_sdd.blockSignals(False)
            self.toggle_ahm.blockSignals(False)
            self.toggle_ndd_normal.blockSignals(False)
            self.toggle_ndd_phu_thai.blockSignals(False)
            self.toggle_dminus.blockSignals(False)

        if pickers_dict is None:
            self.lbl_status.setText("❌ Lỗi đồng bộ Firebase!")
            self.lbl_status.setStyleSheet("color: #EF4444;")
            self.refresh_wms_tasks()
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
            fallback_lb = self.listboxes.get("", list(self.listboxes.values())[0])
            target_lb = self.listboxes.get(block_name, fallback_lb)

            item = QListWidgetItem("")

            prefix = ""
            if block_name == "KHO_E":
                prefix = f"[{v.get('kho_e_label', 'PT-N')}] "
            elif block_name != "":
                urg = v.get("urgent", "N")
                if urg == "Y":
                    prefix = "🔥 "
                elif urg == "A":
                    prefix = "🅰️ "
                elif urg == "S":
                    prefix = "🪼 "
                elif urg == "V":
                    prefix = "🚀 "
                elif urg == "Q":
                    prefix = "⚧️ "

            item.setText(f'{prefix}{v.get("name", "N/A")} - {v.get("wms_id", "")}')
            item.setFlags(item.flags() | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled | Qt.ItemIsEnabled)
            item.setData(Qt.UserRole, v)

            target_lb.addItem(item)

        self.update_all_badges()
        self.lbl_status.setText("✅ Đã đồng bộ Firebase thành công!")
        self.lbl_status.setStyleSheet("color: #10B981;")
        self.refresh_wms_tasks()
        self.trigger_search_update()

    def toggle_config_edit(self):
        if self.btn_edit_config.text() == "Chỉnh sửa":
            self.btn_edit_config.setText("Lưu cài đặt")
            self.btn_edit_config.setObjectName("btn_primary")
            self.btn_edit_config.style().unpolish(self.btn_edit_config)
            self.btn_edit_config.style().polish(self.btn_edit_config)
            self.txt_cfg_a.setReadOnly(False)
            self.txt_cfg_b.setReadOnly(False)
            self.txt_cfg_c.setReadOnly(False)
            self.txt_cfg_e.setReadOnly(False)
        else:
            self.btn_edit_config.setText("Chỉnh sửa")
            self.btn_edit_config.setObjectName("")
            self.btn_edit_config.style().unpolish(self.btn_edit_config)
            self.btn_edit_config.style().polish(self.btn_edit_config)
            self.txt_cfg_a.setReadOnly(True)
            self.txt_cfg_b.setReadOnly(True)
            self.txt_cfg_c.setReadOnly(True)
            self.txt_cfg_e.setReadOnly(True)
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
