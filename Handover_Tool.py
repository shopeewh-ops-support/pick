import os
import sys
import re
import csv
import json
import threading
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import requests

# Thêm hỗ trợ Pillow để xử lý icon chuẩn Windows cho cả PNG và ICO
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Hỗ trợ phát âm thanh trên Windows
try:
    import winsound
except ImportError:
    winsound = None

FIREBASE_BASE_URL = "https://inbound-scs-default-rtdb.firebaseio.com/handover.json"


def get_resource_path(relative_path: str) -> str:
    """Trả về đường dẫn thực tế của tài nguyên tương thích .exe và .py."""
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, relative_path)


SOUND_OK = get_resource_path("OK.wav")
SOUND_ERR = get_resource_path("ERR.wav")
APP_ICON = get_resource_path("GIP.png")


def play_sound_async(sound_type: str):
    """Phát âm thanh không đồng bộ trên worker thread riêng."""
    def _worker():
        if sys.platform == "win32" and winsound:
            target_path = SOUND_OK if sound_type == "ok" else SOUND_ERR
            if os.path.exists(target_path):
                try:
                    winsound.PlaySound(target_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                    return
                except Exception:
                    pass
            if sound_type == "ok":
                winsound.Beep(1200, 100)
            else:
                winsound.Beep(400, 350)
        else:
            print("\a", end="", flush=True)

    threading.Thread(target=_worker, daemon=True).start()


def detect_carrier(tracking_code: str) -> str:
    """
    Quy tắc xác định nhà vận chuyển theo chuẩn kho thực tế.
    ĐÃ LOẠI BỎ: logic nhận diện mã bắt đầu bằng 88/99 của Best Express.
    """
    code = tracking_code.strip().upper()

    # 1. Best Express (Chỉ nhận diện mã tiền tố TTVN hoặc BEST)
    if code.startswith(("TTVN", "BEST")):
        return "Best Express"

    # 2. VNPost (Chuẩn UPU 2 chữ cái + 9 số + VN, ví dụ: EA344301617VN; hoặc đầu EMS, VNP)
    if re.match(r"^[A-Z]{2}\d{9}VN$", code) or code.startswith(("EMS", "VNP")):
        return "VNPost"

    # 3. J&T Express: Bắt đầu bằng 8 và có đúng 12 chữ số thuần số (VD: 862641555308) hoặc tiền tố JNT
    if code.startswith("JNT") or re.match(r"^8\d{11}$", code):
        return "J&T Express"

    # 4. Viettel Post: SHOPEEVTP..., VTPVN..., VTP..., VT... hoặc chuỗi 10 - 11 chữ số
    if (
        code.startswith(("SHOPEEVTP", "VTPVN", "VTP", "VT"))
        or re.match(r"^\d{10,11}$", code)
    ):
        return "Viettel Post"

    # 5. Giao Hàng Nhanh (GHN) - Hỗ trợ GYELQ4PN, G8AB12, GHN...
    if code.startswith("GHN") or re.match(r"^[GE][A-Z0-9]{6,8}$", code):
        return "GHN"

    # 6. SPX Express
    if code.startswith("SPX") or re.match(r"^VN\d{10,12}[A-Z0-9]?$", code):
        return "SPX Express"

    # 7. Ninja Van
    if code.startswith(("NLEVN", "NLVN", "SHP", "NINJA")):
        return "Ninja Van"

    return "Không xác định"


def get_carrier_prefix(carrier_name: str) -> str:
    """Trả về mã viết tắt của nhà vận chuyển để đặt tên phiên."""
    mapping = {
        "Best Express": "BEST",
        "GHN": "GHN",
        "VNPost": "VNP",
        "Viettel Post": "VTP",
        "SPX Express": "SPX",
        "J&T Express": "JNT",
        "Ninja Van": "NJV"
    }
    return mapping.get(carrier_name, "LOG")


class ModernInboundApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Inbound Logistics Management - Handover Scanner")

        self._setup_app_icon()

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        target_w = min(1140, int(screen_w * 0.92))
        target_h = min(820, int(screen_h * 0.90))
        self.root.geometry(f"{target_w}x{target_h}")
        self.root.minsize(860, 600)
        self.root.configure(bg="#0f172a")

        self.locked_carrier = None
        self.current_session_id = None
        self.session_items = []
        self.session_codes_set = set()

        self.global_records = []
        self.global_codes_set = set()
        self.session_history_dict = {}

        self.is_running = True

        self._setup_modern_theme()
        self._build_ui()
        self._bind_close_event()

        self.fetch_firebase_data_async(initial_load=True)
        self._start_firebase_realtime_listener()

    def _setup_app_icon(self):
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("gip.handover.scanner.v1")
            except Exception:
                pass

        if not os.path.exists(APP_ICON):
            return

        try:
            if PIL_AVAILABLE:
                pil_img = Image.open(APP_ICON)
                self._app_icon_ref = ImageTk.PhotoImage(pil_img)
                self.root.iconphoto(True, self._app_icon_ref)

                temp_ico_path = os.path.join(os.path.dirname(APP_ICON), "_gip_temp_icon.ico")
                try:
                    if not os.path.exists(temp_ico_path):
                        pil_img.save(temp_ico_path, format="ICO",
                                     sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128)])
                    self.root.iconbitmap(temp_ico_path)
                except Exception:
                    pass
            else:
                self._app_icon_ref = tk.PhotoImage(file=APP_ICON)
                self.root.iconphoto(True, self._app_icon_ref)
        except Exception as e:
            print(f"[Icon Load Warning]: {e}")

    def _setup_modern_theme(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("TNotebook", background="#0f172a", borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background="#1e293b",
            foreground="#94a3b8",
            padding=[20, 8],
            font=("Segoe UI", 10, "bold"),
            borderwidth=0
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", "#0ea5e9")],
            foreground=[("selected", "#ffffff")]
        )

        style.configure(
            "Treeview",
            background="#1e293b",
            foreground="#f8fafc",
            fieldbackground="#1e293b",
            rowheight=30,
            font=("Segoe UI", 10),
            borderwidth=0
        )
        style.configure(
            "Treeview.Heading",
            background="#334155",
            foreground="#38bdf8",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padding=5
        )
        style.map("Treeview", background=[("selected", "#0284c7")], foreground=[("selected", "#ffffff")])

        style.configure(
            "Primary.TButton",
            background="#0d9488",
            foreground="#ffffff",
            font=("Segoe UI", 10, "bold"),
            borderwidth=0,
            padding=6
        )
        style.map("Primary.TButton", background=[("active", "#14b8a6"), ("disabled", "#475569")])

        style.configure(
            "Danger.TButton",
            background="#be123c",
            foreground="#ffffff",
            font=("Segoe UI", 9, "bold"),
            borderwidth=0,
            padding=5
        )
        style.map("Danger.TButton", background=[("active", "#e11d48")])

        style.configure(
            "Action.TButton",
            background="#2563eb",
            foreground="#ffffff",
            font=("Segoe UI", 10, "bold"),
            borderwidth=0,
            padding=6
        )
        style.map("Action.TButton", background=[("active", "#3b82f6")])

    def _build_ui(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # Tab 1: Quét bàn giao
        self.tab_scan = tk.Frame(self.notebook, bg="#0f172a")
        self.notebook.add(self.tab_scan, text="  ⚡ QUÉT BÀN GIAO  ")
        self._build_scan_view()

        # Tab 2: Tra cứu & Bộ lọc
        self.tab_history = tk.Frame(self.notebook, bg="#0f172a")
        self.notebook.add(self.tab_history, text="  🔍 TRA CỨU & BỘ LỌC  ")
        self._build_history_view()

    # ---------------- VIEW 1: QUÉT BÀN GIAO ----------------
    def _build_scan_view(self):
        # 1. Header Card
        header_card = tk.Frame(self.tab_scan, bg="#1e293b", bd=0, padx=16, pady=8)
        header_card.pack(fill="x", padx=10, pady=(6, 4))

        info_box = tk.Frame(header_card, bg="#1e293b")
        info_box.pack(side="left", fill="y")

        self.lbl_session_title = tk.Label(
            info_box,
            text="NHÀ VẬN CHUYỂN PHIÊN",
            font=("Segoe UI", 9, "bold"),
            fg="#94a3b8",
            bg="#1e293b"
        )
        self.lbl_session_title.pack(anchor="w")

        self.lbl_session_carrier = tk.Label(
            info_box,
            text="CHƯA KHÓA (QUÉT ĐƠN ĐẦU TIÊN ĐỂ KHÓA HÃNG)",
            font=("Segoe UI", 13, "bold"),
            fg="#f59e0b",
            bg="#1e293b"
        )
        self.lbl_session_carrier.pack(anchor="w", pady=(2, 0))

        btn_reset = ttk.Button(
            header_card,
            text="Làm Mới Phiên",
            style="Danger.TButton",
            command=self.reset_session
        )
        btn_reset.pack(side="right", padx=5)

        # 2. Main KPI Box
        kpi_card = tk.Frame(self.tab_scan, bg="#111827", bd=1, relief="solid")
        kpi_card.pack(fill="x", padx=10, pady=4)

        tk.Label(
            kpi_card,
            text="TỔNG SỐ KIỆN TRONG PHIÊN NÀY",
            font=("Segoe UI", 9, "bold"),
            fg="#64748b",
            bg="#111827"
        ).pack(pady=(4, 0))

        self.lbl_big_counter = tk.Label(
            kpi_card,
            text="0",
            font=("Segoe UI", 40, "bold"),
            fg="#38bdf8",
            bg="#111827"
        )
        self.lbl_big_counter.pack(pady=(0, 4))

        # 3. Barcode Input Card (Quét nhận đơn)
        input_card = tk.Frame(self.tab_scan, bg="#1e293b", padx=16, pady=6)
        input_card.pack(fill="x", padx=10, pady=3)

        tk.Label(
            input_card,
            text="MÃ VẬN ĐƠN:",
            font=("Segoe UI", 11, "bold"),
            fg="#f8fafc",
            bg="#1e293b"
        ).pack(side="left", padx=(0, 10))

        self.entry_barcode = tk.Entry(
            input_card,
            font=("Consolas", 14, "bold"),
            bg="#0f172a",
            fg="#38bdf8",
            insertbackground="#38bdf8",
            relief="flat",
            bd=5
        )
        self.entry_barcode.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.entry_barcode.bind("<Return>", self.handle_scan)
        self.entry_barcode.focus()

        self.btn_scan = ttk.Button(
            input_card,
            text="Ghi Nhận (Enter)",
            style="Action.TButton",
            command=self.handle_scan
        )
        self.btn_scan.pack(side="left")

        # 4. Remove Input Card (Tìm & Xóa đơn scan nhầm trong phiên)
        remove_card = tk.Frame(self.tab_scan, bg="#1e293b", padx=16, pady=6)
        remove_card.pack(fill="x", padx=10, pady=3)

        tk.Label(
            remove_card,
            text="TÌM & XÓA ĐƠN NHẦM:",
            font=("Segoe UI", 10, "bold"),
            fg="#f43f5e",
            bg="#1e293b"
        ).pack(side="left", padx=(0, 10))

        self.entry_remove_code = tk.Entry(
            remove_card,
            font=("Consolas", 12, "bold"),
            bg="#0f172a",
            fg="#fb7185",
            insertbackground="#fb7185",
            relief="flat",
            bd=4
        )
        self.entry_remove_code.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.entry_remove_code.bind("<Return>", self.handle_find_and_remove)

        self.btn_remove = ttk.Button(
            remove_card,
            text="Xóa Mã Này (Enter)",
            style="Danger.TButton",
            command=self.handle_find_and_remove
        )
        self.btn_remove.pack(side="left")

        # 5. Table Card
        table_card = tk.Frame(self.tab_scan, bg="#1e293b", padx=8, pady=6)
        table_card.pack(fill="both", expand=True, padx=10, pady=4)

        columns = ("stt", "code", "carrier", "scanned_at")
        self.tree_scan = ttk.Treeview(table_card, columns=columns, show="headings", selectmode="browse")

        self.tree_scan.heading("stt", text="STT")
        self.tree_scan.heading("code", text="MÃ VẬN ĐƠN (Double click để xóa trực tiếp)")
        self.tree_scan.heading("carrier", text="NHÀ VẬN CHUYỂN")
        self.tree_scan.heading("scanned_at", text="THỜI GIAN QUÉT")

        self.tree_scan.column("stt", width=60, anchor="center")
        self.tree_scan.column("code", width=280, anchor="w")
        self.tree_scan.column("carrier", width=180, anchor="w")
        self.tree_scan.column("scanned_at", width=200, anchor="center")

        scroll_y = ttk.Scrollbar(table_card, orient="vertical", command=self.tree_scan.yview)
        self.tree_scan.configure(yscrollcommand=scroll_y.set)

        self.tree_scan.pack(side="left", fill="both", expand=True)
        scroll_y.pack(side="right", fill="y")

        self.tree_scan.bind("<Double-1>", self.on_item_double_click_delete)
        self.tree_scan.bind("<Delete>", self.on_item_double_click_delete)

        # 6. Bottom Action & Status Bar
        bottom_bar = tk.Frame(self.tab_scan, bg="#0f172a", padx=10, pady=6)
        bottom_bar.pack(fill="x")

        self.lbl_status = tk.Label(
            bottom_bar,
            text="Hệ thống sẵn sàng. Vui lòng quét đơn hàng đầu tiên.",
            font=("Segoe UI", 10),
            fg="#94a3b8",
            bg="#0f172a",
            anchor="w"
        )
        self.lbl_status.pack(side="left", fill="x", expand=True)

        self.btn_done = ttk.Button(
            bottom_bar,
            text="✔ HOÀN TẤT & BẮT ĐẦU PHIÊN MỚI (DONE)",
            style="Primary.TButton",
            command=self.confirm_and_submit
        )
        self.btn_done.pack(side="right", ipady=4, ipadx=12)

    def generate_next_session_id(self, carrier: str) -> str:
        date_str = datetime.now().strftime("%Y%m%d")
        carrier_prefix = get_carrier_prefix(carrier)
        prefix_pattern = f"HO_{carrier_prefix}_{date_str}_S"

        existing_nums = []
        for s_id in self.session_history_dict.keys():
            if s_id.startswith(prefix_pattern):
                suffix = s_id.replace(prefix_pattern, "")
                if suffix.isdigit():
                    existing_nums.append(int(suffix))

        next_idx = max(existing_nums, default=0) + 1
        return f"{prefix_pattern}{next_idx:02d}"

    def handle_scan(self, event=None):
        raw_code = self.entry_barcode.get().strip()
        self.entry_barcode.delete(0, tk.END)

        if not raw_code:
            return

        code = raw_code.upper()

        if code in self.session_codes_set:
            play_sound_async("err")
            self.lbl_status.config(
                text=f"❌ BỎ QUA: Mã [{code}] ĐÃ ĐƯỢC QUÉT TRONG PHIÊN NÀY!",
                fg="#f43f5e"
            )
            self.entry_barcode.focus()
            return

        if code in self.global_codes_set:
            play_sound_async("err")
            self.lbl_status.config(
                text=f"❌ BỎ QUA: Mã [{code}] ĐÃ TỒN TẠI TRONG CƠ SỞ DỮ LIỆU TỔNG!",
                fg="#f43f5e"
            )
            self.entry_barcode.focus()
            return

        carrier = detect_carrier(code)

        if carrier == "Không xác định":
            play_sound_async("err")
            self.lbl_status.config(
                text=f"❌ BỎ QUA: Không nhận diện được nhà vận chuyển cho mã [{code}]!",
                fg="#f43f5e"
            )
            self.entry_barcode.focus()
            return

        if self.locked_carrier is None:
            self.locked_carrier = carrier
            self.current_session_id = self.generate_next_session_id(carrier)
            self.lbl_session_title.config(text=f"PHIÊN BÀN GIAO: {self.current_session_id}")
            self.lbl_session_carrier.config(
                text=f"ĐÃ KHÓA: {self.locked_carrier.upper()}",
                fg="#38bdf8"
            )

        if carrier != self.locked_carrier:
            play_sound_async("err")
            self.lbl_status.config(
                text=f"❌ BỎ QUA: Mã [{code}] thuộc [{carrier}], không khớp phiên [{self.locked_carrier}]!",
                fg="#f43f5e"
            )
            self.entry_barcode.focus()
            return

        play_sound_async("ok")
        scan_time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        stt = len(self.session_items) + 1

        item = {
            "stt": stt,
            "tracking_code": code,
            "carrier": carrier,
            "scanned_at": scan_time
        }

        self.session_items.append(item)
        self.session_codes_set.add(code)
        self.global_codes_set.add(code)

        self.tree_scan.insert("", 0, values=(stt, code, carrier, scan_time))
        self.lbl_big_counter.config(text=str(len(self.session_items)))
        self.lbl_status.config(
            text=f"✔ Đã nhận kiện #{stt}: [{code}] - {carrier}",
            fg="#10b981"
        )
        self.entry_barcode.focus()

    def _execute_remove_code(self, code_to_remove: str) -> bool:
        """Hàm dùng chung để loại bỏ một mã vận đơn ra khỏi phiên hiện tại."""
        code_to_remove = code_to_remove.strip().upper()
        if code_to_remove not in self.session_codes_set:
            return False

        # 1. Loại bỏ khỏi cấu trúc dữ liệu phiên
        self.session_items = [it for it in self.session_items if it.get("tracking_code", "").upper() != code_to_remove]
        self.session_codes_set.discard(code_to_remove)
        self.global_codes_set.discard(code_to_remove)

        # 2. Xóa khỏi bảng Treeview
        for child_id in self.tree_scan.get_children():
            row_vals = self.tree_scan.item(child_id, "values")
            if row_vals and len(row_vals) >= 2 and str(row_vals[1]).strip().upper() == code_to_remove:
                self.tree_scan.delete(child_id)
                break

        # 3. Đánh lại số thứ tự từ 1..N
        current_children = self.tree_scan.get_children()
        total_left = len(current_children)
        for idx, child_id in enumerate(reversed(current_children), 1):
            vals = list(self.tree_scan.item(child_id, "values"))
            vals[0] = str(idx)
            self.tree_scan.item(child_id, values=vals)

        # 4. Cập nhật bộ đếm lớn
        self.lbl_big_counter.config(text=str(total_left))

        # 5. Nếu xóa hết kiện thì mở khóa lại hãng
        if total_left == 0:
            self.locked_carrier = None
            self.current_session_id = None
            self.lbl_session_title.config(text="NHÀ VẬN CHUYỂN PHIÊN")
            self.lbl_session_carrier.config(
                text="CHƯA KHÓA (QUÉT ĐƠN ĐẦU TIÊN ĐỂ KHÓA HÃNG)",
                fg="#f59e0b"
            )
            self.lbl_status.config(
                text="Đã xóa toàn bộ đơn. Phiên đã được mở khóa, sẵn sàng quét lại.",
                fg="#94a3b8"
            )
        else:
            self.lbl_status.config(
                text=f"✔ ĐÃ XÓA MÃ [{code_to_remove}] KHỎI PHIÊN! Số lượng còn lại: {total_left}",
                fg="#f59e0b"
            )
        return True

    def handle_find_and_remove(self, event=None):
        """Tìm và xóa mã đơn theo giá trị nhập từ ô tìm kiếm xóa nhầm."""
        target_code = self.entry_remove_code.get().strip().upper()
        self.entry_remove_code.delete(0, tk.END)

        if not target_code:
            return

        removed = self._execute_remove_code(target_code)
        if not removed:
            play_sound_async("err")
            self.lbl_status.config(
                text=f"❌ KHÔNG TÌM THẤY mã [{target_code}] trong phiên quét hiện tại!",
                fg="#f43f5e"
            )
        else:
            play_sound_async("ok")

        # Focus lại ô quét chính để nhân viên tiếp tục bắn đơn
        self.entry_barcode.focus()

    def on_item_double_click_delete(self, event=None):
        """Xóa mã đơn được chọn trực tiếp trên Treeview."""
        selected_item = self.tree_scan.selection()
        if not selected_item:
            return

        row_vals = self.tree_scan.item(selected_item[0], "values")
        if not row_vals or len(row_vals) < 2:
            return

        code_to_remove = str(row_vals[1]).strip().upper()
        self._execute_remove_code(code_to_remove)
        self.entry_barcode.focus()

    def confirm_and_submit(self):
        if not self.session_items:
            self.lbl_status.config(text="⚠️ Chưa có kiện hàng nào trong phiên hiện tại để hoàn tất!", fg="#f59e0b")
            return

        session_id = self.current_session_id
        carrier = self.locked_carrier
        items_to_save = list(self.session_items)
        completed_at = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

        self.reset_session()
        self.lbl_status.config(
            text=f"✔ Đang lưu phiên [{session_id}] ({len(items_to_save)} kiện) lên Firebase...",
            fg="#38bdf8"
        )

        threading.Thread(
            target=self._push_to_firebase_worker,
            args=(session_id, carrier, items_to_save, completed_at),
            daemon=True
        ).start()

    def _push_to_firebase_worker(self, session_id: str, carrier: str, items: list, completed_at: str):
        payload = {
            "session_id": session_id,
            "carrier": carrier,
            "total_packages": len(items),
            "completed_at": completed_at,
            "items": items
        }

        success = False
        error_msg = ""
        try:
            res = requests.post(FIREBASE_BASE_URL, json=payload, timeout=12)
            if res.status_code in (200, 201):
                success = True
            else:
                error_msg = f"HTTP {res.status_code}: {res.text}"
        except Exception as e:
            error_msg = str(e)

        self.root.after(0, self._on_push_finished, success, session_id, len(items), error_msg)

    def _on_push_finished(self, success: bool, session_id: str, count: int, error_msg: str):
        if success:
            self.lbl_status.config(
                text=f"✔ Đã lưu thành công phiên [{session_id}] ({count} kiện) lên Firebase!",
                fg="#10b981"
            )
            self.fetch_firebase_data_async(initial_load=True)
        else:
            self.lbl_status.config(
                text=f"⚠️ Lưu Firebase thất bại ({error_msg}). Vui lòng kiểm tra lại kết nối mạng!",
                fg="#f43f5e"
            )

    def reset_session(self):
        self.locked_carrier = None
        self.current_session_id = None
        self.session_items.clear()
        self.session_codes_set.clear()

        for row in self.tree_scan.get_children():
            self.tree_scan.delete(row)

        self.lbl_session_title.config(text="NHÀ VẬN CHUYỂN PHIÊN")
        self.lbl_session_carrier.config(
            text="CHƯA KHÓA (QUÉT ĐƠN ĐẦU TIÊN ĐỂ KHÓA HÃNG)",
            fg="#f59e0b"
        )
        self.lbl_big_counter.config(text="0")
        self.lbl_status.config(
            text="Phiên quét đã được làm mới. Sẵn sàng cho lượt bàn giao tiếp theo.",
            fg="#94a3b8"
        )
        self.entry_barcode.delete(0, tk.END)
        self.entry_remove_code.delete(0, tk.END)
        self.entry_barcode.focus()

    # ---------------- VIEW 2: TRA CỨU & BỘ LỌC ----------------
    def _build_history_view(self):
        filter_card = tk.Frame(self.tab_history, bg="#1e293b", padx=16, pady=10)
        filter_card.pack(fill="x", padx=10, pady=8)

        f1 = tk.Frame(filter_card, bg="#1e293b")
        f1.grid(row=0, column=0, padx=6, pady=4, sticky="w")
        tk.Label(f1, text="MÃ VẬN ĐƠN", font=("Segoe UI", 8, "bold"), fg="#94a3b8", bg="#1e293b").pack(anchor="w")
        self.entry_search_code = tk.Entry(f1, font=("Consolas", 11), bg="#0f172a", fg="#f8fafc",
                                          insertbackground="#fff", width=20)
        self.entry_search_code.pack()
        self.entry_search_code.bind("<KeyRelease>", lambda e: self.apply_filters())

        f2 = tk.Frame(filter_card, bg="#1e293b")
        f2.grid(row=0, column=1, padx=6, pady=4, sticky="w")
        tk.Label(f2, text="NHÀ VẬN CHUYỂN", font=("Segoe UI", 8, "bold"), fg="#94a3b8", bg="#1e293b").pack(anchor="w")
        self.cb_filter_carrier = ttk.Combobox(
            f2,
            values=["Tất cả", "Best Express", "GHN", "Viettel Post", "VNPost", "SPX Express", "J&T Express", "Ninja Van"],
            state="readonly",
            width=16
        )
        self.cb_filter_carrier.set("Tất cả")
        self.cb_filter_carrier.pack()
        self.cb_filter_carrier.bind("<<ComboboxSelected>>", lambda e: self.apply_filters())

        f3 = tk.Frame(filter_card, bg="#1e293b")
        f3.grid(row=0, column=2, padx=6, pady=4, sticky="w")
        tk.Label(f3, text="NGÀY QUÉT (YYYY/MM/DD)", font=("Segoe UI", 8, "bold"), fg="#94a3b8", bg="#1e293b").pack(anchor="w")
        self.entry_filter_date = tk.Entry(f3, font=("Consolas", 11), bg="#0f172a", fg="#f8fafc",
                                          insertbackground="#fff", width=16)
        self.entry_filter_date.pack()
        self.entry_filter_date.bind("<KeyRelease>", lambda e: self.apply_filters())

        btn_box = tk.Frame(filter_card, bg="#1e293b")
        btn_box.grid(row=0, column=3, padx=10, pady=4, sticky="e")

        btn_clear = ttk.Button(btn_box, text="Xóa Lọc", command=self.clear_filters)
        btn_clear.pack(side="left", padx=3)

        btn_refresh = ttk.Button(
            btn_box,
            text="🔄 Làm Mới Data",
            style="Action.TButton",
            command=lambda: self.fetch_firebase_data_async(initial_load=False)
        )
        btn_refresh.pack(side="left", padx=3)

        btn_export_excel = ttk.Button(
            btn_box,
            text="📊 Xuất Excel (CSV)",
            style="Primary.TButton",
            command=self.export_filtered_to_excel
        )
        btn_export_excel.pack(side="left", padx=3)

        table_card = tk.Frame(self.tab_history, bg="#1e293b", padx=8, pady=6)
        table_card.pack(fill="both", expand=True, padx=10, pady=6)

        cols = ("session_id", "code", "carrier", "scanned_at", "completed_at")
        self.tree_history = ttk.Treeview(table_card, columns=cols, show="headings", selectmode="browse")

        self.tree_history.heading("session_id", text="MÃ PHIÊN")
        self.tree_history.heading("code", text="MÃ VẬN ĐƠN")
        self.tree_history.heading("carrier", text="NHÀ VẬN CHUYỂN")
        self.tree_history.heading("scanned_at", text="THỜI GIAN QUÉT")
        self.tree_history.heading("completed_at", text="HOÀN TẤT PHIÊN")

        self.tree_history.column("session_id", width=180, anchor="w")
        self.tree_history.column("code", width=220, anchor="w")
        self.tree_history.column("carrier", width=150, anchor="w")
        self.tree_history.column("scanned_at", width=170, anchor="center")
        self.tree_history.column("completed_at", width=170, anchor="center")

        scroll_y = ttk.Scrollbar(table_card, orient="vertical", command=self.tree_history.yview)
        self.tree_history.configure(yscrollcommand=scroll_y.set)

        self.tree_history.pack(side="left", fill="both", expand=True)
        scroll_y.pack(side="right", fill="y")

        self.lbl_history_summary = tk.Label(
            self.tab_history,
            text="Tổng tìm thấy: 0 đơn",
            font=("Segoe UI", 9, "bold"),
            fg="#94a3b8",
            bg="#0f172a",
            anchor="w",
            padx=10,
            pady=4
        )
        self.lbl_history_summary.pack(fill="x", side="bottom")

    def export_filtered_to_excel(self):
        rows = self.tree_history.get_children()
        if not rows:
            self.lbl_history_summary.config(
                text="⚠️ Không có dữ liệu đơn hàng nào để xuất file!",
                fg="#f43f5e"
            )
            return

        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        carrier_filter = self.cb_filter_carrier.get().strip()
        carrier_tag = carrier_filter if carrier_filter != "Tất cả" else "ALL"
        default_filename = f"Danh_Sach_Ban_Giao_{carrier_tag}_{now_str}.csv"

        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV (Excel) File", "*.csv"), ("Tất cả tập tin", "*.*")],
            initialfile=default_filename,
            title="Lưu File Excel / CSV Bàn Giao"
        )
        if not filepath:
            return

        try:
            with open(filepath, mode="w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["STT", "Mã Phiên", "Mã Vận Đơn", "Nhà Vận Chuyển", "Thời Gian Quét", "Thời Gian Hoàn Tất Phiên"])
                for idx, row_id in enumerate(rows, 1):
                    vals = self.tree_history.item(row_id, "values")
                    writer.writerow([idx, vals[0], vals[1], vals[2], vals[3], vals[4]])

            self.lbl_history_summary.config(
                text=f"✔ Đã xuất {len(rows)} đơn ra file: {os.path.basename(filepath)}",
                fg="#10b981"
            )
        except Exception as e:
            self.lbl_history_summary.config(
                text=f"❌ Lỗi khi lưu file Excel: {e}",
                fg="#f43f5e"
            )

    def apply_filters(self):
        search_code = self.entry_search_code.get().strip().upper()
        carrier_filter = self.cb_filter_carrier.get().strip()
        date_filter = self.entry_filter_date.get().strip()

        for item in self.tree_history.get_children():
            self.tree_history.delete(item)

        matched_count = 0
        for rec in reversed(self.global_records):
            code = rec["tracking_code"]
            carrier = rec["carrier"]
            scanned_at = rec["scanned_at"]
            completed_at = rec.get("completed_at", "")
            s_id = rec.get("session_id", "")

            if search_code and search_code not in code:
                continue

            if carrier_filter != "Tất cả" and carrier.upper() != carrier_filter.upper():
                continue

            if date_filter and not scanned_at.startswith(date_filter):
                continue

            self.tree_history.insert("", "end", values=(s_id, code, carrier, scanned_at, completed_at))
            matched_count += 1

        self.lbl_history_summary.config(
            text=f"Tổng tìm thấy: {matched_count} đơn hàng thỏa mãn điều kiện lọc."
        )

    def clear_filters(self):
        self.entry_search_code.delete(0, tk.END)
        self.cb_filter_carrier.set("Tất cả")
        self.entry_filter_date.delete(0, tk.END)
        self.apply_filters()

    # ---------------- DỮ LIỆU TỔNG & FIREBASE REALTIME ----------------
    def fetch_firebase_data_async(self, initial_load=False):
        def _fetch():
            new_records = []
            new_codes_set = set()
            new_session_dict = {}

            try:
                res = requests.get(FIREBASE_BASE_URL, timeout=10)
                if res.status_code == 200 and res.text != "null":
                    data = res.json() or {}
                    for _, session in data.items():
                        if not isinstance(session, dict):
                            continue
                        s_id = session.get("session_id", "")
                        carrier = session.get("carrier", "")
                        comp_time = session.get("completed_at", "")
                        items = session.get("items", [])

                        if s_id:
                            new_session_dict[s_id] = {
                                "carrier": carrier,
                                "completed_at": comp_time,
                                "items": items
                            }

                        for item in items:
                            c = item.get("tracking_code", "").strip().upper()
                            if c:
                                new_records.append({
                                    "session_id": s_id,
                                    "tracking_code": c,
                                    "carrier": carrier,
                                    "scanned_at": item.get("scanned_at", ""),
                                    "completed_at": comp_time
                                })
                                new_codes_set.add(c)
            except Exception as e:
                print(f"[Firebase Fetch Warning]: {e}")

            self.root.after(0, self._update_global_cache, new_records, new_codes_set, new_session_dict, initial_load)

        threading.Thread(target=_fetch, daemon=True).start()

    def _update_global_cache(self, records, codes_set, session_dict, initial_load):
        self.global_records = records
        self.global_codes_set = codes_set
        self.session_history_dict = session_dict
        self.apply_filters()
        if not initial_load:
            self.lbl_history_summary.config(
                text=f"✔ Đã đồng bộ thành công {len(records)} đơn hàng từ Firebase!",
                fg="#10b981"
            )

    def _start_firebase_realtime_listener(self):
        def _sse_listener():
            headers = {"Accept": "text/event-stream"}
            while self.is_running:
                try:
                    with requests.get(FIREBASE_BASE_URL, headers=headers, stream=True, timeout=90) as stream_res:
                        for line in stream_res.iter_lines(decode_unicode=True):
                            if not self.is_running:
                                break
                            if not line:
                                continue
                            if line.startswith("event:"):
                                event_type = line.split(":", 1)[1].strip()
                                if event_type in ("put", "patch"):
                                    self.root.after(100, lambda: self.fetch_firebase_data_async(initial_load=True))
                except Exception:
                    import time
                    time.sleep(5)

        listener_thread = threading.Thread(target=_sse_listener, daemon=True)
        listener_thread.start()

    # ---------------- BẢO VỆ CHẶN THOÁT KHI CHƯA DONE ----------------
    def _bind_close_event(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close_attempt)

    def _on_close_attempt(self):
        if self.session_items:
            confirm = messagebox.askyesno(
                "CẢNH BÁO CHƯA LƯU DỮ LIỆU!",
                f"Hiện tại đang có {len(self.session_items)} kiện hàng chưa được bấm [HOÀN TẤT PHIÊN]!\n\n"
                f"Nếu bạn thoát bây giờ, các kiện này sẽ CHƯA ĐƯỢC ĐẨY LÊN HỆ THỐNG.\n"
                f"Bạn có chắc chắn muốn bỏ phiên này và thoát không?",
                icon="warning"
            )
            if not confirm:
                return

        self.is_running = False
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = ModernInboundApp(root)
    root.mainloop()