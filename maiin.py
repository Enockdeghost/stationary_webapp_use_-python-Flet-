#!/usr/bin/env python3
"""
Uptown Stationery — Responsive Web App (Flet)
Secure edition with mobile-first responsive design.
"""

import flet as ft
import sqlite3
import hashlib
import hmac as _hmac
import secrets
import csv
import os
import re
import shutil
import time
from datetime import datetime, timedelta
from functools import partial
from collections import defaultdict

# ── Constants ──────────────────────────────────────────────────────────────────
DB_FILE            = "stationery.db"
BACKUP_DIR         = "backups"
MOBILE_BREAKPOINT  = 700        # px — below this → mobile layout
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_SECONDS    = 300        # 5 min lockout after too many failures

# ─────────────────────────────────────────────────────────────────────────────
#  SECURITY HELPERS
# ─────────────────────────────────────────────────────────────────────────────

# ── Rate Limiting ─────────────────────────────────────────────────────────────
_login_attempts: dict[str, list[float]] = defaultdict(list)

def check_rate_limit(username: str) -> tuple[bool, int]:
    key  = f"login:{username.lower().strip()}"
    now  = time.time()
    _login_attempts[key] = [t for t in _login_attempts[key] if now - t < LOCKOUT_SECONDS]
    if len(_login_attempts[key]) >= MAX_LOGIN_ATTEMPTS:
        remaining = int(LOCKOUT_SECONDS - (now - min(_login_attempts[key])))
        return False, remaining
    return True, 0

def record_failed_attempt(username: str):
    _login_attempts[f"login:{username.lower().strip()}"].append(time.time())

def clear_failed_attempts(username: str):
    _login_attempts.pop(f"login:{username.lower().strip()}", None)

# ── Password Hashing (PBKDF2 + legacy SHA-256 fallback) ──────────────────────
def hash_password(pwd: str) -> str:
    """PBKDF2-HMAC-SHA256 with random salt.  Format: pbkdf2:<salt_hex>:<dk_hex>"""
    salt = secrets.token_hex(16)
    dk   = hashlib.pbkdf2_hmac("sha256", pwd.encode(), salt.encode(), 200_000)
    return f"pbkdf2:{salt}:{dk.hex()}"

def _sha256(pwd: str) -> str:
    return hashlib.sha256(pwd.encode()).hexdigest()

def verify_password(pwd: str, stored: str) -> bool:
    if stored.startswith("pbkdf2:"):
        try:
            _, salt, dk_stored = stored.split(":", 2)
            dk = hashlib.pbkdf2_hmac("sha256", pwd.encode(), salt.encode(), 200_000)
            return _hmac.compare_digest(dk.hex(), dk_stored)
        except Exception:
            return False
    return _hmac.compare_digest(_sha256(pwd), stored)  # legacy

def upgrade_hash_if_legacy(user_id: int, pwd: str, stored: str):
    if not stored.startswith("pbkdf2:"):
        conn = sqlite3.connect(DB_FILE)
        conn.execute("UPDATE users SET password_hash=? WHERE id=?",
                     (hash_password(pwd), user_id))
        conn.commit()
        conn.close()

def validate_password_strength(pwd: str) -> str | None:
    if not pwd or len(pwd) < 6:
        return "Password must be at least 6 characters"
    if not re.search(r"[A-Za-z]", pwd):
        return "Must include at least one letter"
    if not re.search(r"[0-9]", pwd):
        return "Must include at least one digit"
    return None

# ── Input Sanitization ────────────────────────────────────────────────────────
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

def sanitize(text: str | None, max_len: int = 500) -> str:
    if not text:
        return ""
    return _CTRL.sub("", str(text))[:max_len].strip()

def safe_float(val, default=0.0, lo=0.0, hi=1e9) -> float:
    try:
        return max(lo, min(hi, float(val or default)))
    except (ValueError, TypeError):
        return default

def safe_int(val, default=0, lo=0, hi=10_000_000) -> int:
    try:
        return max(lo, min(hi, int(float(val or default))))
    except (ValueError, TypeError):
        return default

# ─────────────────────────────────────────────────────────────────────────────
#  DATABASE
# ─────────────────────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL,
        full_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS suppliers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, contact_person TEXT, phone TEXT, email TEXT, address TEXT
    );
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, category TEXT,
        quantity INTEGER DEFAULT 0, price REAL DEFAULT 0.0, cost_price REAL DEFAULT 0.0,
        low_stock_threshold INTEGER DEFAULT 5, supplier_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
    );
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, phone TEXT, email TEXT,
        loyalty_points INTEGER DEFAULT 0, total_spent REAL DEFAULT 0.0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sale_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        customer_id INTEGER, subtotal REAL, discount REAL DEFAULT 0,
        tax REAL DEFAULT 0, total REAL, payment_method TEXT, user_id INTEGER,
        FOREIGN KEY (customer_id) REFERENCES customers(id),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS sale_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sale_id INTEGER, item_id INTEGER, quantity INTEGER,
        price_at_sale REAL, total REAL,
        FOREIGN KEY (sale_id) REFERENCES sales(id),
        FOREIGN KEY (item_id) REFERENCES items(id)
    );
    CREATE TABLE IF NOT EXISTS purchase_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        supplier_id INTEGER NOT NULL,
        order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expected_date DATE, status TEXT DEFAULT 'pending',
        total_cost REAL DEFAULT 0.0, created_by INTEGER, notes TEXT,
        FOREIGN KEY (supplier_id) REFERENCES suppliers(id),
        FOREIGN KEY (created_by) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS po_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        po_id INTEGER NOT NULL, item_id INTEGER NOT NULL,
        quantity_ordered INTEGER NOT NULL, quantity_received INTEGER DEFAULT 0,
        cost_price REAL NOT NULL,
        FOREIGN KEY (po_id) REFERENCES purchase_orders(id),
        FOREIGN KEY (item_id) REFERENCES items(id)
    );
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, action TEXT, details TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS stock_adjustments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id INTEGER NOT NULL, quantity_before INTEGER NOT NULL,
        quantity_change INTEGER NOT NULL, quantity_after INTEGER NOT NULL,
        reason TEXT, user_id INTEGER,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (item_id) REFERENCES items(id),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT NOT NULL, description TEXT NOT NULL, amount REAL NOT NULL,
        expense_date DATE DEFAULT CURRENT_DATE, user_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS promotions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, code TEXT UNIQUE, promo_type TEXT NOT NULL,
        value REAL NOT NULL, min_purchase REAL DEFAULT 0,
        start_date DATE, end_date DATE, active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    # Seed default users (legacy SHA-256 — upgraded to PBKDF2 on first login)
    for u, p, r, fn in [
        ("admin",  _sha256("admin123"),  "admin",  "Administrator"),
        ("seller", _sha256("seller123"), "seller", "Sales Person"),
    ]:
        c.execute("INSERT OR IGNORE INTO users (username,password_hash,role,full_name) VALUES (?,?,?,?)",
                  (u, p, r, fn))
    for k, v in [
        ("categories", "Pens,Notebooks,Art Supplies,Office Equipment,Other"),
        ("store_name",  "Uptown Stationery"),
        ("tax_rate",    "0"),
        ("dark_mode",   "false"),
        ("currency",    "USD"),
    ]:
        c.execute("INSERT OR IGNORE INTO settings (key,value) VALUES (?,?)", (k, v))
    conn.commit()
    conn.close()

init_db()

def log_audit(user_id: int, action: str, details: str = ""):
    conn = sqlite3.connect(DB_FILE)
    conn.execute("INSERT INTO audit_log (user_id,action,details) VALUES (?,?,?)",
                 (user_id, action, details))
    conn.commit()
    conn.close()

def get_setting(key: str, default: str = "") -> str:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key: str, value: str):
    conn = sqlite3.connect(DB_FILE)
    conn.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)", (key, value))
    conn.commit()
    conn.close()

def currency_symbol() -> str:
    return {"USD": "$", "EUR": "€", "GBP": "£", "TZS": "TSh", "KES": "KSh"}.get(
        get_setting("currency", "USD"), "$")


