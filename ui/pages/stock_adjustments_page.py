import flet as ft

from config import UserRole
from database.connection import fetch_all, execute_query, fetch_one
from ui.pages.base_page import BasePage
from security.validation import sanitize, safe_int
from utils.audit import log_audit


class StockAdjustmentsPage(BasePage):
    def __init__(self, app):
        super().__init__(app)
        self.adj_table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(h)) for h in
                     ("Date","Item","Before","Change","After","Reason","Staff")],
            border=ft.Border.all(1, ft.Colors.GREY_300),
            border_radius=8,
            data_row_max_height=44,
        )

    def build(self) -> ft.Control:
        if self.role != UserRole.ADMIN:
            return ft.Column([ft.Text("Access denied", color=ft.Colors.RED_700)])

        self._refresh_adj_table()

        def new_adj(e):
            self._open_adjustment_dialog()

        return ft.Column([
            ft.Text("Stock Adjustments", size=24, weight=ft.FontWeight.BOLD),
            ft.Text("All adjustments are logged for audit purposes.",
                    size=12, color=ft.Colors.GREY_600),
            ft.Row([
                ft.ElevatedButton("+ New Adjustment", icon=ft.Icons.TUNE, on_click=new_adj,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE)),
                ft.OutlinedButton("Refresh", icon=ft.Icons.REFRESH,
                                   on_click=lambda e: self._refresh_adj_table()),
            ], spacing=10),
            self.scrollable_table(self.adj_table),
        ], expand=True, spacing=14, scroll=ft.ScrollMode.AUTO)

    def _refresh_adj_table(self, e=None):
        rows = fetch_all("""
            SELECT sa.timestamp, i.name, sa.quantity_before, sa.quantity_change,
                   sa.quantity_after, COALESCE(sa.reason,'—'), COALESCE(u.username,'—')
            FROM stock_adjustments sa
            JOIN items i ON sa.item_id = i.id
            LEFT JOIN users u ON sa.user_id = u.id
            ORDER BY sa.timestamp DESC LIMIT 200
        """)
        self.adj_table.rows.clear()
        for ts, name, before, change, after, reason, staff in rows:
            col = (ft.Colors.GREEN_700 if change > 0 else
                   ft.Colors.RED_700 if change < 0 else ft.Colors.GREY_600)
            self.adj_table.rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text((ts or "")[:16], size=11)),
                ft.DataCell(ft.Text(name, weight=ft.FontWeight.W_500)),
                ft.DataCell(ft.Text(str(before))),
                ft.DataCell(ft.Text(f"{'+' if change > 0 else ''}{change}",
                                    color=col, weight=ft.FontWeight.BOLD)),
                ft.DataCell(ft.Text(str(after))),
                ft.DataCell(ft.Text(reason, size=11)),
                ft.DataCell(ft.Text(staff, size=11)),
            ]))
        self.page.update()

    def _open_adjustment_dialog(self):
        rows = fetch_all("SELECT id, name, quantity FROM items ORDER BY name")
        item_dd = ft.Dropdown(
            label="Item *", width=280,
            options=[ft.dropdown.Option(str(r["id"]), f"{r['name']} (stock: {r['quantity']})") for r in rows]
        )
        adj_type = ft.Dropdown(
            label="Type", width=180, value="add",
            options=[ft.dropdown.Option("add", "Add Stock"),
                     ft.dropdown.Option("remove", "Remove Stock"),
                     ft.dropdown.Option("set", "Set Exact Qty")]
        )
        qty_f = ft.TextField(label="Quantity", width=110,
                              keyboard_type=ft.KeyboardType.NUMBER, value="1")
        reason_f = ft.TextField(label="Reason", expand=True)
        err = ft.Text("", color=ft.Colors.RED_400)

        def save_adj(_e):
            if not item_dd.value:
                err.value = "Select an item"; err.update(); return
            qty = safe_int(qty_f.value, lo=1)
            if qty < 1:
                err.value = "Qty must be ≥ 1"; err.update(); return

            item_id = int(item_dd.value)
            item = fetch_one("SELECT quantity FROM items WHERE id=?", (item_id,))
            if not item:
                err.value = "Item not found"; err.update(); return

            before = item["quantity"]
            after = (before + qty if adj_type.value == "add" else
                     max(0, before - qty) if adj_type.value == "remove" else qty)
            change = after - before

            execute_query("UPDATE items SET quantity=? WHERE id=?", (after, item_id))
            execute_query(
                "INSERT INTO stock_adjustments (item_id, quantity_before, quantity_change, quantity_after, reason, user_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (item_id, before, change, after, sanitize(reason_f.value), self.user_id)
            )
            log_audit(self.user_id, "STOCK_ADJ", f"#{item_id}: {before}→{after}")
            self.close_dialog(dlg)
            self._refresh_adj_table()
            self.snack(f"Stock adjusted: {before} → {after}")

        dlg = ft.AlertDialog(
            title=ft.Text("New Stock Adjustment", size=17, weight=ft.FontWeight.BOLD),
            content=ft.Column([
                ft.Row([item_dd, adj_type], spacing=10, wrap=True),
                ft.Row([qty_f, reason_f], spacing=10),
                err,
            ], spacing=10, width=self.dialog_width(560), height=160, scroll=ft.ScrollMode.AUTO),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dlg)),
                ft.ElevatedButton("Save", on_click=save_adj,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.show_dialog(dlg)