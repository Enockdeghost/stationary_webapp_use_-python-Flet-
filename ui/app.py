import asyncio
import flet as ft

from config import get_setting, set_setting, UserRole
from utils.audit import log_audit

from ui.pages.login_page       import LoginPage
from ui.pages.dashboard_page   import DashboardPage
from ui.pages.inventory_page   import InventoryPage
from ui.pages.sales_page       import SalesPage
from ui.pages.sales_history_page import SalesHistoryPage
from ui.pages.reports_page     import ReportsPage
from ui.pages.stock_adjustments_page import StockAdjustmentsPage
from ui.pages.expenses_page    import ExpensesPage
from ui.pages.promotions_page  import PromotionsPage
from ui.pages.suppliers_page   import SuppliersPage
from ui.pages.purchasing_page  import PurchasingPage
from ui.pages.customers_page   import CustomersPage
from ui.pages.users_page       import UsersPage
from ui.pages.settings_page    import SettingsPage

_PRIMARY        = ft.Colors.BLUE_800
_PRIMARY_LIGHT  = ft.Colors.BLUE_600
_ON_PRIMARY     = ft.Colors.WHITE
_SURFACE_LIGHT  = "#FFFFFF"
_TOPBAR_LIGHT   = "#1565C0"
_TOPBAR_DARK    = "#0D1B2A"
_NAV_BG_LIGHT   = "#FFFFFF"
_NAV_BG_DARK    = "#1A1F2E"

_BOTTOM_TABS = [
    (ft.Icons.DASHBOARD_OUTLINED,   ft.Icons.DASHBOARD,        "Dashboard"),
    (ft.Icons.INVENTORY_2_OUTLINED, ft.Icons.INVENTORY_2,      "Inventory"),
    (ft.Icons.POINT_OF_SALE_OUTLINED, ft.Icons.POINT_OF_SALE,  "Sales"),
    (ft.Icons.HISTORY,              ft.Icons.HISTORY,           "History"),
    (ft.Icons.ANALYTICS_OUTLINED,   ft.Icons.ANALYTICS,        "Reports"),
]

_PAGE_REGISTRY = [
    ("Dashboard",   ft.Icons.DASHBOARD_OUTLINED,        0,  DashboardPage,        False),
    ("Inventory",   ft.Icons.INVENTORY_2_OUTLINED,      1,  InventoryPage,        False),
    ("Sales",       ft.Icons.POINT_OF_SALE_OUTLINED,    2,  SalesPage,            False),
    ("History",     ft.Icons.HISTORY,                   3,  SalesHistoryPage,     False),
    ("Reports",     ft.Icons.ANALYTICS_OUTLINED,        4,  ReportsPage,          False),
    ("Stock Adj.",  ft.Icons.TUNE,                      5,  StockAdjustmentsPage, True),
    ("Expenses",    ft.Icons.ACCOUNT_BALANCE_WALLET_OUTLINED, 6, ExpensesPage,    True),
    ("Promotions",  ft.Icons.LOCAL_OFFER_OUTLINED,      7,  PromotionsPage,       True),
    ("Suppliers",   ft.Icons.LOCAL_SHIPPING_OUTLINED,   8,  SuppliersPage,        True),
    ("Purchasing",  ft.Icons.SHOPPING_CART_OUTLINED,    9,  PurchasingPage,       True),
    ("Customers",   ft.Icons.GROUP_OUTLINED,            10, CustomersPage,        True),
    ("Users",       ft.Icons.PEOPLE_OUTLINED,           11, UsersPage,            True),
    ("Settings",    ft.Icons.SETTINGS_OUTLINED,         12, SettingsPage,         True),
]
_BOTTOM_COUNT = 5


