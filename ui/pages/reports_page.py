import flet as ft
from datetime import datetime, timedelta

from config import currency_symbol
from database.connection import fetch_all, fetch_one
from ui.pages.base_page import BasePage


class ReportsPage(BasePage):
    def build(self) -> ft.Control:
        sym = currency_symbol()

        # P&L summary query
        total_rev = fetch_one("SELECT COALESCE(SUM(total),0) FROM sales")[0]
        total_cogs = fetch_one("""
            SELECT COALESCE(SUM(si.quantity * i.cost_price),0)
            FROM sale_items si JOIN items i ON si.item_id = i.id
        """)[0]
        total_exp = fetch_one("SELECT COALESCE(SUM(amount),0) FROM expenses")[0]
        gross = total_rev - total_cogs
        net = gross - total_exp

        def pnl_row(label, val, color=None, bold=False):
            return ft.Row([
                ft.Text(label, size=13, weight=ft.FontWeight.BOLD if bold else None),
                ft.Text(f"{sym}{val:,.2f}", size=13 if not bold else 16,
                        color=color or (ft.Colors.GREEN_700 if val >= 0 else ft.Colors.RED_700),
                        weight=ft.FontWeight.BOLD if bold else None),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        pl_card = ft.Card(
            content=ft.Container(ft.Column([
                ft.Text("Profit & Loss Summary", size=15, weight=ft.FontWeight.W_600),
                ft.Divider(height=6),
                pnl_row("Total Revenue:", total_rev, ft.Colors.GREEN_700),
                pnl_row("Cost of Goods Sold:", total_cogs, ft.Colors.ORANGE_700),
                pnl_row("Gross Profit:", gross),
                pnl_row("Total Expenses:", total_exp, ft.Colors.RED_400),
                ft.Divider(),
                pnl_row("Net Profit:", net, bold=True),
            ]), padding=16),
            elevation=2, expand=True,
        )

        # Month selector for staff performance
        months = []
        for i in range(6):
            d = datetime.now().replace(day=1) - timedelta(days=30*i)
            months.append((d.strftime("%Y-%m"), d.strftime("%B %Y")))
        sel_month = ft.Dropdown(
            label="Month", width=200,
            value=months[0][0] if months else None,
            options=[ft.dropdown.Option(m[0], m[1]) for m in months]
        )
        staff_table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(h)) for h in ("Staff","Sales","Revenue")],
            border=ft.Border.all(1, ft.Colors.GREY_300), border_radius=8,
        )

        def update_staff(e=None):
            m = sel_month.value
            if not m: return
            rows = fetch_all("""
                SELECT u.username, COUNT(s.id), COALESCE(SUM(s.total),0)
                FROM sales s JOIN users u ON s.user_id = u.id
                WHERE strftime('%Y-%m', s.sale_date) = ?
                GROUP BY u.id ORDER BY SUM(s.total) DESC
            """, (m,))
            staff_table.rows = [
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(r["username"])),
                    ft.DataCell(ft.Text(str(r[1]))),
                    ft.DataCell(ft.Text(f"{sym}{r[2]:,.2f}", color=ft.Colors.GREEN_700)),
                ]) for r in rows
            ] or [ft.DataRow(cells=[ft.DataCell(ft.Text("No data"))] * 3)]
            self.page.update()

        sel_month.on_change = update_staff

        # Last 7 days sales
        daily_rows = fetch_all("""
            SELECT DATE(sale_date), COUNT(*), COALESCE(SUM(total),0)
            FROM sales WHERE sale_date >= DATE('now','-6 days')
            GROUP BY DATE(sale_date) ORDER BY 1
        """)
        daily_data_rows = [
            ft.DataRow(cells=[
                ft.DataCell(ft.Text(r[0] or "—")),
                ft.DataCell(ft.Text(str(r[1]))),
                ft.DataCell(ft.Text(f"{sym}{r[2]:,.2f}", color=ft.Colors.GREEN_700)),
            ]) for r in daily_rows
        ]

        # Top products
        top_rows = fetch_all("""
            SELECT i.name, COALESCE(SUM(si.quantity),0), COALESCE(SUM(si.total),0)
            FROM sale_items si JOIN items i ON si.item_id = i.id
            GROUP BY si.item_id ORDER BY SUM(si.total) DESC LIMIT 10
        """)
        top_data_rows = [
            ft.DataRow(cells=[
                ft.DataCell(ft.Text(r[0], overflow=ft.TextOverflow.ELLIPSIS, width=160)),
                ft.DataCell(ft.Text(str(int(r[1])))),
                ft.DataCell(ft.Text(f"{sym}{r[2]:,.2f}", color=ft.Colors.GREEN_700,
                                    weight=ft.FontWeight.W_600)),
            ]) for r in top_rows
        ]

        update_staff()

        # Responsive layout
        r1 = ft.Container(content=pl_card); r1.col = {"xs": 12, "md": 6}
        r2 = ft.Container(
            content=ft.Card(
                content=ft.Container(ft.Column([
                    ft.Text("Staff Performance", size=14, weight=ft.FontWeight.W_600),
                    sel_month,
                    ft.Row([staff_table], scroll=ft.ScrollMode.AUTO),
                ]), padding=14),
                elevation=2,
            ),
        ); r2.col = {"xs": 12, "md": 6}
        top_row = ft.ResponsiveRow([r1, r2], spacing=12, run_spacing=12)

        return ft.Column([
            ft.Text("Reports & Analytics", size=24, weight=ft.FontWeight.BOLD),
            top_row,
            ft.Card(content=ft.Container(ft.Column([
                ft.Text("Sales — Last 7 Days", size=14, weight=ft.FontWeight.W_600),
                ft.Row([ft.DataTable(
                    columns=[ft.DataColumn(ft.Text(h)) for h in ("Date","Orders","Revenue")],
                    rows=daily_data_rows or [ft.DataRow(cells=[ft.DataCell(ft.Text("No data"))]*3)],
                )], scroll=ft.ScrollMode.AUTO),
            ]), padding=14), elevation=2),
            ft.Card(content=ft.Container(ft.Column([
                ft.Text("Top Products", size=14, weight=ft.FontWeight.W_600),
                ft.Row([ft.DataTable(
                    columns=[ft.DataColumn(ft.Text(h)) for h in ("Product","Qty","Revenue")],
                    rows=top_data_rows or [ft.DataRow(cells=[ft.DataCell(ft.Text("No data"))]*3)],
                )], scroll=ft.ScrollMode.AUTO),
            ]), padding=14), elevation=2),
        ], spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)