import flet as ft
import csv
from datetime import datetime

from config import currency_symbol, UserRole
from database.connection import fetch_all, execute_query, fetch_one
from database.repositories.item_repository import ItemRepository
from ui.pages.base_page import BasePage
from ui.components.dialogs import confirm_dialog
from security.validation import sanitize, safe_float, safe_int
from utils.audit import log_audit


class InventoryPage(BasePage):
    def __init__(self, app):
        super().__init__(app)
        self.item_repo = ItemRepository()
        self.inv_search = ft.TextField(
            hint_text="Search by name…",
            expand=True,
            prefix_icon=ft.Icons.SEARCH,
            height=45,
            border_radius=8,
        )
<<<<<<< HEAD
        self.inv_search.on_change = self.refresh_items          # ← after init
=======
        self.inv_search.on_change = self.refresh_items
>>>>>>> a43d19b144b88052d69b9ab13ab7e2ac5717a97d

        self.filter_category = ft.Dropdown(
            width=160,
            hint_text="All Categories",
            height=45,
        )
<<<<<<< HEAD
        self.filter_category.on_change = self.refresh_items     # ← after init
=======
        self.filter_category.on_change = self.refresh_items
>>>>>>> a43d19b144b88052d69b9ab13ab7e2ac5717a97d

        self.item_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Item Name")),
                ft.DataColumn(ft.Text("Category")),
                ft.DataColumn(ft.Text("Stock"), numeric=True),
                ft.DataColumn(ft.Text("Price"), numeric=True),
                ft.DataColumn(ft.Text("Cost"), numeric=True),
                ft.DataColumn(ft.Text("Margin"), numeric=True),
                ft.DataColumn(ft.Text("Supplier")),
                ft.DataColumn(ft.Text("Actions")),
            ],
<<<<<<< HEAD
            border=ft.border.all(1, ft.Colors.GREY_300),
=======
            border=ft.Border.all(1, ft.Colors.GREY_300),
>>>>>>> a43d19b144b88052d69b9ab13ab7e2ac5717a97d
            border_radius=8,
            data_row_max_height=50,
            column_spacing=14,
        )

    def build(self) -> ft.Control:
        self._load_categories()

        add_btn = ft.ElevatedButton(
            "+ Add Item",
            icon=ft.Icons.ADD,
            style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE),
            on_click=self.add_item_dialog,
            disabled=(self.role != UserRole.ADMIN),
        )
        export_btn = ft.OutlinedButton(
            "Export CSV",
            icon=ft.Icons.DOWNLOAD,
            on_click=self.export_items,
        )

        return ft.Column([
            ft.Text("Inventory", size=24, weight=ft.FontWeight.BOLD),
            ft.Row([self.inv_search, self.filter_category, add_btn, export_btn],
                   spacing=10, wrap=True),
<<<<<<< HEAD
            ft.Container(
                content=ft.Row([self.item_table], scroll=ft.ScrollMode.AUTO),
                expand=True,
                border=ft.border.all(1, ft.Colors.GREY_200),
                border_radius=10,
            ),
        ], expand=True, spacing=14)
=======
            self.scrollable_table(self.item_table),
        ], expand=True, spacing=14, scroll=ft.ScrollMode.AUTO)

    def did_mount(self):
        self.refresh_items()