def _apply_theme(page: ft.Page, dark: bool):
    seed = ft.Colors.BLUE_800
    nav_theme = ft.NavigationBarTheme(
        bgcolor          = _NAV_BG_DARK  if dark else _NAV_BG_LIGHT,
        elevation        = 12,
        indicator_color  = ft.Colors.with_opacity(0.20, ft.Colors.WHITE)
                           if dark else ft.Colors.with_opacity(0.15, _PRIMARY),
        indicator_shape  = ft.StadiumBorder(),
        label_behavior   = ft.NavigationBarLabelBehavior.ALWAYS_SHOW,
        overlay_color    = {
            ft.ControlState.PRESSED: ft.Colors.with_opacity(0.12, ft.Colors.WHITE
                                     if dark else _PRIMARY),
            ft.ControlState.HOVERED: ft.Colors.with_opacity(0.06, ft.Colors.WHITE
                                     if dark else _PRIMARY),
        },
        label_text_style = {
            ft.ControlState.SELECTED: ft.TextStyle(
                weight=ft.FontWeight.W_700, size=11,
                color=ft.Colors.WHITE if dark else _PRIMARY,
            ),
            ft.ControlState.DEFAULT: ft.TextStyle(
                weight=ft.FontWeight.W_500, size=11,
            ),
        },
    )

    theme = ft.Theme(
        color_scheme_seed    = seed,
        use_material3        = True,
        navigation_bar_theme = nav_theme,
        visual_density       = ft.VisualDensity.COMFORTABLE,
    )
    dark_theme = ft.Theme(
        color_scheme_seed    = seed,
        use_material3        = True,
        navigation_bar_theme = nav_theme,
        visual_density       = ft.VisualDensity.COMFORTABLE,
    )

    page.theme       = theme
    page.dark_theme  = dark_theme
    page.theme_mode  = ft.ThemeMode.DARK if dark else ft.ThemeMode.LIGHT


