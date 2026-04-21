"""협력사 국제 배송비 (LCL해운 / 해운(자가))."""
from __future__ import annotations

from sqlalchemy import BigInteger, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class InternationalShippingRate(Base, TimestampMixin):
    __tablename__ = "international_shipping_rates"
    __table_args__ = (
        UniqueConstraint(
            "method", "max_weight_kg", name="shipping_rate_unique_method_weight"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    max_weight_kg: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False)
    general_seller_krw: Mapped[int] = mapped_column(Integer, nullable=False)
    super_seller_krw: Mapped[int] = mapped_column(Integer, nullable=False)
    partner_krw: Mapped[int] = mapped_column(Integer, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<IntlShipRate method={self.method} max={self.max_weight_kg}kg "
            f"partner={self.partner_krw}>"
        )
