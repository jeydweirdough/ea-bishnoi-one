"""
Phase 2.3a (Equipment inventory), 2.7 (Contracts & banking), 2.8 (Import/export jobs)
and 2.9 (Generated documents).

Banking: card and account references are kept to the last four characters. CVV, PINs,
online-banking passwords and full card numbers are never stored.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .models import Company, Employee, utcnow
from .models_ops import Money

# ------------------------------------------------------------------ inventory

INV_CATEGORIES = ["Equipment", "Supplies", "Spare Parts", "Consumables", "Promotional Materials"]


class InventoryItem(Base):
    """One stock line per item code and storage location."""

    __tablename__ = "inventory_items"
    __table_args__ = (UniqueConstraint("company_id", "item_code", "location"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    # Main photo (an attachment with purpose "photo"), so lists show it without another query.
    photo_id: Mapped[int | None] = mapped_column(Integer)
    item_code: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(40))
    brand: Mapped[str | None] = mapped_column(String(120))
    model: Mapped[str | None] = mapped_column(String(120))
    unit: Mapped[str] = mapped_column(String(40), default="pc")
    location: Mapped[str] = mapped_column(String(120))
    on_hand: Mapped[int] = mapped_column(Integer, default=0)
    reserved: Mapped[int] = mapped_column(Integer, default=0)
    reorder_level: Mapped[int] = mapped_column(Integer, default=0)
    reorder_quantity: Mapped[int] = mapped_column(Integer, default=0)
    unit_cost_php: Mapped[Decimal | None] = mapped_column(Money)
    supplier: Mapped[str | None] = mapped_column(String(200))
    serialized_on_issue: Mapped[bool] = mapped_column(Boolean, default=False)
    last_counted_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | discontinued
    remarks: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)

    company: Mapped[Company] = relationship(lazy="joined")

    @property
    def available(self) -> int:
        return self.on_hand - self.reserved


class StockMovement(Base):
    __tablename__ = "stock_movements"
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    kind: Mapped[str] = mapped_column(String(16))  # stock_in | issue | use | transfer_out | transfer_in | return | adjustment | write_off | reserve | release
    quantity: Mapped[int] = mapped_column(Integer)  # signed change to on_hand (reserve/release change reserved)
    balance_after: Mapped[int] = mapped_column(Integer)
    request_id: Mapped[int | None] = mapped_column(ForeignKey("requests.id"))
    receipt_id: Mapped[int | None] = mapped_column(ForeignKey("receipts.id"))
    issued_to_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    counterpart_item_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_items.id"))
    reason: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    actor: Mapped[Employee] = relationship(foreign_keys=[actor_id], lazy="joined")
    issued_to: Mapped[Employee | None] = relationship(foreign_keys=[issued_to_id], lazy="joined")


class StockReservation(Base):
    __tablename__ = "stock_reservations"
    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), index=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), index=True)
    request_item_id: Mapped[int] = mapped_column(ForeignKey("request_items.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12), default="reserved")  # reserved | issued | released
    created_by_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InventoryCount(Base):
    __tablename__ = "inventory_counts"
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    location: Mapped[str | None] = mapped_column(String(120))  # None = all locations
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | submitted | posted | cancelled
    # [{item_id, item_code, name, location, unit, expected, counted, unit_cost}]
    lines: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    started_by_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_by_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    started_by: Mapped[Employee] = relationship(foreign_keys=[started_by_id], lazy="joined")
    posted_by: Mapped[Employee | None] = relationship(foreign_keys=[posted_by_id], lazy="joined")


# ------------------------------------------------------------------ contracts


class Lessor(Base):
    __tablename__ = "lessors"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    name: Mapped[str] = mapped_column(String(200))
    contact_person: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(String(400))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    company: Mapped[Company] = relationship(lazy="joined")


CONTRACT_TYPES = ["office_lease", "staff_house", "other"]
CONTRACT_STATUSES = ["active", "for_renewal", "expired", "renewed", "terminated"]


class Contract(Base):
    __tablename__ = "contracts"
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    contract_type: Mapped[str] = mapped_column(String(20), index=True)
    title: Mapped[str] = mapped_column(String(300))
    property_name: Mapped[str | None] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(300))
    lessor_id: Mapped[int | None] = mapped_column(ForeignKey("lessors.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    monthly_rent_php: Mapped[Decimal | None] = mapped_column(Money)
    deposit_php: Mapped[Decimal | None] = mapped_column(Money)
    rent_due_day: Mapped[int | None] = mapped_column(Integer)
    renewal_notice_days: Mapped[int] = mapped_column(Integer, default=60)
    occupants: Mapped[str | None] = mapped_column(Text)  # staff houses
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    # Pointer to the authoritative copy in Bishnoi One Contracts, when it exists there.
    external_reference: Mapped[str | None] = mapped_column(String(120))
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    renewed_from_id: Mapped[int | None] = mapped_column(ForeignKey("contracts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)

    company: Mapped[Company] = relationship(lazy="joined")
    lessor: Mapped[Lessor | None] = relationship(lazy="joined")
    responsible: Mapped[Employee | None] = relationship(lazy="joined")


class RentPayment(Base):
    """Monthly rental monitoring: the rent hand-off to Finance and Finance's reference."""

    __tablename__ = "rent_payments"
    __table_args__ = (UniqueConstraint("contract_id", "period"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    period: Mapped[str] = mapped_column(String(7))
    amount_php: Mapped[Decimal] = mapped_column(Money)
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="due")  # due | sent | paid | cancelled
    finance_reference: Mapped[str | None] = mapped_column(String(120))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))


