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
    "selected_option_id": None,
    "body_style_preview_rendered": False,
    "options_generated": False,
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

    build_images, vehicle_options = _advance_build(state)

    # Once finance-ready, it stays that way for this session even if a later
    # LLM turn second-guesses itself — selecting a concrete option (or a
    # clear earlier confirmation) shouldn't be reversible by the model
    # looping back on its own question.
    is_ready = turn.is_ready_for_finance or session.is_ready_for_finance

    unavailable = (
        turn.requested_unavailable_vehicle
        if turn.requested_unavailable_vehicle and turn.requested_unavailable_vehicle != "none"
        else None
    )

    session.state = state
    session.is_ready_for_finance = is_ready
    db.add(session)
    db.commit()

    return schemas.ChatTurnResponse(
        response_text=turn.response_text,
        state=state,
        is_ready_for_finance=is_ready,
        build_images=build_images,
        vehicle_options=vehicle_options,
        unavailable_vehicle=unavailable,
    )


@router.post("/select-option", response_model=schemas.ChatTurnResponse)
def select_option(payload: schemas.SelectOptionRequest, db: Session = Depends(get_db)):
    """Locking in a specific card is a deterministic action, not something
    left to the LLM to infer from free text — this is what actually
    guarantees the build reaches a finalized, finance-ready state."""
    session = db.query(models.ChatSession).filter(models.ChatSession.id == payload.session_id).first()
    if not session:
        raise HTTPException(404, "Session not found.")

    option = inv.get_by_id(payload.option_id)
    if not option:
        raise HTTPException(404, "That option is no longer available.")

    state = dict(session.state or DEFAULT_STATE)
    state["current_make"] = option["make"]
    state["current_model"] = option["model"]
    state["current_body_style"] = option["body_style"].lower()
    state["stock_color"] = option["color"]
    state["selected_option_id"] = payload.option_id
    state["options_generated"] = True  # the list has served its purpose; don't regenerate it

    build_images = _generate_final_set(state)

    response_text = (
        f"Locked in: {option['year']} {option['make']} {option['model']} {option['trim']} in "
        f"{option['color']}. Whenever you're ready, hit \u201cContinue to delivery & financing\u201d to wrap up."
    )
    db.add(models.ChatMessage(session_id=session.id, role="assistant", content=response_text))

    session.state = state
    session.is_ready_for_finance = True
    db.add(session)
    db.commit()

    return schemas.ChatTurnResponse(
        response_text=response_text,
        state=state,
        is_ready_for_finance=True,
        build_images=build_images,
        vehicle_options=[],
    )


@router.post("/notify-requests", response_model=schemas.NotifyRequestOut)
def create_notify_request(payload: schemas.NotifyRequestIn, db: Session = Depends(get_db)):
    session = db.query(models.ChatSession).filter(models.ChatSession.id == payload.session_id).first()
    if not session:
        raise HTTPException(404, "Session not found.")

    record = models.NotifyRequest(
        session_id=session.id,
        email=payload.email,
        requested_vehicle=payload.requested_vehicle,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _advance_build(state: dict):
    """Runs the body-style-placeholder and options-list milestones only.
    Does NOT generate the final multi-angle set — that's _generate_final_set,
    reachable only through select_option(). Splitting these out means there's
    exactly one path that can ever trigger the final render, instead of two
    (a card click, and free-text color detection) that could independently
    fire for the same milestone and produce duplicate image sets.
    """
    build_images: list[schemas.BuildImage] = []
    vehicle_options: list[schemas.VehicleOption] = []

    body_style = state["current_body_style"]

    # Stage 1: body style only (no make/model yet) — a soft, deliberately
    # blurred placeholder so the build visibly starts the moment someone
    # says "SUV" or "truck", well before they've picked an exact model.
    if body_style not in ("none", "", None) and not state.get("body_style_preview_rendered"):
        url = image_cache.get_or_generate(
            image_cache.cache_key("generic", body_style),
            chat_logic.generic_body_style_prompt(body_style),
        )
        if url:
            build_images.append(schemas.BuildImage(label="Getting started", url=url))
        state["body_style_preview_rendered"] = True

    make, model = state["current_make"], state["current_model"]
    has_vehicle = make not in ("none", "", None) and model not in ("none", "", None)
    if not has_vehicle:
        return build_images, vehicle_options

    # Stage 2: make + model known — straight to the real, selectable
    # inventory list. No intermediate uncolored render here anymore; once we
    # know the exact model, showing the real photographed options is more
    # useful than an uncolored stand-in of the same model.
    if not state.get("options_generated"):
        matches = inv.find_by_make_model(make, model)[:5]
        for match in matches:
            url = image_cache.get_or_generate(
                image_cache.cache_key(make, model, match["color"], "preview"),
                chat_logic.preview_card_prompt(make, model, body_style, match["color"]),
            )
            vehicle_options.append(
                schemas.VehicleOption(
                    option_id=str(match["id"]),
                    year=match["year"],
                    make=match["make"],
                    model=match["model"],
                    trim=match["trim"],
                    color=match["color"],
                    price=match["price"],
                    mileage=match["mileage"],
                    condition=match["condition"],
                    image_url=url,
                )
            )
        state["options_generated"] = True

    return build_images, vehicle_options


def _generate_final_set(state: dict) -> list:
    """Stage 3: the real multi-angle render set for the exact locked-in
    spec. Only ever called from select_option() — not from the regular
    message flow — so a card click is the single deterministic trigger.
    """
    build_images: list[schemas.BuildImage] = []
    make, model = state["current_make"], state["current_model"]
    body_style = state["current_body_style"]
    color = state.get("stock_color", "none")

    if color in ("none", "", None) or state.get("final_set_generated"):
        return build_images

    angle_labels = {"front_3q": "Front 3/4", "side": "Side profile", "rear_3q": "Rear 3/4"}
    for angle, label in angle_labels.items():
        url = image_cache.get_or_generate(
            image_cache.cache_key(make, model, color, angle),
            chat_logic.exterior_angle_prompt(make, model, body_style, color, angle),
        )
        if url:
            build_images.append(schemas.BuildImage(label=label, url=url))

    cockpit_url = image_cache.get_or_generate(
        image_cache.cache_key(make, model, "cockpit"),
        chat_logic.interior_cockpit_prompt(make, model),
    )
    if cockpit_url:
        build_images.append(schemas.BuildImage(label="Cockpit", url=cockpit_url))

    seating_url = image_cache.get_or_generate(
        image_cache.cache_key(make, model, body_style, "seating"),
        chat_logic.interior_seating_prompt(make, model, body_style),
    )
    if seating_url:
        build_images.append(schemas.BuildImage(label="Seating", url=seating_url))

    state["final_set_generated"] = True
    return build_images
