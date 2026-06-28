from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from . import models, schemas, chat_logic, gemini_client, image_cache, inventory as inv
from .database import get_db

router = APIRouter(prefix="/api/chat", tags=["chat"])

GEO_BLOCKED_KEYWORDS = ["california", "90210", "los angeles"]
TRUCK_KEYWORDS = ["tacoma", "f-150", "silverado", "truck"]
SUV_KEYWORDS = ["passport", "cr-v", "blazer", "tahoe", "equinox", "highlander", "suv"]
SEDAN_KEYWORDS = ["camry", "accord", "civic", "malibu", "sedan"]

GREETING = (
    "Welcome to DriveFinder. Tell me the kind of car you're picturing, or just say you're browsing "
    "and we'll figure it out together."
)

GEO_BLOCKED_MESSAGE = (
    "Looks like you're tuning in from California. Due to state-specific franchise rules we can't run "
    "remote sourcing there yet \u2014 sorry about that. We'll let you know the moment that changes."
)

DEFAULT_STATE = {
    "current_body_style": "none",
    "current_make": "none",
    "current_model": "none",
    "stock_color": "none",
    "previews_generated": False,
    "clay_rendered": False,
    "final_set_generated": False,
}


@router.post("/start", response_model=schemas.ChatTurnResponse)
def start_session(payload: schemas.StartSessionRequest, db: Session = Depends(get_db)):
    location = (payload.location or "").strip().lower()

    if location and any(k in location for k in GEO_BLOCKED_KEYWORDS):
        return schemas.ChatTurnResponse(
            response_text=GEO_BLOCKED_MESSAGE,
            state={},
            is_ready_for_finance=False,
            geo_blocked=True,
        )

    session = models.ChatSession(location=location or None, state=dict(DEFAULT_STATE))
    db.add(session)
    db.commit()
    db.refresh(session)

    db.add(models.ChatMessage(session_id=session.id, role="assistant", content=GREETING))
    db.commit()

    return schemas.ChatTurnResponse(
        session_id=session.id,
        response_text=GREETING,
        state=session.state,
        is_ready_for_finance=False,
    )


@router.get("/session/{session_id}")
def get_session(session_id: str, db: Session = Depends(get_db)):
    session = db.query(models.ChatSession).filter(models.ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found.")
    return {
        "session_id": session.id,
        "state": session.state,
        "is_ready_for_finance": session.is_ready_for_finance,
        "messages": [{"role": m.role, "content": m.content} for m in session.messages],
    }


@router.post("/message", response_model=schemas.ChatTurnResponse)
def send_message(payload: schemas.SendMessageRequest, db: Session = Depends(get_db)):
    session = db.query(models.ChatSession).filter(models.ChatSession.id == payload.session_id).first()
    if not session:
        raise HTTPException(404, "Session not found.")

    state = dict(session.state or DEFAULT_STATE)
    history = [{"role": m.role, "content": m.content} for m in session.messages]

    lowered = payload.message.lower()
    if any(t in lowered for t in TRUCK_KEYWORDS):
        state["current_body_style"] = "truck"
    elif any(t in lowered for t in SUV_KEYWORDS):
        state["current_body_style"] = "suv"
    elif any(t in lowered for t in SEDAN_KEYWORDS):
        state["current_body_style"] = "sedan"

    try:
        turn = gemini_client.send_chat_turn(
            system_instruction=chat_logic.system_instruction(),
            history=history,
            new_message=payload.message,
            schema=schemas.ChatTurnSchema,
        )
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception:
        raise HTTPException(502, "Sourcing gateway was temporarily interrupted. Please try again.")

    if turn.detected_body_style != "none":
        state["current_body_style"] = turn.detected_body_style.lower()
    if turn.detected_make != "none":
        state["current_make"] = turn.detected_make
    if turn.detected_model != "none":
        state["current_model"] = turn.detected_model
    if turn.detected_stock_color != "none":
        state["stock_color"] = turn.detected_stock_color

    db.add(models.ChatMessage(session_id=session.id, role="user", content=payload.message))
    db.add(models.ChatMessage(session_id=session.id, role="assistant", content=turn.response_text))

    build_images = _maybe_generate_images(state)

    session.state = state
    session.is_ready_for_finance = turn.is_ready_for_finance
    db.add(session)
    db.commit()

    return schemas.ChatTurnResponse(
        response_text=turn.response_text,
        state=state,
        is_ready_for_finance=turn.is_ready_for_finance,
        build_images=build_images,
    )


def _maybe_generate_images(state: dict) -> list[schemas.BuildImage]:
    """Runs the same three milestones as the original prototype (clay pass,
    preview cards, final 5-shot set) but every render is resolved through the
    spec-keyed cache, so repeat make/model/color combos across different
    users cost nothing after the first generation.
    """
    images: list[schemas.BuildImage] = []
    make, model = state["current_make"], state["current_model"]
    body_style = state["current_body_style"]
    has_vehicle = make not in ("none", "", None) and model not in ("none", "", None)
    if not has_vehicle:
        return images

    if not state.get("clay_rendered"):
        url = image_cache.get_or_generate(
            image_cache.cache_key(make, model, "clay"),
            chat_logic.grey_clay_prompt(make, model, body_style),
        )
        if url:
            images.append(schemas.BuildImage(label="Base structure", url=url))
        state["clay_rendered"] = True

    if not state.get("previews_generated"):
        for match in inv.find_by_make_model(make, model)[:4]:
            url = image_cache.get_or_generate(
                image_cache.cache_key(make, model, match["color"], "preview"),
                chat_logic.preview_card_prompt(make, model, body_style, match["color"]),
            )
            if url:
                images.append(schemas.BuildImage(label=f"{match['color']} option", url=url))
        state["previews_generated"] = True

    color = state.get("stock_color", "none")
    if color not in ("none", "", None) and not state.get("final_set_generated"):
        angle_labels = {"front_3q": "Front 3/4", "side": "Side profile", "rear_3q": "Rear 3/4"}
        for angle, label in angle_labels.items():
            url = image_cache.get_or_generate(
                image_cache.cache_key(make, model, color, angle),
                chat_logic.exterior_angle_prompt(make, model, body_style, color, angle),
            )
            if url:
                images.append(schemas.BuildImage(label=label, url=url))

        cockpit_url = image_cache.get_or_generate(
            image_cache.cache_key(make, model, "cockpit"),
            chat_logic.interior_cockpit_prompt(make, model),
        )
        if cockpit_url:
            images.append(schemas.BuildImage(label="Cockpit", url=cockpit_url))

        seating_url = image_cache.get_or_generate(
            image_cache.cache_key(make, model, body_style, "seating"),
            chat_logic.interior_seating_prompt(make, model, body_style),
        )
        if seating_url:
            images.append(schemas.BuildImage(label="Seating", url=seating_url))

        state["final_set_generated"] = True

    return images