class ContractEvent(Base):
    __tablename__ = "contract_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(30))
    message: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    actor: Mapped[Employee | None] = relationship(lazy="joined")


# ------------------------------------------------------------------ banking


class CorporateCard(Base):
    __tablename__ = "corporate_cards"
    __table_args__ = (UniqueConstraint("bank", "card_last4", "custodian_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    bank: Mapped[str] = mapped_column(String(120))
    card_type: Mapped[str] = mapped_column(String(40))  # credit | debit | prepaid
    card_last4: Mapped[str] = mapped_column(String(4))
    custodian_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    expiry_month: Mapped[int] = mapped_column(Integer)
    expiry_year: Mapped[int] = mapped_column(Integer)
    credit_limit_php: Mapped[Decimal | None] = mapped_column(Money)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | blocked | cancelled | for_renewal | expired
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    company: Mapped[Company] = relationship(lazy="joined")
    custodian: Mapped[Employee] = relationship(lazy="joined")


BANK_CASE_TYPES = ["card_request", "card_renewal", "account_application", "documentation", "bank_renewal", "finance_coordination"]


class BankingCase(Base):
    __tablename__ = "banking_cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    bank: Mapped[str] = mapped_column(String(120))
    case_type: Mapped[str] = mapped_column(String(30), index=True)
    subject: Mapped[str] = mapped_column(String(300))
    account_last4: Mapped[str | None] = mapped_column(String(4))
    card_id: Mapped[int | None] = mapped_column(ForeignKey("corporate_cards.id"))
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    application_date: Mapped[date | None] = mapped_column(Date)
    renewal_date: Mapped[date | None] = mapped_column(Date)
    # [{"name": str, "done": bool}]
    requirements: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)  # open | submitted | approved | completed | rejected | cancelled
    finance_status: Mapped[str] = mapped_column(String(16), default="not_needed")  # not_needed | pending | sent | confirmed | rejected
    finance_reference: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    company: Mapped[Company] = relationship(lazy="joined")
    responsible: Mapped[Employee | None] = relationship(foreign_keys=[responsible_id], lazy="joined")
    card: Mapped[CorporateCard | None] = relationship(lazy="joined")


# ------------------------------------------------------------------ import / export


class ImportJob(Base):
    __tablename__ = "import_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True)
    dataset: Mapped[str] = mapped_column(String(40))
    mode: Mapped[str] = mapped_column(String(16))  # create | update | upsert
    filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(80))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    sheet: Mapped[str | None] = mapped_column(String(120))
    sheets: Mapped[list] = mapped_column(JSON, default=list)
    headers: Mapped[list] = mapped_column(JSON, default=list)
    mapping: Mapped[dict] = mapped_column(JSON, default=dict)  # column header -> field name
    status: Mapped[str] = mapped_column(String(16), default="uploaded")  # uploaded | validated | committed | failed | cancelled
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    issues: Mapped[list] = mapped_column(JSON, default=list)  # [{sheet,row,column,value,error,expected,suggestion,severity}]
    results: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_by: Mapped[Employee] = relationship(lazy="joined")


# ------------------------------------------------------------------ documents

DOC_STATES = ["draft", "for_review", "for_approval", "approved", "rejected", "issued", "signed", "superseded", "voided"]


class GeneratedDocument(Base):
    __tablename__ = "generated_documents"
    __table_args__ = (UniqueConstraint("control_number", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    control_number: Mapped[str] = mapped_column(String(40), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    template_key: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(200))
    related_type: Mapped[str] = mapped_column(String(40))
    related_id: Mapped[int] = mapped_column(Integer)
    related_ref: Mapped[str | None] = mapped_column(String(60))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    signature_status: Mapped[str] = mapped_column(String(16), default="unsigned")  # unsigned | signed
    paper: Mapped[str] = mapped_column(String(8), default="A4")
    storage_key: Mapped[str] = mapped_column(String(80))
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    signed_copy_id: Mapped[int | None] = mapped_column(ForeignKey("attachments.id"))
    void_reason: Mapped[str | None] = mapped_column(Text)
    generated_by_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    generated_by: Mapped[Employee] = relationship(lazy="joined")


class DocumentEvent(Base):
    __tablename__ = "document_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("generated_documents.id"), index=True)
    type: Mapped[str] = mapped_column(String(20))  # generated | downloaded | issued | signed | superseded | voided
    note: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    actor: Mapped[Employee] = relationship(lazy="joined")
