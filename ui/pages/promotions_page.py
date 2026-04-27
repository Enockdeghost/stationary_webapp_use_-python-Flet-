import flet as ft
from datetime import datetime

from config import UserRole, currency_symbol
from database.connection import fetch_all, execute_query, fetch_one          # added fetch_one
from ui.pages.base_page import BasePage
from security.validation import sanitize, safe_float
from ui.components.dialogs import confirm_dialog


class PromotionsPage(BasePage):
    def __init__(self, app):
        super().__init__(app)
        self.promo_table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(h)) for h in
                     ("Name","Code","Type","Value","Min.","Start","End","Active","Actions")],
            border=ft.Border.all(1, ft.Colors.GREY_300),
            border_radius=8,
            data_row_max_height=50,
        )

    def build(self) -> ft.Control:
        if self.role != UserRole.ADMIN:
            return ft.Column([ft.Text("Access denied", color=ft.Colors.RED_700)])

        self._refresh_promo_table()

        def add_promo(e):
            self._add_promotion_dialog()

        return ft.Column([
            ft.Text("Promotions & Discounts", size=24, weight=ft.FontWeight.BOLD),
            ft.Text("Active promotions appear at POS for quick application.",
                    size=12, color=ft.Colors.GREY_600),
            ft.Row([
                ft.ElevatedButton("+ New Promotion", icon=ft.Icons.ADD, on_click=add_promo,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE)),
                ft.OutlinedButton("Refresh", icon=ft.Icons.REFRESH,
                                   on_click=lambda e: self._refresh_promo_table()),
            ], spacing=10),
            self.scrollable_table(self.promo_table),
        ], expand=True, spacing=14, scroll=ft.ScrollMode.AUTO)

    def _refresh_promo_table(self, e=None):
        rows = fetch_all("""
            SELECT id, name, code, promo_type, value, min_purchase,
                   start_date, end_date, active
            FROM promotions ORDER BY created_at DESC
        """)
        sym = currency_symbol()
        self.promo_table.rows.clear()
        for r in rows:
            label = f"{int(r['value'])}%" if r["promo_type"] == "percentage" else f"{sym}{r['value']:.2f}"
            self.promo_table.rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(r["name"], weight=ft.FontWeight.W_500)),
                ft.DataCell(ft.Container(
                    ft.Text(r["code"] or "—", size=10,
                            color=ft.Colors.WHITE if r["code"] else ft.Colors.GREY_500),
                    bgcolor=ft.Colors.PURPLE_700 if r["code"] else None,
                    border_radius=6,
                    padding=ft.padding.symmetric(horizontal=5, vertical=2) if r["code"] else None,
                )),
                ft.DataCell(ft.Text("% Off" if r["promo_type"] == "percentage" else "Fixed")),
                ft.DataCell(ft.Text(label, color=ft.Colors.GREEN_700, weight=ft.FontWeight.W_600)),
                ft.DataCell(ft.Text(f"{sym}{r['min_purchase']:.2f}" if r["min_purchase"] else "—")),
                ft.DataCell(ft.Text(r["start_date"] or "—", size=11)),
                ft.DataCell(ft.Text(r["end_date"] or "—", size=11)),
                ft.DataCell(ft.Container(
                    ft.Text("ACTIVE" if r["active"] else "OFF", size=10, color=ft.Colors.WHITE),
                    bgcolor=ft.Colors.GREEN_700 if r["active"] else ft.Colors.GREY_500,
                    border_radius=6,
                    padding=ft.padding.symmetric(horizontal=5, vertical=2),
                )),
                ft.DataCell(ft.Row([
                    ft.IconButton(ft.Icons.TOGGLE_ON if r["active"] else ft.Icons.TOGGLE_OFF,
                                  icon_color=ft.Colors.GREEN_700 if r["active"] else ft.Colors.GREY_500,
                                  data=r["id"], on_click=self._toggle_promo),
                    ft.IconButton(ft.Icons.DELETE, icon_color=ft.Colors.RED_400,
                                  data=r["id"], on_click=self._delete_promo),
                ], tight=True)),
            ]))
        self.page.update()

    def _add_promotion_dialog(self):
        nm = ft.TextField(label="Promo Name *", expand=True)
        cod = ft.TextField(label="Code (optional)", expand=True)
        pty = ft.Dropdown(label="Type *", expand=True, value="percentage",
                           options=[ft.dropdown.Option("percentage", "% Off"),
                                    ft.dropdown.Option("fixed", "Fixed Off")])
        val = ft.TextField(label="Value *", expand=True, keyboard_type=ft.KeyboardType.NUMBER)
        minp = ft.TextField(label="Min. Purchase", expand=True,
                            keyboard_type=ft.KeyboardType.NUMBER, value="0")
        sd = ft.TextField(label="Start Date (YYYY-MM-DD)", expand=True)
        ed = ft.TextField(label="End Date (YYYY-MM-DD)", expand=True)
        err = ft.Text("", color=ft.Colors.RED_400)

        def save(_e):
            name = sanitize(nm.value)
            if not name:
                err.value = "Name required"; err.update(); return
            v = safe_float(val.value, lo=0.01)
            if v <= 0:
                err.value = "Value must be > 0"; err.update(); return
            try:
                execute_query(
                    """INSERT INTO promotions
                       (name, code, promo_type, value, min_purchase, start_date, end_date)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (name, sanitize(cod.value) or None, pty.value, v,
                     safe_float(minp.value), sanitize(sd.value) or None,
                     sanitize(ed.value) or None)
                )
                self.close_dialog(dlg)
                self._refresh_promo_table()
                self.snack("Promotion created")
            except Exception as ex:
                err.value = str(ex); err.update()

        dlg = ft.AlertDialog(
            title=ft.Text("Create Promotion", size=17, weight=ft.FontWeight.BOLD),
            content=ft.Column([
                ft.Row([nm, cod], spacing=10),
                ft.Row([pty, val, minp], spacing=10, wrap=True),
                ft.Row([sd, ed], spacing=10, wrap=True),
                err,
            ], spacing=10, width=self.dialog_width(600), height=240, scroll=ft.ScrollMode.AUTO),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dlg)),
                ft.ElevatedButton("Create", on_click=save,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.show_dialog(dlg)

    def _toggle_promo(self, e):
        pid = e.control.data
        row = fetch_one("SELECT active FROM promotions WHERE id=?", (pid,))
        if row:
            execute_query("UPDATE promotions SET active=? WHERE id=?",
                          (0 if row["active"] else 1, pid))
            self._refresh_promo_table()

    def _delete_promo(self, e):
        pid = e.control.data
        def confirm():
            execute_query("DELETE FROM promotions WHERE id=?", (pid,))
            self._refresh_promo_table()
            self.snack("Promotion deleted", ft.Colors.RED_700)

        dlg = confirm_dialog(
            self.page,
            "Delete Promotion",
            "Permanently remove this promotion?",
            confirm,
            delete_text="Delete"
        )
        self.show_dialog(dlg)