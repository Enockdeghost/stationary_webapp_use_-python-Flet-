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

        full_dest_pairs = [
            ("Dashboard",  ft.Icons.DASHBOARD,       0),
            ("Inventory",  ft.Icons.INVENTORY_2,     1),
            ("Sales",      ft.Icons.POINT_OF_SALE,   2),
            ("History",    ft.Icons.HISTORY,         3),
            ("Reports",    ft.Icons.ANALYTICS,       4),
        ]
        if is_admin:
            full_dest_pairs += [
                ("Stock Adj.",    ft.Icons.TUNE,                   5),
                ("Expenses",      ft.Icons.ACCOUNT_BALANCE_WALLET, 6),
                ("Promos",        ft.Icons.LOCAL_OFFER,            7),
                ("Suppliers",     ft.Icons.LOCAL_SHIPPING,         8),
                ("Purchasing",    ft.Icons.SHOPPING_CART,          9),
                ("Customers",     ft.Icons.GROUP,                  10),
                ("Users",         ft.Icons.PEOPLE,                 11),
                ("Settings",      ft.Icons.SETTINGS,               12),
            ]

        bottom_pairs = [
            ("Dashboard", ft.Icons.DASHBOARD),
            ("Inventory", ft.Icons.INVENTORY_2),
            ("Sales",     ft.Icons.POINT_OF_SALE),
            ("History",   ft.Icons.HISTORY),
            ("Reports",   ft.Icons.ANALYTICS),
        ]

        menu_items = []
        for label, icon, index in full_dest_pairs:
            menu_items.append(
                ft.PopupMenuItem(
                    content=ft.Text(label),
                    icon=icon,
                    on_click=lambda e, idx=index: self.navigate_to(idx),
                )
            )

        self.nav_bar = ft.NavigationBar(
            selected_index=0,
            bgcolor=ft.Colors.SURFACE,
            destinations=[
                ft.NavigationBarDestination(icon=icon, label=label)
                for label, icon in bottom_pairs
            ],
            on_change=self._on_bottom_bar_change,
        )

        self.dark_mode_switch = ft.Switch(
            value=get_setting("dark_mode", "false") == "true",
            on_change=self.toggle_dark_mode,
            label="Dark",
        )

        self.hamburger_btn = ft.PopupMenuButton(
            icon=ft.Icons.MENU,
            items=menu_items,
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

        self.content_area = ft.Container(expand=True, padding=16, content=ft.Text("Loading…"))
        self.content = ft.Column([
            self.top_bar,
            self.content_area,
            self.nav_bar,
        ], expand=True, spacing=0)

        self._page.on_resize = self.on_page_resize
        self.navigate_to(0)

    @property
    def _is_mobile(self) -> bool:
        return bool(self._page and self._page.width and self._page.width < MOBILE_BREAKPOINT)

    def update_layout(self):
        if not self._page:
            return
        self.content.controls = [
            self.top_bar,
            self.content_area,
            self.nav_bar,
        ]
        self._page.update()

    def on_page_resize(self, e):
        self.update_layout()

    def navigate_to(self, index: int):
        if 0 <= index < len(self.nav_bar.destinations):
            self.nav_bar.selected_index = index
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

    def _on_bottom_bar_change(self, e):
        bottom_index = int(e.data) if e.data else 0
        self.navigate_to(bottom_index)

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

    def open_purchase_order_dialog(self, prefill=None):
        purchasing = PurchasingPage(self)
        purchasing._open_po_dialog(prefill=prefill)


def build_app(page: ft.Page) -> ft.Control:
    return LoginPage(lambda uid, uname, role: (
        page.clean(),
        page.add(StationeryApp(page, uid, uname, role)),
        page.update(),
    ))