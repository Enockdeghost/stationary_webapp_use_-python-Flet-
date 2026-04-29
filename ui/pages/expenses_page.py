import flet as ft
from datetime import datetime, timedelta

from config import UserRole, currency_symbol
from database.connection import fetch_all, execute_query
from ui.pages.base_page import BasePage
from security.validation import sanitize, safe_float
from utils.audit import log_audit
from ui.components.dialogs import confirm_dialog


class ExpensesPage(BasePage):
    CATEGORIES = ["Rent", "Utilities", "Salaries", "Supplies", "Transport",
                  "Marketing", "Maintenance", "Taxes", "Other"]

    def __init__(self, app):
        super().__init__(app)
        self.exp_table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(h))
                     for h in ("Date","Category","Description","Amount","Staff","Del")],
            border=ft.Border.all(1, ft.Colors.GREY_300),
            border_radius=8,
            data_row_max_height=44,
        )
        self.exp_summary = ft.Row(spacing=10, wrap=True)
        self.exp_total_txt = ft.Text("", size=15, weight=ft.FontWeight.BOLD)

    def build(self) -> ft.Control:
        if self.role != UserRole.ADMIN:
            return ft.Column([ft.Text("Access denied", color=ft.Colors.RED_700)])

        months = []
        for i in range(12):
            d = datetime.now().replace(day=1) - timedelta(days=30*i)
            months.append((d.strftime("%Y-%m"), d.strftime("%B %Y")))
        month_dd = ft.Dropdown(
            label="Month", width=190, height=45,
            value=months[0][0],
            options=([ft.dropdown.Option("All", "All Time")] +
                     [ft.dropdown.Option(m[0], m[1]) for m in months]),
            on_change=self._load_expenses
        )

        self._load_expenses(month_dd.value)

        def add_exp(e):
            self._add_expense_dialog(month_dd)

        return ft.Column([
            ft.Text("Expenses", size=24, weight=ft.FontWeight.BOLD),
            ft.Row([
                ft.ElevatedButton("+ Add Expense", icon=ft.Icons.ADD, on_click=add_exp,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE)),
                month_dd,
                self.exp_total_txt,
            ], spacing=12, wrap=True),
            ft.Card(content=ft.Container(ft.Column([
                ft.Text("By Category", size=13, weight=ft.FontWeight.W_600),
                self.exp_summary,
            ], spacing=8), padding=10), elevation=2),
            self.scrollable_table(self.exp_table),
        ], expand=True, spacing=14, scroll=ft.ScrollMode.AUTO)

    def _load_expenses(self, month=None):
        if isinstance(month, ft.ControlEvent):
            month = month.control.value
        params = []
        query = """
            SELECT ex.id, ex.expense_date, ex.category, ex.description, ex.amount,
                   COALESCE(u.username,'—')
            FROM expenses ex
            LEFT JOIN users u ON ex.user_id = u.id
        """
        if month and month != "All":
            query += " WHERE strftime('%Y-%m', ex.expense_date) = ?"
            params.append(month)
        query += " ORDER BY ex.expense_date DESC"

        rows = fetch_all(query, tuple(params))
        sym = currency_symbol()

        self.exp_table.rows.clear()
        total = 0.0
        for eid, edate, cat, desc, amount, staff in rows:
            total += amount or 0
            self.exp_table.rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(edate or "—", size=11)),
                ft.DataCell(ft.Container(
                    ft.Text(cat, size=10, color=ft.Colors.WHITE),
                    bgcolor=ft.Colors.INDIGO_700, border_radius=6,
                    padding=ft.padding.symmetric(horizontal=5, vertical=2),
                )),
                ft.DataCell(ft.Text(desc, overflow=ft.TextOverflow.ELLIPSIS, width=160)),
                ft.DataCell(ft.Text(f"{sym}{amount:,.2f}", color=ft.Colors.RED_400,
                                    weight=ft.FontWeight.W_600)),
                ft.DataCell(ft.Text(staff, size=11)),
                ft.DataCell(ft.IconButton(ft.Icons.DELETE, icon_color=ft.Colors.RED_400,
                                          icon_size=16, data=eid,
                                          on_click=lambda e, eid=eid: self._delete_expense(eid))),
            ]))
        self.exp_total_txt.value = f"Period Total: {sym}{total:,.2f}"

        # Load category summary
        cat_query = """
            SELECT category, COALESCE(SUM(amount),0)
            FROM expenses
        """
        if month and month != "All":
            cat_query += " WHERE strftime('%Y-%m', expense_date) = ?"
            cat_rows = fetch_all(cat_query, (month,))
        else:
            cat_rows = fetch_all(cat_query)

        self.exp_summary.controls.clear()
        for cat, amt in cat_rows:
            self.exp_summary.controls.append(ft.Card(
                content=ft.Container(ft.Column([
                    ft.Text(cat, size=10, color=ft.Colors.GREY_600),
                    ft.Text(f"{sym}{amt:,.2f}", size=13, weight=ft.FontWeight.BOLD),
                ], spacing=2, tight=True), padding=8), elevation=1))
        self.page.update()

    def _add_expense_dialog(self, month_dd):
        sym = currency_symbol()
        cat_dd = ft.Dropdown(
            label="Category *", width=190,
            options=[ft.dropdown.Option(c, c) for c in self.CATEGORIES],
            value="Other"
        )
        desc_f = ft.TextField(label="Description *", expand=True)
        amt_f = ft.TextField(label="Amount *", width=140,
                              keyboard_type=ft.KeyboardType.NUMBER,
                              prefix=ft.Text(sym))
        date_f = ft.TextField(label="Date (YYYY-MM-DD)", width=170,
                               value=datetime.now().strftime("%Y-%m-%d"))
        err = ft.Text("", color=ft.Colors.RED_400)

        def save(_e):
            desc = sanitize(desc_f.value)
            if not desc:
                err.value = "Description required"; err.update(); return
            amt = safe_float(amt_f.value, lo=0.01)
            if amt <= 0:
                err.value = "Amount must be > 0"; err.update(); return
            execute_query(
                "INSERT INTO expenses (category, description, amount, expense_date, user_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (cat_dd.value, desc, amt, sanitize(date_f.value) or None, self.user_id)
            )
            log_audit(self.user_id, "ADD_EXPENSE", f"{cat_dd.value}: {sym}{amt:.2f}")
            self.close_dialog(dlg)
            self._load_expenses(month_dd.value)
            self.snack(f"Expense recorded: {sym}{amt:.2f}")

        dlg = ft.AlertDialog(
            title=ft.Text("Add Expense", size=17, weight=ft.FontWeight.BOLD),
            content=ft.Column([
                ft.Row([cat_dd, amt_f, date_f], spacing=10, wrap=True),
                desc_f, err,
            ], spacing=10, width=self.dialog_width(600), height=160, scroll=ft.ScrollMode.AUTO),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.close_dialog(dlg)),
                ft.ElevatedButton("Save", on_click=save,
                                   style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.show_dialog(dlg)

    def _delete_expense(self, eid):
        def confirm():
            execute_query("DELETE FROM expenses WHERE id=?", (eid,))
            self._load_expenses()
            self.snack("Expense deleted", ft.Colors.RED_700)

        dlg = confirm_dialog(
            self.page,
            "Delete Expense",
            "Remove this expense record?",
            confirm,
            delete_text="Delete"
        )
        self.show_dialog(dlg)