>>>>>>> a43d19b144b88052d69b9ab13ab7e2ac5717a97d

    def _load_categories(self):
        from config import get_setting, DEFAULT_CATEGORIES
        raw = get_setting("categories", DEFAULT_CATEGORIES)
        cats = ["All"] + [x.strip() for x in raw.split(",") if x.strip()]
        self.filter_category.options = [ft.dropdown.Option(c, c) for c in cats]
        self.filter_category.value = "All"

    def refresh_items(self, e=None):
        try:
            search = sanitize(self.inv_search.value or "")
            cat = self.filter_category.value
            items = self.item_repo.search(
                name=search if search else None,
                category=cat if cat != "All" else None
            )

            sym = currency_symbol()
            self.item_table.rows.clear()
            for item in items:
                is_low = item.is_low_stock
                margin = item.margin_percent

                actions = [
                    ft.IconButton(ft.Icons.EDIT, data=item.id, on_click=self._on_edit_click),
                    ft.IconButton(ft.Icons.DELETE, icon_color=ft.Colors.RED_400,
                                  data=item.id, on_click=self._on_delete_click),
                ] if self.role == UserRole.ADMIN else [ft.Text("—")]

                row_color = ft.Colors.RED_50 if is_low else None
                self.item_table.rows.append(ft.DataRow(
                    color=row_color,
                    cells=[
                        ft.DataCell(ft.Row([
                            ft.Text(item.name, weight=ft.FontWeight.W_500),
                            ft.Container(
                                ft.Text("LOW", size=9, color=ft.Colors.WHITE),
                                bgcolor=ft.Colors.RED_700,
                                border_radius=4,
                                padding=ft.padding.symmetric(horizontal=4, vertical=1),
                                visible=is_low,
                            ),
                        ], spacing=5, tight=True)),
                        ft.DataCell(ft.Text(item.category or "—")),
                        ft.DataCell(ft.Text(str(item.quantity),
                                            color=ft.Colors.RED_700 if is_low else None,
                                            weight=ft.FontWeight.W_600 if is_low else None)),
                        ft.DataCell(ft.Text(f"{sym}{item.price:.2f}")),
                        ft.DataCell(ft.Text(f"{sym}{item.cost_price:.2f}", color=ft.Colors.GREY_600)),
                        ft.DataCell(ft.Text(f"{margin:.0f}%",
                                            color=ft.Colors.GREEN_700 if margin >= 20 else ft.Colors.ORANGE_700)),
                        ft.DataCell(ft.Text(self._get_supplier_name(item.supplier_id), size=11)),
                        ft.DataCell(ft.Row(actions, tight=True)),
                    ],
                ))
            self.page.update()
        except Exception as ex:
            self.snack(f"Error loading items: {ex}", ft.Colors.RED_700)

    def _get_supplier_name(self, supplier_id):
        if not supplier_id:
            return "—"
        row = fetch_one("SELECT name FROM suppliers WHERE id=?", (supplier_id,))
        return row["name"] if row else "—"

    def _on_edit_click(self, e):
        self._edit_item_dialog(e.control.data)

    def _on_delete_click(self, e):
        self._delete_item(e.control.data)

    def _item_form_fields(self, item_data=None):
        from config import get_setting, DEFAULT_CATEGORIES
        cats = [x.strip() for x in get_setting("categories", DEFAULT_CATEGORIES).split(",") if x.strip()]
        suppliers = fetch_all("SELECT id, name FROM suppliers ORDER BY name")
        return {
            "name": ft.TextField(label="Item Name *", expand=True,
                                 value=item_data.name if item_data else ""),
            "category": ft.Dropdown(label="Category", expand=True,
                                    options=[ft.dropdown.Option(x, x) for x in cats],
                                    value=item_data.category if item_data else None),
            "price": ft.TextField(label="Selling Price *", expand=True,
                                  keyboard_type=ft.KeyboardType.NUMBER,
                                  value=str(item_data.price) if item_data else "0"),
            "cost": ft.TextField(label="Cost Price", expand=True,
                                 keyboard_type=ft.KeyboardType.NUMBER,
                                 value=str(item_data.cost_price) if item_data else "0"),
            "qty": ft.TextField(label="Quantity", expand=True,
                                keyboard_type=ft.KeyboardType.NUMBER,
                                value=str(item_data.quantity) if item_data else "0"),
            "threshold": ft.TextField(label="Low-stock alert", expand=True,
                                      keyboard_type=ft.KeyboardType.NUMBER,
                                      value=str(item_data.low_stock_threshold) if item_data else "5"),
            "supplier": ft.Dropdown(label="Supplier", expand=True,
                                    options=[ft.dropdown.Option(str(s["id"]), s["name"]) for s in suppliers],
                                    value=str(item_data.supplier_id) if (item_data and item_data.supplier_id) else None),
        }

    def _item_form_content(self, fields):
        return ft.Column([
            ft.Row([fields["name"], fields["category"]], spacing=10),
            ft.Row([fields["price"], fields["cost"]], spacing=10),
            ft.Row([fields["qty"], fields["threshold"]], spacing=10),
            fields["supplier"],
        ], spacing=10, width=self.dialog_width(520), height=290, scroll=ft.ScrollMode.AUTO)

    def add_item_dialog(self, e=None):
        if self.role != UserRole.ADMIN:
            self.snack("Admin access required", ft.Colors.RED_700)
            return
        fields = self._item_form_fields()
        def save(_):
            name = sanitize(fields["name"].value)
            if not name:
                fields["name"].error_text = "Required"
                fields["name"].update()
                return
            try:
                data = {
                    "name": name,
                    "category": fields["category"].value,
                    "price": safe_float(fields["price"].value),
                    "cost_price": safe_float(fields["cost"].value),
                    "quantity": safe_int(fields["qty"].value),
                    "low_stock_threshold": safe_int(fields["threshold"].value, default=5),
                    "supplier_id": int(fields["supplier"].value) if fields["supplier"].value else None,
                }
                self.item_repo.create(data)
                log_audit(self.user_id, "ADD_ITEM", f"Added {name}")
                self.close_dialog(dialog)
                self.refresh_items()
                self.snack("Item added")
            except Exception as ex:
                self.snack(f"Error: {ex}", ft.Colors.RED_700)
        dialog = ft.AlertDialog(
            title=ft.Text("Add New Item", size=17, weight=ft.FontWeight.BOLD),
            content=self._item_form_content(fields),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dialog)),
                ft.ElevatedButton("Save Item", on_click=save,
                                  style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.show_dialog(dialog)

    def _edit_item_dialog(self, item_id):
        if self.role != UserRole.ADMIN:
            self.snack("Admin access required", ft.Colors.RED_700)
            return
        item = self.item_repo.get_by_id(item_id)
        if not item:
            return
        fields = self._item_form_fields(item)
        def save(_):
            name = sanitize(fields["name"].value)
            if not name:
                fields["name"].error_text = "Required"
                fields["name"].update()
                return
            try:
                data = {
                    "name": name,
                    "category": fields["category"].value,
                    "price": safe_float(fields["price"].value),
                    "cost_price": safe_float(fields["cost"].value),
                    "quantity": safe_int(fields["qty"].value),
                    "low_stock_threshold": safe_int(fields["threshold"].value, default=5),
                    "supplier_id": int(fields["supplier"].value) if fields["supplier"].value else None,
                }
                self.item_repo.update(item_id, data)
                log_audit(self.user_id, "EDIT_ITEM", f"Edited #{item_id}")
                self.close_dialog(dialog)
                self.refresh_items()
                self.snack("Item updated")
            except Exception as ex:
                self.snack(f"Error: {ex}", ft.Colors.RED_700)
        dialog = ft.AlertDialog(
            title=ft.Text(f"Edit — {item.name}", size=17, weight=ft.FontWeight.BOLD),
            content=self._item_form_content(fields),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dialog)),
                ft.ElevatedButton("Update", on_click=save,
                                  style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.show_dialog(dialog)

    def _delete_item(self, item_id):
        if self.role != UserRole.ADMIN:
            self.snack("Admin access required", ft.Colors.RED_700)
            return
        def confirm():
            self.item_repo.delete(item_id)
            log_audit(self.user_id, "DELETE_ITEM", f"Deleted #{item_id}")
            self.refresh_items()
            self.snack("Item deleted", ft.Colors.RED_700)
        dlg = confirm_dialog(
            self.page,
            "Confirm Delete",
            "Permanently delete this item?",
            confirm,
            delete_text="Delete"
        )
        self.show_dialog(dlg)

    def export_items(self, e):
        try:
            rows = fetch_all("SELECT name,category,price,cost_price,quantity,low_stock_threshold FROM items")
            filename = f"items_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
            with open(filename, "w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow(["Name","Category","Price","Cost","Qty","Min Stock"])
                writer.writerows([tuple(r) for r in rows])
            self.snack(f"Exported → {filename}")
        except Exception as ex:
            self.snack(f"Export failed: {ex}", ft.Colors.RED_700)