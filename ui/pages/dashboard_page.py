# ui/pages/dashboard_page.py
import flet as ft
import flet_charts as fch
from datetime import datetime

from config import currency_symbol
from database.connection import fetch_all, fetch_one
from ui.pages.base_page import BasePage


class _T:
    BLUE        = "#1D4ED8"
    BLUE_LIGHT  = "#DBEAFE"
    GREEN       = "#059669"
    GREEN_LIGHT = "#D1FAE5"
    AMBER       = "#D97706"
    AMBER_LIGHT = "#FEF3C7"
    RED         = "#DC2626"
    RED_LIGHT   = "#FEE2E2"
    INDIGO      = "#4F46E5"
    INDIGO_LIGHT= "#EEF2FF"
    SURFACE     = "#FFFFFF"
    BORDER      = "#E2E8F0"
    TEXT_PRI    = "#0F172A"
    TEXT_SEC    = "#64748B"
    TEXT_MUTED  = "#94A3B8"
    CHART_COLORS = ["#1D4ED8","#059669","#D97706","#4F46E5","#0EA5E9"]
    RADIUS = 12


def _divider(opacity: float = 1.0):
    return ft.Divider(height=1, color=ft.Colors.with_opacity(opacity, _T.BORDER))


def _card(content: ft.Control, padding: int = 20) -> ft.Container:
    return ft.Container(
        content=ft.Container(
            content=content,
            padding=padding,
            border_radius=_T.RADIUS,
            bgcolor=_T.SURFACE,
        ),
        shadow=ft.BoxShadow(
            blur_radius=8,
            spread_radius=0,
            color=ft.Colors.with_opacity(0.08, "#000000"),
            offset=ft.Offset(0, 2),
        ),
        border_radius=_T.RADIUS,
    )


def _badge(text: str, bg: str, fg: str = "#FFFFFF") -> ft.Container:
    return ft.Container(
        content=ft.Text(text, size=10, color=fg, weight=ft.FontWeight.W_700),
        bgcolor=bg,
        border_radius=6,
        padding=ft.padding.symmetric(horizontal=8, vertical=3),
    )


