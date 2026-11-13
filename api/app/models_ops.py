"""
Phase 2.3 (Assets) and 2.4 (Fleet) records.

Money is stored as Numeric(14, 2) in PHP. Card and account references are kept
masked (last four characters); full card numbers, CVV and PINs are never stored.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .models import Company, Department, Employee, utcnow

Money = Numeric(14, 2)


class AssetCondition(StrEnum):
    brand_new = "brand_new"
    used = "used"
    for_repair = "for_repair"
    damaged = "damaged"
    unserviceable = "unserviceable"


class AssetStatus(StrEnum):
    in_stock = "in_stock"
    assigned = "assigned"
    under_repair = "under_repair"
    retired = "retired"


class RepairStatus(StrEnum):
    open = "open"
    in_repair = "in_repair"
    completed = "completed"
    cancelled = "cancelled"


class VehicleStatus(StrEnum):
    active = "active"
    under_maintenance = "under_maintenance"
    inactive = "inactive"
    disposed = "disposed"


class FinanceStatus(StrEnum):
    draft = "draft"
    sent = "sent"
    paid = "paid"
    rejected = "rejected"
    cancelled = "cancelled"


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# ------------------------------------------------------------------ assets


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    # Main photo (an attachment with purpose "photo"), so lists show it without another query.
    photo_id: Mapped[int | None] = mapped_column(Integer)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    name: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(120))
    # Serialized physical assets: one record per serial, unique across the register.
    serial_number: Mapped[str | None] = mapped_column(String(120), unique=True)
    brand: Mapped[str | None] = mapped_column(String(120))
    model: Mapped[str | None] = mapped_column(String(120))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit: Mapped[str] = mapped_column(String(40), default="unit")
    condition: Mapped[str] = mapped_column(String(32), default=AssetCondition.brand_new)
    status: Mapped[str] = mapped_column(String(32), default=AssetStatus.in_stock, index=True)
    location: Mapped[str | None] = mapped_column(String(300))
    holder_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), index=True)
    issued_by_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    date_issued: Mapped[date | None] = mapped_column(Date)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purchase_date: Mapped[date | None] = mapped_column(Date)
    purchase_reference: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    purpose: Mapped[str | None] = mapped_column(Text)
    remarks: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[int | None] = mapped_column(ForeignKey("requests.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)

    company: Mapped[Company] = relationship(lazy="joined")
    department: Mapped[Department | None] = relationship(lazy="joined")
    holder: Mapped[Employee | None] = relationship(foreign_keys=[holder_id], lazy="joined")
    issued_by: Mapped[Employee | None] = relationship(foreign_keys=[issued_by_id], lazy="joined")


class AssetEvent(Base):
    __tablename__ = "asset_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(40))
    message: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    from_holder_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    to_holder_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    actor: Mapped[Employee | None] = relationship(foreign_keys=[actor_id], lazy="joined")
    from_holder: Mapped[Employee | None] = relationship(foreign_keys=[from_holder_id], lazy="joined")
    to_holder: Mapped[Employee | None] = relationship(foreign_keys=[to_holder_id], lazy="joined")


class AssetRepair(Base):
    __tablename__ = "asset_repairs"
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    request_id: Mapped[int | None] = mapped_column(ForeignKey("requests.id"))
    issue: Mapped[str] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(String(200))
    cost_php: Mapped[Decimal | None] = mapped_column(Money)
    status: Mapped[str] = mapped_column(String(16), default=RepairStatus.open, index=True)
    outcome_condition: Mapped[str | None] = mapped_column(String(32))
    notes: Mapped[str | None] = mapped_column(Text)
    opened_by_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    asset: Mapped[Asset] = relationship(lazy="joined")
    opened_by: Mapped[Employee] = relationship(lazy="joined")


class Receipt(Base):
    """Proof of receiving for a delivered request; lines say what arrived and which asset was registered."""

    __tablename__ = "receipts"
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), index=True)
    received_by_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    received_on: Mapped[date] = mapped_column(Date)
    delivery_reference: Mapped[str | None] = mapped_column(String(120))
    supplier: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    lines: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    received_by: Mapped[Employee] = relationship(lazy="joined")
    company: Mapped[Company] = relationship(lazy="joined")


# ------------------------------------------------------------------ fleet


class Vehicle(Base):
    __tablename__ = "vehicles"
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    # Main photo (an attachment with purpose "photo"), so lists show it without another query.
    photo_id: Mapped[int | None] = mapped_column(Integer)
    vehicle_type: Mapped[str] = mapped_column(String(60))
    make: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(80))
    year_model: Mapped[int | None] = mapped_column(Integer)
    color: Mapped[str | None] = mapped_column(String(40))
    plate_number: Mapped[str | None] = mapped_column(String(20), unique=True)
    conduction_sticker: Mapped[str | None] = mapped_column(String(20), unique=True)
    owner_name: Mapped[str | None] = mapped_column(String(200))
    assigned_driver_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    registration_renewal_date: Mapped[date | None] = mapped_column(Date)
    insurance_expiry_date: Mapped[date | None] = mapped_column(Date)
    insurer: Mapped[str | None] = mapped_column(String(120))
    policy_number: Mapped[str | None] = mapped_column(String(80))
    next_pms_date: Mapped[date | None] = mapped_column(Date)
    odometer_km: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default=VehicleStatus.active, index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)

    company: Mapped[Company] = relationship(lazy="joined")
    assigned_driver: Mapped[Employee | None] = relationship(lazy="joined")

    @property
    def label(self) -> str:
        return f"{self.make} {self.model}" + (f" · {self.plate_number}" if self.plate_number else f" · CS {self.conduction_sticker}" if self.conduction_sticker else "")


class VehicleService(Base):
    __tablename__ = "vehicle_services"
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # pms | repair | parts
    status: Mapped[str] = mapped_column(String(16), default="scheduled")  # scheduled | done | cancelled
    service_date: Mapped[date] = mapped_column(Date)
    provider: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    parts: Mapped[str | None] = mapped_column(Text)
    cost_php: Mapped[Decimal | None] = mapped_column(Money)
    odometer_km: Mapped[int | None] = mapped_column(Integer)
    next_service_date: Mapped[date | None] = mapped_column(Date)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    vehicle: Mapped[Vehicle] = relationship(lazy="joined")
    created_by: Mapped[Employee] = relationship(lazy="joined")


class VehicleRenewal(Base):
    __tablename__ = "vehicle_renewals"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # registration | insurance
    previous_date: Mapped[date | None] = mapped_column(Date)
    new_date: Mapped[date] = mapped_column(Date)
    reference: Mapped[str | None] = mapped_column(String(120))
    cost_php: Mapped[Decimal | None] = mapped_column(Money)
    renewed_by_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    renewed_by: Mapped[Employee] = relationship(lazy="joined")


class FleetCard(Base):
    __tablename__ = "fleet_cards"
    __table_args__ = (UniqueConstraint("provider", "card_last4", "vehicle_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"))
    provider: Mapped[str] = mapped_column(String(60), default="Shell")
    card_last4: Mapped[str] = mapped_column(String(4))
    fuel_type: Mapped[str | None] = mapped_column(String(40))
    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    configured_amount_php: Mapped[Decimal] = mapped_column(Money)
    billing_cycle: Mapped[str] = mapped_column(String(20), default="monthly")
    monitoring_status: Mapped[str] = mapped_column(String(20), default="active")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    vehicle: Mapped[Vehicle | None] = relationship(lazy="joined")
    assigned_user: Mapped[Employee | None] = relationship(lazy="joined")
    company: Mapped[Company] = relationship(lazy="joined")


class RfidAccount(Base):
    __tablename__ = "rfid_accounts"
    __table_args__ = (UniqueConstraint("provider", "account_reference"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"))
    provider: Mapped[str] = mapped_column(String(60))
    account_reference: Mapped[str] = mapped_column(String(60))
    balance_php: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    low_balance_php: Mapped[Decimal] = mapped_column(Money, default=Decimal("500"))
    monitoring_status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    vehicle: Mapped[Vehicle | None] = relationship(lazy="joined")
    company: Mapped[Company] = relationship(lazy="joined")


class FinanceRequest(Base):
    """A payment handed to Finance (fleet card billing, RFID reload). Finance stays the source of truth."""

    __tablename__ = "finance_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    kind: Mapped[str] = mapped_column(String(20))  # fleet_billing | rfid_reload | other
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"))
    fleet_card_id: Mapped[int | None] = mapped_column(ForeignKey("fleet_cards.id"))
    rfid_account_id: Mapped[int | None] = mapped_column(ForeignKey("rfid_accounts.id"))
    period: Mapped[str | None] = mapped_column(String(7))  # YYYY-MM
    amount_php: Mapped[Decimal] = mapped_column(Money)
    status: Mapped[str] = mapped_column(String(16), default=FinanceStatus.draft, index=True)
    finance_reference: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    vehicle: Mapped[Vehicle | None] = relationship(lazy="joined")
    fleet_card: Mapped[FleetCard | None] = relationship(lazy="joined")
    rfid_account: Mapped[RfidAccount | None] = relationship(lazy="joined")
    created_by: Mapped[Employee] = relationship(lazy="joined")
    company: Mapped[Company] = relationship(lazy="joined")
