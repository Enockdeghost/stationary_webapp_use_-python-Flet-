import flet as ft

from config import UserRole
from database.connection import fetch_all, execute_query, fetch_one
from ui.pages.base_page import BasePage
from security.validation import sanitize
from ui.components.dialogs import confirm_dialog


class SuppliersPage(BasePage):
    def __init__(self, app):
        super().__init__(app)
        self.supplier_table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(h))
                     for h in ("Name","Contact","Phone","Email","Address","Actions")],
            border=ft.Border.all(1, ft.Colors.GREY_300),
            border_radius=8,
            data_row_max_height=52,
        )

    def build(self) -> ft.Control:
        if self.role != UserRole.ADMIN:
            return ft.Column([ft.Text("Access denied", color=ft.Colors.RED_700)])

        self._refresh_suppliers()

        return ft.Column([
            ft.Text("Suppliers", size=24, weight=ft.FontWeight.BOLD),
            ft.ElevatedButton("+ Add Supplier", icon=ft.Icons.ADD,
                               style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                    color=ft.Colors.WHITE),
                               on_click=lambda e: self._add_supplier_dialog()),
            self.scrollable_table(self.supplier_table),
        ], expand=True, spacing=14, scroll=ft.ScrollMode.AUTO)

    def _refresh_suppliers(self, e=None):
        rows = fetch_all("SELECT id, name, contact_person, phone, email, address FROM suppliers ORDER BY name")
        self.supplier_table.rows.clear()
        for sid, name, contact, phone, email, address in rows:
            self.supplier_table.rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(name, weight=ft.FontWeight.W_500)),
                ft.DataCell(ft.Text(contact or "—")),
                ft.DataCell(ft.Text(phone or "—")),
                ft.DataCell(ft.Text(email or "—")),
                ft.DataCell(ft.Text(address or "—", overflow=ft.TextOverflow.ELLIPSIS, width=120)),
                ft.DataCell(ft.Row([
                    ft.IconButton(ft.Icons.EDIT, data=sid,
                                  on_click=lambda e, s=sid: self._edit_supplier_dialog(s)),
                    ft.IconButton(ft.Icons.DELETE, icon_color=ft.Colors.RED_400,
                                  data=sid, on_click=lambda e, s=sid: self._delete_supplier(s)),
                ], tight=True)),
            ]))
        self.page.update()

    def _supplier_form_fields(self, data=None):
        return {
            "name": ft.TextField(label="Company Name *", expand=True,
                                 value=data[1] if data else ""),
            "contact": ft.TextField(label="Contact Person", expand=True,
                                     value=data[2] if data else ""),
            "phone": ft.TextField(label="Phone", expand=True,
                                   value=data[3] if data else ""),
            "email": ft.TextField(label="Email", expand=True,
                                   value=data[4] if data else ""),
            "address": ft.TextField(label="Address", expand=True,
                                     value=data[5] if data else "",
                                     multiline=True, min_lines=2),
        }

    def _supplier_form_content(self, fields):
        return ft.Column([
            ft.Row([fields["name"], fields["contact"]], spacing=10),
            ft.Row([fields["phone"], fields["email"]], spacing=10),
            fields["address"],
        ], spacing=10, width=self.dialog_width(520), height=230, scroll=ft.ScrollMode.AUTO)

    def _add_supplier_dialog(self):
        fields = self._supplier_form_fields()

        def save(_e):
            name = sanitize(fields["name"].value)
            if not name:
                fields["name"].error_text = "Required"; fields["name"].update(); return
            execute_query(
                "INSERT INTO suppliers (name, contact_person, phone, email, address) VALUES (?, ?, ?, ?, ?)",
                (name, sanitize(fields["contact"].value), sanitize(fields["phone"].value),
                 sanitize(fields["email"].value), sanitize(fields["address"].value, 300))
            )
            self.close_dialog(dlg)
            self._refresh_suppliers()
            self.snack("Supplier added")

        dlg = ft.AlertDialog(
            title=ft.Text("Add Supplier", size=17, weight=ft.FontWeight.BOLD),
            content=self._supplier_form_content(fields),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dlg)),
                ft.ElevatedButton("Save", on_click=save,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.show_dialog(dlg)

    def _edit_supplier_dialog(self, sid):
        data = fetch_one("SELECT * FROM suppliers WHERE id=?", (sid,))
        if not data:
            return
        fields = self._supplier_form_fields(data)

        def save(_e):
            name = sanitize(fields["name"].value)
            if not name:
                fields["name"].error_text = "Required"; fields["name"].update(); return
            execute_query(
                "UPDATE suppliers SET name=?, contact_person=?, phone=?, email=?, address=? WHERE id=?",
                (name, sanitize(fields["contact"].value), sanitize(fields["phone"].value),
                 sanitize(fields["email"].value), sanitize(fields["address"].value, 300), sid)
            )
            self.close_dialog(dlg)
            self._refresh_suppliers()
            self.snack("Supplier updated")

        dlg = ft.AlertDialog(
            title=ft.Text(f"Edit — {data['name']}", size=17, weight=ft.FontWeight.BOLD),
            content=self._supplier_form_content(fields),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dlg)),
                ft.ElevatedButton("Update", on_click=save,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.show_dialog(dlg)

    def _delete_supplier(self, sid):
        def confirm():
            execute_query("DELETE FROM suppliers WHERE id=?", (sid,))
            self._refresh_suppliers()
            self.snack("Supplier deleted", ft.Colors.RED_700)

        dlg = confirm_dialog(
            self.page,
            "Delete Supplier",
            "Remove this supplier? Linked items will be unlinked.",
            confirm,
            delete_text="Delete"
        )
        self.show_dialog(dlg)