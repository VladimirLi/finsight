"""Database models — multi-company, multi-period history.

Company 1---* FinancialPeriod 1---* Document
                     |
                     *--- stores canonical line items as JSON (FinancialStatement)

Computed ratios are NOT persisted as source-of-truth; they are derived on read by
the deterministic engine so a formula fix instantly applies to all history. We do
cache the latest computed snapshot for fast listing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Company(Base):
    """A company that financial statements belong to."""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    ticker: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    periods: Mapped[list[FinancialPeriod]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )


class FinancialPeriod(Base):
    """A reporting period (e.g. FY2023) holding a canonical statement."""

    __tablename__ = "financial_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    period_type: Mapped[str | None] = mapped_column(String(8), nullable=True)  # FY/Q/...
    fiscal_year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    fiscal_period_end: Mapped[str | None] = mapped_column(String(16), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)

    # Serialized FinancialStatement (canonical items + provenance).
    statement_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    company: Mapped[Company] = relationship(back_populates="periods")
    documents: Mapped[list[Document]] = relationship(
        back_populates="period", cascade="all, delete-orphan"
    )


class Document(Base):
    """An uploaded source document and its pipeline status."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    period_id: Mapped[int | None] = mapped_column(
        ForeignKey("financial_periods.id"), nullable=True, index=True
    )
    filename: Mapped[str] = mapped_column(String(512))
    stored_path: Mapped[str] = mapped_column(String(1024))
    num_pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # pipeline status: uploaded | parsing | extracting | needs_review | ready | failed
    status: Mapped[str] = mapped_column(String(32), default="uploaded", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_statement_types: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    period: Mapped[FinancialPeriod | None] = relationship(back_populates="documents")
