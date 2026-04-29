import flet as ft
import csv
from datetime import datetime

from config import currency_symbol, UserRole
from database.connection import fetch_all, fetch_one
from database.repositories.item_repository import ItemRepository
from ui.pages.base_page import BasePage
from ui.components.dialogs import confirm_dialog
from security.validation import sanitize, safe_float, safe_int
from utils.audit import log_audit

_BLUE   = ft.Colors.BLUE_700
_RED    = ft.Colors.RED_700
_GREEN  = ft.Colors.GREEN_700
_ORANGE = ft.Colors.ORANGE_700
_GREY   = ft.Colors.GREY_600


class InventoryPage(BasePage):
    def __init__(self, app):
        super().__init__(app)
        self.item_repo = ItemRepository()

        self.inv_search = ft.TextField(
            hint_text="Search items…",
            expand=True,
            prefix_icon=ft.Icons.SEARCH,
            height=42,
            border_radius=8,
            on_change=self.refresh_items,
            content_padding=ft.padding.symmetric(horizontal=12, vertical=0),
        )

        self.filter_category = ft.Dropdown(
            width=175,
            hint_text="All Categories",
            height=42,
            border_radius=8,
            content_padding=ft.padding.symmetric(horizontal=10, vertical=0),
        )
        self.filter_category.on_change = self.refresh_items

        self._stat_total = ft.Text("0",  size=20, weight=ft.FontWeight.BOLD)
        self._stat_low   = ft.Text("0",  size=20, weight=ft.FontWeight.BOLD, color=_RED)
        self._stat_value = ft.Text("$0", size=20, weight=ft.FontWeight.BOLD, color=_GREEN)

        self.cards_column = ft.Column(
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        self.body_container = ft.Container(
            content=self.cards_column,
            expand=True,
            border=ft.border.all(1, ft.Colors.GREY_200),
            border_radius=10,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )

    def build(self) -> ft.Control:
        self._load_categories()
        is_admin = self.role == UserRole.ADMIN

        add_btn = ft.ElevatedButton(
            "Add Item",
            icon=ft.Icons.ADD_ROUNDED,
            style=ft.ButtonStyle(
                bgcolor=_BLUE,
                color=ft.Colors.WHITE,
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=ft.padding.symmetric(horizontal=16, vertical=0),
            ),
            height=42,
            on_click=self.add_item_dialog,
            disabled=not is_admin,
        )
        export_btn = ft.OutlinedButton(
            "Export CSV",
            icon=ft.Icons.DOWNLOAD_ROUNDED,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=ft.padding.symmetric(horizontal=14, vertical=0),
            ),
            height=42,
            on_click=self.export_items,
        )

        stats_row = ft.Row(
            [
                self._stat_chip("Total Items",  self._stat_total,
                                ft.Icons.INVENTORY_2_OUTLINED,
                                ft.Colors.BLUE_50,  _BLUE),
                self._stat_chip("Low Stock",    self._stat_low,
                                ft.Icons.WARNING_AMBER_ROUNDED,
                                ft.Colors.RED_50,   _RED),
                self._stat_chip("Stock Value",  self._stat_value,
                                ft.Icons.ATTACH_MONEY_ROUNDED,
                                ft.Colors.GREEN_50, _GREEN),
            ],
            spacing=10,
            wrap=True,
        )

        toolbar = ft.Row(
            [self.inv_search, self.filter_category, add_btn, export_btn],
            spacing=10,
            wrap=True,
        )

        header = ft.Row(
            [
                ft.Icon(ft.Icons.INVENTORY_2, color=_BLUE, size=26),
                ft.Text("Inventory", size=22, weight=ft.FontWeight.BOLD),
            ],
            spacing=8,
        )

        return ft.Column(
            [
                header,
                stats_row,
                ft.Divider(height=1, color=ft.Colors.GREY_200),
                toolbar,
                self.body_container,
            ],
            expand=True,
            spacing=12,
        )

    @staticmethod
    def _stat_chip(label, value_text, icon, bg, icon_color):
        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        ft.Icon(icon, color=icon_color, size=20),
                        bgcolor=bg, border_radius=8, padding=8,
                    ),
                    ft.Column(
                        [ft.Text(label, size=11, color=_GREY), value_text],
                        spacing=0, tight=True,
                    ),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            border=ft.border.all(1, ft.Colors.GREY_200),
            border_radius=10,
            padding=ft.padding.symmetric(horizontal=14, vertical=10),
        )

    def _load_categories(self):
        from config import get_setting, DEFAULT_CATEGORIES
        raw  = get_setting("categories", DEFAULT_CATEGORIES)
        cats = ["All"] + [x.strip() for x in raw.split(",") if x.strip()]
        self.filter_category.options = [ft.dropdown.Option(c, c) for c in cats]
        self.filter_category.value   = "All"

    def _get_supplier_name(self, supplier_id) -> str:
        if not supplier_id:
            return "—"
        try:
            row = fetch_one("SELECT name FROM suppliers WHERE id=?", (supplier_id,))
            return row["name"] if row else "—"
        except Exception:
            return "—"

    def refresh_items(self, e=None):
        try:
            search = sanitize(self.inv_search.value or "")
            cat    = self.filter_category.value or "All"

            items = self.item_repo.search(
                name     = search if search else None,
                category = cat    if cat != "All" else None,
            )

            sym       = currency_symbol()
            low_count = sum(1 for i in items if i.is_low_stock)
            stock_val = sum(i.quantity * i.cost_price for i in items)

            self._stat_total.value = str(len(items))
            self._stat_low.value   = str(low_count)
            self._stat_value.value = f"{sym}{stock_val:,.0f}"

            is_admin = self.role == UserRole.ADMIN

            self.cards_column.controls.clear()

            if not items:
                self.cards_column.controls.append(
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Icon(ft.Icons.INVENTORY_2_OUTLINED,
                                        size=56, color=ft.Colors.GREY_400),
                                ft.Text("No items found", size=16,
                                        color=ft.Colors.GREY_500,
                                        weight=ft.FontWeight.W_500),
                                ft.Text("Try a different search or add a new item",
                                        size=12, color=ft.Colors.GREY_400),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            alignment=ft.MainAxisAlignment.CENTER,
                            spacing=8,
                        ),
                        alignment=ft.Alignment(0, 0),
                        expand=True,
                    )
                )
            else:
                for item in items:
                    card = self._build_item_card(item, sym, is_admin)
                    self.cards_column.controls.append(card)

            if self.page:
                self.page.update()

        except Exception as ex:
            import traceback
            traceback.print_exc()
            if self.page:
                self.snack(f"Error loading items: {ex}", ft.Colors.RED_700)

    def _build_item_card(self, item, sym, is_admin):
        is_low   = item.is_low_stock
        sup_name = self._get_supplier_name(item.supplier_id)

        name_row = ft.Row([
            ft.Text(item.name, weight=ft.FontWeight.W_500, expand=True,
                    overflow=ft.TextOverflow.ELLIPSIS),
            ft.Container(
                ft.Text("LOW", size=9, color=ft.Colors.WHITE,
                        weight=ft.FontWeight.BOLD),
                bgcolor=_RED,
                border_radius=4,
                padding=ft.padding.symmetric(horizontal=5, vertical=2),
                visible=is_low,
            ),
        ], spacing=6, tight=True)

        qty_controls = ft.Row([
            ft.IconButton(
                icon=ft.Icons.REMOVE, icon_size=16,
                on_click=lambda e, it=item: self._adjust_qty(it, -1),
                disabled=not is_admin,
            ),
            ft.Text(str(item.quantity), size=14, weight=ft.FontWeight.W_600),
            ft.IconButton(
                icon=ft.Icons.ADD, icon_size=16,
                on_click=lambda e, it=item: self._adjust_qty(it, 1),
                disabled=not is_admin,
            ),
        ], spacing=4, tight=True)

        price_display = ft.Row([
            ft.Text(f"Price: {sym}{item.price:.2f}", size=12),
            ft.Container(width=8),
            ft.Text(f"Cost: {sym}{item.cost_price:.2f}", size=12, color=_GREY),
            ft.Container(width=8),
            ft.Text(f"Margin: {item.margin_percent:.0f}%",
                    size=12, color=_GREEN if item.margin_percent >= 20 else _ORANGE),
        ], spacing=4, wrap=True)

        tags_row = ft.Row([
            ft.Container(
                ft.Text(item.category or "—", size=10, color=ft.Colors.WHITE),
                bgcolor=_BLUE,
                border_radius=4,
                padding=ft.padding.symmetric(horizontal=5, vertical=2),
            ),
            ft.Container(
                ft.Text(sup_name, size=10, color=ft.Colors.WHITE),
                bgcolor=ft.Colors.GREY_500,
                border_radius=4,
                padding=ft.padding.symmetric(horizontal=5, vertical=2),
            ) if sup_name != "—" else ft.Text(""),
        ], spacing=6, wrap=True)

        action_row = ft.Row([
            ft.IconButton(
                icon=ft.Icons.EDIT_OUTLINED, icon_color=_BLUE, icon_size=16,
                tooltip="Edit", data=item.id, on_click=lambda e: self._on_edit_click(e),
            ),
            ft.IconButton(
                icon=ft.Icons.DELETE_OUTLINE_ROUNDED, icon_color=_RED, icon_size=16,
                tooltip="Delete", data=item.id, on_click=lambda e: self._on_delete_click(e),
            ),
        ], spacing=0, tight=True) if is_admin else ft.Text("")

        card_content = ft.Column([
            name_row,
            ft.Row([
                ft.Text("Qty:", size=12, color=ft.Colors.GREY_600),
                qty_controls,
                ft.VerticalDivider(width=1, color=ft.Colors.GREY_300),
                price_display,
            ], spacing=8),
            ft.Row([
                tags_row,
                ft.Container(expand=True),
                action_row,
            ], spacing=8),
        ], spacing=8)

        return ft.Container(
            content=card_content,
            bgcolor=ft.Colors.SURFACE,
            border_radius=10,
            padding=12,
            margin=ft.margin.only(bottom=8),
            shadow=ft.BoxShadow(blur_radius=6, color=ft.Colors.with_opacity(0.08, "#000")),
            border=ft.border.all(1, ft.Colors.with_opacity(0.15, _RED if is_low else ft.Colors.GREY_300)),
        )

    def _adjust_qty(self, item, delta):
        new_qty = max(0, item.quantity + delta)
        self.item_repo.update(item.id, {"quantity": new_qty})
        item.quantity = new_qty
        log_audit(self.user_id, "QTY_CHANGE", f"#{item.id}: {item.quantity} → {new_qty}")
        self.refresh_items()

    def _on_edit_click(self, e):
        self._edit_item_dialog(e.control.data)

    def _on_delete_click(self, e):
        self._delete_item(e.control.data)

    def _item_form_fields(self, item_data=None):
        from config import get_setting, DEFAULT_CATEGORIES
        cats      = [x.strip() for x in
                     get_setting("categories", DEFAULT_CATEGORIES).split(",")
                     if x.strip()]
        suppliers = fetch_all("SELECT id, name FROM suppliers ORDER BY name")

        def tf(label, val, kb=ft.KeyboardType.TEXT):
            return ft.TextField(
                label=label, expand=True, keyboard_type=kb, value=val,
                border_radius=8,
                content_padding=ft.padding.symmetric(horizontal=12, vertical=10),
            )

        return {
            "name":      tf("Item Name *",
                            item_data.name if item_data else ""),
            "category":  ft.Dropdown(
                            label="Category", expand=True, border_radius=8,
                            options=[ft.dropdown.Option(x, x) for x in cats],
                            value=item_data.category if item_data else None),
            "price":     tf("Selling Price *",
                            str(item_data.price) if item_data else "0",
                            ft.KeyboardType.NUMBER),
            "cost":      tf("Cost Price",
                            str(item_data.cost_price) if item_data else "0",
                            ft.KeyboardType.NUMBER),
            "qty":       tf("Quantity",
                            str(item_data.quantity) if item_data else "0",
                            ft.KeyboardType.NUMBER),
            "threshold": tf("Low-stock Alert",
                            str(item_data.low_stock_threshold) if item_data else "5",
                            ft.KeyboardType.NUMBER),
            "supplier":  ft.Dropdown(
                            label="Supplier", expand=True, border_radius=8,
                            options=[ft.dropdown.Option(str(s["id"]), s["name"])
                                     for s in suppliers],
                            value=(str(item_data.supplier_id)
                                   if item_data and item_data.supplier_id else None)),
        }

    def _item_form_content(self, fields):
        return ft.Column(
            [
                ft.Row([fields["name"],      fields["category"]],  spacing=12),
                ft.Row([fields["price"],     fields["cost"]],      spacing=12),
                ft.Row([fields["qty"],       fields["threshold"]], spacing=12),
                fields["supplier"],
            ],
            spacing=14,
            width=self.dialog_width(540),
            height=310,
            scroll=ft.ScrollMode.AUTO,
        )

    def _save_btn(self, label, on_click):
        return ft.ElevatedButton(
            label, on_click=on_click,
            style=ft.ButtonStyle(
                bgcolor=_BLUE, color=ft.Colors.WHITE,
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
        )

    def _cancel_btn(self, dialog):
        return ft.TextButton(
            "Cancel",
            on_click=lambda _: self.close_dialog(dialog),
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
        )

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
                self.item_repo.create({
                    "name":                name,
                    "category":            fields["category"].value,
                    "price":               safe_float(fields["price"].value),
                    "cost_price":          safe_float(fields["cost"].value),
                    "quantity":            safe_int(fields["qty"].value),
                    "low_stock_threshold": safe_int(fields["threshold"].value, default=5),
                    "supplier_id": (int(fields["supplier"].value)
                                    if fields["supplier"].value else None),
                })
                log_audit(self.user_id, "ADD_ITEM", f"Added {name}")
                self.close_dialog(dialog)
                self.refresh_items()
                self.snack(f"✓ '{name}' added to inventory")
            except Exception as ex:
                self.snack(f"Error: {ex}", ft.Colors.RED_700)

        dialog = ft.AlertDialog(
            title=ft.Row(
                [ft.Icon(ft.Icons.ADD_BOX_OUTLINED, color=_BLUE),
                 ft.Text("Add New Item", size=17, weight=ft.FontWeight.BOLD)],
                spacing=8,
            ),
            content=self._item_form_content(fields),
            actions=[self._cancel_btn(None), self._save_btn("Save Item", save)],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=12),
        )
        dialog.actions[0] = self._cancel_btn(dialog)
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
                self.item_repo.update(item_id, {
                    "name":                name,
                    "category":            fields["category"].value,
                    "price":               safe_float(fields["price"].value),
                    "cost_price":          safe_float(fields["cost"].value),
                    "quantity":            safe_int(fields["qty"].value),
                    "low_stock_threshold": safe_int(fields["threshold"].value, default=5),
                    "supplier_id": (int(fields["supplier"].value)
                                    if fields["supplier"].value else None),
                })
                log_audit(self.user_id, "EDIT_ITEM", f"Edited #{item_id}")
                self.close_dialog(dialog)
                self.refresh_items()
                self.snack(f"✓ '{name}' updated")
            except Exception as ex:
                self.snack(f"Error: {ex}", ft.Colors.RED_700)

        dialog = ft.AlertDialog(
            title=ft.Row(
                [ft.Icon(ft.Icons.EDIT_OUTLINED, color=_BLUE),
                 ft.Text(f"Edit — {item.name}", size=17,
                         weight=ft.FontWeight.BOLD)],
                spacing=8,
            ),
            content=self._item_form_content(fields),
            actions=[self._cancel_btn(None), self._save_btn("Update", save)],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=12),
        )
        dialog.actions[0] = self._cancel_btn(dialog)
        self.show_dialog(dialog)

    def _delete_item(self, item_id):
        if self.role != UserRole.ADMIN:
            self.snack("Admin access required", ft.Colors.RED_700)
            return
        item      = self.item_repo.get_by_id(item_id)
        item_name = item.name if item else f"#{item_id}"

        def confirm():
            self.item_repo.delete(item_id)
            log_audit(self.user_id, "DELETE_ITEM", f"Deleted #{item_id}")
            self.refresh_items()
            self.snack(f"'{item_name}' deleted", ft.Colors.RED_700)

        dlg = confirm_dialog(
            self.page, "Confirm Delete",
            f"Permanently delete '{item_name}'?\nThis cannot be undone.",
            confirm, delete_text="Delete",
        )
        self.show_dialog(dlg)

    def export_items(self, e):
        try:
            rows     = fetch_all(
                "SELECT name, category, price, cost_price, "
                "quantity, low_stock_threshold FROM items ORDER BY name"
            )
            filename = f"inventory_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
            with open(filename, "w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow(["Name","Category","Price","Cost","Qty","Min Stock"])
                writer.writerows([tuple(r) for r in rows])
            self.snack(f"✓ Exported {len(rows)} items → {filename}")
        except Exception as ex:
            self.snack(f"Export failed: {ex}", ft.Colors.RED_700)