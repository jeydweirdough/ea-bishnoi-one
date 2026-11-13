"""
Phase 2.5 (Corporate compliance) and 2.6 (Travel & immigration) records.

Passport and visa data is sensitive personal data: passport numbers are kept as
the last four characters only, and every read of a travel-document record is audited.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .models import Company, Employee, utcnow
from .models_ops import Money

# ------------------------------------------------------------------ compliance

REG_TYPES = ["Bureau of Customs", "SEC", "GIS", "Business Permit", "Pest Control", "Fire Extinguishers", "Other"]
REG_STATUSES = ["ongoing", "for_renewal", "completed", "expired", "terminated", "void"]


class GovRegistration(Base):
    __tablename__ = "gov_registrations"
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    document_name: Mapped[str] = mapped_column(String(300))
    registration_type: Mapped[str] = mapped_column(String(60), index=True)
    registration_number: Mapped[str | None] = mapped_column(String(120))
    registration_date: Mapped[date | None] = mapped_column(Date)
    validity_years: Mapped[int | None] = mapped_column(Integer)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    # The explicit filing deadline (often before expiry).
    due_date: Mapped[date | None] = mapped_column(Date)
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    status: Mapped[str] = mapped_column(String(20), default="ongoing", index=True)
    site: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)

    company: Mapped[Company] = relationship(lazy="joined")
    responsible: Mapped[Employee | None] = relationship(lazy="joined")


class RegistrationRenewal(Base):
    __tablename__ = "registration_renewals"
    id: Mapped[int] = mapped_column(primary_key=True)
    registration_id: Mapped[int] = mapped_column(ForeignKey("gov_registrations.id"), index=True)
    previous_expiry: Mapped[date | None] = mapped_column(Date)
    registration_date: Mapped[date] = mapped_column(Date)
    new_expiry: Mapped[date] = mapped_column(Date)
    new_due: Mapped[date | None] = mapped_column(Date)
    registration_number: Mapped[str | None] = mapped_column(String(120))
    cost_php: Mapped[Decimal | None] = mapped_column(Money)
    notes: Mapped[str | None] = mapped_column(Text)
    filed_by_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    filed_by: Mapped[Employee] = relationship(lazy="joined")


BOC_MILESTONES = ["draft", "lodged", "assessment", "duties_paid", "released", "delivered", "closed", "cancelled"]


class BocCase(Base):
    __tablename__ = "boc_cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    direction: Mapped[str] = mapped_column(String(10))  # import | export
    shipment_reference: Mapped[str | None] = mapped_column(String(120))
    bill_of_lading: Mapped[str | None] = mapped_column(String(120))
    entry_number: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    counterparty: Mapped[str | None] = mapped_column(String(200))  # supplier or consignee
    origin: Mapped[str | None] = mapped_column(String(120))
    destination: Mapped[str | None] = mapped_column(String(120))
    eta: Mapped[date | None] = mapped_column(Date)
    broker: Mapped[str | None] = mapped_column(String(200))
    officer_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    company: Mapped[Company] = relationship(lazy="joined")
    officer: Mapped[Employee | None] = relationship(foreign_keys=[officer_id], lazy="joined")


class BocEvent(Base):
    __tablename__ = "boc_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("boc_cases.id", ondelete="CASCADE"), index=True)
    milestone: Mapped[str | None] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    actor: Mapped[Employee] = relationship(lazy="joined")


# ------------------------------------------------------------------ travel

FLIGHT_STATUSES = ["requested", "booked", "ticketed", "completed", "cancelled"]


class FlightBooking(Base):
    __tablename__ = "flight_bookings"
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    passenger_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    travel_type: Mapped[str] = mapped_column(String(16))  # domestic | international
    origin: Mapped[str] = mapped_column(String(120))
    destination: Mapped[str] = mapped_column(String(120))
    destination_country: Mapped[str | None] = mapped_column(String(80))
    departure_date: Mapped[date] = mapped_column(Date)
    return_date: Mapped[date | None] = mapped_column(Date)
    airline: Mapped[str | None] = mapped_column(String(120))
    booking_reference: Mapped[str | None] = mapped_column(String(40))  # airline PNR
    status: Mapped[str] = mapped_column(String(16), default="requested", index=True)
    purpose: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    # requirement_id -> {"done": bool, "by": employee_id, "at": iso}
    checklist: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    company: Mapped[Company] = relationship(lazy="joined")
    passenger: Mapped[Employee] = relationship(foreign_keys=[passenger_id], lazy="joined")


class HotelReservation(Base):
    __tablename__ = "hotel_reservations"
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    guest_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    flight_id: Mapped[int | None] = mapped_column(ForeignKey("flight_bookings.id"))
    hotel: Mapped[str] = mapped_column(String(200))
    destination: Mapped[str] = mapped_column(String(120))
    check_in: Mapped[date] = mapped_column(Date)
    check_out: Mapped[date] = mapped_column(Date)
    booking_reference: Mapped[str | None] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(16), default="requested", index=True)  # requested|booked|completed|cancelled
    cost_reference: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    company: Mapped[Company] = relationship(lazy="joined")
    guest: Mapped[Employee] = relationship(foreign_keys=[guest_id], lazy="joined")


class TravelRequirement(Base):
    """Configurable checklist items per travel type and (optionally) destination country."""

    __tablename__ = "travel_requirements"
    id: Mapped[int] = mapped_column(primary_key=True)
    travel_type: Mapped[str] = mapped_column(String(16))  # domestic | international
    country: Mapped[str | None] = mapped_column(String(80))  # None = every destination of this type
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)


class TravelDocument(Base):
    """Passports and visas (employee and expat). Sensitive: masked numbers, audited reads."""

    __tablename__ = "travel_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    doc_type: Mapped[str] = mapped_column(String(16))  # passport | visa
    holder_kind: Mapped[str] = mapped_column(String(16), default="employee")  # employee | expat
    visa_type: Mapped[str | None] = mapped_column(String(80))
    country: Mapped[str] = mapped_column(String(80))
    number_last4: Mapped[str | None] = mapped_column(String(4))
    application_date: Mapped[date | None] = mapped_column(Date)
    issue_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    renewal_date: Mapped[date | None] = mapped_column(Date)  # when renewal should start
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # applied|active|for_renewal|expired|cancelled
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)

    company: Mapped[Company] = relationship(lazy="joined")
    employee: Mapped[Employee] = relationship(foreign_keys=[employee_id], lazy="joined")
    responsible: Mapped[Employee | None] = relationship(foreign_keys=[responsible_id], lazy="joined")
