import os
import flet as ft
from config import init_db
from ui.app import build_app

def main(page: ft.Page):
    page.title = "Uptown Stationery"
    page.padding = 0
    page.scroll = ft.ScrollMode.HIDDEN
    page.add(build_app(page))

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 8080))
    ft.run(main, view=ft.AppView.WEB_BROWSER, port=port, host="0.0.0.0")