# ─────────────────────────────────────────────────────────────────────────────
#  LOGIN PAGE  (with rate limiting + lockout countdown)
# ─────────────────────────────────────────────────────────────────────────────
class LoginPage(ft.Container):
    def __init__(self, on_login_success):
        super().__init__(expand=True)
        self.on_login_success = on_login_success

        self.username_field = ft.TextField(
            label="Username", width=320, height=55, border_radius=10,
            prefix_icon=ft.Icons.PERSON, on_submit=self.do_login,
        )
        self.password_field = ft.TextField(
            label="Password", password=True, can_reveal_password=True,
            width=320, height=55, border_radius=10,
            prefix_icon=ft.Icons.LOCK, on_submit=self.do_login,
        )
        self.error_text = ft.Text("", color=ft.Colors.RED_400, size=13)
        self.login_btn  = ft.ElevatedButton(
            "Login", width=320, height=50,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=10),
                bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE,
            ),
            on_click=self.do_login,
        )

        store_name = get_setting("store_name", "Uptown Stationery")
        self.content = ft.Container(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.STORE_MALL_DIRECTORY, size=80, color=ft.Colors.BLUE_700),
                        ft.Text(store_name, size=28, weight=ft.FontWeight.BOLD,
                                text_align=ft.TextAlign.CENTER),
                        ft.Text("Professional Management System", size=15,
                                color=ft.Colors.GREY_600, text_align=ft.TextAlign.CENTER),
                        ft.Container(height=8),
                        self.username_field,
                        self.password_field,
                        self.error_text,
                        self.login_btn,
                        ft.Container(height=4),
                        ft.Text("Default: admin / admin123  •  seller / seller123",
                                size=11, color=ft.Colors.GREY_400,
                                text_align=ft.TextAlign.CENTER),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=14,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                padding=40, border_radius=16, bgcolor=ft.Colors.WHITE,
                shadow=ft.BoxShadow(blur_radius=20, color=ft.Colors.BLACK12,
                                    offset=ft.Offset(0, 4)),
                width=420,
            ),
            expand=True, alignment=ft.Alignment(0, 0),
        )

    def do_login(self, e):
        user = sanitize(self.username_field.value or "")
        pwd  = (self.password_field.value or "").strip()

        if not user or not pwd:
            self.error_text.value = "Please enter username and password"
            self.update()
            return

        # Rate limit check
        allowed, secs = check_rate_limit(user)
        if not allowed:
            mins = secs // 60
            self.error_text.value = (
                f"Too many failed attempts. Try again in {mins}m {secs % 60}s."
            )
            self.login_btn.disabled = True
            self.update()
            return

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id,password_hash,role FROM users WHERE username=?", (user,))
        row = c.fetchone()
        conn.close()

        if row and verify_password(pwd, row[1]):
            clear_failed_attempts(user)
            upgrade_hash_if_legacy(row[0], pwd, row[1])
            log_audit(row[0], "LOGIN", f"User {user} logged in")
            self.on_login_success(row[0], user, row[2])
        else:
            record_failed_attempt(user)
            remaining_allowed, _ = check_rate_limit(user)
            # Count remaining attempts
            attempts_left = MAX_LOGIN_ATTEMPTS - len(
                [t for t in _login_attempts.get(f"login:{user.lower()}", [])
                 if time.time() - t < LOCKOUT_SECONDS]
            )
            if attempts_left <= 0:
                self.error_text.value = f"Account locked for {LOCKOUT_SECONDS//60} minutes."
                self.login_btn.disabled = True
            else:
                self.error_text.value = (
                    f"Invalid username or password. "
                    f"{attempts_left} attempt(s) remaining."
                )
            self.update()


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN APPLICATION
# ─────────────────────────────────────────────────────────────────────────────
class StationeryApp(ft.Container):
    def __init__(self, user_id: int, username: str, role: str):
        super().__init__(expand=True)
        self.user_id    = user_id
        self.username   = username
        self.role       = role
        self.cart_items: list[dict] = []
        self.pos_results_container  = None
        self._build_ui()

    # ── Layout building ───────────────────────────────────────────────────────
    def _build_ui(self):
        is_admin = (self.role == "admin")

        dest_pairs = [
            (ft.Icons.DASHBOARD,       "Dashboard"),
            (ft.Icons.INVENTORY_2,     "Inventory"),
            (ft.Icons.POINT_OF_SALE,   "Sales"),
            (ft.Icons.HISTORY,         "History"),
            (ft.Icons.ANALYTICS,       "Reports"),
        ]
        if is_admin:
            dest_pairs += [
                (ft.Icons.TUNE,                   "Stock Adj."),
                (ft.Icons.ACCOUNT_BALANCE_WALLET, "Expenses"),
                (ft.Icons.LOCAL_OFFER,            "Promos"),
                (ft.Icons.LOCAL_SHIPPING,         "Suppliers"),
                (ft.Icons.SHOPPING_CART,          "Purchasing"),
                (ft.Icons.GROUP,                  "Customers"),
                (ft.Icons.PEOPLE,                 "Users"),
                (ft.Icons.SETTINGS,               "Settings"),
            ]
        self._dest_pairs = dest_pairs

        # Desktop navigation rail
        self.nav_rail = ft.NavigationRail(
            selected_index=0,
            label_type=ft.NavigationRailLabelType.ALL,
            extended=True,
            min_width=80,
            min_extended_width=200,
            leading=ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.STORE, size=28, color=ft.Colors.BLUE_700),
                    ft.Text(
                        get_setting("store_name", "Uptown"),
                        size=12, weight=ft.FontWeight.BOLD,
                        text_align=ft.TextAlign.CENTER,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
                padding=ft.padding.symmetric(vertical=12, horizontal=6),
            ),
            destinations=[
                ft.NavigationRailDestination(icon=icon, label=label)
                for icon, label in dest_pairs
            ],
            on_change=self.on_nav_change,
        )

        # Mobile bottom navigation bar
        self.nav_bar = ft.NavigationBar(
            selected_index=0,
            bgcolor=ft.Colors.SURFACE,
            destinations=[
                ft.NavigationBarDestination(icon=icon, label=label)
                for icon, label in dest_pairs
            ],
            on_change=self.on_nav_change,
        )

        # Dark mode switch
        self.dark_mode_switch = ft.Switch(
            value=get_setting("dark_mode", "false") == "true",
            on_change=self.toggle_dark_mode,
            label="Dark",
        )

        # Top bar
        self.top_bar = ft.Container(
            content=ft.Row([
                self.dark_mode_switch,
                ft.Row([
                    ft.CircleAvatar(
                        content=ft.Text(self.username[0].upper(), size=13),
                        bgcolor=ft.Colors.BLUE_700, radius=15,
                    ),
                    ft.Column([
                        ft.Text(f"{self.username} ({self.role})", size=12,
                                weight=ft.FontWeight.W_600),
                        ft.Text(get_setting("store_name", "Uptown Stationery"),
                                size=10, color=ft.Colors.GREY_500),
                    ], spacing=0, tight=True),
                    ft.IconButton(ft.Icons.LOGOUT, tooltip="Logout",
                                  on_click=self.logout),
                ], spacing=6),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            padding=ft.padding.symmetric(horizontal=16, vertical=8),
            border=ft.Border.only(bottom=ft.BorderSide(1, ft.Colors.GREY_300)),
        )

        self.content_area = ft.Container(
            expand=True, padding=16, content=ft.Text("Loading…"))

        # Placeholder until did_mount resolves dimensions
        self.content = ft.Column([self.top_bar, ft.Text("Loading…")],
                                  expand=True, spacing=0)

    def did_mount(self):
        self.page.on_resize = self.on_page_resize
        self.update_layout()
        self.on_nav_change(None)

    @property
    def _is_mobile(self) -> bool:
        return bool(self.page and self.page.width and
                    self.page.width < MOBILE_BREAKPOINT)

    def _dialog_width(self, desktop_w: int = 520) -> int:
        if self.page and self.page.width:
            return int(min(desktop_w, self.page.width * 0.94))
        return desktop_w

    def update_layout(self):
        if not self.page:
            return
        if self._is_mobile:
            self.content = ft.Column([
                self.top_bar,
                self.content_area,
                self.nav_bar,
            ], expand=True, spacing=0)
        else:
            self.content = ft.Column([
                self.top_bar,
                ft.Row([
                    self.nav_rail,
                    ft.VerticalDivider(width=1),
                    self.content_area,
                ], expand=True, spacing=0),
            ], expand=True, spacing=0)

    def on_page_resize(self, e):
        self.update_layout()
        self.safe_update()

    # ── Utilities ─────────────────────────────────────────────────────────────
    def snack(self, msg: str, color=ft.Colors.GREEN_700):
        if not self.page:
            return
        self.page.snack_bar = ft.SnackBar(ft.Text(msg), bgcolor=color)
        self.page.snack_bar.open = True
        self.page.update()

    def safe_update(self):
        try:
            if self.page:
                self.update()
        except Exception:
            pass

    def close_dialog(self, dialog):
        dialog.open = False
        if dialog in self.page.overlay:
            self.page.overlay.remove(dialog)
        self.page.update()

    def _scrollable_table(self, table: ft.DataTable,
                          expand=True, height=None) -> ft.Container:
        """Wrap a DataTable in a horizontally + vertically scrollable container."""
        inner = ft.Column(
            [ft.Row([table], scroll=ft.ScrollMode.AUTO)],
            scroll=ft.ScrollMode.AUTO,
        )
        return ft.Container(
            content=inner,
            expand=expand,
            height=height,
            border=ft.Border.all(1, ft.Colors.GREY_200),
            border_radius=10,
        )

    # ── Navigation ────────────────────────────────────────────────────────────
    def on_nav_change(self, e):
        if e is not None:
            try:
                idx = int(e.data)
            except (ValueError, TypeError, AttributeError):
                idx = getattr(getattr(e, "control", None),
                              "selected_index", 0) or 0
        else:
            idx = 0

        self.nav_rail.selected_index = idx
        self.nav_bar.selected_index  = idx

        is_admin = (self.role == "admin")
        if is_admin:
            fn = {
                0:  self.dashboard_view,
                1:  self.inventory_view,
                2:  self.sales_view,
                3:  self.sales_history_view,
                4:  self.reports_view,
                5:  self.stock_adjustments_view,
                6:  self.expenses_view,
                7:  self.promotions_view,
                8:  self.suppliers_view,
                9:  self.purchasing_view,
                10: self.customers_view,
                11: self.users_view,
                12: self.settings_view,
            }.get(idx, lambda: ft.Text("Not implemented"))
        else:
            fn = {
                0: self.dashboard_view,
                1: self.inventory_view,
                2: self.sales_view,
                3: self.sales_history_view,
                4: self.reports_view,
            }.get(idx, lambda: ft.Text("Not implemented"))

        self.content_area.content = fn()
        self.safe_update()

    # ─────────────────────────────────────────────────────────────────────────
    #  DASHBOARD
    # ─────────────────────────────────────────────────────────────────────────
    def dashboard_view(self):
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT COALESCE(SUM(quantity),0) FROM items")
        total_qty = c.fetchone()[0]
        c.execute("SELECT COALESCE(SUM(quantity*price),0.0) FROM items")
        total_val = c.fetchone()[0]
        today = datetime.now().strftime("%Y-%m-%d")
        c.execute("SELECT COALESCE(SUM(total),0.0) FROM sales WHERE DATE(sale_date)=?", (today,))
        today_rev = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM sales WHERE DATE(sale_date)=?", (today,))
        today_cnt = c.fetchone()[0]
        month = datetime.now().strftime("%Y-%m")
        c.execute("SELECT COALESCE(SUM(amount),0) FROM expenses "
                  "WHERE strftime('%Y-%m',expense_date)=?", (month,))
        month_expenses = c.fetchone()[0]
        c.execute("""SELECT DATE(sale_date), COUNT(*), COALESCE(SUM(total),0)
                     FROM sales WHERE sale_date>=DATE('now','-6 days')
                     GROUP BY DATE(sale_date) ORDER BY 1""")
        daily_data = c.fetchall()
        c.execute("""SELECT i.name, COALESCE(SUM(si.quantity),0), COALESCE(SUM(si.total),0)
                     FROM sale_items si JOIN items i ON si.item_id=i.id
                     GROUP BY si.item_id ORDER BY SUM(si.total) DESC LIMIT 5""")
        top_prods = c.fetchall()
        c.execute("""SELECT s.id, s.sale_date, COALESCE(cu.name,'Walk-in'), s.total, s.payment_method
                     FROM sales s LEFT JOIN customers cu ON s.customer_id=cu.id
                     ORDER BY s.sale_date DESC LIMIT 8""")
        recent_sales = c.fetchall()
        c.execute("""SELECT id, name, quantity, low_stock_threshold, supplier_id
                     FROM items WHERE quantity<=low_stock_threshold
                     ORDER BY (low_stock_threshold*2-quantity) DESC LIMIT 8""")
        reorder_items = c.fetchall()
        conn.close()

        sym = currency_symbol()

        def stat_card(title, value, bg, icon):
            return ft.Card(
                content=ft.Container(
                    ft.Row([
                        ft.Container(ft.Icon(icon, color=ft.Colors.WHITE, size=24),
                                     bgcolor=bg, border_radius=10, padding=10),
                        ft.Column([
                            ft.Text(title, size=12, color=ft.Colors.GREY_500),
                            ft.Text(value, size=19, weight=ft.FontWeight.BOLD),
                        ], spacing=2, tight=True),
                    ], spacing=12),
                    padding=ft.padding.symmetric(horizontal=14, vertical=12),
                ),
                elevation=3,
            )

        stat_data = [
            ("Total Stock",    f"{total_qty:,} units",         ft.Colors.BLUE_700,   ft.Icons.INVENTORY_2),
            ("Inv. Value",     f"{sym}{total_val:,.2f}",        ft.Colors.GREEN_700,  ft.Icons.ATTACH_MONEY),
            ("Today Revenue",  f"{sym}{today_rev:,.2f}",        ft.Colors.INDIGO_700, ft.Icons.TRENDING_UP),
            ("Today Sales",    str(today_cnt),                  ft.Colors.ORANGE_700, ft.Icons.RECEIPT_LONG),
            ("Month Expenses", f"{sym}{month_expenses:,.2f}",   ft.Colors.RED_700,    ft.Icons.ACCOUNT_BALANCE_WALLET),
        ]
        cards = []
        for title, value, bg, icon in stat_data:
            card = stat_card(title, value, bg, icon)
            card.col = {"xs": 12, "sm": 6, "md": 4, "lg": 2}
            cards.append(card)
        stats_row = ft.ResponsiveRow(controls=cards, spacing=10, run_spacing=10)

        def mini_table(title, headers, rows):
            empty = [ft.DataRow(cells=[ft.DataCell(ft.Text("No data"))] * len(headers))]
            return ft.Card(
                content=ft.Container(
                    ft.Column([
                        ft.Text(title, size=14, weight=ft.FontWeight.W_600),
                        ft.Divider(height=6),
                        ft.Row([ft.DataTable(
                            columns=[ft.DataColumn(ft.Text(h)) for h in headers],
                            rows=rows or empty,
                            data_row_max_height=40,
                        )], scroll=ft.ScrollMode.AUTO),
                    ], spacing=6),
                    padding=12,
                ),
                elevation=2, expand=True,
            )

        daily_rows = [
            ft.DataRow(cells=[
                ft.DataCell(ft.Text(d or "—")),
                ft.DataCell(ft.Text(str(cnt))),
                ft.DataCell(ft.Text(f"{sym}{rev:,.2f}", color=ft.Colors.GREEN_700)),
            ]) for d, cnt, rev in daily_data
        ]
        top_rows = [
            ft.DataRow(cells=[
                ft.DataCell(ft.Text(name, overflow=ft.TextOverflow.ELLIPSIS)),
                ft.DataCell(ft.Text(str(int(qty)))),
                ft.DataCell(ft.Text(f"{sym}{rev:,.2f}", color=ft.Colors.GREEN_700,
                                    weight=ft.FontWeight.W_600)),
            ]) for name, qty, rev in top_prods
        ]
        recent_rows = [
            ft.DataRow(cells=[
                ft.DataCell(ft.TextButton(f"#{sid}",
                            on_click=lambda e, s=sid: self.show_sale_details(s))),
                ft.DataCell(ft.Text((sdate or "")[:16], size=11)),
                ft.DataCell(ft.Text(cname)),
                ft.DataCell(ft.Text(f"{sym}{tot:.2f}", color=ft.Colors.GREEN_700,
                                    weight=ft.FontWeight.W_600)),
                ft.DataCell(ft.Container(
                    ft.Text(pay or "Cash", size=10, color=ft.Colors.WHITE),
                    bgcolor=ft.Colors.BLUE_700, border_radius=6,
                    padding=ft.padding.symmetric(horizontal=6, vertical=2),
                )),
            ]) for sid, sdate, cname, tot, pay in recent_sales
        ]
        reorder_rows = []
        for iid, name, qty, threshold, sup_id in reorder_items:
            suggest = max(threshold * 2 - qty, 1)
            reorder_rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(name)),
                ft.DataCell(ft.Text(str(qty), color=ft.Colors.RED_700,
                                    weight=ft.FontWeight.BOLD)),
                ft.DataCell(ft.Text(str(threshold))),
                ft.DataCell(ft.Text(str(suggest), color=ft.Colors.BLUE_700)),
                ft.DataCell(ft.IconButton(
                    ft.Icons.ADD_SHOPPING_CART,
                    data={"id": iid, "name": name, "qty": suggest, "sup_id": sup_id},
                    on_click=self.create_po_from_suggestion,
                )),
            ]))

        table_row_col = {"xs": 12, "md": 6}
        t1 = ft.Container(content=mini_table("Last 7 Days", ("Date","Orders","Revenue"), daily_rows),
                          expand=True)
        t1.col = table_row_col
        t2 = ft.Container(content=mini_table("Top 5 Products", ("Product","Qty","Revenue"), top_rows),
                          expand=True)
        t2.col = table_row_col
        tables_row = ft.ResponsiveRow([t1, t2], spacing=12, run_spacing=12)

        r1 = ft.Container(
            content=ft.Card(
                content=ft.Container(ft.Column([
                    ft.Text("Recent Sales", size=14, weight=ft.FontWeight.W_600),
                    ft.Divider(height=6),
                    ft.Row([ft.DataTable(
                        columns=[ft.DataColumn(ft.Text(h))
                                 for h in ("ID","Date","Customer","Total","Pay")],
                        rows=recent_rows or [ft.DataRow(cells=[ft.DataCell(ft.Text("—"))] * 5)],
                        data_row_max_height=40,
                    )], scroll=ft.ScrollMode.AUTO),
                ], spacing=6), padding=12),
                elevation=2,
            ),
            expand=True,
        )
        r1.col = {"xs": 12, "md": 7}

        reorder_card_content = ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.WARNING_AMBER, color=ft.Colors.ORANGE_700, size=16),
                ft.Text("Reorder Suggestions", size=14, weight=ft.FontWeight.W_600,
                        color=ft.Colors.ORANGE_700),
            ]),
            ft.Divider(height=6),
            ft.Row([ft.DataTable(
                columns=[ft.DataColumn(ft.Text(h))
                         for h in ("Item","Stock","Min","Suggest","")],
                rows=reorder_rows or [
                    ft.DataRow(cells=[ft.DataCell(ft.Text("All stock OK ✓"))] * 5)],
                data_row_max_height=40,
            )], scroll=ft.ScrollMode.AUTO),
            ft.ElevatedButton("Create PO from all suggestions",
                              icon=ft.Icons.SHOPPING_CART,
                              on_click=self.create_po_from_all_suggestions),
        ], spacing=6)

        r2 = ft.Container(
            content=ft.Card(content=ft.Container(reorder_card_content, padding=12),
                            elevation=2),
            expand=True,
        )
        r2.col = {"xs": 12, "md": 5}
        bottom_row = ft.ResponsiveRow([r1, r2], spacing=12, run_spacing=12)

        return ft.Column([
            ft.Text("Dashboard", size=26, weight=ft.FontWeight.BOLD),
            stats_row,
            tables_row,
            bottom_row,
        ], spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)

    def show_sale_details(self, sale_id):
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("""SELECT i.name, si.quantity, si.price_at_sale, si.total
                     FROM sale_items si JOIN items i ON si.item_id=i.id
                     WHERE si.sale_id=?""", (sale_id,))
        items = c.fetchall()
        c.execute("SELECT total,payment_method,sale_date,subtotal,discount,tax "
                  "FROM sales WHERE id=?", (sale_id,))
        info = c.fetchone()
        conn.close()
        if not info:
            return
        sym = currency_symbol()
        total, pay, sdate, subtotal, discount, tax = info
        w = self._dialog_width(560)
        content = ft.Column([
            ft.Text(f"Sale #{sale_id} — {(sdate or '')[:16]}", weight=ft.FontWeight.BOLD),
            ft.Row([
                ft.Text(f"Subtotal: {sym}{subtotal:.2f}"),
                ft.Text(f"Discount: -{sym}{discount:.2f}"),
                ft.Text(f"Tax: {sym}{tax:.2f}"),
                ft.Text(f"Total: {sym}{total:.2f}", weight=ft.FontWeight.BOLD,
                        color=ft.Colors.GREEN_700),
            ], spacing=10, wrap=True),
            ft.Text(f"Payment: {pay}"),
            ft.Divider(),
            ft.Row([ft.DataTable(
                columns=[ft.DataColumn(ft.Text(h))
                         for h in ("Item", "Qty", "Price", "Total")],
                rows=[ft.DataRow(cells=[
                    ft.DataCell(ft.Text(n)),
                    ft.DataCell(ft.Text(str(q))),
                    ft.DataCell(ft.Text(f"{sym}{p:.2f}")),
                    ft.DataCell(ft.Text(f"{sym}{t:.2f}")),
                ]) for n, q, p, t in items],
                data_row_max_height=40,
            )], scroll=ft.ScrollMode.AUTO),
        ], spacing=10, width=w, height=340, scroll=ft.ScrollMode.AUTO)
        dialog = ft.AlertDialog(
            title=ft.Text("Sale Details"),
            content=content,
            actions=[ft.TextButton("Close", on_click=lambda _: self.close_dialog(dialog))],
        )
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def create_po_from_suggestion(self, e):
        self.open_purchase_order_dialog(prefill=[e.control.data])

    def create_po_from_all_suggestions(self, e):
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("""SELECT id,name,quantity,low_stock_threshold,supplier_id
                     FROM items WHERE quantity<=low_stock_threshold""")
        rows = c.fetchall()
        conn.close()
        prefilled = [{"id": iid, "name": name, "qty": max(threshold*2-qty, 1), "sup_id": sup_id}
                     for iid, name, qty, threshold, sup_id in rows]
        self.open_purchase_order_dialog(prefill=prefilled)

    # ─────────────────────────────────────────────────────────────────────────
    #  INVENTORY
    # ─────────────────────────────────────────────────────────────────────────
    def inventory_view(self):
        self.inv_search = ft.TextField(
            hint_text="Search by name…", expand=True,
            prefix_icon=ft.Icons.SEARCH, height=45, border_radius=8,
            on_change=self.refresh_items,
        )
        self.filter_category = ft.Dropdown(
            width=160, hint_text="All Categories", height=45,
            on_change=self.refresh_items,
        )
        self.item_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Item Name")),
                ft.DataColumn(ft.Text("Category")),
                ft.DataColumn(ft.Text("Stock"),   numeric=True),
                ft.DataColumn(ft.Text("Price"),   numeric=True),
                ft.DataColumn(ft.Text("Cost"),    numeric=True),
                ft.DataColumn(ft.Text("Margin"),  numeric=True),
                ft.DataColumn(ft.Text("Supplier")),
                ft.DataColumn(ft.Text("Actions")),
            ],
            border=ft.Border.all(1, ft.Colors.GREY_300),
            border_radius=8, data_row_max_height=50, column_spacing=14,
        )
        self.load_categories()
        self.refresh_items()

        add_btn = ft.ElevatedButton(
            "+ Add Item", icon=ft.Icons.ADD,
            style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE),
            on_click=self.add_item_dialog,
            disabled=(self.role != "admin"),
        )
        export_btn = ft.OutlinedButton(
            "Export CSV", icon=ft.Icons.DOWNLOAD, on_click=self.export_items,
        )
        return ft.Column([
            ft.Text("Inventory", size=24, weight=ft.FontWeight.BOLD),
            ft.Row([self.inv_search, self.filter_category, add_btn, export_btn],
                   spacing=10, wrap=True),
            self._scrollable_table(self.item_table),
        ], expand=True, spacing=14, scroll=ft.ScrollMode.AUTO)

    def load_categories(self):
        raw  = get_setting("categories", "Pens,Notebooks,Art Supplies,Office Equipment,Other")
        cats = ["All"] + [x.strip() for x in raw.split(",") if x.strip()]
        self.filter_category.options = [ft.dropdown.Option(c, c) for c in cats]

    def refresh_items(self, e=None):
        if not hasattr(self, "item_table"):
            return
        search  = sanitize(getattr(self, "inv_search", None) and
                           (self.inv_search.value or ""))
        cat     = getattr(self, "filter_category", None) and self.filter_category.value
        conn    = sqlite3.connect(DB_FILE)
        c       = conn.cursor()
        q       = """SELECT i.id,i.name,i.category,i.quantity,i.price,i.cost_price,
                            i.low_stock_threshold,COALESCE(s.name,'—')
                     FROM items i LEFT JOIN suppliers s ON i.supplier_id=s.id WHERE 1=1"""
        params  = []
        if search:
            q += " AND i.name LIKE ?"; params.append(f"%{search}%")
        if cat and cat != "All":
            q += " AND i.category=?"; params.append(cat)
        q += " ORDER BY i.name"
        c.execute(q, params)
        rows = c.fetchall()
        conn.close()

        sym = currency_symbol()
        self.item_table.rows.clear()
        for iid, name, cat_, qty, price, cost, threshold, supplier in rows:
            is_low = qty <= threshold
            margin = ((price - cost) / price * 100) if price > 0 else 0.0
            if self.role == "admin":
                actions = [
                    ft.IconButton(ft.Icons.EDIT, data=iid, on_click=self.on_edit_item_click),
                    ft.IconButton(ft.Icons.DELETE, icon_color=ft.Colors.RED_400,
                                  data=iid, on_click=self.on_delete_item_click),
                ]
            else:
                actions = [ft.Text("—")]
            self.item_table.rows.append(ft.DataRow(
                color=ft.Colors.RED_50 if is_low else None,
                cells=[
                    ft.DataCell(ft.Row([
                        ft.Text(name, weight=ft.FontWeight.W_500),
                        ft.Container(ft.Text("LOW", size=9, color=ft.Colors.WHITE),
                                     bgcolor=ft.Colors.RED_700, border_radius=4,
                                     padding=ft.padding.symmetric(horizontal=4, vertical=1),
                                     visible=is_low),
                    ], spacing=5, tight=True)),
                    ft.DataCell(ft.Text(cat_ or "—")),
                    ft.DataCell(ft.Text(str(qty),
                                        color=ft.Colors.RED_700 if is_low else None,
                                        weight=ft.FontWeight.W_600 if is_low else None)),
                    ft.DataCell(ft.Text(f"{sym}{price:.2f}")),
                    ft.DataCell(ft.Text(f"{sym}{cost:.2f}", color=ft.Colors.GREY_600)),
                    ft.DataCell(ft.Text(f"{margin:.0f}%",
                                        color=ft.Colors.GREEN_700 if margin >= 20
                                              else ft.Colors.ORANGE_700)),
                    ft.DataCell(ft.Text(supplier, size=11)),
                    ft.DataCell(ft.Row(actions, tight=True)),
                ],
            ))
        self.safe_update()

    def on_edit_item_click(self, e):
        self.edit_item_dialog(e.control.data)

    def on_delete_item_click(self, e):
        self.delete_item(e.control.data)

    def _item_fields(self, data=None):
        conn = sqlite3.connect(DB_FILE)
        c    = conn.cursor()
        c.execute("SELECT id,name FROM suppliers ORDER BY name")
        suppliers = c.fetchall()
        conn.close()
        cats = [x.strip() for x in
                get_setting("categories", "Pens,Notebooks,Art Supplies,Office Equipment,Other")
                .split(",") if x.strip()]
        return {
            "name":      ft.TextField(label="Item Name *", expand=True,
                                       value=data[1] if data else ""),
            "category":  ft.Dropdown(label="Category", expand=True,
                                      options=[ft.dropdown.Option(x, x) for x in cats],
                                      value=data[2] if data else None),
            "price":     ft.TextField(label="Selling Price *", expand=True,
                                       keyboard_type=ft.KeyboardType.NUMBER,
                                       value=str(data[4]) if data else "0"),
            "cost":      ft.TextField(label="Cost Price", expand=True,
                                       keyboard_type=ft.KeyboardType.NUMBER,
                                       value=str(data[5]) if data else "0"),
            "qty":       ft.TextField(label="Quantity", expand=True,
                                       keyboard_type=ft.KeyboardType.NUMBER,
                                       value=str(data[3]) if data else "0"),
            "threshold": ft.TextField(label="Low-stock alert", expand=True,
                                       keyboard_type=ft.KeyboardType.NUMBER,
                                       value=str(data[6]) if data else "5"),
            "supplier":  ft.Dropdown(label="Supplier", expand=True,
                                      options=[ft.dropdown.Option(str(s[0]), s[1])
                                               for s in suppliers],
                                      value=str(data[7]) if (data and data[7]) else None),
        }

    def _item_form_content(self, f):
        w = self._dialog_width(520)
        return ft.Column([
            ft.Row([f["name"],      f["category"]], spacing=10),
            ft.Row([f["price"],     f["cost"]],     spacing=10),
            ft.Row([f["qty"],       f["threshold"]], spacing=10),
            f["supplier"],
        ], spacing=10, width=w, height=290, scroll=ft.ScrollMode.AUTO)

    def add_item_dialog(self, e=None):
        if self.role != "admin":
            self.snack("Admin access required", ft.Colors.RED_700); return
        f = self._item_fields()

        def save(_e):
            name = sanitize(f["name"].value)
            if not name:
                f["name"].error_text = "Required"; f["name"].update(); return
            try:
                conn = sqlite3.connect(DB_FILE)
                conn.execute(
                    """INSERT INTO items (name,category,price,cost_price,quantity,
                       low_stock_threshold,supplier_id) VALUES (?,?,?,?,?,?,?)""",
                    (name, f["category"].value,
                     safe_float(f["price"].value), safe_float(f["cost"].value),
                     safe_int(f["qty"].value), safe_int(f["threshold"].value, default=5),
                     int(f["supplier"].value) if f["supplier"].value else None),
                )
                conn.commit(); conn.close()
                log_audit(self.user_id, "ADD_ITEM", f"Added {name}")
                self.close_dialog(dialog); self.refresh_items()
                self.snack("Item added")
            except Exception as ex:
                self.snack(f"Error: {ex}", ft.Colors.RED_700)

        dialog = ft.AlertDialog(
            title=ft.Text("Add New Item", size=17, weight=ft.FontWeight.BOLD),
            content=self._item_form_content(f),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dialog)),
                ft.ElevatedButton("Save Item", on_click=save,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.overlay.append(dialog); dialog.open = True; self.page.update()

    def edit_item_dialog(self, item_id):
        if self.role != "admin":
            self.snack("Admin access required", ft.Colors.RED_700); return
        conn = sqlite3.connect(DB_FILE)
        c    = conn.cursor()
        c.execute("SELECT id,name,category,quantity,price,cost_price,"
                  "low_stock_threshold,supplier_id FROM items WHERE id=?", (item_id,))
        data = c.fetchone(); conn.close()
        if not data: return
        f = self._item_fields(data)

        def save(_e):
            name = sanitize(f["name"].value)
            if not name:
                f["name"].error_text = "Required"; f["name"].update(); return
            try:
                conn = sqlite3.connect(DB_FILE)
                conn.execute(
                    """UPDATE items SET name=?,category=?,price=?,cost_price=?,
                       quantity=?,low_stock_threshold=?,supplier_id=? WHERE id=?""",
                    (name, f["category"].value,
                     safe_float(f["price"].value), safe_float(f["cost"].value),
                     safe_int(f["qty"].value), safe_int(f["threshold"].value, default=5),
                     int(f["supplier"].value) if f["supplier"].value else None, item_id),
                )
                conn.commit(); conn.close()
                log_audit(self.user_id, "EDIT_ITEM", f"Edited #{item_id}")
                self.close_dialog(dialog); self.refresh_items()
                self.snack("Item updated")
            except Exception as ex:
                self.snack(f"Error: {ex}", ft.Colors.RED_700)

        dialog = ft.AlertDialog(
            title=ft.Text(f"Edit — {data[1]}", size=17, weight=ft.FontWeight.BOLD),
            content=self._item_form_content(f),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dialog)),
                ft.ElevatedButton("Update", on_click=save,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.overlay.append(dialog); dialog.open = True; self.page.update()

    def delete_item(self, item_id):
        if self.role != "admin":
            self.snack("Admin access required", ft.Colors.RED_700); return

        def confirm(_e):
            conn = sqlite3.connect(DB_FILE)
            conn.execute("DELETE FROM items WHERE id=?", (item_id,))
            conn.commit(); conn.close()
            log_audit(self.user_id, "DELETE_ITEM", f"Deleted #{item_id}")
            self.close_dialog(dialog); self.refresh_items()
            self.snack("Item deleted", ft.Colors.RED_700)

        dialog = ft.AlertDialog(
            title=ft.Text("Confirm Delete"),
            content=ft.Text("Permanently delete this item?"),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dialog)),
                ft.ElevatedButton("Delete", on_click=confirm,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.RED_700,
                                                        color=ft.Colors.WHITE)),
            ],
        )
        self.page.overlay.append(dialog); dialog.open = True; self.page.update()

    def export_items(self, e):
        try:
            conn = sqlite3.connect(DB_FILE)
            c    = conn.cursor()
            c.execute("SELECT name,category,price,cost_price,quantity,low_stock_threshold FROM items")
            rows = c.fetchall(); conn.close()
            fn   = f"items_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
            with open(fn, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["Name","Category","Price","Cost","Qty","Min Stock"])
                w.writerows(rows)
            self.snack(f"Exported → {fn}")
        except Exception as ex:
            self.snack(f"Export failed: {ex}", ft.Colors.RED_700)

    # ─────────────────────────────────────────────────────────────────────────
    #  SALES (POS)
    # ─────────────────────────────────────────────────────────────────────────
    def sales_view(self):
        self.cart_items = []
        self.pos_search = ft.TextField(
            label="Search item…", prefix_icon=ft.Icons.SEARCH,
            expand=True, height=48, on_change=self._pos_search_changed,
        )
        self.pos_results = ft.ListView(spacing=2, height=160)
        self.pos_results_container = ft.Container(
            content=self.pos_results,
            border=ft.Border.all(1, ft.Colors.GREY_300),
            border_radius=8, visible=False, padding=4,
        )
        self.cart_list = ft.ListView(spacing=6, expand=True, padding=4)
        sym = currency_symbol()
        self.cart_total_text = ft.Text(f"{sym}0.00", size=26, weight=ft.FontWeight.BOLD,
                                       color=ft.Colors.BLUE_700)
        self.subtotal_text = ft.Text(f"Subtotal: {sym}0.00", size=12, color=ft.Colors.GREY_600)
        self.discount_text = ft.Text(f"Discount: -{sym}0.00", size=12, color=ft.Colors.GREY_600)
        self.tax_text      = ft.Text(f"Tax: {sym}0.00", size=12, color=ft.Colors.GREY_600)
        self.discount_field = ft.TextField(
            label="Discount ($)", value="0",
            keyboard_type=ft.KeyboardType.NUMBER, width=128, height=45,
            on_change=self._recalculate,
        )
        self.tax_field = ft.TextField(
            label="Tax (%)", value=get_setting("tax_rate", "0"),
            keyboard_type=ft.KeyboardType.NUMBER, width=128, height=45,
            on_change=self._recalculate,
        )
        self.payment_dd = ft.Dropdown(
            label="Payment", width=155, height=45, value="Cash",
            options=[ft.dropdown.Option(m, m)
                     for m in ("Cash", "Card", "Mobile Money", "Bank Transfer")],
        )
        self.customer_dd = ft.Dropdown(label="Customer", expand=True, height=45)
        self._load_customer_dropdown()
        self.promo_dd = ft.Dropdown(label="Apply Promotion", expand=True, height=45,
                                     hint_text="No promo", on_change=self._apply_promo)
        self._load_promo_dropdown()

        complete_btn = ft.ElevatedButton(
            "Complete Sale", icon=ft.Icons.PAYMENT,
            height=50, expand=True,
            style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE,
                                 shape=ft.RoundedRectangleBorder(radius=10)),
            on_click=self.complete_sale_handler,
        )
        clear_btn = ft.OutlinedButton(
            "Clear Cart", icon=ft.Icons.CLEAR_ALL,
            height=44, expand=True, on_click=self.clear_cart_handler,
        )

        # Responsive: on mobile stack vertically
        summary = ft.Container(
            content=ft.Column([
                ft.Text("Order Summary", size=16, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                self.customer_dd,
                self.promo_dd,
                ft.Row([self.discount_field, self.tax_field], spacing=8),
                self.payment_dd,
                ft.Divider(),
                self.subtotal_text,
                self.discount_text,
                self.tax_text,
                ft.Divider(),
                ft.Row([ft.Text("TOTAL", size=14, weight=ft.FontWeight.BOLD),
                        self.cart_total_text],
                       alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Container(height=6),
                complete_btn,
                clear_btn,
            ], spacing=8, scroll=ft.ScrollMode.AUTO),
            padding=14, width=260,
        )
        pos_panel = ft.Column([
            ft.Text("Point of Sale", size=20, weight=ft.FontWeight.BOLD),
            self.pos_search,
            self.pos_results_container,
            ft.Text("Cart", size=14, weight=ft.FontWeight.W_600),
            ft.Container(
                content=self.cart_list,
                border=ft.Border.all(1, ft.Colors.GREY_300),
                border_radius=10, expand=True, padding=6,
            ),
        ], expand=True, spacing=8)

        return ft.Row([
            pos_panel,
            ft.VerticalDivider(width=1),
            summary,
        ], expand=True, spacing=0)

    def _load_promo_dropdown(self):
        conn  = sqlite3.connect(DB_FILE)
        c     = conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        c.execute("""SELECT id,name,promo_type,value FROM promotions
                     WHERE active=1
                     AND (start_date IS NULL OR start_date<=?)
                     AND (end_date   IS NULL OR end_date  >=?)""", (today, today))
        rows = c.fetchall(); conn.close()
        self.promo_dd.options = [ft.dropdown.Option("", "No Promotion")]
        for pid, name, ptype, val in rows:
            lbl = f"{name} ({'{}%'.format(int(val)) if ptype=='percentage' else '${:.2f}'.format(val)} off)"
            self.promo_dd.options.append(ft.dropdown.Option(str(pid), lbl))
        self.promo_dd.value = ""

    def _apply_promo(self, e):
        if not self.promo_dd.value:
            return
        try:
            pid = int(self.promo_dd.value)
        except (ValueError, TypeError):
            return
        conn = sqlite3.connect(DB_FILE)
        c    = conn.cursor()
        c.execute("SELECT promo_type,value,min_purchase FROM promotions WHERE id=?", (pid,))
        row  = c.fetchone(); conn.close()
        if not row: return
        ptype, val, minp = row
        subtotal = sum(ci["subtotal"] for ci in self.cart_items)
        if subtotal < minp:
            self.snack(f"Promo requires min. {currency_symbol()}{minp:.2f}", ft.Colors.ORANGE_700)
            self.promo_dd.value = ""; self.promo_dd.update(); return
        discount = subtotal * val / 100 if ptype == "percentage" else val
        self.discount_field.value = f"{discount:.2f}"
        self._recalculate()
        self.snack(f"Promo applied: {currency_symbol()}{discount:.2f} off")

    def complete_sale_handler(self, e):
        self.complete_sale()

    def complete_sale(self):
        if not self.cart_items:
            self.snack("Cart is empty!", ft.Colors.ORANGE_700); return
        sym      = currency_symbol()
        subtotal = sum(ci["subtotal"] for ci in self.cart_items)
        discount = safe_float(self.discount_field.value)
        tax_pct  = safe_float(self.tax_field.value)
        tax      = (subtotal - discount) * tax_pct / 100
        total    = max(0.0, subtotal - discount + tax)
        customer_id = None
        try:
            if self.customer_dd.value:
                customer_id = int(self.customer_dd.value)
        except (ValueError, TypeError):
            pass
        payment = self.payment_dd.value or "Cash"
        conn    = sqlite3.connect(DB_FILE)
        cur     = conn.cursor()
        for ci in self.cart_items:
            cur.execute("SELECT quantity FROM items WHERE id=?", (ci["item_id"],))
            row = cur.fetchone()
            if not row or row[0] < ci["qty"]:
                conn.close()
                self.snack(f"Insufficient stock: {ci['name']}", ft.Colors.RED_700); return
        try:
            cur.execute(
                """INSERT INTO sales (customer_id,subtotal,discount,tax,total,payment_method,user_id)
                   VALUES (?,?,?,?,?,?,?)""",
                (customer_id, subtotal, discount, tax, total, payment, self.user_id),
            )
            sale_id = cur.lastrowid
            for ci in self.cart_items:
                cur.execute(
                    "INSERT INTO sale_items (sale_id,item_id,quantity,price_at_sale,total) "
                    "VALUES (?,?,?,?,?)",
                    (sale_id, ci["item_id"], ci["qty"], ci["price"], ci["subtotal"]),
                )
                cur.execute("UPDATE items SET quantity=quantity-? WHERE id=?",
                            (ci["qty"], ci["item_id"]))
            if customer_id:
                cur.execute("UPDATE customers SET loyalty_points=loyalty_points+?,"
                            "total_spent=total_spent+? WHERE id=?",
                            (int(total), total, customer_id))
            conn.commit()
            log_audit(self.user_id, "SALE", f"Sale #{sale_id} — {sym}{total:.2f}")
            self.snack(f"Sale #{sale_id} completed — {sym}{total:.2f}")
            self.clear_cart()
        except Exception as ex:
            self.snack(f"Sale failed: {ex}", ft.Colors.RED_700)
        finally:
            conn.close()

    def clear_cart_handler(self, e):
        self.clear_cart()

    def clear_cart(self):
        self.cart_items.clear()
        self.cart_list.controls.clear()
        sym = currency_symbol()
        self.cart_total_text.value = f"{sym}0.00"
        self.subtotal_text.value   = f"Subtotal: {sym}0.00"
        self.discount_text.value   = f"Discount: -{sym}0.00"
        self.tax_text.value        = f"Tax: {sym}0.00"
        self.discount_field.value  = "0"
        if hasattr(self, "promo_dd"):
            self.promo_dd.value = ""
        self.safe_update()

    def _load_customer_dropdown(self):
        conn = sqlite3.connect(DB_FILE)
        c    = conn.cursor()
        c.execute("SELECT id,name FROM customers ORDER BY name")
        rows = c.fetchall(); conn.close()
        self.customer_dd.options = (
            [ft.dropdown.Option("", "Walk-in Customer")] +
            [ft.dropdown.Option(str(r[0]), r[1]) for r in rows]
        )
        self.customer_dd.value = ""

    def _pos_search_changed(self, e):
        query = sanitize(self.pos_search.value or "")
        if not query:
            if self.pos_results_container:
                self.pos_results_container.visible = False
            self.pos_results.controls.clear()
            self.safe_update(); return
        conn = sqlite3.connect(DB_FILE)
        c    = conn.cursor()
        c.execute("SELECT id,name,price,quantity FROM items "
                  "WHERE name LIKE ? AND quantity>0 ORDER BY name LIMIT 10",
                  (f"%{query}%",))
        rows = c.fetchall(); conn.close()
        sym  = currency_symbol()
        self.pos_results.controls.clear()
        for iid, name, price, qty in rows:
            self.pos_results.controls.append(ft.ListTile(
                title=ft.Text(name, size=13),
                subtitle=ft.Text(f"Stock: {qty}  •  {sym}{price:.2f}",
                                 size=11, color=ft.Colors.GREY_600),
                trailing=ft.IconButton(ft.Icons.ADD_CIRCLE,
                                       data={"id": iid, "name": name, "price": price},
                                       on_click=self.on_add_to_cart_click),
                dense=True,
            ))
        if self.pos_results_container:
            self.pos_results_container.visible = bool(rows)
        self.safe_update()

    def on_add_to_cart_click(self, e):
        d = e.control.data
        self._add_to_cart(d["id"], d["name"], d["price"])

    def _add_to_cart(self, item_id, name, price):
        for ci in self.cart_items:
            if ci["item_id"] == item_id:
                ci["qty"] += 1
                ci["subtotal"] = ci["qty"] * ci["price"]
                self._rebuild_cart_ui(); return
        self.cart_items.append({"item_id": item_id, "name": name,
                                 "price": price, "qty": 1, "subtotal": price})
        self._rebuild_cart_ui()

    def _rebuild_cart_ui(self):
        sym = currency_symbol()
        self.cart_list.controls.clear()
        for item in self.cart_items:
            qty_field = ft.TextField(
                value=str(item["qty"]), width=52, height=34,
                keyboard_type=ft.KeyboardType.NUMBER,
                text_align=ft.TextAlign.CENTER, border_radius=6, data=item,
                on_change=self.on_cart_qty_changed,
            )
            row = ft.Container(
                content=ft.Row([
                    ft.Column([
                        ft.Text(item["name"], size=12, weight=ft.FontWeight.W_500,
                                overflow=ft.TextOverflow.ELLIPSIS),
                        ft.Text(f"{sym}{item['price']:.2f} each", size=10,
                                color=ft.Colors.GREY_500),
                    ], expand=True, spacing=2, tight=True),
                    ft.Row([
                        ft.IconButton(ft.Icons.REMOVE, width=28, height=28, data=item,
                                      on_click=partial(self.on_cart_qty_step, delta=-1)),
                        qty_field,
                        ft.IconButton(ft.Icons.ADD, width=28, height=28, data=item,
                                      on_click=partial(self.on_cart_qty_step, delta=1)),
                    ], spacing=2, tight=True),
                    ft.Text(f"{sym}{item['subtotal']:.2f}", size=13,
                            weight=ft.FontWeight.W_600, width=64,
                            text_align=ft.TextAlign.RIGHT),
                    ft.IconButton(ft.Icons.CLOSE, icon_size=15,
                                  icon_color=ft.Colors.RED_400, data=item,
                                  on_click=self.on_cart_remove_item),
                ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.padding.symmetric(horizontal=8, vertical=5),
                border=ft.Border.all(1, ft.Colors.GREY_200), border_radius=8,
            )
            self.cart_list.controls.append(row)
        self._recalculate()

    def on_cart_qty_step(self, e, delta):
        item = e.control.data
        item["qty"]      = max(1, item["qty"] + delta)
        item["subtotal"] = item["qty"] * item["price"]
        self._rebuild_cart_ui()

    def on_cart_qty_changed(self, e):
        item = e.control.data
        try:
            item["qty"]      = max(1, int(e.control.value))
            item["subtotal"] = item["qty"] * item["price"]
            self._recalculate()
        except ValueError:
            pass

    def on_cart_remove_item(self, e):
        item = e.control.data
        self.cart_items = [ci for ci in self.cart_items if ci["item_id"] != item["item_id"]]
        self._rebuild_cart_ui()

    def _recalculate(self, e=None):
        sym      = currency_symbol()
        subtotal = sum(ci["subtotal"] for ci in self.cart_items)
        discount = safe_float(self.discount_field.value)
        tax_pct  = safe_float(self.tax_field.value)
        tax      = (subtotal - discount) * tax_pct / 100
        total    = max(0.0, subtotal - discount + tax)
        self.subtotal_text.value   = f"Subtotal: {sym}{subtotal:.2f}"
        self.discount_text.value   = f"Discount: -{sym}{discount:.2f}"
        self.tax_text.value        = f"Tax ({tax_pct:.0f}%): {sym}{tax:.2f}"
        self.cart_total_text.value = f"{sym}{total:.2f}"
        self.safe_update()

    # ─────────────────────────────────────────────────────────────────────────
    #  SALES HISTORY
    # ─────────────────────────────────────────────────────────────────────────
    def sales_history_view(self):
        sym = currency_symbol()
        date_from = ft.TextField(label="From (YYYY-MM-DD)", width=155, height=45,
                                  value=(datetime.now()-timedelta(days=30)).strftime("%Y-%m-%d"))
        date_to   = ft.TextField(label="To (YYYY-MM-DD)", width=155, height=45,
                                  value=datetime.now().strftime("%Y-%m-%d"))
        pay_filter = ft.Dropdown(label="Payment", width=150, height=45, value="All",
                                  options=[ft.dropdown.Option(m, m)
                                           for m in ("All","Cash","Card",
                                                     "Mobile Money","Bank Transfer")])
        staff_dd = ft.Dropdown(label="Staff", width=150, height=45, value="All")
        conn = sqlite3.connect(DB_FILE)
        c    = conn.cursor()
        c.execute("SELECT id,username FROM users ORDER BY username")
        users = c.fetchall(); conn.close()
        staff_dd.options = ([ft.dropdown.Option("All","All Staff")] +
                             [ft.dropdown.Option(str(u[0]), u[1]) for u in users])

        history_table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(h))
                     for h in ("ID","Date","Customer","Items","Subtotal","Discount","Total","Payment","Staff","")],
            border=ft.Border.all(1, ft.Colors.GREY_300), border_radius=8, data_row_max_height=44,
        )
        summary_text = ft.Text("", size=13, color=ft.Colors.GREY_700)

        def load(e=None):
            params = []
            q = """SELECT s.id,s.sale_date,COALESCE(cu.name,'Walk-in'),
                          COUNT(si.id),s.subtotal,s.discount,s.total,
                          s.payment_method,u.username
                   FROM sales s
                   LEFT JOIN customers cu ON s.customer_id=cu.id
                   LEFT JOIN sale_items si ON si.sale_id=s.id
                   LEFT JOIN users u ON s.user_id=u.id WHERE 1=1"""
            if date_from.value:
                q += " AND DATE(s.sale_date)>=?"; params.append(date_from.value)
            if date_to.value:
                q += " AND DATE(s.sale_date)<=?"; params.append(date_to.value)
            if pay_filter.value and pay_filter.value != "All":
                q += " AND s.payment_method=?"; params.append(pay_filter.value)
            if self.role == "admin" and staff_dd.value and staff_dd.value != "All":
                q += " AND s.user_id=?"; params.append(staff_dd.value)
            if self.role != "admin":
                q += " AND s.user_id=?"; params.append(str(self.user_id))
            q += " GROUP BY s.id ORDER BY s.sale_date DESC"
            conn = sqlite3.connect(DB_FILE)
            cur  = conn.cursor(); cur.execute(q, params); rows = cur.fetchall(); conn.close()
            history_table.rows.clear()
            total_rev = 0.0
            for sid, sdate, cname, icnt, sub, disc, tot, pay, staff in rows:
                total_rev += (tot or 0)
                history_table.rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.TextButton(f"#{sid}",
                                on_click=lambda e, s=sid: self.show_sale_details(s))),
                    ft.DataCell(ft.Text((sdate or "")[:16], size=11)),
                    ft.DataCell(ft.Text(cname or "—", size=11)),
                    ft.DataCell(ft.Text(str(icnt))),
                    ft.DataCell(ft.Text(f"{sym}{(sub or 0):.2f}")),
                    ft.DataCell(ft.Text(f"-{sym}{(disc or 0):.2f}", color=ft.Colors.ORANGE_700)),
                    ft.DataCell(ft.Text(f"{sym}{(tot or 0):.2f}", color=ft.Colors.GREEN_700,
                                        weight=ft.FontWeight.W_600)),
                    ft.DataCell(ft.Container(
                        ft.Text(pay or "Cash", size=10, color=ft.Colors.WHITE),
                        bgcolor=ft.Colors.BLUE_700, border_radius=6,
                        padding=ft.padding.symmetric(horizontal=5, vertical=2),
                    )),
                    ft.DataCell(ft.Text(staff or "—", size=11)),
                    ft.DataCell(ft.IconButton(ft.Icons.RECEIPT, icon_size=15,
                                              data=sid,
                                              on_click=lambda e, s=sid: self.show_sale_details(s))),
                ]))
            summary_text.value = (f"  {len(rows)} transactions  •  "
                                   f"Total: {sym}{total_rev:,.2f}")
            if self.page: self.page.update()

        def export(e):
            conn = sqlite3.connect(DB_FILE)
            cur  = conn.cursor()
            cur.execute("""SELECT s.id,s.sale_date,COALESCE(cu.name,'Walk-in'),
                                  s.subtotal,s.discount,s.tax,s.total,
                                  s.payment_method,u.username
                           FROM sales s
                           LEFT JOIN customers cu ON s.customer_id=cu.id
                           LEFT JOIN users u ON s.user_id=u.id
                           ORDER BY s.sale_date DESC""")
            rows = cur.fetchall(); conn.close()
            fn   = f"sales_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
            with open(fn, "w", newline="", encoding="utf-8") as fh:
                csv.writer(fh).writerows([
                    ["ID","Date","Customer","Subtotal","Discount","Tax","Total","Payment","Staff"]
                ] + list(rows))
            self.snack(f"Exported → {fn}")

        date_from.on_submit = load; date_to.on_submit = load
        pay_filter.on_change = load; staff_dd.on_change = load
        load()

        controls = [date_from, date_to, pay_filter]
        if self.role == "admin": controls.append(staff_dd)
        controls += [
            ft.ElevatedButton("Search", icon=ft.Icons.SEARCH, on_click=load,
                               style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                    color=ft.Colors.WHITE)),
            ft.OutlinedButton("Export CSV", icon=ft.Icons.DOWNLOAD, on_click=export),
        ]
        return ft.Column([
            ft.Text("Sales History", size=24, weight=ft.FontWeight.BOLD),
            ft.Row(controls, spacing=8, wrap=True),
            ft.Row([ft.Icon(ft.Icons.INFO_OUTLINE, size=15, color=ft.Colors.GREY_500),
                    summary_text], spacing=6),
            self._scrollable_table(history_table),
        ], expand=True, spacing=14, scroll=ft.ScrollMode.AUTO)

    # ─────────────────────────────────────────────────────────────────────────
    #  REPORTS
    # ─────────────────────────────────────────────────────────────────────────
    def reports_view(self):
        conn = sqlite3.connect(DB_FILE)
        c    = conn.cursor()
        c.execute("SELECT COALESCE(SUM(total),0) FROM sales")
        total_rev = c.fetchone()[0]
        c.execute("""SELECT COALESCE(SUM(si.quantity*i.cost_price),0)
                     FROM sale_items si JOIN items i ON si.item_id=i.id""")
        total_cogs = c.fetchone()[0]
        c.execute("SELECT COALESCE(SUM(amount),0) FROM expenses")
        total_exp  = c.fetchone()[0]
        gross      = total_rev - total_cogs
        net        = gross - total_exp
        sym        = currency_symbol()

        def pnl_row(label, val, color=None, bold=False):
            return ft.Row([
                ft.Text(label, size=13, weight=ft.FontWeight.BOLD if bold else None),
                ft.Text(f"{sym}{val:,.2f}", size=13 if not bold else 16,
                        color=color or (ft.Colors.GREEN_700 if val >= 0 else ft.Colors.RED_700),
                        weight=ft.FontWeight.BOLD if bold else None),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        pl_card = ft.Card(
            content=ft.Container(ft.Column([
                ft.Text("Profit & Loss Summary", size=15, weight=ft.FontWeight.W_600),
                ft.Divider(height=6),
                pnl_row("Total Revenue:", total_rev, ft.Colors.GREEN_700),
                pnl_row("Cost of Goods Sold:", total_cogs, ft.Colors.ORANGE_700),
                pnl_row("Gross Profit:", gross),
                pnl_row("Total Expenses:", total_exp, ft.Colors.RED_400),
                ft.Divider(),
                pnl_row("Net Profit:", net, bold=True),
            ]), padding=16),
            elevation=2, expand=True,
        )

        months = []
        for i in range(6):
            d = datetime.now().replace(day=1) - timedelta(days=30*i)
            months.append((d.strftime("%Y-%m"), d.strftime("%B %Y")))
        sel_month = ft.Dropdown(label="Month", width=200,
                                 value=months[0][0] if months else None,
                                 options=[ft.dropdown.Option(m[0], m[1]) for m in months])
        staff_table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(h)) for h in ("Staff","Sales","Revenue")],
            border=ft.Border.all(1, ft.Colors.GREY_300), border_radius=8,
        )

        def update_staff(e=None):
            m = sel_month.value
            if not m: return
            conn2 = sqlite3.connect(DB_FILE)
            c2    = conn2.cursor()
            c2.execute("""SELECT u.username,COUNT(s.id),COALESCE(SUM(s.total),0)
                          FROM sales s JOIN users u ON s.user_id=u.id
                          WHERE strftime('%Y-%m',s.sale_date)=?
                          GROUP BY u.id ORDER BY SUM(s.total) DESC""", (m,))
            rows = c2.fetchall(); conn2.close()
            staff_table.rows = [
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(u)),
                    ft.DataCell(ft.Text(str(cnt))),
                    ft.DataCell(ft.Text(f"{sym}{rev:,.2f}", color=ft.Colors.GREEN_700)),
                ]) for u, cnt, rev in rows
            ] or [ft.DataRow(cells=[ft.DataCell(ft.Text("No data"))] * 3)]
            if self.page: self.page.update()

        sel_month.on_change = update_staff
        c.execute("""SELECT DATE(sale_date),COUNT(*),COALESCE(SUM(total),0)
                     FROM sales WHERE sale_date>=DATE('now','-6 days')
                     GROUP BY DATE(sale_date) ORDER BY 1""")
        daily = c.fetchall()
        c.execute("""SELECT i.name,COALESCE(SUM(si.quantity),0),COALESCE(SUM(si.total),0)
                     FROM sale_items si JOIN items i ON si.item_id=i.id
                     GROUP BY si.item_id ORDER BY SUM(si.total) DESC LIMIT 10""")
        top_prods = c.fetchall(); conn.close()
        update_staff()

        daily_rows = [ft.DataRow(cells=[
            ft.DataCell(ft.Text(d or "—")), ft.DataCell(ft.Text(str(cnt))),
            ft.DataCell(ft.Text(f"{sym}{rev:,.2f}", color=ft.Colors.GREEN_700)),
        ]) for d, cnt, rev in daily]
        top_rows = [ft.DataRow(cells=[
            ft.DataCell(ft.Text(name, overflow=ft.TextOverflow.ELLIPSIS, width=160)),
            ft.DataCell(ft.Text(str(int(qty)))),
            ft.DataCell(ft.Text(f"{sym}{rev:,.2f}", color=ft.Colors.GREEN_700,
                                weight=ft.FontWeight.W_600)),
        ]) for name, qty, rev in top_prods]

        r1 = ft.Container(content=pl_card); r1.col = {"xs": 12, "md": 6}
        r2 = ft.Container(
            content=ft.Card(
                content=ft.Container(ft.Column([
                    ft.Text("Staff Performance", size=14, weight=ft.FontWeight.W_600),
                    sel_month,
                    ft.Row([staff_table], scroll=ft.ScrollMode.AUTO),
                ]), padding=14),
                elevation=2,
            ),
        ); r2.col = {"xs": 12, "md": 6}
        top_row = ft.ResponsiveRow([r1, r2], spacing=12, run_spacing=12)

        return ft.Column([
            ft.Text("Reports & Analytics", size=24, weight=ft.FontWeight.BOLD),
            top_row,
            ft.Card(content=ft.Container(ft.Column([
                ft.Text("Sales — Last 7 Days", size=14, weight=ft.FontWeight.W_600),
                ft.Row([ft.DataTable(
                    columns=[ft.DataColumn(ft.Text(h)) for h in ("Date","Orders","Revenue")],
                    rows=daily_rows or [ft.DataRow(cells=[ft.DataCell(ft.Text("No data"))]*3)],
                )], scroll=ft.ScrollMode.AUTO),
            ]), padding=14), elevation=2),
            ft.Card(content=ft.Container(ft.Column([
                ft.Text("Top Products", size=14, weight=ft.FontWeight.W_600),
                ft.Row([ft.DataTable(
                    columns=[ft.DataColumn(ft.Text(h)) for h in ("Product","Qty","Revenue")],
                    rows=top_rows or [ft.DataRow(cells=[ft.DataCell(ft.Text("No data"))]*3)],
                )], scroll=ft.ScrollMode.AUTO),
            ]), padding=14), elevation=2),
        ], spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)

    # ─────────────────────────────────────────────────────────────────────────
    #  STOCK ADJUSTMENTS
    # ─────────────────────────────────────────────────────────────────────────
    def stock_adjustments_view(self):
        if self.role != "admin":
            return ft.Column([ft.Text("Access denied", color=ft.Colors.RED_700)])
        self.adj_table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(h)) for h in
                     ("Date","Item","Before","Change","After","Reason","Staff")],
            border=ft.Border.all(1, ft.Colors.GREY_300),
            border_radius=8, data_row_max_height=44,
        )
        self._refresh_adj_table()

        def new_adj(e):
            conn = sqlite3.connect(DB_FILE)
            c    = conn.cursor()
            c.execute("SELECT id,name,quantity FROM items ORDER BY name")
            items = c.fetchall(); conn.close()
            item_dd = ft.Dropdown(label="Item *", width=280,
                                   options=[ft.dropdown.Option(str(it[0]),
                                            f"{it[1]} (stock: {it[2]})") for it in items])
            adj_type = ft.Dropdown(label="Type", width=180, value="add",
                                    options=[ft.dropdown.Option("add","Add Stock"),
                                             ft.dropdown.Option("remove","Remove Stock"),
                                             ft.dropdown.Option("set","Set Exact Qty")])
            qty_f    = ft.TextField(label="Quantity", width=110,
                                     keyboard_type=ft.KeyboardType.NUMBER, value="1")
            reason_f = ft.TextField(label="Reason", expand=True)
            err      = ft.Text("", color=ft.Colors.RED_400)
            w        = self._dialog_width(560)

            def save_adj(_e):
                if not item_dd.value:
                    err.value = "Select an item"; err.update(); return
                qty = safe_int(qty_f.value, lo=1)
                if qty < 1:
                    err.value = "Qty must be ≥ 1"; err.update(); return
                item_id = int(item_dd.value)
                conn = sqlite3.connect(DB_FILE)
                cur  = conn.cursor()
                cur.execute("SELECT quantity FROM items WHERE id=?", (item_id,))
                row = cur.fetchone()
                if not row:
                    conn.close(); err.value = "Item not found"; err.update(); return
                before = row[0]
                after  = (before + qty if adj_type.value == "add" else
                           max(0, before - qty) if adj_type.value == "remove" else qty)
                change = after - before
                cur.execute("UPDATE items SET quantity=? WHERE id=?", (after, item_id))
                cur.execute("INSERT INTO stock_adjustments "
                            "(item_id,quantity_before,quantity_change,quantity_after,reason,user_id) "
                            "VALUES (?,?,?,?,?,?)",
                            (item_id, before, change, after,
                             sanitize(reason_f.value), self.user_id))
                conn.commit()
                log_audit(self.user_id, "STOCK_ADJ", f"#{item_id}: {before}→{after}")
                conn.close()
                self.close_dialog(dlg); self._refresh_adj_table()
                self.snack(f"Stock adjusted: {before} → {after}")

            dlg = ft.AlertDialog(
                title=ft.Text("New Stock Adjustment", size=17, weight=ft.FontWeight.BOLD),
                content=ft.Column([
                    ft.Row([item_dd, adj_type], spacing=10, wrap=True),
                    ft.Row([qty_f, reason_f], spacing=10),
                    err,
                ], spacing=10, width=w, height=160, scroll=ft.ScrollMode.AUTO),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dlg)),
                    ft.ElevatedButton("Save", on_click=save_adj,
                                       style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                            color=ft.Colors.WHITE)),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            self.page.overlay.append(dlg); dlg.open = True; self.page.update()

        return ft.Column([
            ft.Text("Stock Adjustments", size=24, weight=ft.FontWeight.BOLD),
            ft.Text("All adjustments are logged for audit purposes.",
                    size=12, color=ft.Colors.GREY_600),
            ft.Row([
                ft.ElevatedButton("+ New Adjustment", icon=ft.Icons.TUNE, on_click=new_adj,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE)),
                ft.OutlinedButton("Refresh", icon=ft.Icons.REFRESH,
                                   on_click=lambda e: self._refresh_adj_table()),
            ], spacing=10),
            self._scrollable_table(self.adj_table),
        ], expand=True, spacing=14, scroll=ft.ScrollMode.AUTO)

    def _refresh_adj_table(self, e=None):
        if not hasattr(self, "adj_table"): return
        conn = sqlite3.connect(DB_FILE)
        c    = conn.cursor()
        c.execute("""SELECT sa.timestamp,i.name,sa.quantity_before,sa.quantity_change,
                            sa.quantity_after,COALESCE(sa.reason,'—'),COALESCE(u.username,'—')
                     FROM stock_adjustments sa
                     JOIN items i ON sa.item_id=i.id
                     LEFT JOIN users u ON sa.user_id=u.id
                     ORDER BY sa.timestamp DESC LIMIT 200""")
        rows = c.fetchall(); conn.close()
        self.adj_table.rows.clear()
        for ts, name, before, change, after, reason, staff in rows:
            col = (ft.Colors.GREEN_700 if change > 0 else
                   ft.Colors.RED_700 if change < 0 else ft.Colors.GREY_600)
            self.adj_table.rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text((ts or "")[:16], size=11)),
                ft.DataCell(ft.Text(name, weight=ft.FontWeight.W_500)),
                ft.DataCell(ft.Text(str(before))),
                ft.DataCell(ft.Text(f"{'+' if change > 0 else ''}{change}",
                                    color=col, weight=ft.FontWeight.BOLD)),
                ft.DataCell(ft.Text(str(after))),
                ft.DataCell(ft.Text(reason, size=11)),
                ft.DataCell(ft.Text(staff, size=11)),
            ]))
        self.safe_update()

    # ─────────────────────────────────────────────────────────────────────────
    #  EXPENSES
    # ─────────────────────────────────────────────────────────────────────────
    def expenses_view(self):
        if self.role != "admin":
            return ft.Column([ft.Text("Access denied", color=ft.Colors.RED_700)])
        sym  = currency_symbol()
        CATS = ["Rent","Utilities","Salaries","Supplies","Transport",
                "Marketing","Maintenance","Taxes","Other"]
        months = []
        for i in range(12):
            d = datetime.now().replace(day=1) - timedelta(days=30*i)
            months.append((d.strftime("%Y-%m"), d.strftime("%B %Y")))
        month_dd = ft.Dropdown(label="Month", width=190, height=45,
                                value=months[0][0],
                                options=([ft.dropdown.Option("All","All Time")] +
                                         [ft.dropdown.Option(m[0], m[1]) for m in months]))
        self.exp_table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(h))
                     for h in ("Date","Category","Description","Amount","Staff","Del")],
            border=ft.Border.all(1, ft.Colors.GREY_300),
            border_radius=8, data_row_max_height=44,
        )
        self.exp_summary   = ft.Row(spacing=10, wrap=True)
        self.exp_total_txt = ft.Text("", size=15, weight=ft.FontWeight.BOLD)

        def load_exp(e=None):
            m    = month_dd.value
            conn = sqlite3.connect(DB_FILE)
            cur  = conn.cursor()
            base = ("SELECT ex.id,ex.expense_date,ex.category,ex.description,ex.amount,"
                    "COALESCE(u.username,'—') FROM expenses ex "
                    "LEFT JOIN users u ON ex.user_id=u.id")
            if m and m != "All":
                cur.execute(base + " WHERE strftime('%Y-%m',ex.expense_date)=? "
                            "ORDER BY ex.expense_date DESC", (m,))
            else:
                cur.execute(base + " ORDER BY ex.expense_date DESC")
            rows = cur.fetchall()
            if m and m != "All":
                cur.execute("SELECT category,COALESCE(SUM(amount),0) FROM expenses "
                            "WHERE strftime('%Y-%m',expense_date)=? "
                            "GROUP BY category ORDER BY SUM(amount) DESC", (m,))
            else:
                cur.execute("SELECT category,COALESCE(SUM(amount),0) FROM expenses "
                            "GROUP BY category ORDER BY SUM(amount) DESC")
            cat_sum = cur.fetchall(); conn.close()

            self.exp_table.rows.clear()
            total = 0.0
            for eid, edate, cat, desc, amount, staff in rows:
                total += amount or 0
                self.exp_table.rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(edate or "—", size=11)),
                    ft.DataCell(ft.Container(
                        ft.Text(cat, size=10, color=ft.Colors.WHITE),
                        bgcolor=ft.Colors.INDIGO_700, border_radius=6,
                        padding=ft.padding.symmetric(horizontal=5, vertical=2),
                    )),
                    ft.DataCell(ft.Text(desc, overflow=ft.TextOverflow.ELLIPSIS, width=160)),
                    ft.DataCell(ft.Text(f"{sym}{amount:,.2f}", color=ft.Colors.RED_400,
                                        weight=ft.FontWeight.W_600)),
                    ft.DataCell(ft.Text(staff, size=11)),
                    ft.DataCell(ft.IconButton(ft.Icons.DELETE, icon_color=ft.Colors.RED_400,
                                              icon_size=16, data=eid,
                                              on_click=lambda ev, eid=eid: del_exp(eid))),
                ]))
            self.exp_total_txt.value = f"Period Total: {sym}{total:,.2f}"
            self.exp_summary.controls.clear()
            for cat, amt in cat_sum:
                self.exp_summary.controls.append(ft.Card(
                    content=ft.Container(ft.Column([
                        ft.Text(cat, size=10, color=ft.Colors.GREY_600),
                        ft.Text(f"{sym}{amt:,.2f}", size=13, weight=ft.FontWeight.BOLD),
                    ], spacing=2, tight=True), padding=8), elevation=1))
            if self.page: self.page.update()

        def del_exp(eid):
            def confirm(_e):
                conn = sqlite3.connect(DB_FILE)
                conn.execute("DELETE FROM expenses WHERE id=?", (eid,))
                conn.commit(); conn.close()
                self.close_dialog(dlg); load_exp()
                self.snack("Expense deleted", ft.Colors.RED_700)
            dlg = ft.AlertDialog(
                title=ft.Text("Delete Expense"),
                content=ft.Text("Remove this expense record?"),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dlg)),
                    ft.ElevatedButton("Delete", on_click=confirm,
                                       style=ft.ButtonStyle(bgcolor=ft.Colors.RED_700,
                                                            color=ft.Colors.WHITE)),
                ],
            )
            self.page.overlay.append(dlg); dlg.open = True; self.page.update()

        def add_exp(e):
            w      = self._dialog_width(600)
            cat_dd = ft.Dropdown(label="Category *", width=190,
                                  options=[ft.dropdown.Option(c, c) for c in CATS], value="Other")
            desc_f = ft.TextField(label="Description *", expand=True)
            amt_f  = ft.TextField(label="Amount *", width=140,
                                   keyboard_type=ft.KeyboardType.NUMBER,
                                   prefix=ft.Text(sym))
            date_f = ft.TextField(label="Date (YYYY-MM-DD)", width=170,
                                   value=datetime.now().strftime("%Y-%m-%d"))
            err    = ft.Text("", color=ft.Colors.RED_400)

            def save(_e):
                desc = sanitize(desc_f.value)
                if not desc:
                    err.value = "Description required"; err.update(); return
                amt = safe_float(amt_f.value, lo=0.01)
                if amt <= 0:
                    err.value = "Amount must be > 0"; err.update(); return
                conn = sqlite3.connect(DB_FILE)
                conn.execute("INSERT INTO expenses "
                             "(category,description,amount,expense_date,user_id) VALUES (?,?,?,?,?)",
                             (cat_dd.value, desc, amt, sanitize(date_f.value) or None, self.user_id))
                conn.commit(); conn.close()
                log_audit(self.user_id, "ADD_EXPENSE", f"{cat_dd.value}: {sym}{amt:.2f}")
                self.close_dialog(dlg); load_exp()
                self.snack(f"Expense recorded: {sym}{amt:.2f}")

            dlg = ft.AlertDialog(
                title=ft.Text("Add Expense", size=17, weight=ft.FontWeight.BOLD),
                content=ft.Column([
                    ft.Row([cat_dd, amt_f, date_f], spacing=10, wrap=True),
                    desc_f, err,
                ], spacing=10, width=w, height=160, scroll=ft.ScrollMode.AUTO),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dlg)),
                    ft.ElevatedButton("Save", on_click=save,
                                       style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                            color=ft.Colors.WHITE)),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            self.page.overlay.append(dlg); dlg.open = True; self.page.update()

        month_dd.on_change = load_exp
        load_exp()

        return ft.Column([
            ft.Text("Expenses", size=24, weight=ft.FontWeight.BOLD),
            ft.Row([
                ft.ElevatedButton("+ Add Expense", icon=ft.Icons.ADD, on_click=add_exp,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE)),
                month_dd, self.exp_total_txt,
            ], spacing=12, wrap=True),
            ft.Card(content=ft.Container(ft.Column([
                ft.Text("By Category", size=13, weight=ft.FontWeight.W_600),
                self.exp_summary,
            ], spacing=8), padding=10), elevation=2),
            self._scrollable_table(self.exp_table),
        ], expand=True, spacing=14, scroll=ft.ScrollMode.AUTO)

    # ─────────────────────────────────────────────────────────────────────────
    #  PROMOTIONS
    # ─────────────────────────────────────────────────────────────────────────
    def promotions_view(self):
        if self.role != "admin":
            return ft.Column([ft.Text("Access denied", color=ft.Colors.RED_700)])
        self.promo_table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(h)) for h in
                     ("Name","Code","Type","Value","Min.","Start","End","Active","Actions")],
            border=ft.Border.all(1, ft.Colors.GREY_300), border_radius=8, data_row_max_height=50,
        )
        self._refresh_promo_table()

        def add_promo(e):
            w   = self._dialog_width(600)
            nm  = ft.TextField(label="Promo Name *", expand=True)
            cod = ft.TextField(label="Code (optional)", expand=True)
            pty = ft.Dropdown(label="Type *", expand=True, value="percentage",
                               options=[ft.dropdown.Option("percentage","% Off"),
                                        ft.dropdown.Option("fixed","Fixed Off")])
            val = ft.TextField(label="Value *", expand=True,
                                keyboard_type=ft.KeyboardType.NUMBER)
            minp = ft.TextField(label="Min. Purchase", expand=True,
                                 keyboard_type=ft.KeyboardType.NUMBER, value="0")
            sd  = ft.TextField(label="Start Date", expand=True)
            ed  = ft.TextField(label="End Date", expand=True)
            err = ft.Text("", color=ft.Colors.RED_400)

            def save(_e):
                name = sanitize(nm.value)
                if not name:
                    err.value = "Name required"; err.update(); return
                v = safe_float(val.value, lo=0.01)
                if v <= 0:
                    err.value = "Value must be > 0"; err.update(); return
                try:
                    conn = sqlite3.connect(DB_FILE)
                    conn.execute(
                        "INSERT INTO promotions (name,code,promo_type,value,min_purchase,"
                        "start_date,end_date) VALUES (?,?,?,?,?,?,?)",
                        (name, sanitize(cod.value) or None, pty.value, v,
                         safe_float(minp.value),
                         sanitize(sd.value) or None, sanitize(ed.value) or None)
                    )
                    conn.commit(); conn.close()
                    self.close_dialog(dlg); self._refresh_promo_table()
                    self.snack("Promotion created")
                except sqlite3.IntegrityError:
                    err.value = "Promo code already exists"; err.update()
                except Exception as ex:
                    err.value = str(ex); err.update()

            dlg = ft.AlertDialog(
                title=ft.Text("Create Promotion", size=17, weight=ft.FontWeight.BOLD),
                content=ft.Column([
                    ft.Row([nm, cod], spacing=10),
                    ft.Row([pty, val, minp], spacing=10, wrap=True),
                    ft.Row([sd, ed], spacing=10, wrap=True),
                    err,
                ], spacing=10, width=w, height=240, scroll=ft.ScrollMode.AUTO),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dlg)),
                    ft.ElevatedButton("Create", on_click=save,
                                       style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                            color=ft.Colors.WHITE)),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            self.page.overlay.append(dlg); dlg.open = True; self.page.update()

        return ft.Column([
            ft.Text("Promotions & Discounts", size=24, weight=ft.FontWeight.BOLD),
            ft.Text("Active promotions appear at POS for quick application.",
                    size=12, color=ft.Colors.GREY_600),
            ft.Row([
                ft.ElevatedButton("+ New Promotion", icon=ft.Icons.ADD, on_click=add_promo,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE)),
                ft.OutlinedButton("Refresh", icon=ft.Icons.REFRESH,
                                   on_click=lambda e: self._refresh_promo_table()),
            ], spacing=10),
            self._scrollable_table(self.promo_table),
        ], expand=True, spacing=14, scroll=ft.ScrollMode.AUTO)

    def _refresh_promo_table(self, e=None):
        if not hasattr(self, "promo_table"): return
        sym  = currency_symbol()
        conn = sqlite3.connect(DB_FILE)
        c    = conn.cursor()
        c.execute("SELECT id,name,code,promo_type,value,min_purchase,start_date,end_date,active "
                  "FROM promotions ORDER BY created_at DESC")
        rows = c.fetchall(); conn.close()
        self.promo_table.rows.clear()
        for pid, name, code, ptype, val, minp, sd, ed, active in rows:
            lbl = f"{int(val)}%" if ptype == "percentage" else f"{sym}{val:.2f}"
            self.promo_table.rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(name, weight=ft.FontWeight.W_500)),
                ft.DataCell(ft.Container(
                    ft.Text(code or "—", size=10,
                            color=ft.Colors.WHITE if code else ft.Colors.GREY_500),
                    bgcolor=ft.Colors.PURPLE_700 if code else None, border_radius=6,
                    padding=ft.padding.symmetric(horizontal=5, vertical=2) if code else None,
                )),
                ft.DataCell(ft.Text("% Off" if ptype == "percentage" else "Fixed")),
                ft.DataCell(ft.Text(lbl, color=ft.Colors.GREEN_700, weight=ft.FontWeight.W_600)),
                ft.DataCell(ft.Text(f"{sym}{minp:.2f}" if minp else "—")),
                ft.DataCell(ft.Text(sd or "—", size=11)),
                ft.DataCell(ft.Text(ed or "—", size=11)),
                ft.DataCell(ft.Container(
                    ft.Text("ACTIVE" if active else "OFF", size=10, color=ft.Colors.WHITE),
                    bgcolor=ft.Colors.GREEN_700 if active else ft.Colors.GREY_500,
                    border_radius=6,
                    padding=ft.padding.symmetric(horizontal=5, vertical=2),
                )),
                ft.DataCell(ft.Row([
                    ft.IconButton(ft.Icons.TOGGLE_ON if active else ft.Icons.TOGGLE_OFF,
                                  icon_color=ft.Colors.GREEN_700 if active else ft.Colors.GREY_500,
                                  data=pid, on_click=self._toggle_promo),
                    ft.IconButton(ft.Icons.DELETE, icon_color=ft.Colors.RED_400,
                                  data=pid, on_click=self._delete_promo),
                ], tight=True)),
            ]))
        self.safe_update()

    def _toggle_promo(self, e):
        pid  = e.control.data
        conn = sqlite3.connect(DB_FILE)
        c    = conn.cursor()
        c.execute("SELECT active FROM promotions WHERE id=?", (pid,))
        row  = c.fetchone()
        if row:
            conn.execute("UPDATE promotions SET active=? WHERE id=?",
                         (0 if row[0] else 1, pid))
            conn.commit()
        conn.close(); self._refresh_promo_table()

    def _delete_promo(self, e):
        pid = e.control.data
        def confirm(_e):
            conn = sqlite3.connect(DB_FILE)
            conn.execute("DELETE FROM promotions WHERE id=?", (pid,))
            conn.commit(); conn.close()
            self.close_dialog(dlg); self._refresh_promo_table()
            self.snack("Promotion deleted", ft.Colors.RED_700)
        dlg = ft.AlertDialog(
            title=ft.Text("Delete Promotion"),
            content=ft.Text("Permanently remove this promotion?"),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dlg)),
                ft.ElevatedButton("Delete", on_click=confirm,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.RED_700,
                                                        color=ft.Colors.WHITE)),
            ],
        )
        self.page.overlay.append(dlg); dlg.open = True; self.page.update()

    # ─────────────────────────────────────────────────────────────────────────
    #  SUPPLIERS
    # ─────────────────────────────────────────────────────────────────────────
    def suppliers_view(self):
        if self.role != "admin":
            return ft.Column([ft.Text("Access denied", color=ft.Colors.RED_700)])
        self.supplier_table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(h))
                     for h in ("Name","Contact","Phone","Email","Address","Actions")],
            border=ft.Border.all(1, ft.Colors.GREY_300),
            border_radius=8, data_row_max_height=52,
        )
        self.refresh_suppliers()
        return ft.Column([
            ft.Text("Suppliers", size=24, weight=ft.FontWeight.BOLD),
            ft.ElevatedButton("+ Add Supplier", icon=ft.Icons.ADD,
                               style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                    color=ft.Colors.WHITE),
                               on_click=lambda e: self.add_supplier_dialog()),
            self._scrollable_table(self.supplier_table),
        ], expand=True, spacing=14, scroll=ft.ScrollMode.AUTO)

    def refresh_suppliers(self, e=None):
        if not hasattr(self, "supplier_table"): return
        conn = sqlite3.connect(DB_FILE)
        c    = conn.cursor()
        c.execute("SELECT id,name,contact_person,phone,email,address FROM suppliers ORDER BY name")
        rows = c.fetchall(); conn.close()
        self.supplier_table.rows.clear()
        for sid, name, contact, phone, email, address in rows:
            self.supplier_table.rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(name, weight=ft.FontWeight.W_500)),
                ft.DataCell(ft.Text(contact or "—")),
                ft.DataCell(ft.Text(phone   or "—")),
                ft.DataCell(ft.Text(email   or "—")),
                ft.DataCell(ft.Text(address or "—", overflow=ft.TextOverflow.ELLIPSIS, width=120)),
                ft.DataCell(ft.Row([
                    ft.IconButton(ft.Icons.EDIT, data=sid,
                                  on_click=lambda e, s=sid: self.edit_supplier_dialog(s)),
                    ft.IconButton(ft.Icons.DELETE, icon_color=ft.Colors.RED_400,
                                  data=sid, on_click=lambda e, s=sid: self.delete_supplier(s)),
                ], tight=True)),
            ]))
        self.safe_update()

    def _supplier_form(self, data=None):
        w = self._dialog_width(520)
        f = {
            "name":    ft.TextField(label="Company Name *", expand=True,
                                     value=data[1] if data else ""),
            "contact": ft.TextField(label="Contact Person", expand=True,
                                     value=data[2] if data else ""),
            "phone":   ft.TextField(label="Phone", expand=True,
                                     value=data[3] if data else ""),
            "email":   ft.TextField(label="Email", expand=True,
                                     value=data[4] if data else ""),
            "address": ft.TextField(label="Address", expand=True,
                                     value=data[5] if data else "",
                                     multiline=True, min_lines=2),
        }
        content = ft.Column([
            ft.Row([f["name"],  f["contact"]], spacing=10),
            ft.Row([f["phone"], f["email"]],   spacing=10),
            f["address"],
        ], spacing=10, width=w, height=230, scroll=ft.ScrollMode.AUTO)
        return f, content

    def add_supplier_dialog(self):
        f, content = self._supplier_form()
        def save(_e):
            name = sanitize(f["name"].value)
            if not name:
                f["name"].error_text = "Required"; f["name"].update(); return
            conn = sqlite3.connect(DB_FILE)
            conn.execute("INSERT INTO suppliers (name,contact_person,phone,email,address) "
                         "VALUES (?,?,?,?,?)",
                         (name, sanitize(f["contact"].value), sanitize(f["phone"].value),
                          sanitize(f["email"].value), sanitize(f["address"].value, 300)))
            conn.commit(); conn.close()
            self.close_dialog(dlg); self.refresh_suppliers()
            self.snack("Supplier added")
        dlg = ft.AlertDialog(
            title=ft.Text("Add Supplier", size=17, weight=ft.FontWeight.BOLD),
            content=content,
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dlg)),
                ft.ElevatedButton("Save", on_click=save,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.overlay.append(dlg); dlg.open = True; self.page.update()

    def edit_supplier_dialog(self, sid):
        conn = sqlite3.connect(DB_FILE)
        c    = conn.cursor()
        c.execute("SELECT id,name,contact_person,phone,email,address FROM suppliers WHERE id=?", (sid,))
        data = c.fetchone(); conn.close()
        if not data: return
        f, content = self._supplier_form(data)
        def save(_e):
            name = sanitize(f["name"].value)
            if not name:
                f["name"].error_text = "Required"; f["name"].update(); return
            conn = sqlite3.connect(DB_FILE)
            conn.execute("UPDATE suppliers SET name=?,contact_person=?,phone=?,email=?,address=? "
                         "WHERE id=?",
                         (name, sanitize(f["contact"].value), sanitize(f["phone"].value),
                          sanitize(f["email"].value), sanitize(f["address"].value, 300), sid))
            conn.commit(); conn.close()
            self.close_dialog(dlg); self.refresh_suppliers()
            self.snack("Supplier updated")
        dlg = ft.AlertDialog(
            title=ft.Text(f"Edit — {data[1]}", size=17, weight=ft.FontWeight.BOLD),
            content=content,
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dlg)),
                ft.ElevatedButton("Update", on_click=save,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.overlay.append(dlg); dlg.open = True; self.page.update()

    def delete_supplier(self, sid):
        def confirm(_e):
            conn = sqlite3.connect(DB_FILE)
            conn.execute("DELETE FROM suppliers WHERE id=?", (sid,))
            conn.commit(); conn.close()
            self.close_dialog(dlg); self.refresh_suppliers()
            self.snack("Supplier deleted", ft.Colors.RED_700)
        dlg = ft.AlertDialog(
            title=ft.Text("Delete Supplier"),
            content=ft.Text("Remove this supplier? Linked items will be unlinked."),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dlg)),
                ft.ElevatedButton("Delete", on_click=confirm,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.RED_700,
                                                        color=ft.Colors.WHITE)),
            ],
        )
        self.page.overlay.append(dlg); dlg.open = True; self.page.update()

    # ─────────────────────────────────────────────────────────────────────────
    #  PURCHASING (Purchase Orders)
    # ─────────────────────────────────────────────────────────────────────────
    def purchasing_view(self):
        if self.role != "admin":
            return ft.Column([ft.Text("Access denied", color=ft.Colors.RED_700)])
        self.po_table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(h))
                     for h in ("PO #","Supplier","Order Date","Expected","Status","Total","Actions")],
            border=ft.Border.all(1, ft.Colors.GREY_300), border_radius=8,
        )
        self.refresh_po_list()
        return ft.Column([
            ft.Text("Purchase Orders", size=24, weight=ft.FontWeight.BOLD),
            ft.Row([
                ft.ElevatedButton("+ New PO", icon=ft.Icons.ADD,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE),
                                   on_click=lambda e: self.open_purchase_order_dialog()),
                ft.OutlinedButton("Refresh", icon=ft.Icons.REFRESH,
                                   on_click=self.refresh_po_list),
            ], spacing=10),
            self._scrollable_table(self.po_table),
        ], expand=True, spacing=14, scroll=ft.ScrollMode.AUTO)

    def refresh_po_list(self, e=None):
        if not hasattr(self, "po_table"): return
        conn = sqlite3.connect(DB_FILE)
        c    = conn.cursor()
        c.execute("""SELECT po.id,s.name,po.order_date,po.expected_date,po.status,po.total_cost
                     FROM purchase_orders po JOIN suppliers s ON po.supplier_id=s.id
                     ORDER BY po.order_date DESC""")
        rows = c.fetchall(); conn.close()
        sym  = currency_symbol()
        STATUS_COLORS = {
            "pending":   ft.Colors.ORANGE_700, "ordered":   ft.Colors.BLUE_700,
            "received":  ft.Colors.GREEN_700,  "cancelled": ft.Colors.RED_700,
        }
        self.po_table.rows = [
            ft.DataRow(cells=[
                ft.DataCell(ft.Text(str(pid))),
                ft.DataCell(ft.Text(sname)),
                ft.DataCell(ft.Text((odate or "")[:10])),
                ft.DataCell(ft.Text(edate or "—")),
                ft.DataCell(ft.Container(
                    ft.Text(status.upper(), size=10, color=ft.Colors.WHITE),
                    bgcolor=STATUS_COLORS.get(status, ft.Colors.GREY_700), border_radius=6,
                    padding=ft.padding.symmetric(horizontal=6, vertical=2),
                )),
                ft.DataCell(ft.Text(f"{sym}{total:.2f}")),
                ft.DataCell(ft.Row([
                    ft.IconButton(ft.Icons.CHECK_CIRCLE, data=pid,
                                  tooltip="Receive Items",
                                  on_click=self.receive_po_dialog),
                ], tight=True)),
            ]) for pid, sname, odate, edate, status, total in rows
        ]
        self.safe_update()

    def open_purchase_order_dialog(self, prefill=None):
        if prefill is None: prefill = []
        conn = sqlite3.connect(DB_FILE)
        c    = conn.cursor()
        c.execute("SELECT id,name FROM suppliers ORDER BY name")
        suppliers = c.fetchall()
        c.execute("SELECT id,name,cost_price FROM items ORDER BY name")
        all_items = c.fetchall(); conn.close()
        if not suppliers:
            self.snack("No suppliers. Add a supplier first.", ft.Colors.ORANGE_700); return
        sym         = currency_symbol()
        item_opts   = [ft.dropdown.Option(str(it[0]), f"{it[1]} (cost: {sym}{it[2]:.2f})")
                       for it in all_items]
        supplier_dd = ft.Dropdown(label="Supplier *", width=250,
                                   options=[ft.dropdown.Option(str(s[0]), s[1])
                                            for s in suppliers])
        exp_date    = ft.TextField(label="Expected Date (YYYY-MM-DD)", width=200)
        notes       = ft.TextField(label="Notes", multiline=True, min_lines=2, width=400)
        items_col   = ft.Column(spacing=8, width=600, height=240, scroll=ft.ScrollMode.AUTO)
        items_data  = []

        def add_item_row(item_id=None, qty=1, cost=0.0):
            idd  = ft.Dropdown(width=220, hint_text="Select Item", options=item_opts)
            if item_id: idd.value = str(item_id)
            qf   = ft.TextField(value=str(qty), width=70,
                                 keyboard_type=ft.KeyboardType.NUMBER)
            cf   = ft.TextField(value=f"{cost:.2f}", width=100,
                                 keyboard_type=ft.KeyboardType.NUMBER,
                                 prefix=ft.Text(sym))
            rb   = ft.IconButton(ft.Icons.DELETE, icon_color=ft.Colors.RED_400)
            row_d = {"item_dd": idd, "qty": qf, "cost": cf}
            items_data.append(row_d)
            row  = ft.Row([idd, qf, cf, rb], spacing=8)
            items_col.controls.append(row)
            def rm(_e):
                items_col.controls.remove(row)
                items_data.remove(row_d)
                if self.page: self.page.update()
            rb.on_click = rm
            if self.page: self.page.update()

        for p in prefill:
            add_item_row(p.get("id"), p.get("qty", 1))

        w = self._dialog_width(680)

        def save_po(e):
            if not supplier_dd.value:
                self.snack("Supplier required", ft.Colors.RED_700); return
            if not items_data:
                self.snack("At least one item required", ft.Colors.RED_700); return
            conn = sqlite3.connect(DB_FILE)
            cur  = conn.cursor()
            try:
                cur.execute("INSERT INTO purchase_orders "
                            "(supplier_id,expected_date,notes,created_by) VALUES (?,?,?,?)",
                            (int(supplier_dd.value),
                             sanitize(exp_date.value) or None,
                             sanitize(notes.value, 1000), self.user_id))
                po_id = cur.lastrowid; total_cost = 0.0
                for rd in items_data:
                    if not rd["item_dd"].value: continue
                    qty  = safe_int(rd["qty"].value, lo=1)
                    cost = safe_float(rd["cost"].value)
                    total_cost += qty * cost
                    cur.execute("INSERT INTO po_items (po_id,item_id,quantity_ordered,cost_price) "
                                "VALUES (?,?,?,?)",
                                (po_id, int(rd["item_dd"].value), qty, cost))
                cur.execute("UPDATE purchase_orders SET total_cost=? WHERE id=?",
                            (total_cost, po_id))
                conn.commit()
                log_audit(self.user_id, "CREATE_PO", f"PO #{po_id} created")
                self.close_dialog(dlg); self.refresh_po_list()
                self.snack(f"PO #{po_id} created")
            except Exception as ex:
                self.snack(f"Error: {ex}", ft.Colors.RED_700)
            finally:
                conn.close()

        dlg = ft.AlertDialog(
            title=ft.Text("Create Purchase Order", size=17, weight=ft.FontWeight.BOLD),
            content=ft.Column([
                supplier_dd, exp_date, notes,
                ft.Divider(),
                ft.Text("Items:", weight=ft.FontWeight.W_500),
                items_col,
                ft.OutlinedButton("+ Add Item", icon=ft.Icons.ADD,
                                   on_click=lambda e: add_item_row()),
            ], spacing=10, width=w, height=500, scroll=ft.ScrollMode.AUTO),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dlg)),
                ft.ElevatedButton("Save PO", on_click=save_po,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.overlay.append(dlg); dlg.open = True; self.page.update()

    def receive_po_dialog(self, e):
        po_id = e.control.data
        conn  = sqlite3.connect(DB_FILE)
        c     = conn.cursor()
        c.execute("SELECT status FROM purchase_orders WHERE id=?", (po_id,))
        status = c.fetchone()
        if status and status[0] in ("received", "cancelled"):
            self.snack("Cannot receive this PO", ft.Colors.RED_700); conn.close(); return
        c.execute("""SELECT pi.id,i.name,pi.quantity_ordered,pi.quantity_received,pi.cost_price
                     FROM po_items pi JOIN items i ON pi.item_id=i.id WHERE pi.po_id=?""", (po_id,))
        items = c.fetchall(); conn.close()
        fields = []
        for pi_id, name, ordered, received, cost in items:
            remaining = ordered - received
            if remaining <= 0: continue
            qf = ft.TextField(label=f"{name} (max {remaining})", value=str(remaining),
                               keyboard_type=ft.KeyboardType.NUMBER, width=250)
            fields.append((pi_id, qf, cost))
        if not fields:
            self.snack("All items already received", ft.Colors.ORANGE_700); return

        def do_receive(_e):
            conn = sqlite3.connect(DB_FILE)
            cur  = conn.cursor()
            try:
                for pi_id, qf, cost in fields:
                    qty = safe_int(qf.value, lo=0)
                    if qty > 0:
                        cur.execute("UPDATE po_items SET quantity_received=quantity_received+? "
                                    "WHERE id=?", (qty, pi_id))
                        cur.execute("SELECT item_id FROM po_items WHERE id=?", (pi_id,))
                        item_id = cur.fetchone()[0]
                        cur.execute("UPDATE items SET quantity=quantity+?,cost_price=? WHERE id=?",
                                    (qty, cost, item_id))
                cur.execute("SELECT COUNT(*) FROM po_items "
                            "WHERE po_id=? AND quantity_received<quantity_ordered", (po_id,))
                new_status = "received" if cur.fetchone()[0] == 0 else "ordered"
                cur.execute("UPDATE purchase_orders SET status=? WHERE id=?",
                            (new_status, po_id))
                conn.commit()
                log_audit(self.user_id, "RECEIVE_PO", f"PO #{po_id}")
                self.close_dialog(dlg); self.refresh_po_list()
                self.snack("Items received successfully")
            except Exception as ex:
                self.snack(f"Error: {ex}", ft.Colors.RED_700)
            finally:
                conn.close()

        dlg = ft.AlertDialog(
            title=ft.Text(f"Receive PO #{po_id}"),
            content=ft.Column([f for _, f, _ in fields], spacing=8, width=300,
                               height=min(len(fields)*70+20, 400), scroll=ft.ScrollMode.AUTO),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dlg)),
                ft.ElevatedButton("Confirm Receive", on_click=do_receive,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_700,
                                                        color=ft.Colors.WHITE)),
            ],
        )
        self.page.overlay.append(dlg); dlg.open = True; self.page.update()

    # ─────────────────────────────────────────────────────────────────────────
    #  CUSTOMERS
    # ─────────────────────────────────────────────────────────────────────────
    def customers_view(self):
        if self.role != "admin":
            return ft.Column([ft.Text("Access denied", color=ft.Colors.RED_700)])
        self.customer_table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(h))
                     for h in ("Name","Phone","Email","Points","Spent","Since","Actions")],
            border=ft.Border.all(1, ft.Colors.GREY_300), border_radius=8, data_row_max_height=52,
        )
        self.refresh_customers()
        return ft.Column([
            ft.Text("Customers", size=24, weight=ft.FontWeight.BOLD),
            ft.ElevatedButton("+ Add Customer", icon=ft.Icons.PERSON_ADD,
                               style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                    color=ft.Colors.WHITE),
                               on_click=lambda e: self.add_customer_dialog()),
            self._scrollable_table(self.customer_table),
        ], expand=True, spacing=14, scroll=ft.ScrollMode.AUTO)

    def refresh_customers(self, e=None):
        if not hasattr(self, "customer_table"): return
        conn = sqlite3.connect(DB_FILE)
        c    = conn.cursor()
        c.execute("SELECT id,name,phone,email,loyalty_points,total_spent,created_at "
                  "FROM customers ORDER BY name")
        rows = c.fetchall(); conn.close()
        sym  = currency_symbol()
        self.customer_table.rows.clear()
        for cid, name, phone, email, pts, spent, joined in rows:
            self.customer_table.rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(name, weight=ft.FontWeight.W_500)),
                ft.DataCell(ft.Text(phone or "—")),
                ft.DataCell(ft.Text(email or "—")),
                ft.DataCell(ft.Container(
                    ft.Text(str(pts), color=ft.Colors.WHITE, size=11),
                    bgcolor=ft.Colors.AMBER_700, border_radius=10,
                    padding=ft.padding.symmetric(horizontal=6, vertical=2),
                )),
                ft.DataCell(ft.Text(f"{sym}{spent:,.2f}", color=ft.Colors.GREEN_700)),
                ft.DataCell(ft.Text((joined or "")[:10], size=11, color=ft.Colors.GREY_600)),
                ft.DataCell(ft.Row([
                    ft.IconButton(ft.Icons.EDIT, data=cid,
                                  on_click=lambda e, c=cid: self.edit_customer_dialog(c)),
                    ft.IconButton(ft.Icons.DELETE, icon_color=ft.Colors.RED_400,
                                  data=cid, on_click=lambda e, c=cid: self.delete_customer(c)),
                ], tight=True)),
            ]))
        self.safe_update()

    def _customer_form(self, data=None):
        w = self._dialog_width(460)
        f = {
            "name":  ft.TextField(label="Full Name *", expand=True,
                                   value=data[1] if data else ""),
            "phone": ft.TextField(label="Phone", expand=True,
                                   value=data[2] if data else ""),
            "email": ft.TextField(label="Email", expand=True,
                                   value=data[3] if data else ""),
        }
        return f, ft.Column([f["name"], ft.Row([f["phone"], f["email"]], spacing=10)],
                             spacing=10, width=w, height=140, scroll=ft.ScrollMode.AUTO)

    def add_customer_dialog(self):
        f, content = self._customer_form()
        def save(_e):
            name = sanitize(f["name"].value)
            if not name:
                f["name"].error_text = "Required"; f["name"].update(); return
            conn = sqlite3.connect(DB_FILE)
            conn.execute("INSERT INTO customers (name,phone,email) VALUES (?,?,?)",
                         (name, sanitize(f["phone"].value), sanitize(f["email"].value)))
            conn.commit(); conn.close()
            self.close_dialog(dlg); self.refresh_customers()
            if hasattr(self, "customer_dd"): self._load_customer_dropdown()
            self.snack("Customer added")
        dlg = ft.AlertDialog(
            title=ft.Text("Add Customer", size=17, weight=ft.FontWeight.BOLD),
            content=content,
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dlg)),
                ft.ElevatedButton("Save", on_click=save,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.overlay.append(dlg); dlg.open = True; self.page.update()

    def edit_customer_dialog(self, cid):
        conn = sqlite3.connect(DB_FILE)
        c    = conn.cursor()
        c.execute("SELECT id,name,phone,email FROM customers WHERE id=?", (cid,))
        data = c.fetchone(); conn.close()
        if not data: return
        f, content = self._customer_form(data)
        def save(_e):
            name = sanitize(f["name"].value)
            if not name:
                f["name"].error_text = "Required"; f["name"].update(); return
            conn = sqlite3.connect(DB_FILE)
            conn.execute("UPDATE customers SET name=?,phone=?,email=? WHERE id=?",
                         (name, sanitize(f["phone"].value), sanitize(f["email"].value), cid))
            conn.commit(); conn.close()
            self.close_dialog(dlg); self.refresh_customers()
            self.snack("Customer updated")
        dlg = ft.AlertDialog(
            title=ft.Text(f"Edit — {data[1]}", size=17, weight=ft.FontWeight.BOLD),
            content=content,
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dlg)),
                ft.ElevatedButton("Update", on_click=save,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.overlay.append(dlg); dlg.open = True; self.page.update()

    def delete_customer(self, cid):
        def confirm(_e):
            conn = sqlite3.connect(DB_FILE)
            conn.execute("DELETE FROM customers WHERE id=?", (cid,))
            conn.commit(); conn.close()
            self.close_dialog(dlg); self.refresh_customers()
            self.snack("Customer deleted", ft.Colors.RED_700)
        dlg = ft.AlertDialog(
            title=ft.Text("Delete Customer"),
            content=ft.Text("Remove this customer? Sales history is kept."),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dlg)),
                ft.ElevatedButton("Delete", on_click=confirm,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.RED_700,
                                                        color=ft.Colors.WHITE)),
            ],
        )
        self.page.overlay.append(dlg); dlg.open = True; self.page.update()

    # ─────────────────────────────────────────────────────────────────────────
    #  USERS
    # ─────────────────────────────────────────────────────────────────────────
    def users_view(self):
        if self.role != "admin":
            return ft.Column([ft.Text("Access denied", color=ft.Colors.RED_700)])
        self.user_table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(h))
                     for h in ("Username","Full Name","Role","Created","Actions")],
            border=ft.Border.all(1, ft.Colors.GREY_300), border_radius=8, data_row_max_height=52,
        )
        self.refresh_users()
        return ft.Column([
            ft.Text("User Management", size=24, weight=ft.FontWeight.BOLD),
            ft.ElevatedButton("+ Add User", icon=ft.Icons.PERSON_ADD,
                               style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                    color=ft.Colors.WHITE),
                               on_click=lambda e: self.add_user_dialog()),
            ft.Text("⚠ Password requirements: min 6 chars, 1 letter, 1 digit.",
                    size=11, color=ft.Colors.GREY_500),
            self._scrollable_table(self.user_table),
        ], expand=True, spacing=14, scroll=ft.ScrollMode.AUTO)

    def refresh_users(self, e=None):
        if not hasattr(self, "user_table"): return
        conn = sqlite3.connect(DB_FILE)
        c    = conn.cursor()
        c.execute("SELECT id,username,full_name,role,created_at FROM users ORDER BY username")
        rows = c.fetchall(); conn.close()
        self.user_table.rows.clear()
        for uid, uname, full_name, role, created in rows:
            self.user_table.rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(uname, weight=ft.FontWeight.W_500)),
                ft.DataCell(ft.Text(full_name or "—")),
                ft.DataCell(ft.Container(
                    ft.Text(role.upper(), size=10, color=ft.Colors.WHITE),
                    bgcolor=ft.Colors.BLUE_700 if role == "admin" else ft.Colors.GREEN_700,
                    border_radius=6,
                    padding=ft.padding.symmetric(horizontal=6, vertical=2),
                )),
                ft.DataCell(ft.Text((created or "")[:10], size=11, color=ft.Colors.GREY_600)),
                ft.DataCell(ft.Row([
                    ft.IconButton(ft.Icons.EDIT, data=uid,
                                  on_click=lambda e, u=uid: self.edit_user_dialog(u)),
                    ft.IconButton(ft.Icons.DELETE, icon_color=ft.Colors.RED_400,
                                  data=uid, on_click=lambda e, u=uid: self.delete_user(u)),
                ], tight=True)),
            ]))
        self.safe_update()

    def _user_form(self, data=None):
        w = self._dialog_width(520)
        f = {
            "username":  ft.TextField(label="Username *", expand=True,
                                       value=data[1] if data else ""),
            "full_name": ft.TextField(label="Full Name", expand=True,
                                       value=data[2] if data else ""),
            "role":      ft.Dropdown(label="Role *", expand=True,
                                      value=data[3] if data else "seller",
                                      options=[ft.dropdown.Option("admin","Administrator"),
                                               ft.dropdown.Option("seller","Seller")]),
            "password":  ft.TextField(label="Password (leave blank = no change)",
                                       password=True, can_reveal_password=True, expand=True),
        }
        content = ft.Column([
            ft.Row([f["username"], f["full_name"]], spacing=10),
            ft.Row([f["role"],     f["password"]],  spacing=10),
        ], spacing=10, width=w, height=150, scroll=ft.ScrollMode.AUTO)
        return f, content

    def add_user_dialog(self):
        f, content = self._user_form()
        err = ft.Text("", color=ft.Colors.RED_400)
        content.controls.append(err)

        def save(_e):
            uname = sanitize(f["username"].value)
            if not uname:
                f["username"].error_text = "Required"; f["username"].update(); return
            if not f["role"].value:
                f["role"].error_text = "Required"; f["role"].update(); return
            pwd   = f["password"].value or ""
            if not pwd:
                err.value = "Password required for new user"; err.update(); return
            strength_err = validate_password_strength(pwd)
            if strength_err:
                err.value = strength_err; err.update(); return
            try:
                conn = sqlite3.connect(DB_FILE)
                conn.execute("INSERT INTO users (username,password_hash,role,full_name) VALUES (?,?,?,?)",
                             (uname, hash_password(pwd), f["role"].value,
                              sanitize(f["full_name"].value)))
                conn.commit(); conn.close()
                log_audit(self.user_id, "ADD_USER", f"Added user {uname}")
                self.close_dialog(dlg); self.refresh_users()
                self.snack("User added")
            except sqlite3.IntegrityError:
                err.value = "Username already exists"; err.update()
            except Exception as ex:
                err.value = str(ex); err.update()

        dlg = ft.AlertDialog(
            title=ft.Text("Add User", size=17, weight=ft.FontWeight.BOLD),
            content=content,
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dlg)),
                ft.ElevatedButton("Save", on_click=save,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.overlay.append(dlg); dlg.open = True; self.page.update()

    def edit_user_dialog(self, uid):
        conn = sqlite3.connect(DB_FILE)
        c    = conn.cursor()
        c.execute("SELECT id,username,full_name,role FROM users WHERE id=?", (uid,))
        data = c.fetchone(); conn.close()
        if not data: return
        f, content = self._user_form(data)
        err = ft.Text("", color=ft.Colors.RED_400)
        content.controls.append(err)

        def save(_e):
            uname = sanitize(f["username"].value)
            if not uname:
                f["username"].error_text = "Required"; f["username"].update(); return
            pwd = f["password"].value or ""
            if pwd:
                strength_err = validate_password_strength(pwd)
                if strength_err:
                    err.value = strength_err; err.update(); return
            try:
                conn = sqlite3.connect(DB_FILE)
                if pwd:
                    conn.execute("UPDATE users SET username=?,full_name=?,role=?,password_hash=? "
                                 "WHERE id=?",
                                 (uname, sanitize(f["full_name"].value), f["role"].value,
                                  hash_password(pwd), uid))
                else:
                    conn.execute("UPDATE users SET username=?,full_name=?,role=? WHERE id=?",
                                 (uname, sanitize(f["full_name"].value), f["role"].value, uid))
                conn.commit(); conn.close()
                log_audit(self.user_id, "EDIT_USER", f"Edited user #{uid}")
                self.close_dialog(dlg); self.refresh_users()
                self.snack("User updated")
            except sqlite3.IntegrityError:
                err.value = "Username already exists"; err.update()
            except Exception as ex:
                err.value = str(ex); err.update()

        dlg = ft.AlertDialog(
            title=ft.Text(f"Edit — {data[1]}", size=17, weight=ft.FontWeight.BOLD),
            content=content,
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dlg)),
                ft.ElevatedButton("Update", on_click=save,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.overlay.append(dlg); dlg.open = True; self.page.update()

    def delete_user(self, uid):
        if uid == self.user_id:
            self.snack("Cannot delete yourself", ft.Colors.RED_700); return
        def confirm(_e):
            conn = sqlite3.connect(DB_FILE)
            conn.execute("DELETE FROM users WHERE id=?", (uid,))
            conn.commit(); conn.close()
            log_audit(self.user_id, "DELETE_USER", f"Deleted user #{uid}")
            self.close_dialog(dlg); self.refresh_users()
            self.snack("User deleted", ft.Colors.RED_700)
        dlg = ft.AlertDialog(
            title=ft.Text("Delete User"),
            content=ft.Text("Permanently delete this user account?"),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dlg)),
                ft.ElevatedButton("Delete", on_click=confirm,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.RED_700,
                                                        color=ft.Colors.WHITE)),
            ],
        )
        self.page.overlay.append(dlg); dlg.open = True; self.page.update()

    # ─────────────────────────────────────────────────────────────────────────
    #  SETTINGS
    # ─────────────────────────────────────────────────────────────────────────
    def settings_view(self):
        if self.role != "admin":
            return ft.Column([ft.Text("Access denied", color=ft.Colors.RED_700)])
        store_f = ft.TextField(label="Store Name",
                               value=get_setting("store_name", "Uptown Stationery"), width=260)
        tax_f   = ft.TextField(label="Default Tax (%)",
                               value=get_setting("tax_rate", "0"),
                               keyboard_type=ft.KeyboardType.NUMBER, width=170)
        curr_dd = ft.Dropdown(label="Currency", width=170,
                               value=get_setting("currency", "USD"),
                               options=[ft.dropdown.Option(x, x)
                                        for x in ("USD","EUR","GBP","TZS","KES")])
        cats_f  = ft.TextField(
            label="Categories (comma-separated)",
            value=get_setting("categories","Pens,Notebooks,Art Supplies,Office Equipment,Other"),
            multiline=True, min_lines=2, width=460,
        )

        def save_settings(_e):
            set_setting("store_name", sanitize(store_f.value) or "Uptown Stationery")
            set_setting("tax_rate",   sanitize(tax_f.value)   or "0")
            set_setting("currency",   curr_dd.value           or "USD")
            set_setting("categories", sanitize(cats_f.value, 1000))
            self.snack("Settings saved")

        def change_password(_e):
            old = ft.TextField(label="Current Password",     password=True,
                                can_reveal_password=True, width=280)
            nw  = ft.TextField(label="New Password",         password=True,
                                can_reveal_password=True, width=280)
            cf  = ft.TextField(label="Confirm New Password", password=True,
                                can_reveal_password=True, width=280)
            err = ft.Text("", color=ft.Colors.RED_400)

            def do_change(_ev):
                conn = sqlite3.connect(DB_FILE)
                c    = conn.cursor()
                c.execute("SELECT password_hash FROM users WHERE id=?", (self.user_id,))
                row  = c.fetchone(); conn.close()
                if not row or not verify_password(old.value or "", row[0]):
                    err.value = "Current password is incorrect"; err.update(); return
                if nw.value != cf.value:
                    err.value = "Passwords do not match"; err.update(); return
                strength_err = validate_password_strength(nw.value or "")
                if strength_err:
                    err.value = strength_err; err.update(); return
                conn = sqlite3.connect(DB_FILE)
                conn.execute("UPDATE users SET password_hash=? WHERE id=?",
                             (hash_password(nw.value), self.user_id))
                conn.commit(); conn.close()
                log_audit(self.user_id, "CHANGE_PWD", "Password changed")
                self.close_dialog(pw_dlg); self.snack("Password changed")

            pw_dlg = ft.AlertDialog(
                title=ft.Text("Change Password"),
                content=ft.Column([old, nw, cf, err], spacing=10,
                                   width=self._dialog_width(320), height=280,
                                   scroll=ft.ScrollMode.AUTO),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(pw_dlg)),
                    ft.ElevatedButton("Change", on_click=do_change,
                                       style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                            color=ft.Colors.WHITE)),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            self.page.overlay.append(pw_dlg); pw_dlg.open = True; self.page.update()

        def card(title, controls):
            return ft.Card(
                content=ft.Container(
                    ft.Column([ft.Text(title, size=14, weight=ft.FontWeight.W_600),
                               ft.Divider(height=6)] + controls, spacing=10),
                    padding=16,
                ),
                elevation=2,
            )

        return ft.Column([
            ft.Text("Settings", size=24, weight=ft.FontWeight.BOLD),
            card("Store Configuration", [
                ft.Row([store_f, tax_f, curr_dd], spacing=12, wrap=True),
                cats_f,
                ft.ElevatedButton("Save Settings", icon=ft.Icons.SAVE,
                                   on_click=save_settings,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE)),
            ]),
            card("Security", [
                ft.Text("Password policy: min 6 chars, 1 letter, 1 digit.",
                        size=11, color=ft.Colors.GREY_600),
                ft.ElevatedButton("Change My Password", icon=ft.Icons.LOCK,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE),
                                   on_click=change_password),
            ]),
            card("Database", [
                ft.Row([
                    ft.ElevatedButton("Backup DB", icon=ft.Icons.BACKUP,
                                       on_click=lambda e: self.backup_db()),
                    ft.ElevatedButton("Restore DB", icon=ft.Icons.RESTORE,
                                       on_click=lambda e: self.restore_db()),
                ], spacing=10),
            ]),
        ], spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)

    def backup_db(self):
        try:
            os.makedirs(BACKUP_DIR, exist_ok=True)
            dest = os.path.join(BACKUP_DIR,
                                f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
            shutil.copy(DB_FILE, dest)
            self.snack(f"Backup saved: {os.path.basename(dest)}")
        except Exception as ex:
            self.snack(f"Backup failed: {ex}", ft.Colors.RED_700)

    def restore_db(self):
        if not os.path.exists(BACKUP_DIR):
            self.snack("No backups directory found", ft.Colors.ORANGE_700); return
        backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.endswith(".db")], reverse=True)
        if not backups:
            self.snack("No backup files found", ft.Colors.ORANGE_700); return
        bk_list = ft.ListView(spacing=4, height=200)
        for bfile in backups[:10]:
            bk_list.controls.append(ft.ListTile(
                title=ft.Text(bfile, size=12),
                trailing=ft.TextButton("Restore",
                                        data=bfile, on_click=self._do_restore),
            ))
        dlg = ft.AlertDialog(
            title=ft.Text("Select Backup"),
            content=ft.Container(bk_list, width=380, height=220),
            actions=[ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dlg))],
        )
        self.page.overlay.append(dlg); dlg.open = True; self.page.update()

    def _do_restore(self, e):
        filename = e.control.data
        try:
            shutil.copy(os.path.join(BACKUP_DIR, filename), DB_FILE)
            for ctl in self.page.overlay:
                if isinstance(ctl, ft.AlertDialog):
                    self.close_dialog(ctl); break
            self.snack(f"Restored from {filename}")
        except Exception as ex:
            self.snack(f"Restore failed: {ex}", ft.Colors.RED_700)

    # ─────────────────────────────────────────────────────────────────────────
    #  THEME + LOGOUT
    # ─────────────────────────────────────────────────────────────────────────
    def toggle_dark_mode(self, e):
        is_dark = self.dark_mode_switch.value
        set_setting("dark_mode", "true" if is_dark else "false")
        self.page.theme_mode = ft.ThemeMode.DARK if is_dark else ft.ThemeMode.LIGHT
        self.page.update()

    def logout(self, e):
        log_audit(self.user_id, "LOGOUT", f"User {self.username} logged out")
        self.page.on_resize = None
        self.page.clean()
        self.page.add(LoginPage(lambda uid, uname, role: (
            self.page.clean(),
            self.page.add(StationeryApp(uid, uname, role)),
            self.page.update(),
        )))
        self.page.update()


# ─────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
def main(page: ft.Page):
    page.title = f"{get_setting('store_name', 'Uptown Stationery')} — Manager"
    page.theme_mode = (ft.ThemeMode.DARK
                        if get_setting("dark_mode", "false") == "true"
                        else ft.ThemeMode.LIGHT)
    page.padding  = 0
    page.spacing  = 0
    # Web-friendly: no fixed window dimensions
    page.scroll   = ft.ScrollMode.HIDDEN

    def show_login():
        page.clean()
        page.add(LoginPage(lambda uid, uname, role: (
            page.clean(),
            page.add(StationeryApp(uid, uname, role)),
            page.update(),
        )))
        page.update()

    show_login()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    ft.app(
        target=main,
        view=ft.AppView.WEB_BROWSER,   # change to ft.AppView.FLET_APP for desktop
        port=port,
        host="0.0.0.0",
    )