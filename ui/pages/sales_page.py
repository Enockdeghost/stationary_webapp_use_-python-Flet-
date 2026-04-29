import flet as ft
from functools import partial
from datetime import datetime

from config import currency_symbol, UserRole, get_setting
from database.connection import fetch_all, execute_query, fetch_one
from ui.pages.base_page import BasePage
from security.validation import sanitize, safe_float
from utils.audit import log_audit


class SalesPage(BasePage):
    def __init__(self, app):
        super().__init__(app)
        self.cart_items: list[dict] = []
        self.pos_results_container = None

        self.pos_search = ft.TextField(
            label="Search item…",
            prefix_icon=ft.Icons.SEARCH,
            expand=True,
            height=48,
            on_change=self._pos_search_changed,
        )
        self.pos_results = ft.ListView(spacing=2, height=160)
        self.pos_results_container = ft.Container(
            content=self.pos_results,
            border=ft.Border.all(1, ft.Colors.GREY_300),
            border_radius=8,
            visible=False,
            padding=4,
        )
        self.cart_list = ft.ListView(spacing=6, expand=True, padding=4)

        sym = currency_symbol()
        self.cart_total_text = ft.Text(f"{sym}0.00", size=26, weight=ft.FontWeight.BOLD,
                                       color=ft.Colors.BLUE_700)
        self.subtotal_text = ft.Text(f"Subtotal: {sym}0.00", size=12, color=ft.Colors.GREY_600)
        self.discount_text = ft.Text(f"Discount: -{sym}0.00", size=12, color=ft.Colors.GREY_600)
        self.tax_text = ft.Text(f"Tax: {sym}0.00", size=12, color=ft.Colors.GREY_600)

        self.discount_field = ft.TextField(
            label="Discount ($)",
            value="0",
            keyboard_type=ft.KeyboardType.NUMBER,
            width=128,
            height=45,
            on_change=self._recalculate,
        )
        self.tax_field = ft.TextField(
            label="Tax (%)",
            value=get_setting("tax_rate", "0"),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=128,
            height=45,
            on_change=self._recalculate,
        )
        self.payment_dd = ft.Dropdown(
            label="Payment",
            width=155,
            height=45,
            value="Cash",
            options=[ft.dropdown.Option(m, m) for m in ("Cash", "Card", "Mobile Money", "Bank Transfer")],
        )
        self.customer_dd = ft.Dropdown(label="Customer", expand=True, height=45)
        self.promo_dd = ft.Dropdown(
            label="Apply Promotion",
            expand=True,
            height=45,
            hint_text="No promo",
        )

    def build(self) -> ft.Control:
        self._load_customer_dropdown()
        self._load_promo_dropdown()

        sym = currency_symbol()
        complete_btn = ft.ElevatedButton(
            "Complete Sale",
            icon=ft.Icons.PAYMENT,
            height=50,
            expand=True,
            style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE,
                                 shape=ft.RoundedRectangleBorder(radius=10)),
            on_click=self.complete_sale_handler,
        )
        clear_btn = ft.OutlinedButton(
            "Clear Cart",
            icon=ft.Icons.CLEAR_ALL,
            height=44,
            expand=True,
            on_click=self.clear_cart_handler,
        )

        summary = ft.Container(
            content=ft.Column([
                ft.Text("Order Summary", size=16, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                self.customer_dd,
                self.promo_dd,
                ft.Row([self.discount_field, self.tax_field], spacing=8),
                self.payment_dd,
                ft.Divider(),
                self.subtotal_text,
                self.discount_text,
                self.tax_text,
                ft.Divider(),
                ft.Row([ft.Text("TOTAL", size=14, weight=ft.FontWeight.BOLD),
                        self.cart_total_text],
                       alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Container(height=6),
                complete_btn,
                clear_btn,
            ], spacing=8, scroll=ft.ScrollMode.AUTO),
            padding=14,
            width=260,
        )

        pos_panel = ft.Column([
            ft.Text("Point of Sale", size=20, weight=ft.FontWeight.BOLD),
            self.pos_search,
            self.pos_results_container,
            ft.Text("Cart", size=14, weight=ft.FontWeight.W_600),
            ft.Container(
                content=self.cart_list,
                border=ft.Border.all(1, ft.Colors.GREY_300),
                border_radius=10,
                expand=True,
                padding=6,
            ),
        ], expand=True, spacing=8)

        return ft.Row([
            pos_panel,
            ft.VerticalDivider(width=1),
            summary,
        ], expand=True, spacing=0)

    def _load_customer_dropdown(self):
        rows = fetch_all("SELECT id, name FROM customers ORDER BY name")
        self.customer_dd.options = (
            [ft.dropdown.Option("", "Walk-in Customer")] +
            [ft.dropdown.Option(str(r["id"]), r["name"]) for r in rows]
        )
        self.customer_dd.value = ""

    def _load_promo_dropdown(self):
        today = datetime.now().strftime("%Y-%m-%d")
        rows = fetch_all(
            """SELECT id, name, promo_type, value FROM promotions
               WHERE active=1 AND (start_date IS NULL OR start_date<=?)
               AND (end_date IS NULL OR end_date>=?)""",
            (today, today)
        )
        self.promo_dd.options = [ft.dropdown.Option("", "No Promotion")]
        for r in rows:
            lbl = f"{r['name']} ({int(r['value'])}% off)" if r["promo_type"] == "percentage" else f"{r['name']} (${r['value']:.2f} off)"
            self.promo_dd.options.append(ft.dropdown.Option(str(r["id"]), lbl))
        self.promo_dd.value = ""

    def _apply_promo(self, e):
        if not self.promo_dd.value:
            return
        try:
            pid = int(self.promo_dd.value)
        except (ValueError, TypeError):
            return

        promo = fetch_one("SELECT promo_type, value, min_purchase FROM promotions WHERE id=?", (pid,))
        if not promo:
            return

        subtotal = sum(ci["subtotal"] for ci in self.cart_items)
        if subtotal < promo["min_purchase"]:
            sym = currency_symbol()
            self.snack(f"Promo requires min. {sym}{promo['min_purchase']:.2f}", ft.Colors.ORANGE_700)
            self.promo_dd.value = ""
            self.promo_dd.update()
            return

        discount = subtotal * promo["value"] / 100 if promo["promo_type"] == "percentage" else promo["value"]
        self.discount_field.value = f"{discount:.2f}"
        self._recalculate()
        sym = currency_symbol()
        self.snack(f"Promo applied: {sym}{discount:.2f} off")

    def _pos_search_changed(self, e):
        query = sanitize(self.pos_search.value or "")
        if not query:
            if self.pos_results_container:
                self.pos_results_container.visible = False
            self.pos_results.controls.clear()
            self.page.update()
            return

        rows = fetch_all(
            "SELECT id, name, price, quantity FROM items WHERE name LIKE ? AND quantity>0 ORDER BY name LIMIT 10",
            (f"%{query}%",)
        )
        sym = currency_symbol()
        self.pos_results.controls.clear()
        for r in rows:
            self.pos_results.controls.append(ft.ListTile(
                title=ft.Text(r["name"], size=13),
                subtitle=ft.Text(f"Stock: {r['quantity']}  •  {sym}{r['price']:.2f}",
                                 size=11, color=ft.Colors.GREY_600),
                trailing=ft.IconButton(ft.Icons.ADD_CIRCLE,
                                       data={"id": r["id"], "name": r["name"], "price": r["price"]},
                                       on_click=self._on_add_to_cart_click),
                dense=True,
            ))
        if self.pos_results_container:
            self.pos_results_container.visible = bool(rows)
        self.page.update()

    def _on_add_to_cart_click(self, e):
        d = e.control.data
        self._add_to_cart(d["id"], d["name"], d["price"])

    def _add_to_cart(self, item_id, name, price):
        for ci in self.cart_items:
            if ci["item_id"] == item_id:
                ci["qty"] += 1
                ci["subtotal"] = ci["qty"] * ci["price"]
                self._rebuild_cart_ui()
                return
        self.cart_items.append({"item_id": item_id, "name": name, "price": price, "qty": 1, "subtotal": price})
        self._rebuild_cart_ui()

    def _rebuild_cart_ui(self):
        sym = currency_symbol()
        self.cart_list.controls.clear()
        for item in self.cart_items:
            qty_field = ft.TextField(
                value=str(item["qty"]),
                width=52,
                height=34,
                keyboard_type=ft.KeyboardType.NUMBER,
                text_align=ft.TextAlign.CENTER,
                border_radius=6,
                data=item,
            )
            row = ft.Container(
                content=ft.Row([
                    ft.Column([
                        ft.Text(item["name"], size=12, weight=ft.FontWeight.W_500,
                                overflow=ft.TextOverflow.ELLIPSIS),
                        ft.Text(f"{sym}{item['price']:.2f} each", size=10,
                                color=ft.Colors.GREY_500),
                    ], expand=True, spacing=2, tight=True),
                    ft.Row([
                        ft.IconButton(ft.Icons.REMOVE, width=28, height=28, data=item,
                                      on_click=partial(self._on_cart_qty_step, delta=-1)),
                        qty_field,
                        ft.IconButton(ft.Icons.ADD, width=28, height=28, data=item,
                                      on_click=partial(self._on_cart_qty_step, delta=1)),
                    ], spacing=2, tight=True),
                    ft.Text(f"{sym}{item['subtotal']:.2f}", size=13,
                            weight=ft.FontWeight.W_600, width=64,
                            text_align=ft.TextAlign.RIGHT),
                    ft.IconButton(ft.Icons.CLOSE, icon_size=15,
                                  icon_color=ft.Colors.RED_400, data=item,
                                  on_click=self._on_cart_remove_item),
                ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.padding.symmetric(horizontal=8, vertical=5),
                border=ft.Border.all(1, ft.Colors.GREY_200),
                border_radius=8,
            )
            self.cart_list.controls.append(row)
        self._recalculate()

    def _on_cart_qty_step(self, e, delta):
        item = e.control.data
        item["qty"] = max(1, item["qty"] + delta)
        item["subtotal"] = item["qty"] * item["price"]
        self._rebuild_cart_ui()

    def _on_cart_qty_changed(self, e):
        item = e.control.data
        try:
            item["qty"] = max(1, int(e.control.value))
            item["subtotal"] = item["qty"] * item["price"]
            self._recalculate()
        except ValueError:
            pass

    def _on_cart_remove_item(self, e):
        item = e.control.data
        self.cart_items = [ci for ci in self.cart_items if ci["item_id"] != item["item_id"]]
        self._rebuild_cart_ui()

    def _recalculate(self, e=None):
        sym = currency_symbol()
        subtotal = sum(ci["subtotal"] for ci in self.cart_items)
        discount = safe_float(self.discount_field.value)
        tax_pct = safe_float(self.tax_field.value)
        tax = (subtotal - discount) * tax_pct / 100
        total = max(0.0, subtotal - discount + tax)
        self.subtotal_text.value = f"Subtotal: {sym}{subtotal:.2f}"
        self.discount_text.value = f"Discount: -{sym}{discount:.2f}"
        self.tax_text.value = f"Tax ({tax_pct:.0f}%): {sym}{tax:.2f}"
        self.cart_total_text.value = f"{sym}{total:.2f}"
        self.page.update()

    def clear_cart_handler(self, e):
        self.clear_cart()

    def clear_cart(self):
        self.cart_items.clear()
        self.cart_list.controls.clear()
        sym = currency_symbol()
        self.cart_total_text.value = f"{sym}0.00"
        self.subtotal_text.value = f"Subtotal: {sym}0.00"
        self.discount_text.value = f"Discount: -{sym}0.00"
        self.tax_text.value = f"Tax: {sym}0.00"
        self.discount_field.value = "0"
        if hasattr(self, "promo_dd"):
            self.promo_dd.value = ""
        self.page.update()

    def complete_sale_handler(self, e):
        self.complete_sale()

    def complete_sale(self):
        if not self.cart_items:
            self.snack("Cart is empty!", ft.Colors.ORANGE_700)
            return

        sym = currency_symbol()
        subtotal = sum(ci["subtotal"] for ci in self.cart_items)
        discount = safe_float(self.discount_field.value)
        tax_pct = safe_float(self.tax_field.value)
        tax = (subtotal - discount) * tax_pct / 100
        total = max(0.0, subtotal - discount + tax)

        customer_id = None
        if self.customer_dd.value:
            try:
                customer_id = int(self.customer_dd.value)
            except (ValueError, TypeError):
                pass

        payment = self.payment_dd.value or "Cash"

        # Check stock
        for ci in self.cart_items:
            row = fetch_one("SELECT quantity FROM items WHERE id=?", (ci["item_id"],))
            if not row or row["quantity"] < ci["qty"]:
                self.snack(f"Insufficient stock: {ci['name']}", ft.Colors.RED_700)
                return

        try:
            sale_id = self._insert_sale(customer_id, subtotal, discount, tax, total, payment)
            self._insert_sale_items(sale_id)
            self._update_stock()
            if customer_id:
                execute_query(
                    "UPDATE customers SET loyalty_points=loyalty_points+?, total_spent=total_spent+? WHERE id=?",
                    (int(total), total, customer_id)
                )
            log_audit(self.user_id, "SALE", f"Sale #{sale_id} — {sym}{total:.2f}")
            self.snack(f"Sale #{sale_id} completed — {sym}{total:.2f}")
            self.clear_cart()
        except Exception as ex:
            self.snack(f"Sale failed: {ex}", ft.Colors.RED_700)

    def _insert_sale(self, customer_id, subtotal, discount, tax, total, payment):
        cursor = execute_query(
            """INSERT INTO sales (customer_id, subtotal, discount, tax, total, payment_method, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (customer_id, subtotal, discount, tax, total, payment, self.user_id)
        )
        return cursor.lastrowid

    def _insert_sale_items(self, sale_id):
        for ci in self.cart_items:
            execute_query(
                "INSERT INTO sale_items (sale_id, item_id, quantity, price_at_sale, total) VALUES (?, ?, ?, ?, ?)",
                (sale_id, ci["item_id"], ci["qty"], ci["price"], ci["subtotal"])
            )

    def _update_stock(self):
        for ci in self.cart_items:
            execute_query(
                "UPDATE items SET quantity = quantity - ? WHERE id = ?",
                (ci["qty"], ci["item_id"])
            )