import flet as ft

from config import UserRole
from database.connection import fetch_all, execute_query, fetch_one
from ui.pages.base_page import BasePage
from security.validation import sanitize, validate_password_strength
from security.auth import hash_password
from utils.audit import log_audit
from ui.components.dialogs import confirm_dialog


class UsersPage(BasePage):
    def __init__(self, app):
        super().__init__(app)
        self.user_table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(h))
                     for h in ("Username","Full Name","Role","Created","Actions")],
            border=ft.Border.all(1, ft.Colors.GREY_300),
            border_radius=8,
            data_row_max_height=52,
        )

    def build(self) -> ft.Control:
        if self.role != UserRole.ADMIN:
            return ft.Column([ft.Text("Access denied", color=ft.Colors.RED_700)])

        self._refresh_users()

        return ft.Column([
            ft.Text("User Management", size=24, weight=ft.FontWeight.BOLD),
            ft.ElevatedButton("+ Add User", icon=ft.Icons.PERSON_ADD,
                               style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                    color=ft.Colors.WHITE),
                               on_click=lambda e: self._add_user_dialog()),
            ft.Text("⚠ Password requirements: min 6 chars, 1 letter, 1 digit.",
                    size=11, color=ft.Colors.GREY_500),
            self.scrollable_table(self.user_table),
        ], expand=True, spacing=14, scroll=ft.ScrollMode.AUTO)

    def _refresh_users(self, e=None):
        rows = fetch_all("SELECT id, username, full_name, role, created_at FROM users ORDER BY username")
        self.user_table.rows.clear()
        for uid, uname, full_name, role, created in rows:
            self.user_table.rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(uname, weight=ft.FontWeight.W_500)),
                ft.DataCell(ft.Text(full_name or "—")),
                ft.DataCell(ft.Container(
                    ft.Text(role.upper(), size=10, color=ft.Colors.WHITE),
                    bgcolor=ft.Colors.BLUE_700 if role == UserRole.ADMIN else ft.Colors.GREEN_700,
                    border_radius=6,
                    padding=ft.padding.symmetric(horizontal=6, vertical=2),
                )),
                ft.DataCell(ft.Text((created or "")[:10], size=11, color=ft.Colors.GREY_600)),
                ft.DataCell(ft.Row([
                    ft.IconButton(ft.Icons.EDIT, data=uid,
                                  on_click=lambda e, u=uid: self._edit_user_dialog(u)),
                    ft.IconButton(ft.Icons.DELETE, icon_color=ft.Colors.RED_400,
                                  data=uid, on_click=lambda e, u=uid: self._delete_user(u)),
                ], tight=True)),
            ]))
        self.page.update()

    def _user_form_fields(self, data=None):
        return {
            "username": ft.TextField(label="Username *", expand=True,
                                     value=data["username"] if data else ""),
            "full_name": ft.TextField(label="Full Name", expand=True,
                                      value=data["full_name"] if data else ""),
            "role": ft.Dropdown(label="Role *", expand=True,
                                value=data["role"] if data else UserRole.SELLER,
                                options=[ft.dropdown.Option(UserRole.ADMIN, "Administrator"),
                                         ft.dropdown.Option(UserRole.SELLER, "Seller")]),
            "password": ft.TextField(label="Password (leave blank = no change)",
                                     password=True, can_reveal_password=True, expand=True),
        }

    def _user_form_content(self, fields):
        return ft.Column([
            ft.Row([fields["username"], fields["full_name"]], spacing=10),
            ft.Row([fields["role"], fields["password"]], spacing=10),
        ], spacing=10, width=self.dialog_width(520), height=150, scroll=ft.ScrollMode.AUTO)

    def _add_user_dialog(self):
        fields = self._user_form_fields()
        err = ft.Text("", color=ft.Colors.RED_400)

        def save(_e):
            uname = sanitize(fields["username"].value)
            if not uname:
                fields["username"].error_text = "Required"
                fields["username"].update()
                return
            if not fields["role"].value:
                fields["role"].error_text = "Required"
                fields["role"].update()
                return

            pwd = fields["password"].value or ""
            if not pwd:
                err.value = "Password required for new user"
                err.update()
                return

            strength_err = validate_password_strength(pwd)
            if strength_err:
                err.value = strength_err
                err.update()
                return

            try:
                execute_query(
                    "INSERT INTO users (username, password_hash, role, full_name) VALUES (?, ?, ?, ?)",
                    (uname, hash_password(pwd), fields["role"].value, sanitize(fields["full_name"].value))
                )
                log_audit(self.user_id, "ADD_USER", f"Added user {uname}")
                self.close_dialog(dlg)
                self._refresh_users()
                self.snack("User added")
            except Exception as ex:
                err.value = "Username already exists" if "UNIQUE" in str(ex) else str(ex)
                err.update()

        content = self._user_form_content(fields)
        content.controls.append(err)
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
        self.show_dialog(dlg)

    def _edit_user_dialog(self, uid):
        data = fetch_one("SELECT id, username, full_name, role FROM users WHERE id=?", (uid,))
        if not data:
            return

        fields = self._user_form_fields(data)
        err = ft.Text("", color=ft.Colors.RED_400)

        def save(_e):
            uname = sanitize(fields["username"].value)
            if not uname:
                fields["username"].error_text = "Required"
                fields["username"].update()
                return

            pwd = fields["password"].value or ""
            if pwd:
                strength_err = validate_password_strength(pwd)
                if strength_err:
                    err.value = strength_err
                    err.update()
                    return
                execute_query(
                    "UPDATE users SET username=?, full_name=?, role=?, password_hash=? WHERE id=?",
                    (uname, sanitize(fields["full_name"].value), fields["role"].value,
                     hash_password(pwd), uid)
                )
            else:
                execute_query(
                    "UPDATE users SET username=?, full_name=?, role=? WHERE id=?",
                    (uname, sanitize(fields["full_name"].value), fields["role"].value, uid)
                )
            log_audit(self.user_id, "EDIT_USER", f"Edited user #{uid}")
            self.close_dialog(dlg)
            self._refresh_users()
            self.snack("User updated")

        content = self._user_form_content(fields)
        content.controls.append(err)
        dlg = ft.AlertDialog(
            title=ft.Text(f"Edit — {data['username']}", size=17, weight=ft.FontWeight.BOLD),
            content=content,
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dlg)),
                ft.ElevatedButton("Update", on_click=save,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.show_dialog(dlg)

    def _delete_user(self, uid):
        if uid == self.user_id:
            self.snack("Cannot delete yourself", ft.Colors.RED_700)
            return

        def confirm():
            execute_query("DELETE FROM users WHERE id=?", (uid,))
            log_audit(self.user_id, "DELETE_USER", f"Deleted user #{uid}")
            self._refresh_users()
            self.snack("User deleted", ft.Colors.RED_700)

        dlg = confirm_dialog(
            self.page,
            "Delete User",
            "Permanently delete this user account?",
            confirm,
            delete_text="Delete"
        )
        self.show_dialog(dlg)