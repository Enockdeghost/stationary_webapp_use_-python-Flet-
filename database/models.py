
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Any, ClassVar, Type, TypeVar
from enum import Enum

from config import UserRole, POStatus


T = TypeVar("T", bound="BaseModel")


class BaseModel:
    """Base class providing common methods for all models."""

    table_name: ClassVar[str] = ""
    id_column: ClassVar[str] = "id"

    def to_dict(self, exclude_none: bool = False) -> dict[str, Any]:
        """Convert instance to dictionary, optionally excluding None values."""
        data = asdict(self)
        if exclude_none:
            data = {k: v for k, v in data.items() if v is not None}
        return data

    @classmethod
    def from_row(cls: Type[T], row: Any) -> T:
        """Create instance from a database row (sqlite3.Row or tuple with matching order)."""
        if hasattr(row, "keys"):
            field_names = [f.name for f in cls.__dataclass_fields__.values()]
            kwargs = {k: row[k] for k in field_names if k in row.keys()}
        else:
            field_names = [f.name for f in cls.__dataclass_fields__.values()]
            kwargs = dict(zip(field_names, row))
        return cls(**kwargs)


@dataclass
class User(BaseModel):
    table_name: ClassVar[str] = "users"

    id: int
    username: str
    password_hash: str
    role: str
    full_name: Optional[str] = None
    created_at: Optional[datetime] = None

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    @property
    def is_seller(self) -> bool:
        return self.role == UserRole.SELLER


@dataclass
class Supplier(BaseModel):
    table_name: ClassVar[str] = "suppliers"

    id: int
    name: str
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None


@dataclass
class Item(BaseModel):
    table_name: ClassVar[str] = "items"

    id: int
    name: str
    category: Optional[str] = None
    quantity: int = 0
    price: float = 0.0
    cost_price: float = 0.0
    low_stock_threshold: int = 5
    supplier_id: Optional[int] = None
    created_at: Optional[datetime] = None

    @property
    def is_low_stock(self) -> bool:
        return self.quantity <= self.low_stock_threshold

    @property
    def margin_percent(self) -> float:
        if self.price > 0:
            return ((self.price - self.cost_price) / self.price) * 100
        return 0.0

    @property
    def suggested_reorder_qty(self) -> int:
        return max(self.low_stock_threshold * 2 - self.quantity, 1)


@dataclass
class Customer(BaseModel):
    table_name: ClassVar[str] = "customers"

    id: int
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    loyalty_points: int = 0
    total_spent: float = 0.0
    created_at: Optional[datetime] = None


@dataclass
class Sale(BaseModel):
    table_name: ClassVar[str] = "sales"

    id: int
    sale_date: Optional[datetime] = None
    customer_id: Optional[int] = None
    subtotal: float = 0.0
    discount: float = 0.0
    tax: float = 0.0
    total: float = 0.0
    payment_method: Optional[str] = None
    user_id: Optional[int] = None


@dataclass
class SaleItem(BaseModel):
    table_name: ClassVar[str] = "sale_items"

    id: int
    sale_id: int
    item_id: int
    quantity: int
    price_at_sale: float
    total: float


@dataclass
class PurchaseOrder(BaseModel):
    table_name: ClassVar[str] = "purchase_orders"

    id: int
    supplier_id: int
    order_date: Optional[datetime] = None
    expected_date: Optional[datetime] = None
    status: str = POStatus.PENDING
    total_cost: float = 0.0
    created_by: Optional[int] = None
    notes: Optional[str] = None

    @property
    def is_received(self) -> bool:
        return self.status == POStatus.RECEIVED

    @property
    def is_cancelled(self) -> bool:
        return self.status == POStatus.CANCELLED


@dataclass
class POItem(BaseModel):
    table_name: ClassVar[str] = "po_items"

    id: int
    po_id: int
    item_id: int
    quantity_ordered: int
    quantity_received: int = 0
    cost_price: float = 0.0

    @property
    def remaining(self) -> int:
        return self.quantity_ordered - self.quantity_received


@dataclass
class Expense(BaseModel):
    table_name: ClassVar[str] = "expenses"

    id: int
    category: str
    description: str
    amount: float
    expense_date: Optional[datetime] = None
    user_id: Optional[int] = None
    created_at: Optional[datetime] = None


class PromotionType(str, Enum):
    PERCENTAGE = "percentage"
    FIXED = "fixed"


@dataclass
class Promotion(BaseModel):
    table_name: ClassVar[str] = "promotions"

    id: int
    name: str
    code: Optional[str] = None
    promo_type: str = PromotionType.PERCENTAGE.value
    value: float = 0.0
    min_purchase: float = 0.0
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    active: bool = True
    created_at: Optional[datetime] = None

    def is_valid(self, order_subtotal: float = 0.0) -> bool:
        if not self.active:
            return False
        now = datetime.now().date()
        if self.start_date and now < self.start_date:
            return False
        if self.end_date and now > self.end_date:
            return False
        if order_subtotal < self.min_purchase:
            return False
        return True

    def calculate_discount(self, subtotal: float) -> float:
        if not self.is_valid(subtotal):
            return 0.0
        if self.promo_type == PromotionType.PERCENTAGE.value:
            return subtotal * (self.value / 100)
        return min(self.value, subtotal)


@dataclass
class StockAdjustment(BaseModel):
    table_name: ClassVar[str] = "stock_adjustments"

    id: int
    item_id: int
    quantity_before: int
    quantity_change: int
    quantity_after: int
    reason: Optional[str] = None
    user_id: Optional[int] = None
    timestamp: Optional[datetime] = None

    @property
    def adjustment_type(self) -> str:
        if self.quantity_change > 0:
            return "increase"
        elif self.quantity_change < 0:
            return "decrease"
        return "set"
