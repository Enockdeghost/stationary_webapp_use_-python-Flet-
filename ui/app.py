import flet as ft
import asyncio

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

# ── Page registry ──────────────────────────────────────────────────────────────
#  (label, icon, index, class, admin-only)
PAGE_REGISTRY = [
    ("Dashboard",  ft.Icons.DASHBOARD,              0,  DashboardPage,         False),
    ("Inventory",  ft.Icons.INVENTORY_2,            1,  InventoryPage,         False),
    ("Sales",      ft.Icons.POINT_OF_SALE,          2,  SalesPage,             False),
    ("History",    ft.Icons.HISTORY,                3,  SalesHistoryPage,      False),
    ("Reports",    ft.Icons.ANALYTICS,              4,  ReportsPage,           False),
    ("Stock Adj.", ft.Icons.TUNE,                   5,  StockAdjustmentsPage,  True),
    ("Expenses",   ft.Icons.ACCOUNT_BALANCE_WALLET, 6,  ExpensesPage,          True),
    ("Promos",     ft.Icons.LOCAL_OFFER,            7,  PromotionsPage,        True),
    ("Suppliers",  ft.Icons.LOCAL_SHIPPING,         8,  SuppliersPage,         True),
    ("Purchasing", ft.Icons.SHOPPING_CART,          9,  PurchasingPage,        True),
    ("Customers",  ft.Icons.GROUP,                  10, CustomersPage,         True),
    ("Users",      ft.Icons.PEOPLE,                 11, UsersPage,             True),
    ("Settings",   ft.Icons.SETTINGS,               12, SettingsPage,          True),
]

BOTTOM_NAV_COUNT = 5   # first N entries go into the bottom bar


