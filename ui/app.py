# ui/app.py
import flet as ft

from config import get_setting, set_setting, MOBILE_BREAKPOINT, UserRole, currency_symbol
from database.connection import fetch_one
from ui.pages.login_page import LoginPage
from ui.pages.dashboard_page import DashboardPage
from ui.pages.inventory_page import InventoryPage
from ui.pages.sales_page import SalesPage
from ui.pages.sales_history_page import SalesHistoryPage
from ui.pages.reports_page import ReportsPage
from ui.pages.stock_adjustments_page import StockAdjustmentsPage
from ui.pages.expenses_page import ExpensesPage
from ui.pages.promotions_page import PromotionsPage
from ui.pages.suppliers_page import SuppliersPage
from ui.pages.purchasing_page import PurchasingPage
from ui.pages.customers_page import CustomersPage
from ui.pages.users_page import UsersPage
from ui.pages.settings_page import SettingsPage
from utils.audit import log_audit


class StationeryApp(ft.Container):
    def __init__(self, page: ft.Page, user_id: int, username: str, role: str):
        super().__init__(expand=True)
        self._page = page
        self.user_id = user_id
        self.username = username
        self.role = role
        self._build_ui()

    def _build_ui(self):
        is_admin = (self.role == UserRole.ADMIN)

        # ── All navigation destinations (full list) ──────────────────────
        full_dest_pairs = [
            (ft.Icons.DASHBOARD,       "Dashboard",       0),
            (ft.Icons.INVENTORY_2,     "Inventory",       1),
            (ft.Icons.POINT_OF_SALE,   "Sales",           2),
            (ft.Icons.HISTORY,         "History",         3),
            (ft.Icons.ANALYTICS,       "Reports",         4),
        ]
        if is_admin:
            full_dest_pairs += [
                (ft.Icons.TUNE,                   "Stock Adj.",      5),
                (ft.Icons.ACCOUNT_BALANCE_WALLET, "Expenses",       6),
                (ft.Icons.LOCAL_OFFER,            "Promos",         7),
                (ft.Icons.LOCAL_SHIPPING,         "Suppliers",      8),
                (ft.Icons.SHOPPING_CART,          "Purchasing",     9),
                (ft.Icons.GROUP,                  "Customers",      10),
                (ft.Icons.PEOPLE,                 "Users",          11),
                (ft.Icons.SETTINGS,               "Settings",       12),
            ]

        # ── Bottom bar destinations (only 5) ─────────────────────────────
        bottom_pairs = [
            (ft.Icons.DASHBOARD,    "Dashboard"),
            (ft.Icons.INVENTORY_2,  "Inventory"),
            (ft.Icons.POINT_OF_SALE,"Sales"),
            (ft.Icons.HISTORY,      "History"),
            (ft.Icons.ANALYTICS,    "Reports"),
        ]

        # ── Hamburger drawer (will be assigned to page later) ────────────
        self.drawer = ft.NavigationDrawer(
            controls=[
                ft.Container(
                    content=ft.Text("Menu", size=20, weight=ft.FontWeight.BOLD),
                    padding=ft.padding.only(left=16, top=16, bottom=8),
                ),
                ft.Divider(),
                *[
                    ft.NavigationDrawerDestination(
                        icon=icon,
                        label=label,
                        data=str(index),
                    )
                    for icon, label, index in full_dest_pairs
                ],
            ],
            on_change=self._on_drawer_change,
        )

        # ── Bottom navigation bar (5 items) ──────────────────────────────
        self.nav_bar = ft.NavigationBar(
            selected_index=0,
            bgcolor=ft.Colors.SURFACE,
            destinations=[
                ft.NavigationBarDestination(icon=icon, label=label)
                for icon, label in bottom_pairs
            ],
            on_change=self._on_bottom_bar_change,
        )

        # ── Dark mode switch ──────────────────────────────────────────────
        self.dark_mode_switch = ft.Switch(
            value=get_setting("dark_mode", "false") == "true",
            on_change=self.toggle_dark_mode,
            label="Dark",
        )

        # ── Top bar with hamburger ───────────────────────────────────────
        self.hamburger_btn = ft.IconButton(
            icon=ft.Icons.MENU,
            on_click=self._open_drawer,
        )
        top_bar_content = ft.Row([
            self.hamburger_btn,
            ft.Text(get_setting("store_name", "Uptown Stationery"),
                    size=14, weight=ft.FontWeight.W_600),
            ft.Row([
                self.dark_mode_switch,
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
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        self.top_bar = ft.Container(
            content=top_bar_content,
            padding=ft.padding.symmetric(horizontal=16, vertical=8),
            border=ft.Border.only(bottom=ft.BorderSide(1, ft.Colors.GREY_300)),
        )

        # ── Content area ─────────────────────────────────────────────────
        self.content_area = ft.Container(expand=True, padding=16, content=ft.Text("Loading…"))
        self.content = ft.Column([
            self.top_bar,
            self.content_area,
            self.nav_bar,
        ], expand=True, spacing=0)

        # ── Put it all on the page ───────────────────────────────────────
        self._page.add(self.content)   # add the main container to page
        self._page.on_resize = self.on_page_resize

        # 🔧 Assign drawer AFTER the main UI is on the page
        self._page.drawer = self.drawer
        self._page.update()

        # Navigate to dashboard
        self.navigate_to(0)

    # ── Drawer open / close ──────────────────────────────────────────────
    def _open_drawer(self, e):
        """Show the hamburger drawer."""
        self.drawer.open = True
        self._page.update()

    def _close_drawer(self):
        """Hide the drawer."""
        self.drawer.open = False
        self._page.update()

    # ── Layout helpers ───────────────────────────────────────────────────
    @property
    def _is_mobile(self) -> bool:
        return bool(self._page and self._page.width and self._page.width < MOBILE_BREAKPOINT)

    def update_layout(self):
        if not self._page:
            return
        # Rebuild the content with correct layout if needed
        self.content.controls = [
            self.top_bar,
            self.content_area,
            self.nav_bar,
        ]
        self._page.update()

    def on_page_resize(self, e):
        self.update_layout()

    # ── Navigation logic ─────────────────────────────────────────────────
    def navigate_to(self, index: int):
        self.nav_bar.selected_index = index if index < 5 else -1
        self._set_page_content(index)
        self._page.update()

    def _set_page_content(self, index: int):
        is_admin = (self.role == UserRole.ADMIN)
        if is_admin:
            page_map = {
                0:  DashboardPage(self),
                1:  InventoryPage(self),
                2:  SalesPage(self),
                3:  SalesHistoryPage(self),
                4:  ReportsPage(self),
                5:  StockAdjustmentsPage(self),
                6:  ExpensesPage(self),
                7:  PromotionsPage(self),
                8:  SuppliersPage(self),
                9:  PurchasingPage(self),
                10: CustomersPage(self),
                11: UsersPage(self),
                12: SettingsPage(self),
            }
        else:
            page_map = {
                0: DashboardPage(self),
                1: InventoryPage(self),
                2: SalesPage(self),
                3: SalesHistoryPage(self),
                4: ReportsPage(self),
            }

        content = page_map.get(index, ft.Text("Not implemented"))
        if hasattr(content, 'build'):
            content = content.build()
        self.content_area.content = content
        self._page.update()

    def _on_drawer_change(self, e):
        if e.control.selected_index is not None:
            idx = int(e.control.selected_index.data)
            self._close_drawer()
            self.navigate_to(idx)

    def _on_bottom_bar_change(self, e):
        bottom_index = int(e.data) if e.data else 0
        self.navigate_to(bottom_index)

    # ── Other UI callbacks ───────────────────────────────────────────────
    def snack(self, msg: str, color=ft.Colors.GREEN_700):
        if not self._page:
            return
        self._page.snack_bar = ft.SnackBar(ft.Text(msg), bgcolor=color)
        self._page.snack_bar.open = True
        self._page.update()

    def toggle_dark_mode(self, e):
        is_dark = e.control.value
        set_setting("dark_mode", "true" if is_dark else "false")
        self._page.theme_mode = ft.ThemeMode.DARK if is_dark else ft.ThemeMode.LIGHT
        self._page.update()

    def logout(self, e):
        log_audit(self.user_id, "LOGOUT", f"User {self.username} logged out")
        self._page.on_resize = None
        self._page.clean()
        self._page.add(LoginPage(lambda uid, uname, role: (
            self._page.clean(),
            self._page.add(StationeryApp(self._page, uid, uname, role)),
            self._page.update(),
        )))
        self._page.update()

    # ─── PO dialog bridge ────────────────────────────────────────────────
    def open_purchase_order_dialog(self, prefill=None):
        purchasing = PurchasingPage(self)
        purchasing._open_po_dialog(prefill=prefill)


def build_app(page: ft.Page) -> ft.Control:
    # build_app now returns None because StationeryApp adds itself to the page.
    # We must return the login page initially.
    return LoginPage(lambda uid, uname, role: (
        page.clean(),
        StationeryApp(page, uid, uname, role),  # This adds itself to page
        page.update(),
    ))