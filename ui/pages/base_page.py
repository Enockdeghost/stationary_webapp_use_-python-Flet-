import flet as ft
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ui.app import StationeryApp


class BasePage:
    def __init__(self, app: "StationeryApp"):
        self.app = app
        self.page = app._page          # ← now uses the app's stored page
        self.user_id = app.user_id
        self.username = app.username
        self.role = app.role

    def build(self) -> ft.Control:
        raise NotImplementedError

    def snack(self, msg: str, color=ft.Colors.GREEN_700):
        self.app.snack(msg, color)

    def close_dialog(self, dialog: ft.AlertDialog):
        dialog.open = False
        if dialog in self.page.overlay:
            self.page.overlay.remove(dialog)
        self.page.update()

    def show_dialog(self, dialog: ft.AlertDialog):
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def dialog_width(self, desktop_w: int = 520) -> int:
        if self.page and self.page.width:
            return int(min(desktop_w, self.page.width * 0.94))
        return desktop_w

    def scrollable_table(self, table: ft.DataTable, expand=True, height=None) -> ft.Container:
        from ui.components.tables import scrollable_table
        return scrollable_table(table, expand, height)