class StationeryApp(ft.Container):
    def __init__(self, page: ft.Page, user_id: int, username: str, role: str):
        super().__init__(expand=True)
        self._page = page
        self.user_id = user_id
        self.username = username
        self.role = role
        self.current_page_obj = None
        self._active_index = 0
        self._build_ui()

    # ── build ──────────────────────────────────────────────────────────────────

    def _build_ui(self):
        is_admin = (self.role == UserRole.ADMIN)
        visible_pages = [p for p in PAGE_REGISTRY if not p[4] or is_admin]

        # ── hamburger menu (all accessible pages with icons) ─────────────────
        menu_items = []
        for label, icon, index, _, admin_only in visible_pages:
            menu_items.append(
                ft.PopupMenuItem(
                    content=ft.Row(
                        [
                            ft.Icon(icon, size=16, color=ft.Colors.BLUE_700),
                            ft.Text(label, size=13),
                        ],
                        spacing=10,
                    ),
                    on_click=lambda e, idx=index: self.navigate_to(idx),
                )
            )
            # divider before admin section
            if index == BOTTOM_NAV_COUNT - 1 and is_admin:
                menu_items.append(ft.PopupMenuItem())   # separator

        # ── bottom nav bar (first 5 pages only) ──────────────────────────────
        bottom_pages = [p for p in PAGE_REGISTRY if p[2] < BOTTOM_NAV_COUNT]
        self.nav_bar = ft.NavigationBar(
            selected_index=0,
            bgcolor=ft.Colors.SURFACE,
            elevation=8,
            destinations=[
                ft.NavigationBarDestination(icon=icon, label=label)
                for label, icon, *_ in bottom_pages
            ],
            on_change=self._on_bottom_bar_change,
        )

        self.dark_mode_switch = ft.Switch(
            value=get_setting("dark_mode", "false") == "true",
            on_change=self.toggle_dark_mode,
            label="Dark",
        )

        # ── hamburger button ──────────────────────────────────────────────────
        self.hamburger_btn = ft.PopupMenuButton(
            icon=ft.Icons.MENU_ROUNDED,
            items=menu_items,
            tooltip="Navigation menu",
        )

        # ── top bar ───────────────────────────────────────────────────────────
        store_name = get_setting("store_name", "Uptown Stationery")
        self._store_name_text = ft.Text(
            store_name, size=15, weight=ft.FontWeight.BOLD,
            color=ft.Colors.BLUE_700,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        top_left = ft.Row(
            [self.hamburger_btn, self._store_name_text],
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        top_right = ft.Row(
            [
                self.dark_mode_switch,
                ft.VerticalDivider(width=1, color=ft.Colors.GREY_300),
                ft.CircleAvatar(
                    content=ft.Text(
                        self.username[0].upper(), size=13,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.WHITE,
                    ),
                    bgcolor=ft.Colors.BLUE_700,
                    radius=16,
                ),
                ft.Column(
                    [
                        ft.Text(self.username, size=12,
                                weight=ft.FontWeight.W_600),
                        ft.Text(self.role, size=10,
                                color=ft.Colors.GREY_500),
                    ],
                    spacing=0,
                    tight=True,
                ),
                ft.IconButton(
                    icon=ft.Icons.LOGOUT_ROUNDED,
                    tooltip="Logout",
                    on_click=self.logout,
                    icon_color=ft.Colors.RED_400,
                    icon_size=20,
                    style=ft.ButtonStyle(
                        overlay_color={
                            ft.ControlState.HOVERED: ft.Colors.RED_50,
                        }
                    ),
                ),
            ],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self.top_bar = ft.Container(
            content=ft.Row(
                [top_left, top_right],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.symmetric(horizontal=14, vertical=6),
            # FIX: use lowercase ft.border.only (ft.Border.only was a bug)
            border=ft.border.only(
                bottom=ft.BorderSide(1, ft.Colors.GREY_300)
            ),
        )

        # ── scrollable content area ───────────────────────────────────────────
        self.content_area = ft.Container(
            expand=True,
            padding=ft.padding.all(12),
            content=self._loading_spinner(),
        )

        # ── root layout ───────────────────────────────────────────────────────
        self.content = ft.Column(
            controls=[
                self.top_bar,
                self.content_area,
                self.nav_bar,
            ],
            expand=True,
            spacing=0,
        )

        self._page.on_resize = self.on_page_resize
        self.navigate_to(0)

    # ── helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _loading_spinner() -> ft.Control:
        return ft.Column(
            [ft.ProgressRing(width=32, height=32, stroke_width=3)],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True,
        )

    @property
    def _is_mobile(self) -> bool:
        return bool(
            self._page and self._page.width
            and self._page.width < MOBILE_BREAKPOINT
        )

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

    # ── navigation ─────────────────────────────────────────────────────────────

    def navigate_to(self, index: int):
        self._active_index = index

        # FIX: only update bottom bar for the 5 tabs it actually has.
        # Setting selected_index to 5-12 caused blank / broken pages.
        if 0 <= index < BOTTOM_NAV_COUNT:
            self.nav_bar.selected_index = index
        else:
            self.nav_bar.selected_index = None   # deselect when on admin page

        self._set_page_content(index)
        self._page.update()

    def _make_page(self, index: int):
        """Instantiate only the page being navigated to (lazy, not all at once)."""
        is_admin = (self.role == UserRole.ADMIN)
        for label, icon, idx, cls, admin_only in PAGE_REGISTRY:
            if idx == index:
                if admin_only and not is_admin:
                    return None
                return cls(self)
        return None

    def _set_page_content(self, index: int):
        # Show spinner immediately so content area is never blank
        self.content_area.content = self._loading_spinner()
        self._page.update()

        page_obj = self._make_page(index)
        if page_obj is None:
            self.content_area.content = ft.Column(
                [
                    ft.Icon(ft.Icons.LOCK_OUTLINE, size=48,
                            color=ft.Colors.GREY_400),
                    ft.Text("Page not available", color=ft.Colors.GREY_500,
                            size=16),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
            )
            self._page.update()
            return

        built_content = page_obj.build()
        self.content_area.content = built_content
        self.current_page_obj = page_obj

        if hasattr(page_obj, "refresh_items"):
            self._page.run_task(self._delayed_refresh)

        self._page.update()

    async def _delayed_refresh(self):
        await asyncio.sleep(0.1)
        if self.current_page_obj and hasattr(self.current_page_obj, "refresh_items"):
            self.current_page_obj.refresh_items()

    def _on_bottom_bar_change(self, e):
        bottom_index = int(e.data) if e.data else 0
        self.navigate_to(bottom_index)

    # ── ui helpers ─────────────────────────────────────────────────────────────

    def snack(self, msg: str, color=ft.Colors.GREEN_700):
        if not self._page:
            return
        self._page.snack_bar = ft.SnackBar(
            ft.Text(msg, color=ft.Colors.WHITE),
            bgcolor=color,
            duration=3000,
        )
        self._page.snack_bar.open = True
        self._page.update()

    def toggle_dark_mode(self, e):
        is_dark = e.control.value
        set_setting("dark_mode", "true" if is_dark else "false")
        self._page.theme_mode = (
            ft.ThemeMode.DARK if is_dark else ft.ThemeMode.LIGHT
        )
        # Update top-bar border to match new theme
        self.top_bar.border = ft.border.only(
            bottom=ft.BorderSide(
                1, ft.Colors.GREY_700 if is_dark else ft.Colors.GREY_300
            )
        )
        self._page.update()

    def logout(self, e):
        log_audit(self.user_id, "LOGOUT", f"User {self.username} logged out")
        self._page.on_resize = None
        self._page.clean()
        self._page.add(
            LoginPage(
                lambda uid, uname, role: (
                    self._page.clean(),
                    self._page.add(StationeryApp(self._page, uid, uname, role)),
                    self._page.update(),
                )
            )
        )
        self._page.update()

    def open_purchase_order_dialog(self, prefill=None):
        purchasing = PurchasingPage(self)
        purchasing._open_po_dialog(prefill=prefill)


def build_app(page: ft.Page) -> ft.Control:
    return LoginPage(
        lambda uid, uname, role: (
            page.clean(),
            page.add(StationeryApp(page, uid, uname, role)),
            page.update(),
        )
    )