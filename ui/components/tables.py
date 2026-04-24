import flet as ft


def scrollable_table(
    table: ft.DataTable,
    expand: bool = True,
    height: int = None,
) -> ft.Container:
    """Wrap a DataTable in a horizontally and vertically scrollable container."""
    inner = ft.Column(
        [ft.Row([table], scroll=ft.ScrollMode.AUTO)],
        scroll=ft.ScrollMode.AUTO,
    )
    return ft.Container(
        content=inner,
        expand=expand,
        height=height,
        border=ft.Border.all(1, ft.Colors.GREY_200),
        border_radius=10,
    )