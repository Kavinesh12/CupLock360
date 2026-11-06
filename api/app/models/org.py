from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin


class Branch(Base, TimestampMixin):
    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True)  # used in document numbering, e.g. CHN
    name: Mapped[str] = mapped_column(String(120))
    city: Mapped[str | None] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(60), default="Tamil Nadu")
    gstin: Mapped[str | None] = mapped_column(String(15))
    address: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    warehouses: Mapped[list["Warehouse"]] = relationship(back_populates="branch")


class Warehouse(Base, TimestampMixin):
    __tablename__ = "warehouses"

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    address: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    branch: Mapped[Branch] = relationship(back_populates="warehouses")
