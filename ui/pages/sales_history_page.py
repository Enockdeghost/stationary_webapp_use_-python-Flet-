import flet as ft
import csv
from datetime import datetime, timedelta

from config import currency_symbol, UserRole
from database.connection import fetch_all
from ui.pages.base_page import BasePage
from security.validation import sanitize


class SalesHistoryPage(BasePage):
    def build(self) -> ft.Control:
        sym = currency_symbol()
        date_from = ft.TextField(
            label="From (YYYY-MM-DD)",
            width=155,
            height=45,
            value=(datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
        )
        date_to = ft.TextField(
            label="To (YYYY-MM-DD)",
            width=155,
            height=45,
            value=datetime.now().strftime("%Y-%m-%d"),
        )
        pay_filter = ft.Dropdown(
            label="Payment",
            width=150,
            height=45,
            value="All",
            options=[ft.dropdown.Option(m, m) for m in ("All", "Cash", "Card", "Mobile Money", "Bank Transfer")],
        )
        staff_dd = ft.Dropdown(label="Staff", width=150, height=45, value="All")
        self._load_staff_dropdown(staff_dd)

        self.history_table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(h))
                     for h in ("ID","Date","Customer","Items","Subtotal","Discount","Total","Payment","Staff","")],
            border=ft.Border.all(1, ft.Colors.GREY_300),
            border_radius=8,
            data_row_max_height=44,
        )
        self.summary_text = ft.Text("", size=13, color=ft.Colors.GREY_700)

        def load(e=None):
            self._load_history(date_from, date_to, pay_filter, staff_dd, sym)

        def export_csv(e):
            self._export_sales(sym)

        date_from.on_submit = load
        date_to.on_submit = load
        pay_filter.on_change = load
        staff_dd.on_change = load
        load()

        controls = [date_from, date_to, pay_filter]
        if self.role == UserRole.ADMIN:
            controls.append(staff_dd)
        controls += [
            ft.ElevatedButton("Search", icon=ft.Icons.SEARCH, on_click=load,
                               style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE)),
            ft.OutlinedButton("Export CSV", icon=ft.Icons.DOWNLOAD, on_click=export_csv),
        ]

        return ft.Column([
            ft.Text("Sales History", size=24, weight=ft.FontWeight.BOLD),
            ft.Row(controls, spacing=8, wrap=True),
            ft.Row([ft.Icon(ft.Icons.INFO_OUTLINE, size=15, color=ft.Colors.GREY_500),
                    self.summary_text], spacing=6),
            self.scrollable_table(self.history_table),
        ], expand=True, spacing=14, scroll=ft.ScrollMode.AUTO)

    def _load_staff_dropdown(self, staff_dd: ft.Dropdown):
        rows = fetch_all("SELECT id, username FROM users ORDER BY username")
        staff_dd.options = [ft.dropdown.Option("All", "All Staff")] + [
            ft.dropdown.Option(str(r["id"]), r["username"]) for r in rows
        ]
        staff_dd.value = "All"

    def _load_history(self, date_from, date_to, pay_filter, staff_dd, sym):
        params = []
        query = """
            SELECT s.id, s.sale_date, COALESCE(cu.name,'Walk-in'),
                   COUNT(si.id), s.subtotal, s.discount, s.total,
                   s.payment_method, u.username
            FROM sales s
            LEFT JOIN customers cu ON s.customer_id = cu.id
            LEFT JOIN sale_items si ON si.sale_id = s.id
            LEFT JOIN users u ON s.user_id = u.id
            WHERE 1=1
        """
        if date_from.value:
            query += " AND DATE(s.sale_date) >= ?"
            params.append(date_from.value)
        if date_to.value:
            query += " AND DATE(s.sale_date) <= ?"
            params.append(date_to.value)
        if pay_filter.value and pay_filter.value != "All":
            query += " AND s.payment_method = ?"
            params.append(pay_filter.value)
        if self.role == UserRole.ADMIN and staff_dd.value and staff_dd.value != "All":
            query += " AND s.user_id = ?"
            params.append(staff_dd.value)
        if self.role != UserRole.ADMIN:
            query += " AND s.user_id = ?"
            params.append(str(self.user_id))
        query += " GROUP BY s.id ORDER BY s.sale_date DESC"

        rows = fetch_all(query, tuple(params))
        self.history_table.rows.clear()
        total_rev = 0.0
        for r in rows:
            total_rev += r["total"] or 0
            self.history_table.rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.TextButton(f"#{r['id']}",
                            on_click=lambda e, sid=r['id']: self._show_sale_details(sid))),
                ft.DataCell(ft.Text((r["sale_date"] or "")[:16], size=11)),
                ft.DataCell(ft.Text(r[2] or "—", size=11)),
                ft.DataCell(ft.Text(str(r[3]))),
                ft.DataCell(ft.Text(f"{sym}{(r['subtotal'] or 0):.2f}")),
                ft.DataCell(ft.Text(f"-{sym}{(r['discount'] or 0):.2f}", color=ft.Colors.ORANGE_700)),
                ft.DataCell(ft.Text(f"{sym}{(r['total'] or 0):.2f}", color=ft.Colors.GREEN_700,
                                    weight=ft.FontWeight.W_600)),
                ft.DataCell(ft.Container(
                    ft.Text(r["payment_method"] or "Cash", size=10, color=ft.Colors.WHITE),
                    bgcolor=ft.Colors.BLUE_700, border_radius=6,
                    padding=ft.padding.symmetric(horizontal=5, vertical=2),
                )),
                ft.DataCell(ft.Text(r["username"] or "—", size=11)),
                ft.DataCell(ft.IconButton(ft.Icons.RECEIPT, icon_size=15,
                                          on_click=lambda e, sid=r['id']: self._show_sale_details(sid))),
            ]))
        self.summary_text.value = f"  {len(rows)} transactions  •  Total: {sym}{total_rev:,.2f}"
        self.page.update()

    def _show_sale_details(self, sale_id):
        # Reuse the same dialog logic from original code; simplified here:
        rows = fetch_all(
            """SELECT i.name, si.quantity, si.price_at_sale, si.total
               FROM sale_items si JOIN items i ON si.item_id = i.id
               WHERE si.sale_id = ?""",
            (sale_id,)
        )
        info = fetch_one(
            "SELECT total, payment_method, sale_date, subtotal, discount, tax FROM sales WHERE id = ?",
            (sale_id,)
        )
        if not info:
            return
        sym = currency_symbol()
        content = ft.Column([
            ft.Text(f"Sale #{sale_id} — {(info['sale_date'] or '')[:16]}", weight=ft.FontWeight.BOLD),
            ft.Row([
                ft.Text(f"Subtotal: {sym}{info['subtotal']:.2f}"),
                ft.Text(f"Discount: -{sym}{info['discount']:.2f}"),
                ft.Text(f"Tax: {sym}{info['tax']:.2f}"),
                ft.Text(f"Total: {sym}{info['total']:.2f}", weight=ft.FontWeight.BOLD,
                        color=ft.Colors.GREEN_700),
            ], spacing=10, wrap=True),
            ft.Text(f"Payment: {info['payment_method']}"),
            ft.Divider(),
            ft.Row([ft.DataTable(
                columns=[ft.DataColumn(ft.Text(h)) for h in ("Item", "Qty", "Price", "Total")],
                rows=[ft.DataRow(cells=[
                    ft.DataCell(ft.Text(r["name"])),
                    ft.DataCell(ft.Text(str(r["quantity"]))),
                    ft.DataCell(ft.Text(f"{sym}{r['price_at_sale']:.2f}")),
                    ft.DataCell(ft.Text(f"{sym}{r['total']:.2f}")),
                ]) for r in rows],
                data_row_max_height=40,
            )], scroll=ft.ScrollMode.AUTO),
        ], spacing=10, width=self.dialog_width(560), height=340, scroll=ft.ScrollMode.AUTO)

        dialog = ft.AlertDialog(
            title=ft.Text("Sale Details"),
            content=content,
            actions=[ft.TextButton("Close", on_click=lambda _: self.close_dialog(dialog))],
        )
        self.show_dialog(dialog)

    def _export_sales(self, sym):
        rows = fetch_all("""
            SELECT s.id, s.sale_date, COALESCE(cu.name,'Walk-in'),
                   s.subtotal, s.discount, s.tax, s.total,
                   s.payment_method, u.username
            FROM sales s
            LEFT JOIN customers cu ON s.customer_id = cu.id
            LEFT JOIN users u ON s.user_id = u.id
            ORDER BY s.sale_date DESC
        """)
        fn = f"sales_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        with open(fn, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["ID","Date","Customer","Subtotal","Discount","Tax","Total","Payment","Staff"])
            writer.writerows([tuple(r) for r in rows])
        self.snack(f"Exported → {fn}")