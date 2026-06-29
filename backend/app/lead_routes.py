from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from . import models, schemas, inventory as inv
from .database import get_db
from .deps import require_user

router = APIRouter(prefix="/api/leads", tags=["leads"])


@router.post("", response_model=schemas.LeadOut)
def create_lead(
    payload: schemas.CreateLeadRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_user),
):
    session = db.query(models.ChatSession).filter(models.ChatSession.id == payload.session_id).first()
    if not session:
        raise HTTPException(404, "Session not found.")

    state = session.state or {}
    make = state.get("current_make", "none")
    model_name = state.get("current_model", "none")
    color = state.get("stock_color", "none")

    car = inv.best_match_for_lead(make, model_name, color)

    logistics_intent = "Home Delivery Request" if payload.is_home_delivery else "Dealership VIP Pickup Request"

    # NOTE: credit_tier below is a placeholder for the Bumper soft-pull, same
    # as the original prototype. Wire this to the real Bumper API before any
    # of this touches a real applicant's credit profile.
    credit_tier = "Unverified / Awaiting Outside Bank Verification"
    if payload.funding_strategy == "dealer_financing":
        credit_tier = "Verified Tier 1 (720+ Top Tier Credit Profile) \u2014 placeholder, not a real bureau pull"

    lead = models.Lead(
        session_id=session.id,
        user_id=user.id,
        vin=car.get("vin"),
        vehicle_specs=f"{car.get('year')} {car.get('make')} {car.get('model')}",
        dealer_id=car.get("dealer_id"),
        dealer_name=car.get("dealer_name"),
        funding_strategy=payload.funding_strategy,
        credit_tier=credit_tier,
        logistics_intent=logistics_intent,
        dealer_cross_sell_allowed=payload.dealer_cross_sell_allowed,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


@router.get("/mine", response_model=list[schemas.LeadOut])
def my_leads(db: Session = Depends(get_db), user: models.User = Depends(require_user)):
    return db.query(models.Lead).filter(models.Lead.user_id == user.id).order_by(models.Lead.created_at.desc()).all()
