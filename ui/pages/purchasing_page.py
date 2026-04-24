import flet as ft
from datetime import datetime

from config import UserRole, POStatus, currency_symbol
from database.connection import fetch_all, execute_query, fetch_one
from ui.pages.base_page import BasePage
from security.validation import sanitize, safe_int, safe_float
from utils.audit import log_audit


class PurchasingPage(BasePage):
    def __init__(self, app):
        super().__init__(app)
        self.po_table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(h))
                     for h in ("PO #","Supplier","Order Date","Expected","Status","Total","Actions")],
            border=ft.Border.all(1, ft.Colors.GREY_300),
            border_radius=8,
        )

    def build(self) -> ft.Control:
        if self.role != UserRole.ADMIN:
            return ft.Column([ft.Text("Access denied", color=ft.Colors.RED_700)])

        self._refresh_po_list()

        return ft.Column([
            ft.Text("Purchase Orders", size=24, weight=ft.FontWeight.BOLD),
            ft.Row([
                ft.ElevatedButton("+ New PO", icon=ft.Icons.ADD,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE),
                                   on_click=lambda e: self._open_po_dialog()),
                ft.OutlinedButton("Refresh", icon=ft.Icons.REFRESH,
                                   on_click=lambda e: self._refresh_po_list()),
            ], spacing=10),
            self.scrollable_table(self.po_table),
        ], expand=True, spacing=14, scroll=ft.ScrollMode.AUTO)

    def _refresh_po_list(self, e=None):
        rows = fetch_all("""
            SELECT po.id, s.name, po.order_date, po.expected_date, po.status, po.total_cost
            FROM purchase_orders po
            JOIN suppliers s ON po.supplier_id = s.id
            ORDER BY po.order_date DESC
        """)
        sym = currency_symbol()
        STATUS_COLORS = {
            POStatus.PENDING:  ft.Colors.ORANGE_700,
            POStatus.ORDERED:  ft.Colors.BLUE_700,
            POStatus.RECEIVED: ft.Colors.GREEN_700,
            POStatus.CANCELLED: ft.Colors.RED_700,
        }
        self.po_table.rows = [
            ft.DataRow(cells=[
                ft.DataCell(ft.Text(str(r["id"]))),
                ft.DataCell(ft.Text(r["name"])),
                ft.DataCell(ft.Text((r["order_date"] or "")[:10])),
                ft.DataCell(ft.Text(r["expected_date"] or "—")),
                ft.DataCell(ft.Container(
                    ft.Text(r["status"].upper(), size=10, color=ft.Colors.WHITE),
                    bgcolor=STATUS_COLORS.get(r["status"], ft.Colors.GREY_700),
                    border_radius=6,
                    padding=ft.padding.symmetric(horizontal=6, vertical=2),
                )),
                ft.DataCell(ft.Text(f"{sym}{r['total_cost']:.2f}")),
                ft.DataCell(ft.Row([
                    ft.IconButton(ft.Icons.CHECK_CIRCLE, data=r["id"],
                                  tooltip="Receive Items",
                                  on_click=self._receive_po_dialog),
                ], tight=True)),
            ]) for r in rows
        ]
        self.page.update()

    def _open_po_dialog(self, prefill=None):
        if prefill is None:
            prefill = []

        suppliers = fetch_all("SELECT id, name FROM suppliers ORDER BY name")
        all_items = fetch_all("SELECT id, name, cost_price FROM items ORDER BY name")
        if not suppliers:
            self.snack("No suppliers. Add a supplier first.", ft.Colors.ORANGE_700)
            return

        sym = currency_symbol()
        item_opts = [ft.dropdown.Option(str(it["id"]), f"{it['name']} (cost: {sym}{it['cost_price']:.2f})")
                     for it in all_items]

        supplier_dd = ft.Dropdown(
            label="Supplier *", width=250,
            options=[ft.dropdown.Option(str(s["id"]), s["name"]) for s in suppliers]
        )
        exp_date = ft.TextField(label="Expected Date (YYYY-MM-DD)", width=200)
        notes = ft.TextField(label="Notes", multiline=True, min_lines=2, width=400)

        items_col = ft.Column(spacing=8, width=600, height=240, scroll=ft.ScrollMode.AUTO)
        items_data = []

        def add_item_row(item_id=None, qty=1, cost=0.0):
            idd = ft.Dropdown(width=220, hint_text="Select Item", options=item_opts)
            if item_id:
                idd.value = str(item_id)
            qf = ft.TextField(value=str(qty), width=70, keyboard_type=ft.KeyboardType.NUMBER)
            cf = ft.TextField(value=f"{cost:.2f}", width=100,
                              keyboard_type=ft.KeyboardType.NUMBER, prefix=ft.Text(sym))
            rb = ft.IconButton(ft.Icons.DELETE, icon_color=ft.Colors.RED_400)
            row_data = {"item_dd": idd, "qty": qf, "cost": cf}
            items_data.append(row_data)
            row = ft.Row([idd, qf, cf, rb], spacing=8)
            items_col.controls.append(row)

            def rm(_e):
                items_col.controls.remove(row)
                items_data.remove(row_data)
                self.page.update()
            rb.on_click = rm
            self.page.update()

        for p in prefill:
            item = fetch_one("SELECT cost_price FROM items WHERE id=?", (p.get("id"),))
            cost = item["cost_price"] if item else 0.0
            add_item_row(p.get("id"), p.get("qty", 1), cost)

        def save_po(e):
            if not supplier_dd.value:
                self.snack("Supplier required", ft.Colors.RED_700)
                return
            if not items_data:
                self.snack("At least one item required", ft.Colors.RED_700)
                return

            try:
                cursor = execute_query(
                    "INSERT INTO purchase_orders (supplier_id, expected_date, notes, created_by) "
                    "VALUES (?, ?, ?, ?)",
                    (int(supplier_dd.value), sanitize(exp_date.value) or None,
                     sanitize(notes.value, 1000), self.user_id)
                )
                po_id = cursor.lastrowid
                total_cost = 0.0
                for rd in items_data:
                    if not rd["item_dd"].value:
                        continue
                    qty = safe_int(rd["qty"].value, lo=1)
                    cost = safe_float(rd["cost"].value)
                    total_cost += qty * cost
                    execute_query(
                        "INSERT INTO po_items (po_id, item_id, quantity_ordered, cost_price) "
                        "VALUES (?, ?, ?, ?)",
                        (po_id, int(rd["item_dd"].value), qty, cost)
                    )
                execute_query("UPDATE purchase_orders SET total_cost=? WHERE id=?", (total_cost, po_id))
                log_audit(self.user_id, "CREATE_PO", f"PO #{po_id} created")
                self.close_dialog(dlg)
                self._refresh_po_list()
                self.snack(f"PO #{po_id} created")
            except Exception as ex:
                self.snack(f"Error: {ex}", ft.Colors.RED_700)

        dlg = ft.AlertDialog(
            title=ft.Text("Create Purchase Order", size=17, weight=ft.FontWeight.BOLD),
            content=ft.Column([
                supplier_dd, exp_date, notes,
                ft.Divider(),
                ft.Text("Items:", weight=ft.FontWeight.W_500),
                items_col,
                ft.OutlinedButton("+ Add Item", icon=ft.Icons.ADD,
                                   on_click=lambda e: add_item_row()),
            ], spacing=10, width=self.dialog_width(680), height=500, scroll=ft.ScrollMode.AUTO),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dlg)),
                ft.ElevatedButton("Save PO", on_click=save_po,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.show_dialog(dlg)

    def _receive_po_dialog(self, e):
        po_id = e.control.data
        po = fetch_one("SELECT status FROM purchase_orders WHERE id=?", (po_id,))
        if not po or po["status"] in (POStatus.RECEIVED, POStatus.CANCELLED):
            self.snack("Cannot receive this PO", ft.Colors.RED_700)
            return

        items = fetch_all("""
            SELECT pi.id, i.name, pi.quantity_ordered, pi.quantity_received, pi.cost_price
            FROM po_items pi
            JOIN items i ON pi.item_id = i.id
            WHERE pi.po_id = ? AND pi.quantity_received < pi.quantity_ordered
        """, (po_id,))
        if not items:
            self.snack("All items already received", ft.Colors.ORANGE_700)
            return

        fields = []
        for it in items:
            remaining = it["quantity_ordered"] - it["quantity_received"]
            qf = ft.TextField(label=f"{it['name']} (max {remaining})", value=str(remaining),
                               keyboard_type=ft.KeyboardType.NUMBER, width=250)
            fields.append((it["id"], qf, it["cost_price"]))

        def do_receive(_e):
            conn = None
            try:
                # We'll use the reusable execute_query but need transaction
                import sqlite3
                from config import DB_FILE
                conn = sqlite3.connect(DB_FILE)
                cur = conn.cursor()
                for pi_id, qf, cost in fields:
                    qty = safe_int(qf.value, lo=0)
                    if qty > 0:
                        cur.execute("UPDATE po_items SET quantity_received = quantity_received + ? WHERE id = ?",
                                    (qty, pi_id))
                        cur.execute("SELECT item_id FROM po_items WHERE id = ?", (pi_id,))
                        item_id = cur.fetchone()[0]
                        cur.execute("UPDATE items SET quantity = quantity + ?, cost_price = ? WHERE id = ?",
                                    (qty, cost, item_id))
                cur.execute("SELECT COUNT(*) FROM po_items WHERE po_id = ? AND quantity_received < quantity_ordered",
                            (po_id,))
                new_status = POStatus.RECEIVED if cur.fetchone()[0] == 0 else POStatus.ORDERED
                cur.execute("UPDATE purchase_orders SET status = ? WHERE id = ?", (new_status, po_id))
                conn.commit()
                log_audit(self.user_id, "RECEIVE_PO", f"PO #{po_id}")
                self.close_dialog(dlg)
                self._refresh_po_list()
                self.snack("Items received successfully")
            except Exception as ex:
                if conn:
                    conn.rollback()
                self.snack(f"Error: {ex}", ft.Colors.RED_700)
            finally:
                if conn:
                    conn.close()

        dlg = ft.AlertDialog(
            title=ft.Text(f"Receive PO #{po_id}"),
            content=ft.Column([qf for _, qf, _ in fields], spacing=8, width=300,
                               height=min(len(fields)*70+20, 400), scroll=ft.ScrollMode.AUTO),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dlg)),
                ft.ElevatedButton("Confirm Receive", on_click=do_receive,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_700,
                                                        color=ft.Colors.WHITE)),
            ],
        )
        self.show_dialog(dlg)