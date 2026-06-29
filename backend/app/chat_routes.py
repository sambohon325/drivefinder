from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from . import models, schemas, chat_logic, gemini_client, image_cache, inventory as inv, regions as regions_module
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

REGION_NOT_SUPPORTED_MESSAGE = (
    "DriveFinder is still rolling out one market at a time, and we're not in your area yet \u2014 sorry "
    "about that. We're expanding alongside our dealer network, so check back soon."
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

    # Hardcoded on purpose — this is a legal constraint, not a business
    # rollout decision, so it's never exposed as an admin toggle.
    if location and any(k in location for k in GEO_BLOCKED_KEYWORDS):
        return schemas.ChatTurnResponse(
            response_text=GEO_BLOCKED_MESSAGE,
            state={},
            is_ready_for_finance=False,
            geo_blocked=True,
        )

    # Admin-controlled rollout gate: only block if we can actually identify a
    # specific state/province AND it's been explicitly disabled — an
    # unrecognized location is let through rather than guessed at.
    if location:
        detected = regions_module.detect_region(location)
        if detected:
            country, code, _name = detected
            row = (
                db.query(models.RegionAvailability)
                .filter(models.RegionAvailability.country == country, models.RegionAvailability.code == code)
                .first()
            )
            if row and not row.is_enabled:
                return schemas.ChatTurnResponse(
                    response_text=REGION_NOT_SUPPORTED_MESSAGE,
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

    # If the options list already showed once but nothing's locked in yet,
    # and this message just narrowed things down (a color got detected),
    # re-surface a freshly filtered list so there's something to actually
    # click and confirm — otherwise a refinement like "the grey one" only
    # gets acknowledged in text, with no way to act on it.
    if (
        not vehicle_options
        and turn.detected_stock_color != "none"
        and state.get("options_generated")
        and not state.get("final_set_generated")
    ):
        vehicle_options = _build_vehicle_options(
            state["current_make"],
            state["current_model"],
            state["current_body_style"],
            color_filter=state["stock_color"],
        )

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

    # Idempotent: if this exact option was already locked in (a rapid
    # double-click, or two requests racing each other before either had
    # committed), don't re-append a duplicate chat message or report a
    # second image set — just hand back the same confirmation.
    already_locked = (
        state.get("selected_option_id") == payload.option_id and state.get("final_set_generated")
    )

    state["current_make"] = option["make"]
    state["current_model"] = option["model"]
    state["current_body_style"] = option["body_style"].lower()
    state["stock_color"] = option["color"]
    state["selected_option_id"] = payload.option_id
    state["options_generated"] = True  # the list has served its purpose; don't regenerate it

    build_images = [] if already_locked else _generate_final_set(state)

    response_text = (
        f"Locked in: {option['year']} {option['make']} {option['model']} {option['trim']} in "
        f"{option['color']}. Whenever you're ready, hit \u201cContinue to delivery & financing\u201d to wrap up."
    )
    if not already_locked:
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


def _build_vehicle_options(make: str, model: str, body_style: str, color_filter: str = None) -> list:
    """Builds the selectable card list for a make/model, optionally narrowed
    to a specific color when the conversation has gotten more specific."""
    matches = inv.find_by_make_model(make, model)
    if color_filter and color_filter not in ("none", "", None):
        filtered = [m for m in matches if m["color"].lower() == color_filter.lower()]
        if filtered:
            matches = filtered
    matches = matches[:5]

    options = []
    for match in matches:
        url = image_cache.get_or_generate(
            image_cache.cache_key(make, model, match["color"], "preview"),
            chat_logic.preview_card_prompt(make, model, body_style, match["color"]),
            meta={"make": make, "model": model, "color": match["color"], "category": "preview"},
        )
        options.append(
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
    return options


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
    make, model = state["current_make"], state["current_model"]
    has_vehicle = make not in ("none", "", None) and model not in ("none", "", None)

    # Stage 1: body style only — but only when we don't already know the
    # exact make/model in this same turn. If someone jumps straight to
    # "Toyota Camry," there's no reason to flash a generic blurred sedan
    # for a moment before the real options replace it.
    if body_style not in ("none", "", None) and not state.get("body_style_preview_rendered"):
        if has_vehicle:
            state["body_style_preview_rendered"] = True  # skip the image, but still mark the rail stage done
        else:
            url = image_cache.get_or_generate(
                image_cache.cache_key("generic", body_style),
                chat_logic.generic_body_style_prompt(body_style),
                meta={"make": None, "model": None, "color": None, "category": f"generic_{body_style}"},
            )
            if url:
                build_images.append(schemas.BuildImage(label="Getting started", url=url))
            state["body_style_preview_rendered"] = True

    if not has_vehicle:
        return build_images, vehicle_options

    # Stage 2: make + model known — straight to the real, selectable
    # inventory list. No intermediate uncolored render here anymore; once we
    # know the exact model, showing the real photographed options is more
    # useful than an uncolored stand-in of the same model.
    if not state.get("options_generated"):
        vehicle_options = _build_vehicle_options(make, model, body_style)
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
            meta={"make": make, "model": model, "color": color, "category": angle},
        )
        if url:
            build_images.append(schemas.BuildImage(label=label, url=url))

    cockpit_url = image_cache.get_or_generate(
        image_cache.cache_key(make, model, "cockpit"),
        chat_logic.interior_cockpit_prompt(make, model),
        meta={"make": make, "model": model, "color": None, "category": "cockpit"},
    )
    if cockpit_url:
        build_images.append(schemas.BuildImage(label="Cockpit", url=cockpit_url))

    seating_url = image_cache.get_or_generate(
        image_cache.cache_key(make, model, body_style, "seating"),
        chat_logic.interior_seating_prompt(make, model, body_style),
        meta={"make": make, "model": model, "color": None, "category": "seating"},
    )
    if seating_url:
        build_images.append(schemas.BuildImage(label="Seating", url=seating_url))

    state["final_set_generated"] = True
    return build_images
