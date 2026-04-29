import flet as ft

def main(page: ft.Page):
    page.title = "Quick Test"

    def do_login(e):
        page.clean()
        page.add(
            ft.Column([
                ft.Text("✅ Inventory is ALIVE!", size=30, weight=ft.FontWeight.BOLD),
                ft.ElevatedButton("Logout", on_click=lambda _: page.clean())
            ])
        )
        page.update()

    # Simple login UI
    page.add(
        ft.Column([
            ft.Text("Login", size=20),
            ft.ElevatedButton("Click to Login", on_click=do_login),
        ])
    )

ft.run(main)