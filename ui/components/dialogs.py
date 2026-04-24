import flet as ft


def confirm_dialog(
    page: ft.Page,
    title: str,
    content: str,
    on_confirm: callable,
    confirm_text: str = "Delete",
    confirm_color: str = ft.Colors.RED_700,
) -> ft.AlertDialog:
    """Creates a standard confirmation dialog."""

    def close_dialog(dlg: ft.AlertDialog):
        dlg.open = False
        if dlg in page.overlay:
            page.overlay.remove(dlg)
        page.update()

    dlg = ft.AlertDialog(
        title=ft.Text(title),
        content=ft.Text(content),
        actions=[
            ft.TextButton("Cancel", on_click=lambda _: close_dialog(dlg)),
            ft.ElevatedButton(
                confirm_text,
                on_click=lambda e: (on_confirm(), close_dialog(dlg)),
                style=ft.ButtonStyle(bgcolor=confirm_color, color=ft.Colors.WHITE),
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    return dlg


def show_snack(page: ft.Page, message: str, color: str = ft.Colors.GREEN_700):
    """Show a SnackBar notification."""
    page.snack_bar = ft.SnackBar(ft.Text(message), bgcolor=color)
    page.snack_bar.open = True
    page.update()


def close_dialog(page: ft.Page, dialog: ft.AlertDialog):
    """Close and remove a dialog from overlay."""
    dialog.open = False
    if dialog in page.overlay:
        page.overlay.remove(dialog)
    page.update()