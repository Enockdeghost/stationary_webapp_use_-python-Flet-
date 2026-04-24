# ui/pages/customers_page.py
import flet as ft

from config import UserRole, currency_symbol
from database.connection import fetch_all, execute_query, fetch_one
from ui.pages.base_page import BasePage
from security.validation import sanitize
from ui.components.dialogs import confirm_dialog


class CustomersPage(BasePage):
    def __init__(self, app):
        super().__init__(app)
        self.customer_table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(h))
                     for h in ("Name","Phone","Email","Points","Spent","Since","Actions")],
            border=ft.Border.all(1, ft.Colors.GREY_300),
            border_radius=8,
            data_row_max_height=52,
        )

    def build(self) -> ft.Control:
        if self.role != UserRole.ADMIN:
            return ft.Column([ft.Text("Access denied", color=ft.Colors.RED_700)])

        self._refresh_customers()

        return ft.Column([
            ft.Text("Customers", size=24, weight=ft.FontWeight.BOLD),
            ft.ElevatedButton("+ Add Customer", icon=ft.Icons.PERSON_ADD,
                               style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                    color=ft.Colors.WHITE),
                               on_click=lambda e: self._add_customer_dialog()),
            self.scrollable_table(self.customer_table),
        ], expand=True, spacing=14, scroll=ft.ScrollMode.AUTO)

    def _refresh_customers(self, e=None):
        rows = fetch_all("""
            SELECT id, name, phone, email, loyalty_points, total_spent, created_at
            FROM customers ORDER BY name
        """)
        sym = currency_symbol()
        self.customer_table.rows.clear()
        for cid, name, phone, email, pts, spent, joined in rows:
            self.customer_table.rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(name, weight=ft.FontWeight.W_500)),
                ft.DataCell(ft.Text(phone or "—")),
                ft.DataCell(ft.Text(email or "—")),
                ft.DataCell(ft.Container(
                    ft.Text(str(pts), color=ft.Colors.WHITE, size=11),
                    bgcolor=ft.Colors.AMBER_700,
                    border_radius=10,
                    padding=ft.padding.symmetric(horizontal=6, vertical=2),
                )),
                ft.DataCell(ft.Text(f"{sym}{spent:,.2f}", color=ft.Colors.GREEN_700)),
                ft.DataCell(ft.Text((joined or "")[:10], size=11, color=ft.Colors.GREY_600)),
                ft.DataCell(ft.Row([
                    ft.IconButton(ft.Icons.EDIT, data=cid,
                                  on_click=lambda e, c=cid: self._edit_customer_dialog(c)),
                    ft.IconButton(ft.Icons.DELETE, icon_color=ft.Colors.RED_400,
                                  data=cid, on_click=lambda e, c=cid: self._delete_customer(c)),
                ], tight=True)),
            ]))
        self.page.update()

    def _customer_form_fields(self, data=None):
        return {
            "name": ft.TextField(label="Full Name *", expand=True,
                                 value=data["name"] if data else ""),
            "phone": ft.TextField(label="Phone", expand=True,
                                  value=data["phone"] if data else ""),
            "email": ft.TextField(label="Email", expand=True,
                                  value=data["email"] if data else ""),
        }

    def _customer_form_content(self, fields):
        return ft.Column([
            fields["name"],
            ft.Row([fields["phone"], fields["email"]], spacing=10)
        ], spacing=10, width=self.dialog_width(460), height=140, scroll=ft.ScrollMode.AUTO)

    def _add_customer_dialog(self):
        fields = self._customer_form_fields()

        def save(_e):
            name = sanitize(fields["name"].value)
            if not name:
                fields["name"].error_text = "Required"
                fields["name"].update()
                return
            execute_query(
                "INSERT INTO customers (name, phone, email) VALUES (?, ?, ?)",
                (name, sanitize(fields["phone"].value), sanitize(fields["email"].value))
            )
            self.close_dialog(dlg)
            self._refresh_customers()
            self.snack("Customer added")

        dlg = ft.AlertDialog(
            title=ft.Text("Add Customer", size=17, weight=ft.FontWeight.BOLD),
            content=self._customer_form_content(fields),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dlg)),
                ft.ElevatedButton("Save", on_click=save,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.show_dialog(dlg)

    def _edit_customer_dialog(self, cid):
        data = fetch_one("SELECT id, name, phone, email FROM customers WHERE id=?", (cid,))
        if not data:
            return
        fields = self._customer_form_fields(data)

        def save(_e):
            name = sanitize(fields["name"].value)
            if not name:
                fields["name"].error_text = "Required"
                fields["name"].update()
                return
            execute_query(
                "UPDATE customers SET name=?, phone=?, email=? WHERE id=?",
                (name, sanitize(fields["phone"].value), sanitize(fields["email"].value), cid)
            )
            self.close_dialog(dlg)
            self._refresh_customers()
            self.snack("Customer updated")

        dlg = ft.AlertDialog(
            title=ft.Text(f"Edit — {data['name']}", size=17, weight=ft.FontWeight.BOLD),
            content=self._customer_form_content(fields),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dlg)),
                ft.ElevatedButton("Update", on_click=save,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.show_dialog(dlg)

    def _delete_customer(self, cid):
        def confirm():
            execute_query("DELETE FROM customers WHERE id=?", (cid,))
            self._refresh_customers()
            self.snack("Customer deleted", ft.Colors.RED_700)

        dlg = confirm_dialog(
            self.page,
            "Delete Customer",
            "Remove this customer? Sales history is kept.",
            confirm,
            delete_text="Delete"
        )
        self.show_dialog(dlg)