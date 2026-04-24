
import os
import flet as ft

from config import get_setting, init_db
from ui.app import build_app


def main(page: ft.Page) -> None:
    """Flet entry point – sets up the page and displays the login screen."""
    page.title = f"{get_setting('store_name', 'Uptown Stationery')} — Manager"
    page.theme_mode = (
        ft.ThemeMode.DARK
        if get_setting("dark_mode", "false") == "true"
        else ft.ThemeMode.LIGHT
    )
    page.padding = 0
    page.spacing = 0
    page.scroll = ft.ScrollMode.HIDDEN

    page.add(build_app(page))


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 8080))
    ft.run(
        main,
        view=ft.AppView.WEB_BROWSER,
        port=port,
        host="0.0.0.0",
    )