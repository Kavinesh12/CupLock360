"""Rate lookup: project card > client card > standard card, among cards valid on the date."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import Project, RateCard, RateCardLine


@dataclass
class EffectiveRate:
    item_id: int
    rate_per_day: Decimal
    rate_per_month: Decimal | None
    min_days: int
    grace_days: int
    rate_card_id: int
    rate_card_name: str
    level: str  # project | client | standard


def effective_rates(db: Session, *, on: date, item_ids: list[int], client_id: int | None = None,
                    project_id: int | None = None) -> dict[int, EffectiveRate]:
    if project_id and not client_id:
        p = db.get(Project, project_id)
        client_id = p.client_id if p else None
    level_filters = [and_(RateCard.client_id.is_(None), RateCard.project_id.is_(None))]
    if client_id:
        level_filters.append(and_(RateCard.client_id == client_id, RateCard.project_id.is_(None)))
    if project_id:
        level_filters.append(RateCard.project_id == project_id)
    rows = db.execute(
        select(RateCardLine, RateCard).join(RateCard)
        .where(RateCard.is_active, RateCard.valid_from <= on,
               or_(RateCard.valid_to.is_(None), RateCard.valid_to >= on),
               RateCardLine.item_id.in_(item_ids), or_(*level_filters))
    ).all()

    def rank(card: RateCard) -> tuple[int, date, int]:
        lvl = 2 if card.project_id else 1 if card.client_id else 0
        return (lvl, card.valid_from, card.id)

    best: dict[int, tuple[RateCardLine, RateCard]] = {}
    for line, card in rows:
        cur = best.get(line.item_id)
        if cur is None or rank(card) > rank(cur[1]):
            best[line.item_id] = (line, card)
    return {
        item_id: EffectiveRate(
            item_id=item_id, rate_per_day=line.rate_per_day, rate_per_month=line.rate_per_month,
            min_days=card.min_days, grace_days=card.grace_days, rate_card_id=card.id, rate_card_name=card.name,
            level="project" if card.project_id else "client" if card.client_id else "standard",
        )
        for item_id, (line, card) in best.items()
    }
