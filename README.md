# Uptown Stationery Manager

A modern, responsive, full‑featured stationery shop management system built with **Flet** (Python) and **SQLite**.

![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Flet](https://img.shields.io/badge/Flet-0.84%2B-orange)
![Docker](https://img.shields.io/badge/docker-ready-brightgreen)

---

## 📌 Overview

Uptown Stationery Manager is a complete point‑of‑sale, inventory, and business analytics tool tailored for small‑to‑medium stationery stores. It provides an intuitive web interface for daily sales, inventory tracking, expense management, customer loyalty, supplier purchase orders, and more—all backed by a secure, multi‑role authentication system.

The project was crafted with **maintainability** in mind: a clean modular architecture, separation of concerns, reusable components, and full Docker support.

---

## 🚀 Key Features

### 🔐 Security & Access Control
- **PBKDF2‑HMAC‑SHA256** password hashing with automatic legacy hash upgrade  
- **Rate‑limiting** and account lockout after repeated failed logins  
- **Role‑based access**: Admin (full control) and Seller (restricted)  
- **Audit logging** for all critical actions  

### 📊 Interactive Dashboard
- **KPI Cards** – Total stock, inventory value, today’s revenue, transactions, monthly expenses  
- **Real‑time charts** (powered by `flet-charts`)  
  - Line chart – Sales trend over 7 days  
  - Bar chart – Daily revenue comparison  
  - Pie chart – Top 5 products by revenue  
- **Low‑stock alerts** with one‑click purchase order creation  
- **Recent sales** table with detailed transaction dialogs  

### 📦 Inventory Management
- Add, edit, delete items with name, category, price, cost, stock, supplier  
- **Stock level indicators** (LOW) with colour coding  
- Search by name and filter by category  
- Export inventory to **CSV**

### 💰 Point of Sale (POS)
- Quick item search and add‑to‑cart  
- Quantity adjustment and removal in cart  
- **Discount** (flat or percentage) and **tax** (percentage) calculations  
- Built‑in **promotions** – auto‑apply discounts with minimum purchase rules  
- Multi‑method payment: Cash, Card, Mobile Money, Bank Transfer  
- Customer selection (optional) – loyalty points and spending tracking  
- Inventory auto‑deduction on sale completion  

### 📈 Sales History & Reports
- Filter sales by date range, payment method, and staff  
- **P&L summary** (revenue, COGS, expenses, net profit)  
- Staff performance per month  
- Top products report  
- CSV export  

### 🛠️ Admin Modules

| Module | Purpose |
|--------|---------|
| **Stock Adjustments** | Increase/decrease/set exact stock with reason logging |
| **Expenses** | Track by category (Rent, Utilities, Salaries, etc.), view monthly totals |
| **Promotions** | Create percentage or fixed discounts with optional codes and validity dates |
| **Suppliers** | Manage contact details of suppliers |
| **Purchasing (PO)** | Create and receive purchase orders; automatic stock update upon receipt |
| **Customers** | View/edit customer info, loyalty points & total spent |
| **Users** | Add/edit/delete staff accounts with role assignment |
| **Settings** | Store name, default tax rate, currency, category list, password change, DB backup/restore |

### 🎨 User Experience
- **Responsive design** – adapts seamlessly to mobile and desktop  
- **Bottom navigation bar** for quick access to 5 main tabs  
- **Hamburger menu** (PopupMenuButton) for all navigation links  
- **Dark / Light theme** toggle – all cards, charts, and text adapt automatically  
- Consistent Flet Material Design controls  

---

## 🧱 Technology Stack

| Layer | Technology |
|-------|------------|
| **Framework** | [Flet](https://flet.dev) 0.84+ – Python → Flutter web/desktop |
| **Database** | SQLite via Python’s `sqlite3` (file‑based, zero‑configuration) |
| **Charts** | `flet-charts` package (LineChart, BarChart, PieChart) |
| **Security** | PBKDF2‑HMAC‑SHA256, `hmac.compare_digest`, rate limiting |
| **Deployment** | Docker with non‑root user, persistent volume for database |

---

## 📦 Installation

### Prerequisites
- Python 3.11 or higher
- **Optional**: Docker (if you prefer containerised deployment)

