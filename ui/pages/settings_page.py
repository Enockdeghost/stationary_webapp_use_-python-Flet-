# ui/pages/settings_page.py
import flet as ft
import os
import shutil
from datetime import datetime

from config import UserRole, get_setting, set_setting, BACKUP_DIR, DB_FILE
from ui.pages.base_page import BasePage
from security.validation import sanitize, validate_password_strength
from security.auth import verify_password, hash_password
from utils.audit import log_audit
from database.connection import fetch_one


class SettingsPage(BasePage):
    def build(self) -> ft.Control:
        if self.role != UserRole.ADMIN:
            return ft.Column([ft.Text("Access denied", color=ft.Colors.RED_700)])

        store_f = ft.TextField(
            label="Store Name",
            value=get_setting("store_name", "Uptown Stationery"),
            width=260
        )
        tax_f = ft.TextField(
            label="Default Tax (%)",
            value=get_setting("tax_rate", "0"),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=170
        )
        curr_dd = ft.Dropdown(
            label="Currency",
            width=170,
            value=get_setting("currency", "USD"),
            options=[ft.dropdown.Option(x, x) for x in ("USD", "EUR", "GBP", "TZS", "KES")]
        )
        cats_f = ft.TextField(
            label="Categories (comma-separated)",
            value=get_setting("categories", "Pens,Notebooks,Art Supplies,Office Equipment,Other"),
            multiline=True,
            min_lines=2,
            width=460,
        )

        def save_settings(_e):
            set_setting("store_name", sanitize(store_f.value) or "Uptown Stationery")
            set_setting("tax_rate", sanitize(tax_f.value) or "0")
            set_setting("currency", curr_dd.value or "USD")
            set_setting("categories", sanitize(cats_f.value, 1000))
            self.snack("Settings saved")

        def change_password(_e):
            old = ft.TextField(label="Current Password", password=True, can_reveal_password=True, width=280)
            new = ft.TextField(label="New Password", password=True, can_reveal_password=True, width=280)
            confirm = ft.TextField(label="Confirm New Password", password=True, can_reveal_password=True, width=280)
            err = ft.Text("", color=ft.Colors.RED_400)

            def do_change(_ev):
                user = fetch_one("SELECT password_hash FROM users WHERE id=?", (self.user_id,))
                if not user or not verify_password(old.value or "", user["password_hash"]):
                    err.value = "Current password is incorrect"
                    err.update()
                    return
                if new.value != confirm.value:
                    err.value = "Passwords do not match"
                    err.update()
                    return
                strength_err = validate_password_strength(new.value or "")
                if strength_err:
                    err.value = strength_err
                    err.update()
                    return
                import sqlite3
                from config import DB_FILE
                conn = sqlite3.connect(DB_FILE)
                conn.execute("UPDATE users SET password_hash=? WHERE id=?",
                             (hash_password(new.value), self.user_id))
                conn.commit()
                conn.close()
                log_audit(self.user_id, "CHANGE_PWD", "Password changed")
                self.close_dialog(pw_dlg)
                self.snack("Password changed")

            pw_dlg = ft.AlertDialog(
                title=ft.Text("Change Password"),
                content=ft.Column([old, new, confirm, err], spacing=10,
                                   width=self.dialog_width(320), height=280,
                                   scroll=ft.ScrollMode.AUTO),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(pw_dlg)),
                    ft.ElevatedButton("Change", on_click=do_change,
                                       style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                            color=ft.Colors.WHITE)),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            self.show_dialog(pw_dlg)

        def backup_db(_e):
            try:
                os.makedirs(BACKUP_DIR, exist_ok=True)
                dest = os.path.join(BACKUP_DIR, f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
                shutil.copy(DB_FILE, dest)
                self.snack(f"Backup saved: {os.path.basename(dest)}")
            except Exception as ex:
                self.snack(f"Backup failed: {ex}", ft.Colors.RED_700)

        def restore_db(_e):
            if not os.path.exists(BACKUP_DIR):
                self.snack("No backups directory found", ft.Colors.ORANGE_700)
                return
            backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.endswith(".db")], reverse=True)
            if not backups:
                self.snack("No backup files found", ft.Colors.ORANGE_700)
                return

            bk_list = ft.ListView(spacing=4, height=200)
            for bfile in backups[:10]:
                bk_list.controls.append(ft.ListTile(
                    title=ft.Text(bfile, size=12),
                    trailing=ft.TextButton("Restore", data=bfile, on_click=self._do_restore),
                ))

            dlg = ft.AlertDialog(
                title=ft.Text("Select Backup"),
                content=ft.Container(bk_list, width=380, height=220),
                actions=[ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dlg))],
            )
            self.show_dialog(dlg)

        def card(title, controls):
            return ft.Card(
                content=ft.Container(
                    ft.Column([ft.Text(title, size=14, weight=ft.FontWeight.W_600),
                               ft.Divider(height=6)] + controls, spacing=10),
                    padding=16,
                ),
                elevation=2,
            )

        return ft.Column([
            ft.Text("Settings", size=24, weight=ft.FontWeight.BOLD),
            card("Store Configuration", [
                ft.Row([store_f, tax_f, curr_dd], spacing=12, wrap=True),
                cats_f,
                ft.ElevatedButton("Save Settings", icon=ft.Icons.SAVE,
                                   on_click=save_settings,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE)),
            ]),
            card("Security", [
                ft.Text("Password policy: min 6 chars, 1 letter, 1 digit.",
                        size=11, color=ft.Colors.GREY_600),
                ft.ElevatedButton("Change My Password", icon=ft.Icons.LOCK,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE),
                                   on_click=change_password),
            ]),
            card("Database", [
                ft.Row([
                    ft.ElevatedButton("Backup DB", icon=ft.Icons.BACKUP, on_click=backup_db),
                    ft.ElevatedButton("Restore DB", icon=ft.Icons.RESTORE, on_click=restore_db),
                ], spacing=10),
            ]),
        ], spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)

    def _do_restore(self, e):
        filename = e.control.data
        try:
            shutil.copy(os.path.join(BACKUP_DIR, filename), DB_FILE)
            for ctl in self.page.overlay:
                if isinstance(ctl, ft.AlertDialog):
                    self.close_dialog(ctl)
                    break
            self.snack(f"Restored from {filename}")
        except Exception as ex:
            self.snack(f"Restore failed: {ex}", ft.Colors.RED_700)