import flet as ft

class BasePage:
    def __init__(self, app):
        self.app = app
        self.page = app._page          
        self.user_id = app.user_id
        self.username = app.username
        self.role = app.role

    def build(self):
        raise NotImplementedError

    def snack(self, msg, color=ft.Colors.GREEN_700):
        self.app.snack(msg, color)

    def close_dialog(self, dialog):
        dialog.open = False
        if dialog in self.page.overlay:
            self.page.overlay.remove(dialog)
        self.page.update()

    def show_dialog(self, dialog):
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def dialog_width(self, desktop_w=520):
        if self.page and self.page.width:
            return int(min(desktop_w, self.page.width * 0.94))
        return desktop_w