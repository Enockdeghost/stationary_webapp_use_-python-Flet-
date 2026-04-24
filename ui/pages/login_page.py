# ui/pages/login_page.py
import flet as ft
import time

from config import LOCKOUT_SECONDS, MAX_LOGIN_ATTEMPTS
from security.auth import _login_attempts, check_rate_limit
from security.validation import sanitize
from services.auth_service import AuthService


class LoginPage(ft.Container):
    def __init__(self, on_login_success):
        super().__init__(expand=True)
        self.on_login_success = on_login_success
        self.auth_service = AuthService()

        self.username_field = ft.TextField(
            label="Username",
            width=320,
            height=55,
            border_radius=10,
            prefix_icon=ft.Icons.PERSON,
            on_submit=self.do_login,
        )
        self.password_field = ft.TextField(
            label="Password",
            password=True,
            can_reveal_password=True,
            width=320,
            height=55,
            border_radius=10,
            prefix_icon=ft.Icons.LOCK,
            on_submit=self.do_login,
        )
        self.error_text = ft.Text("", color=ft.Colors.RED_400, size=13)
        self.login_btn = ft.ElevatedButton(
            "Login",
            width=320,
            height=50,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=10),
                bgcolor=ft.Colors.BLUE_700,
                color=ft.Colors.WHITE,
            ),
            on_click=self.do_login,
        )

        store_name = self._get_store_name()
        self.content = self._build_content(store_name)

    def _get_store_name(self) -> str:
        from config import get_setting
        return get_setting("store_name", "Uptown Stationery")

    def _build_content(self, store_name: str) -> ft.Container:
        return ft.Container(
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
                padding=40,
                border_radius=16,
                bgcolor=ft.Colors.WHITE,
                shadow=ft.BoxShadow(blur_radius=20, color=ft.Colors.BLACK12,
                                    offset=ft.Offset(0, 4)),
                width=420,
            ),
            expand=True,
            alignment=ft.Alignment(0, 0),
        )

    def do_login(self, e):
        username = sanitize(self.username_field.value or "")
        password = (self.password_field.value or "").strip()

        user_id, uname, role, error = self.auth_service.authenticate(username, password)

        if error:
            self.error_text.value = error
            # Check if temporarily locked out to disable button
            allowed, _ = check_rate_limit(username)
            self.login_btn.disabled = not allowed
            self.update()
            return

        self.on_login_success(user_id, uname, role)