class DashboardPage(BasePage):

    def build(self) -> ft.Control:
        stats         = self._get_statistics()
        daily_data    = self._get_daily_sales()
        top_products  = self._get_top_products()
        recent_sales  = self._get_recent_sales()
        reorder_items = self._get_reorder_suggestions()
        sym = currency_symbol()

        charts_row = ft.ResponsiveRow([
            ft.Container(self._build_line_chart(daily_data, sym),  col={"xs": 12, "lg": 4}),
            ft.Container(self._build_bar_chart(daily_data, sym),   col={"xs": 12, "lg": 4}),
            ft.Container(self._build_pie_chart(top_products, sym), col={"xs": 12, "lg": 4}),
        ], spacing=12, run_spacing=12)

        return ft.Column(
            controls=[
                self._build_header(),
                self._build_kpi_row(stats, sym),
                charts_row,
                self._build_bottom_row(recent_sales, reorder_items, sym),
            ],
            spacing=20,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def _get_statistics(self):
        import sqlite3
        from config import DB_FILE
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT COALESCE(SUM(quantity),0) FROM items")
        total_qty = c.fetchone()[0]
        c.execute("SELECT COALESCE(SUM(quantity*price),0.0) FROM items")
        total_val = c.fetchone()[0]
        today = datetime.now().strftime("%Y-%m-%d")
        c.execute("SELECT COALESCE(SUM(total),0.0) FROM sales WHERE DATE(sale_date)=?", (today,))
        today_rev = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM sales WHERE DATE(sale_date)=?", (today,))
        today_cnt = c.fetchone()[0]
        month = datetime.now().strftime("%Y-%m")
        c.execute("SELECT COALESCE(SUM(amount),0) FROM expenses WHERE strftime('%Y-%m',expense_date)=?", (month,))
        month_exp = c.fetchone()[0]
        conn.close()
        return {
            "total_qty": total_qty,
            "total_val": total_val,
            "today_rev": today_rev,
            "today_cnt": today_cnt,
            "month_exp": month_exp,
        }

    def _get_daily_sales(self):
        return fetch_all(
            """SELECT DATE(sale_date), COUNT(*), COALESCE(SUM(total),0)
               FROM sales WHERE sale_date >= DATE('now','-6 days')
               GROUP BY DATE(sale_date) ORDER BY 1"""
        )

    def _get_top_products(self):
        return fetch_all(
            """SELECT i.name, COALESCE(SUM(si.quantity),0), COALESCE(SUM(si.total),0)
               FROM sale_items si JOIN items i ON si.item_id = i.id
               GROUP BY si.item_id ORDER BY SUM(si.total) DESC LIMIT 5"""
        )

    def _get_recent_sales(self):
        return fetch_all(
            """SELECT s.id, s.sale_date, COALESCE(cu.name,'Walk-in'), s.total, s.payment_method
               FROM sales s LEFT JOIN customers cu ON s.customer_id = cu.id
               ORDER BY s.sale_date DESC LIMIT 8"""
        )

    def _get_reorder_suggestions(self):
        return fetch_all(
            """SELECT id, name, quantity, low_stock_threshold, supplier_id
               FROM items WHERE quantity <= low_stock_threshold
               ORDER BY (low_stock_threshold*2 - quantity) DESC LIMIT 8"""
        )

    def _build_header(self) -> ft.Control:
        hour = datetime.now().hour
        greeting = (
            "Good morning"   if hour < 12 else
            "Good afternoon" if hour < 18 else
            "Good evening"
        )
        today_str = datetime.now().strftime("%A, %d %B %Y")
        left = ft.Column([
            ft.Text(f"{greeting}, {self.username}", size=26, weight=ft.FontWeight.BOLD, color=_T.TEXT_PRI),
            ft.Text(today_str, size=13, color=_T.TEXT_SEC, weight=ft.FontWeight.W_400),
        ], spacing=2, tight=True)
        right = ft.Container(
            content=ft.Row([
                ft.Container(width=8, height=8, bgcolor=_T.GREEN, border_radius=4),
                ft.Text("Live data", size=12, color=_T.GREEN, weight=ft.FontWeight.W_600),
            ], spacing=6),
            bgcolor=_T.GREEN_LIGHT,
            border_radius=20,
            padding=ft.padding.symmetric(horizontal=14, vertical=7),
        )
        return ft.Row(
            controls=[left, right],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _build_kpi_row(self, stats: dict, sym: str) -> ft.ResponsiveRow:
        kpis = [
            ("Total Stock", f"{stats['total_qty']:,}", "units in inventory",
             ft.Icons.INVENTORY_2, _T.BLUE, _T.BLUE_LIGHT),
            ("Inventory Value", f"{sym}{stats['total_val']:,.2f}", "current stock worth",
             ft.Icons.ACCOUNT_BALANCE_WALLET, _T.GREEN, _T.GREEN_LIGHT),
            ("Today Revenue", f"{sym}{stats['today_rev']:,.2f}", "sales today",
             ft.Icons.TRENDING_UP, _T.INDIGO, _T.INDIGO_LIGHT),
            ("Today Transactions", f"{stats['today_cnt']:,}", "orders processed",
             ft.Icons.RECEIPT_LONG, _T.AMBER, _T.AMBER_LIGHT),
            ("Month Expenses", f"{sym}{stats['month_exp']:,.2f}", "total this month",
             ft.Icons.PAYMENTS, _T.RED, _T.RED_LIGHT),
        ]
        cards = []
        for title, value, sub, icon, accent, light in kpis:
            c = self._kpi_card(title, value, sub, icon, accent, light)
            c.col = {"xs": 12, "sm": 6, "md": 4, "lg": 2}
            cards.append(c)
        return ft.ResponsiveRow(controls=cards, spacing=12, run_spacing=12)

    def _kpi_card(self, title: str, value: str, sub: str,
                  icon, accent: str, light: str) -> ft.Container:
        return ft.Container(
            content=ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Container(
                            content=ft.Icon(icon, size=20, color=accent),
                            bgcolor=light,
                            border_radius=8,
                            padding=8,
                        ),
                    ]),
                    ft.Container(height=8),
                    ft.Text(value, size=22, weight=ft.FontWeight.BOLD, color=_T.TEXT_PRI),
                    ft.Text(title, size=12, color=_T.TEXT_SEC, weight=ft.FontWeight.W_600),
                    ft.Text(sub, size=10, color=_T.TEXT_MUTED),
                ], spacing=2, tight=True),
                bgcolor=_T.SURFACE,
                padding=ft.padding.all(16),
                border=ft.Border(left=ft.BorderSide(4, accent)),
                border_radius=ft.BorderRadius(
                    top_left=0, bottom_left=0,
                    top_right=_T.RADIUS, bottom_right=_T.RADIUS,
                ),
            ),
            shadow=ft.BoxShadow(
                blur_radius=8,
                spread_radius=0,
                color=ft.Colors.with_opacity(0.08, "#000000"),
                offset=ft.Offset(0, 2),
            ),
            border_radius=_T.RADIUS,
        )

    def _build_line_chart(self, daily_data, sym):
        if not daily_data:
            return _card(ft.Container(
                ft.Text("No sales data", color=_T.TEXT_MUTED, size=13),
                alignment=ft.Alignment(0, 0),
                height=160,
            ))

        data_points = [
            fch.LineChartDataPoint(x=i, y=float(cnt))
            for i, (_, cnt, _) in enumerate(daily_data)
        ]

        chart = fch.LineChart(
            data_series=[
                fch.LineChartData(
                    points=data_points,
                    stroke_width=3,
                    color=_T.BLUE,
                    curved=True,
                    rounded_stroke_cap=True,
                    rounded_stroke_join=True,
                )
            ],
            border=ft.Border.all(0, ft.Colors.TRANSPARENT),
            left_axis=fch.ChartAxis(label_size=40, show_labels=True),
            bottom_axis=fch.ChartAxis(
                labels=[
                    fch.ChartAxisLabel(value=i, label=ft.Text(date[-5:], size=10, color=_T.TEXT_SEC))
                    for i, (date, _, _) in enumerate(daily_data)
                ],
                label_size=28,
            ),
            horizontal_grid_lines=fch.ChartGridLines(
                interval=1,
                color=ft.Colors.with_opacity(0.1, _T.TEXT_PRI),
                width=1,
            ),
            tooltip=fch.LineChartTooltip(bgcolor=ft.Colors.with_opacity(0.8, "#0F172A")),
            min_y=0,
            max_y=max(cnt for _, cnt, _ in daily_data) * 1.3,
            expand=True,
        )
        return _card(ft.Column([
            ft.Text("Sales Trend (units)", size=14, weight=ft.FontWeight.W_600, color=_T.TEXT_PRI),
            ft.Container(chart, height=180),
        ], spacing=10))

    def _build_bar_chart(self, daily_data, sym):
        if not daily_data:
            return _card(ft.Container(
                ft.Text("No revenue data", color=_T.TEXT_MUTED, size=13),
                alignment=ft.Alignment(0, 0),
                height=160,
            ))

        max_rev = max(rev for _, _, rev in daily_data) or 1
        bar_groups = [
            fch.BarChartGroup(
                x=i,
                rods=[
                    fch.BarChartRod(
                        from_y=0,
                        to_y=rev,
                        width=22,
                        color=_T.GREEN,
                        border_radius=ft.BorderRadius(4, 4, 0, 0),
                        tooltip=f"{sym}{rev:,.2f}",
                    )
                ],
            )
            for i, (_, _, rev) in enumerate(daily_data)
        ]

        chart = fch.BarChart(
            groups=bar_groups,
            border=ft.Border.all(0, ft.Colors.TRANSPARENT),
            left_axis=fch.ChartAxis(label_size=40, show_labels=True),
            bottom_axis=fch.ChartAxis(
                labels=[
                    fch.ChartAxisLabel(value=i, label=ft.Text(date[-5:], size=10, color=_T.TEXT_SEC))
                    for i, (date, _, _) in enumerate(daily_data)
                ],
                label_size=28,
            ),
            horizontal_grid_lines=fch.ChartGridLines(
                interval=max_rev / 4,
                color=ft.Colors.with_opacity(0.1, _T.TEXT_PRI),
                width=1,
            ),
            tooltip=fch.BarChartTooltip(bgcolor=ft.Colors.with_opacity(0.8, "#0F172A")),
            max_y=max_rev * 1.2,
            min_y=0,
            expand=True,
        )
        return _card(ft.Column([
            ft.Text("Daily Revenue", size=14, weight=ft.FontWeight.W_600, color=_T.TEXT_PRI),
            ft.Container(chart, height=180),
        ], spacing=10))

    def _build_pie_chart(self, top_products, sym):
        if not top_products:
            return _card(ft.Container(
                ft.Text("No product data", color=_T.TEXT_MUTED, size=13),
                alignment=ft.Alignment(0, 0),
                height=160,
            ))

        total = sum(rev for _, _, rev in top_products) or 1
        sections = [
            fch.PieChartSection(
                value=(rev / total) * 100,
                title=f"{name[:10]}: {int((rev/total)*100)}%",
                title_style=ft.TextStyle(size=9, color=ft.Colors.WHITE),
                color=_T.CHART_COLORS[i % len(_T.CHART_COLORS)],
                radius=60,
            )
            for i, (name, _, rev) in enumerate(top_products)
        ]

        chart = fch.PieChart(
            sections=sections,
            sections_space=2,
            center_space_radius=30,
            expand=True,
        )
        return _card(ft.Column([
            ft.Text("Product Distribution", size=14, weight=ft.FontWeight.W_600, color=_T.TEXT_PRI),
            ft.Container(chart, height=180),
        ], spacing=10))

    def _build_bottom_row(self, recent_sales, reorder_items, sym: str) -> ft.ResponsiveRow:
        left  = self._build_recent_sales_card(recent_sales, sym)
        right = self._build_reorder_card(reorder_items, sym)
        left.col  = {"xs": 12, "md": 7}
        right.col = {"xs": 12, "md": 5}
        return ft.ResponsiveRow([left, right], spacing=12, run_spacing=12)

    def _build_recent_sales_card(self, recent_sales, sym: str) -> ft.Container:
        header = self._section_header("Recent Transactions", ft.Icons.RECEIPT_LONG, _T.BLUE)

        if not recent_sales:
            return ft.Container(content=_card(ft.Column([
                header,
                ft.Container(
                    ft.Text("No sales yet", color=_T.TEXT_MUTED, size=13),
                    alignment=ft.Alignment(0, 0),
                    height=80,
                ),
            ], spacing=14)))

        col_hdr = ft.Container(
            content=ft.Row([
                ft.Text("ID", size=10, color=_T.TEXT_MUTED, weight=ft.FontWeight.W_600, width=44),
                ft.Text("Date", size=10, color=_T.TEXT_MUTED, weight=ft.FontWeight.W_600, expand=True),
                ft.Text("Customer", size=10, color=_T.TEXT_MUTED, weight=ft.FontWeight.W_600, expand=True),
                ft.Text("Total", size=10, color=_T.TEXT_MUTED, weight=ft.FontWeight.W_600, width=84,
                        text_align=ft.TextAlign.RIGHT),
                ft.Text("Method", size=10, color=_T.TEXT_MUTED, weight=ft.FontWeight.W_600, width=80),
            ], spacing=8),
            padding=ft.padding.symmetric(horizontal=4, vertical=4),
        )

        METHOD_COLOR = {
            "Cash": _T.GREEN,
            "Card": _T.BLUE,
            "Mobile Money": _T.AMBER,
            "Bank Transfer": _T.INDIGO,
        }

        sale_rows = []
        for i, (sid, sdate, cname, tot, pay) in enumerate(recent_sales):
            bg = ft.Colors.with_opacity(0.03, _T.TEXT_PRI) if i % 2 == 0 else ft.Colors.TRANSPARENT
            sale_rows.append(
                ft.Container(
                    content=ft.Row([
                        ft.TextButton(
                            f"#{sid}",
                            style=ft.ButtonStyle(
                                color=_T.BLUE,
                                padding=ft.padding.all(0),
                                overlay_color=ft.Colors.TRANSPARENT,
                            ),
                            on_click=lambda e, s=sid: self._show_sale_details(s),
                        ),
                        ft.Text((sdate or "")[:16], size=11, color=_T.TEXT_SEC, expand=True),
                        ft.Text(
                            cname if len(cname) <= 14 else cname[:12] + "…",
                            size=11, color=_T.TEXT_PRI, expand=True, weight=ft.FontWeight.W_500,
                        ),
                        ft.Text(
                            f"{sym}{tot:.2f}",
                            size=12, color=_T.GREEN, weight=ft.FontWeight.W_700,
                            width=84, text_align=ft.TextAlign.RIGHT,
                        ),
                        ft.Container(
                            content=ft.Text(pay or "Cash", size=9, color="#FFFFFF", weight=ft.FontWeight.W_600),
                            bgcolor=METHOD_COLOR.get(pay or "Cash", _T.TEXT_SEC),
                            border_radius=5,
                            padding=ft.padding.symmetric(horizontal=7, vertical=3),
                            width=80,
                            alignment=ft.Alignment(0, 0),
                        ),
                    ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    bgcolor=bg,
                    border_radius=6,
                    padding=ft.padding.symmetric(horizontal=4, vertical=6),
                )
            )

        content = ft.Column([
            header,
            _divider(),
            col_hdr,
            _divider(0.4),
            ft.Column(sale_rows, spacing=0),
        ], spacing=8)

        return ft.Container(content=_card(content, padding=18))

    def _build_reorder_card(self, reorder_items, sym: str) -> ft.Container:
        header = ft.Row([
            ft.Container(
                content=ft.Icon(ft.Icons.WARNING_AMBER, size=16, color=_T.AMBER),
                bgcolor=_T.AMBER_LIGHT,
                border_radius=7,
                padding=6,
            ),
            ft.Column([
                ft.Text("Reorder Suggestions", size=13, weight=ft.FontWeight.W_700, color=_T.TEXT_PRI),
                ft.Text("Items below minimum stock", size=10, color=_T.TEXT_MUTED),
            ], spacing=1, tight=True),
        ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        if not reorder_items:
            ok = ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=36, color=_T.GREEN),
                    ft.Text("All stock levels are healthy", size=12, color=_T.TEXT_SEC,
                            text_align=ft.TextAlign.CENTER),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                alignment=ft.Alignment(0, 0),
                height=120,
            )
            return ft.Container(content=_card(ft.Column([header, _divider(), ok], spacing=14), padding=18))

        item_rows = []
        for iid, name, qty, threshold, sup_id in reorder_items:
            suggest = max(threshold * 2 - qty, 1)
            urgency = (
                _T.RED if qty == 0 else
                _T.AMBER if qty <= threshold // 2 else
                _T.TEXT_SEC
            )
            item_rows.append(
                ft.Container(
                    content=ft.Row([
                        ft.Column([
                            ft.Text(
                                name if len(name) <= 18 else name[:16] + "…",
                                size=11, color=_T.TEXT_PRI, weight=ft.FontWeight.W_600,
                            ),
                            ft.Row([
                                ft.Text("Stock:", size=9, color=_T.TEXT_MUTED),
                                ft.Text(str(qty), size=9, color=urgency, weight=ft.FontWeight.BOLD),
                                ft.Text(f"/ Min {threshold}", size=9, color=_T.TEXT_MUTED),
                            ], spacing=3),
                        ], spacing=2, tight=True, expand=True),
                        ft.Container(
                            content=ft.Text(f"Order {suggest}", size=9, color=_T.BLUE,
                                            weight=ft.FontWeight.W_600),
                            bgcolor=_T.BLUE_LIGHT,
                            border_radius=5,
                            padding=ft.padding.symmetric(horizontal=7, vertical=3),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.ADD_SHOPPING_CART,
                            icon_color=_T.BLUE,
                            icon_size=18,
                            tooltip="Create Purchase Order",
                            data={"id": iid, "name": name, "qty": suggest, "sup_id": sup_id},
                            on_click=self._create_po_from_suggestion,
                            style=ft.ButtonStyle(
                                padding=ft.padding.all(4),
                                overlay_color=_T.BLUE_LIGHT,
                            ),
                        ),
                    ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    bgcolor=ft.Colors.with_opacity(0.025, urgency),
                    border=ft.Border(left=ft.BorderSide(3, urgency)),
                    border_radius=ft.BorderRadius(
                        top_left=0, bottom_left=0,
                        top_right=6, bottom_right=6,
                    ),
                    padding=ft.padding.symmetric(horizontal=10, vertical=8),
                )
            )

        bulk_btn = ft.Container(
            content=ft.ElevatedButton(
                text="Create PO for All",
                icon=ft.Icons.SHOPPING_CART,
                on_click=self._create_po_from_all_suggestions,
                style=ft.ButtonStyle(
                    bgcolor=_T.BLUE,
                    color="#FFFFFF",
                    shape=ft.RoundedRectangleBorder(radius=8),
                    padding=ft.padding.symmetric(horizontal=16, vertical=12),
                    elevation=0,
                ),
            ),
            padding=ft.padding.only(top=4),
        )

        content = ft.Column(
            [header, _divider()] + item_rows + [bulk_btn],
            spacing=8,
        )
        return ft.Container(content=_card(content, padding=18))

    def _section_header(self, title: str, icon, icon_color: str) -> ft.Row:
        return ft.Row([
            ft.Container(
                content=ft.Icon(icon, size=15, color=icon_color),
                bgcolor=ft.Colors.with_opacity(0.1, icon_color),
                border_radius=7,
                padding=6,
            ),
            ft.Text(title, size=13, weight=ft.FontWeight.W_700, color=_T.TEXT_PRI),
        ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _mini_pill(self, value: str, label: str, accent: str, light: str) -> ft.Container:
        return ft.Container(
            content=ft.Column([
                ft.Text(value, size=13, weight=ft.FontWeight.BOLD, color=accent),
                ft.Text(label, size=9, color=_T.TEXT_MUTED),
            ], spacing=1, tight=True),
            bgcolor=light,
            border_radius=8,
            padding=ft.padding.symmetric(horizontal=12, vertical=6),
        )

    def _show_sale_details(self, sale_id):
        sym  = currency_symbol()
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

        detail_rows = [
            ft.DataRow(cells=[
                ft.DataCell(ft.Text(r["name"], size=12)),
                ft.DataCell(ft.Text(str(r["quantity"]), size=12)),
                ft.DataCell(ft.Text(f"{sym}{r['price_at_sale']:.2f}", size=12)),
                ft.DataCell(ft.Text(f"{sym}{r['total']:.2f}", size=12,
                                    color=_T.GREEN, weight=ft.FontWeight.W_600)),
            ]) for r in rows
        ]

        summary_row = ft.Row([
            self._mini_pill(f"{sym}{info['subtotal']:.2f}", "Subtotal", _T.BLUE, _T.BLUE_LIGHT),
            self._mini_pill(f"{sym}{info['discount']:.2f}", "Discount", _T.AMBER, _T.AMBER_LIGHT),
            self._mini_pill(f"{sym}{info['tax']:.2f}", "Tax", _T.INDIGO, _T.INDIGO_LIGHT),
            self._mini_pill(f"{sym}{info['total']:.2f}", "Total", _T.GREEN, _T.GREEN_LIGHT),
        ], spacing=8, wrap=True)

        w = self.dialog_width(580)
        content = ft.Column([
            ft.Row([
                ft.Text(f"Sale #{sale_id}", size=16, weight=ft.FontWeight.BOLD, color=_T.TEXT_PRI),
                _badge(info["payment_method"] or "Cash", _T.BLUE),
            ], spacing=10, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Text((info["sale_date"] or "")[:16], size=11, color=_T.TEXT_SEC),
            summary_row,
            _divider(),
            ft.Row([ft.DataTable(
                columns=[ft.DataColumn(ft.Text(h, size=10, color=_T.TEXT_MUTED))
                         for h in ("Item", "Qty", "Unit Price", "Total")],
                rows=detail_rows,
                data_row_max_height=38,
                heading_row_height=36,
            )], scroll=ft.ScrollMode.AUTO),
        ], spacing=12, width=w, height=360, scroll=ft.ScrollMode.AUTO)

        dialog = ft.AlertDialog(
            title=ft.Text("Transaction Details", size=16, weight=ft.FontWeight.BOLD, color=_T.TEXT_PRI),
            content=content,
            actions=[ft.TextButton("Close", on_click=lambda _: self.close_dialog(dialog),
                                   style=ft.ButtonStyle(color=_T.BLUE))],
        )
        self.show_dialog(dialog)

    def _create_po_from_suggestion(self, e):
        self.app.open_purchase_order_dialog(prefill=[e.control.data])

    def _create_po_from_all_suggestions(self, e):
        rows = fetch_all(
            """SELECT id, name, quantity, low_stock_threshold, supplier_id
               FROM items WHERE quantity <= low_stock_threshold"""
        )
        prefilled = [
            {"id": iid, "name": name, "qty": max(threshold * 2 - qty, 1), "sup_id": sup_id}
            for iid, name, qty, threshold, sup_id in rows
        ]
        self.app.open_purchase_order_dialog(prefill=prefilled)