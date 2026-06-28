from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from . import models
from .database import get_db
from .deps import require_role

router = APIRouter(prefix="/api/dealer", tags=["dealer"])

require_dealer = require_role("dealer")


@router.get("/dashboard")
def dashboard(dealer: models.User = Depends(require_dealer), db: Session = Depends(get_db)):
    """Placeholder dashboard payload for the prototype.

    In production this becomes the actual lead-routing + inventory-sync view,
    and the dealer login likely hands off to Bumper rather than living here.
    For now it just needs to look and feel like the real thing.
    """
    leads = (
        db.query(models.Lead)
        .filter(models.Lead.dealer_id != None)  # noqa: E711
        .order_by(models.Lead.created_at.desc())
        .limit(25)
        .all()
    )
    return {
        "dealer_name": dealer.dealer_name,
        "is_vicimus_client": dealer.is_vicimus_client,
        "is_trial_active": dealer.is_trial_active,
        "trial_ends_at": dealer.trial_ends_at,
        "inventory_sync_status": "Synced" if dealer.is_vicimus_client else "Not connected",
        "leads": [
            {
                "id": lead.id,
                "vehicle_specs": lead.vehicle_specs,
                "status": lead.status,
                "created_at": lead.created_at,
            }
            for lead in leads
        ],
    }