class StationeryApp:
    def __init__(self, page: ft.Page, user_id: int, username: str, role: str):
        self._page    = page
        self.user_id  = user_id
        self.username = username
        self.role     = role
        self._active_index = 0
        self._is_dark = get_setting("dark_mode", "false") == "true"

        _apply_theme(page, self._is_dark)
        self._build_ui()

    def _build_ui(self):
        is_admin = self.role == UserRole.ADMIN

        menu_items: list[ft.PopupMenuItem] = []
        common_pages  = [p for p in _PAGE_REGISTRY if not p[4]]
        admin_pages   = [p for p in _PAGE_REGISTRY if p[4]] if is_admin else []

        for label, icon, index, _, _ in common_pages:
            menu_items.append(self._menu_item(label, icon, index))

        if admin_pages:
            menu_items.append(ft.PopupMenuItem())   # divider
            menu_items.append(ft.PopupMenuItem(
                content=ft.Text("ADMIN", size=10,
                                weight=ft.FontWeight.W_700,
                                color=ft.Colors.with_opacity(0.5, ft.Colors.WHITE)),
            ))
            for label, icon, index, _, _ in admin_pages:
                menu_items.append(self._menu_item(label, icon, index))

        self._hamburger = ft.PopupMenuButton(
            icon=ft.Icons.MENU_ROUNDED,
            icon_color=ft.Colors.WHITE,
            items=menu_items,
            tooltip="Navigation menu",
            bgcolor=_TOPBAR_DARK if self._is_dark else _TOPBAR_LIGHT,
            elevation=8,
            shape=ft.RoundedRectangleBorder(radius=10),
        )

        self._theme_btn = ft.IconButton(
            icon=ft.Icons.DARK_MODE_OUTLINED if not self._is_dark
                 else ft.Icons.LIGHT_MODE_OUTLINED,
            icon_color=ft.Colors.WHITE,
            icon_size=20,
            tooltip="Toggle dark mode",
            on_click=self._toggle_dark_mode,
            style=ft.ButtonStyle(
                overlay_color={ft.ControlState.HOVERED:
                               ft.Colors.with_opacity(0.15, ft.Colors.WHITE)},
            ),
        )

        avatar = ft.Container(
            content=ft.Text(
                self.username[0].upper(), size=14,
                weight=ft.FontWeight.BOLD, color=_TOPBAR_LIGHT,
            ),
            width=34, height=34,
            bgcolor=ft.Colors.WHITE,
            border_radius=17,
            alignment=ft.Alignment(0, 0),
        )

        role_badge = ft.Container(
            ft.Text(self.role.upper(), size=9,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.WHITE),
            bgcolor=ft.Colors.GREEN_700 if self.role == UserRole.ADMIN
                    else ft.Colors.ORANGE_700,
            border_radius=4,
            padding=ft.padding.symmetric(horizontal=5, vertical=2),
        )

        user_info = ft.Row(
            [
                avatar,
                ft.Column(
                    [
                        ft.Text(self.username, size=12,
                                weight=ft.FontWeight.W_600,
                                color=ft.Colors.WHITE),
                        role_badge,
                    ],
                    spacing=2,
                    tight=True,
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        logout_btn = ft.IconButton(
            icon=ft.Icons.LOGOUT_ROUNDED,
            icon_color=ft.Colors.with_opacity(0.85, ft.Colors.WHITE),
            icon_size=20,
            tooltip="Logout",
            on_click=self._logout,
            style=ft.ButtonStyle(
                overlay_color={
                    ft.ControlState.HOVERED:
                        ft.Colors.with_opacity(0.15, ft.Colors.WHITE),
                },
            ),
        )

        store_name = get_setting("store_name", "Uptown Stationery")
        brand = ft.Row(
            [
                ft.Container(
                    ft.Icon(ft.Icons.STOREFRONT_ROUNDED,
                            color=ft.Colors.WHITE, size=20),
                    bgcolor=ft.Colors.with_opacity(0.18, ft.Colors.WHITE),
                    border_radius=8, padding=6,
                ),
                ft.Column(
                    [
                        ft.Text(store_name, size=14,
                                weight=ft.FontWeight.BOLD,
                                color=ft.Colors.WHITE),
                        ft.Text("POS System", size=10,
                                color=ft.Colors.with_opacity(0.7, ft.Colors.WHITE)),
                    ],
                    spacing=0,
                    tight=True,
                ),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self._top_bar = ft.Container(
            content=ft.Row(
                [
                    ft.Row([self._hamburger, brand],
                           spacing=8,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Row([self._theme_btn,
                            ft.VerticalDivider(
                                width=1,
                                color=ft.Colors.with_opacity(0.3, ft.Colors.WHITE),
                            ),
                            user_info,
                            logout_btn],
                           spacing=8,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            gradient=ft.LinearGradient(
                begin=ft.Alignment(-1, 0),
                end=ft.Alignment(1, 0),
                colors=[_TOPBAR_LIGHT, "#1976D2"],
            ),
            padding=ft.padding.symmetric(horizontal=16, vertical=10),
            shadow=ft.BoxShadow(
                spread_radius=0, blur_radius=8,
                color=ft.Colors.with_opacity(0.25, ft.Colors.BLACK),
                offset=ft.Offset(0, 2),
            ),
        )

        self._nav_bar = ft.NavigationBar(
            selected_index = 0,
            destinations   = [
                ft.NavigationBarDestination(
                    icon          = icon_off,
                    selected_icon = icon_on,
                    label         = label,
                )
                for icon_off, icon_on, label in _BOTTOM_TABS
            ],
            on_change=self._on_bottom_change,
        )

        self._content = ft.Container(
            expand  = True,
            padding = ft.padding.all(14),
            content = ft.Column(
                [ft.ProgressRing(width=30, height=30, stroke_width=3)],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
            ),
        )

        self.content = ft.Column(
            [self._top_bar, self._content, self._nav_bar],
            expand  = True,
            spacing = 0,
        )

        self._page.on_resize = lambda e: self._page.update()
        self._navigate(0)

    def _menu_item(self, label: str, icon, index: int) -> ft.PopupMenuItem:
        return ft.PopupMenuItem(
            content=ft.Row(
                [
                    ft.Container(
                        ft.Icon(icon, size=15, color=ft.Colors.WHITE),
                        bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.WHITE),
                        border_radius=6, padding=4,
                    ),
                    ft.Text(label, size=13, color=ft.Colors.WHITE,
                            weight=ft.FontWeight.W_500),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            on_click=lambda e, idx=index: self._navigate(idx),
        )

    def _navigate(self, index: int):
        self._active_index = index
        if 0 <= index < _BOTTOM_COUNT:
            self._nav_bar.selected_index = index
        else:
            self._nav_bar.selected_index = None
        self._load_page(index)

    def _load_page(self, index: int):
        is_admin = self.role == UserRole.ADMIN

        cls = None
        for _, _, idx, page_cls, admin_only in _PAGE_REGISTRY:
            if idx == index:
                if admin_only and not is_admin:
                    break
                cls = page_cls
                break

        if cls is None:
            self._content.content = ft.Column(
                [
                    ft.Icon(ft.Icons.LOCK_OUTLINE, size=52,
                            color=ft.Colors.GREY_400),
                    ft.Text("Page not available",
                            size=16, color=ft.Colors.GREY_500),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
            )
            self._page.update()
            return

        self._content.content = ft.Column(
            [ft.ProgressRing(width=30, height=30, stroke_width=3)],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True,
        )
        self._page.update()

        page_obj = cls(self)
        self._content.content = page_obj.build()
        self._page.update()

        if hasattr(page_obj, "refresh_items"):
            async def _later():
                await asyncio.sleep(0.08)
                page_obj.refresh_items()
            self._page.run_task(_later)

    def _on_bottom_change(self, e):
        self._navigate(int(e.data) if e.data else 0)

    def _toggle_dark_mode(self, e):
        self._is_dark = not self._is_dark
        set_setting("dark_mode", "true" if self._is_dark else "false")

        self._theme_btn.icon = (
            ft.Icons.LIGHT_MODE_OUTLINED if self._is_dark
            else ft.Icons.DARK_MODE_OUTLINED
        )

        self._top_bar.gradient = ft.LinearGradient(
            begin=ft.Alignment(-1, 0),
            end=ft.Alignment(1, 0),
            colors=(
                [_TOPBAR_DARK, "#1A2744"]
                if self._is_dark else [_TOPBAR_LIGHT, "#1976D2"]
            ),
        )

        _apply_theme(self._page, self._is_dark)
        self._page.update()

    def snack(self, msg: str, color=ft.Colors.GREEN_700):
        if not self._page:
            return
        self._page.snack_bar = ft.SnackBar(
            content=ft.Row(
                [
                    ft.Icon(
                        ft.Icons.CHECK_CIRCLE_OUTLINE
                        if color == ft.Colors.GREEN_700
                        else ft.Icons.ERROR_OUTLINE,
                        color=ft.Colors.WHITE, size=18,
                    ),
                    ft.Text(msg, color=ft.Colors.WHITE, expand=True),
                ],
                spacing=10,
            ),
            bgcolor=color,
            duration=3000,
            show_close_icon=True,
            close_icon_color=ft.Colors.WHITE,
        )
        self._page.snack_bar.open = True
        self._page.update()

    def _logout(self, e):
        log_audit(self.user_id, "LOGOUT", f"User {self.username} logged out")
        self._page.on_resize = None
        self._page.clean()
        self._page.add(LoginPage(lambda uid, uname, role: _launch(
            self._page, uid, uname, role
        )))
        self._page.update()

    def open_purchase_order_dialog(self, prefill=None):
        PurchasingPage(self)._open_po_dialog(prefill=prefill)


def _launch(page: ft.Page, uid: int, uname: str, role: str):
    page.clean()
    app = StationeryApp(page, uid, uname, role)
    page.add(app.content)
    page.update()


def build_app(page: ft.Page) -> ft.Control:
    _apply_theme(page, get_setting("dark_mode", "false") == "true")
    return LoginPage(lambda uid, uname, role: _launch(page, uid, uname, role))