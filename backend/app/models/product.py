"""User-supplied 1688 product (사용자 입력 상품)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from .feedback import Feedback
    from .keyword import Keyword
    from .product_score import ProductScore


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    keyword_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("keywords.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cny_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    moq: Mapped[int] = mapped_column(Integer, nullable=False)
    china_domestic_shipping_krw: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    intl_shipping_krw: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 관세율 (decimal: 0.08 = 8%). NULL이면 scorer 기본(8%) 사용.
    # 한-중 FTA 대상이면 0.00, 부분 적용이면 0.02~0.05 식으로 override.
    customs_duty_pct: Mapped[float | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )
    # 수동 판매가 override. NULL이면 keyword_metrics.shopping_avg_price_krw,
    # 그것도 없으면 unit_cost × 3 휴리스틱.
    expected_sell_price_krw: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    # 광고비율 override (decimal). NULL이면 채널별 기본(SS 10%, 쿠팡 15%).
    # 0.0 = 유기적 판매 (광고 미집행).
    ad_cost_pct: Mapped[float | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )
    # 개당 무게 (kg). 국제배송비 자동 조회에 사용.
    unit_weight_kg: Mapped[float | None] = mapped_column(
        Numeric(6, 3), nullable=True
    )
    # 운송 방식: 'lcl' / 'sea_self' / NULL (자동: ≤40kg LCL, 그 이상 자가)
    shipping_method: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user: Mapped[str | None] = mapped_column(String(255), nullable=True)

    keyword: Mapped["Keyword | None"] = relationship(
        "Keyword", back_populates="products"
    )
    scores: Mapped[list["ProductScore"]] = relationship(
        "ProductScore",
        back_populates="product",
        cascade="all, delete-orphan",
    )
    feedbacks: Mapped[list["Feedback"]] = relationship(
        "Feedback",
        back_populates="product",
        cascade="all, delete-orphan",
    )
