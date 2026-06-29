import json

from . import inventory as inv

STUDIO_PRESET = (
    "A clean professional studio product photograph captured from a uniform 15-foot fixed camera distance, "
    "centered frame placement, vehicle parked flat on a boundless seamless uniform light-grey infinity cove floor. "
    "Absolutely no visible wall joints, no visible ceiling lights, no reflective overhead rings, no ceiling "
    "fixtures, completely boundless flat background sky, smooth diffuse illumination, crisp subtle shadow casting "
    "beneath the tires. All window trim moldings, body-side moldings, and hardware accents are finished "
    "exclusively in matching blacked-out trim, absolutely zero chrome trim accents and zero chrome wheels allowed. "
    "Every image generated must strictly use a uniform set of matte-black 10-spoke split-rim wheels to maintain "
    "perfect showroom consistency across all views."
)

WINDOW_LOCK_RULE = (
    "All side windows and windshield glass are completely opaque and heavily dark tinted, windows show clean "
    "solid diffuse uniform light-grey studio backdrop lighting in the glass surfaces. All side mirrors, wing "
    "mirrors, and rearview mirrors are entirely flat, solid, non-reflective matte dark gray surfaces showing "
    "strictly zero reflections. The front grille is a completely clean, blank, uniform mesh structure with "
    "absolutely zero brand emblems, zero manufacturer badges, and zero text plates (strictly no competitor "
    "branding permitted)."
)


def system_instruction() -> str:
    inventory_data = json.dumps(inv.load_inventory())
    return (
        "You are a helpful, casual automotive retail assistant guiding a buyer to select an exact model "
        f"from this inventory:\n{inventory_data}\n\n"
        "CONVERSATIONAL RULES:\n"
        "- Speak like a normal human peer. No marketing buzzwords, no cheesy pitches.\n"
        "- Help take the pain out of car buying by being transparent.\n"
        "- If the user says they are 'just looking' or 'browsing', do NOT repeat introductory lines. "
        "Acknowledge it naturally and help them explore.\n"
        "- Ask contextual questions about powertrain (Gas, Hybrid, EV) or feature layout (Sunroof, Moonroof) "
        "naturally if they are hunting for a specific tier.\n"
        "- If the user requests a make/model we don't have, tell them plainly that we don't carry it, set "
        "'requested_unavailable_vehicle' to exactly what they asked for (e.g. 'Honda Civic'), and immediately "
        "suggest one or two specific in-stock alternatives by name that are reasonably close (similar body "
        "style or price range) rather than just listing everything we have. Do NOT set 'detected_model' to "
        "the unavailable name until they accept an available option.\n"
        "- If the user explicitly states 'new' or 'used', set 'already_asked_condition' to true.\n"
        "- If they select a vehicle that lists a color, capture it in 'detected_stock_color'.\n"
        "- Once a clear Make and Model are determined, summarize cleanly and set 'is_ready_for_finance' to true.\n"
        "- IMPORTANT: once you have already said something like 'ready to talk financing' earlier in this "
        "conversation (check the message history before asking), do NOT ask that same question again. The "
        "person has a 'Continue to delivery & financing' button on screen for that — your job from that point "
        "on is just to answer any other questions about the vehicle, not to re-ask if they're ready. If they "
        "say something like 'yes' or 'ready' after you've already covered this, acknowledge it briefly and "
        "point them to that button rather than repeating the question."
    )


_GENERIC_BODY_DESC = {
    "sedan": "a generic modern mid-size four-door sedan silhouette",
    "suv": "a generic modern mid-size SUV crossover silhouette",
    "truck": "a generic modern crew-cab pickup truck silhouette",
}


def generic_body_style_prompt(body_style: str) -> str:
    """The very first thing shown, the instant a body style is mentioned —
    before any specific make or model is chosen. Deliberately soft/blurred
    so it reads as 'we're getting started,' not as a finished render."""
    desc = _GENERIC_BODY_DESC.get(body_style, _GENERIC_BODY_DESC["sedan"])
    return (
        f"A soft, gently out-of-focus studio product photograph of {desc}, entirely unbranded with no visible "
        f"badges, manufacturer marks, or model-specific details, finished in a uniform neutral light-grey "
        f"color. Apply a soft dreamy blur across the entire image, like an indistinct placeholder silhouette "
        f"rather than a sharp product shot — intentionally vague since no exact model has been chosen yet. A "
        f"uniform 3/4 front perspective view angle. {STUDIO_PRESET}"
    )


LUXURY_MAKES = {"bmw", "maserati"}


def _market_tier(make: str) -> str:
    """Only BMW and Maserati are actual luxury marques in this inventory.
    Calling a Camry or Civic 'luxury' in every prompt was nudging the image
    model toward unrelated luxury-brand proportions (Bentley, BMW) instead of
    the mainstream sedan it was actually supposed to be."""
    return "luxury" if make.lower() in LUXURY_MAKES else "modern, well-equipped"


def _identity_lock(make: str, model: str) -> str:
    """Explicit anchor so the render actually looks like the selected
    make/model rather than 'a generic car'. Without this, especially for
    sedans, the model had nothing to hold onto and would substitute whatever
    silhouette it associated with the surrounding studio/luxury language."""
    return (
        f"This must be immediately recognizable as a current-generation {make} {model} by its real body "
        f"proportions, greenhouse shape, hood length, and overall silhouette — not a different make or model, "
        f"and not a generic stand-in shape. Do not substitute the design language of an unrelated manufacturer "
        f"(no Bentley, Rolls-Royce, Mercedes-Benz, or other unrelated marque proportions). The only thing "
        f"altered from the real {make} {model} is branding: badges, grille emblems, and model-name text are "
        f"removed, but the body itself stays true to the actual vehicle."
    )


def body_desc(make: str, model: str, body_style: str) -> str:
    tier = _market_tier(make)
    lock = _identity_lock(make, model)
    if body_style == "truck":
        return (
            f"a {tier} crew-cab pickup truck matching the real cab and cargo-bed proportions of a {make} "
            f"{model}. {lock}"
        )
    if body_style == "suv":
        return (
            f"a {tier} {make} {model} SUV crossover, matching its real chassis height, greenhouse, and body "
            f"profile. {lock}"
        )
    return f"a {tier} {make} {model} sedan, matching its real wheelbase and body proportions. {lock}"


def color_modifier(color: str) -> str:
    if color.lower() == "grey":
        return "non-reflective dark charcoal gunmetal grey metallic panel finish with deep low-key diffuse shadows"
    return f"flawless glossy deep metallic {color} paint coat finish"


def preview_card_prompt(make: str, model: str, body_style: str, color: str) -> str:
    desc = body_desc(make, model, body_style)
    return (
        f"An immaculate photorealistic studio product photograph of {desc} {color_modifier(color)}, "
        f"glistening clear coat layer. All wheels, multi-spoke rims, and trim details fully rendered. Completely "
        f"emblem-free. {WINDOW_LOCK_RULE} A uniform 3/4 front passenger-side perspective view angle. "
        f"{STUDIO_PRESET}"
    )


_ANGLE_TEXT = {
    "front_3q": "A uniform 3/4 front passenger-side perspective view angle.",
    "side": "Direct flat horizontal side profile view angle.",
    "rear_3q": "A uniform 3/4 rear driver-side angle view perspective.",
}


def exterior_angle_prompt(make: str, model: str, body_style: str, color: str, angle: str) -> str:
    desc = body_desc(make, model, body_style)
    return (
        f"An immaculate photorealistic studio product photograph of {desc} {color_modifier(color)}, "
        f"glistening clear coat layer. All wheels and trim details fully rendered. Completely emblem-free. "
        f"{_ANGLE_TEXT[angle]} {WINDOW_LOCK_RULE} {STUDIO_PRESET}"
    )


def interior_cockpit_prompt(make: str, model: str) -> str:
    tier = _market_tier(make)
    return (
        f"A premium studio first-person cockpit view looking directly forward from the driver's seat eye-line "
        f"perspective inside a {tier} {make} {model}, matching its real dashboard layout, steering wheel "
        f"design, and instrument cluster style. There is exactly one steering wheel in this image, positioned "
        f"directly in front of the driver's seat on one side of the dashboard only. Do not render a second "
        f"steering wheel, a duplicate or mirrored wheel, any wheel-like shape on the passenger side, or any "
        f"second steering control of any kind anywhere in the frame. A prominent fully detailed black "
        f"leather-wrapped modern steering wheel is positioned directly in front of the center field of view. "
        f"Directly behind that single steering wheel, a fully active digital instrumentation gauge cluster and "
        f"binnacle display is completely visible showing illuminated driver metrics. Soft stitched dashboard "
        f"inserts flank the active multimedia screen array. The sunroof opening reveals a solid uniform soft "
        f"diffuse studio illumination light box sky ceiling, strictly zero blue sky or clouds permitted. The "
        f"view looking through the front windshield and all side window panes reveals nothing but a solid, "
        f"completely uniform, boundless flat light-grey studio infinity cove backdrop with strictly zero "
        f"external vehicles, zero structures, and zero background shapes permitted. Both wing mirrors visible "
        f"through the windows are modified to be completely solid, blank, opaque matte black plastic textures "
        f"containing zero reflections."
    )


THREE_ROW_MODELS = {"tahoe", "explorer", "pilot", "highlander"}


def interior_seating_prompt(make: str, model: str, body_style: str) -> str:
    tier = _market_tier(make)
    orientation_lock = (
        "Every seat in the cabin — front and rear — faces the same direction: forward, toward the "
        "windshield, exactly like a real car. All seats point the same way, toward the front of the vehicle. "
        "No seat is rotated, reversed, flipped, spun around, or facing sideways, backward, or toward another "
        "seat. None of the seats face each other or face the rear of the vehicle. Every headrest points "
        "toward the front windshield. Picture sitting in the driver's seat and looking back over your "
        "shoulder: every seat behind you faces the exact same forward direction you are facing."
    )
    window_lock = (
        "Every window in the cabin, without exception — including the rear side windows, the rear hatch or "
        "tailgate glass, and the sunroof glass — is uniformly dark-tinted. There is no clear, bright, "
        "reflective-white, or untinted glass anywhere in the frame; every pane of glass reads as the same "
        "heavily smoked dark tone, with zero exceptions."
    )

    if body_style == "suv" and model.lower() in THREE_ROW_MODELS:
        return (
            f"A high-fidelity studio detailed photograph taken inside the middle seat passenger cabin area of a "
            f"{tier} {make} {model} three-row SUV, matching its real cabin width and seating layout. "
            f"{orientation_lock} The middle passenger row features an immaculate, standalone set of leather "
            f"captain's chairs with crisp diamond-quilted stitching. A clear, wide, completely empty dark "
            f"carpeted center aisle pathway separates the chairs, and the third-row seating architecture is "
            f"safely constrained far in the background distance. The detailed backs of the front driver and "
            f"passenger bucket seats are clearly visible, normally positioned, and occupy the lower left and "
            f"right foreground corners of the frame layout. The painted steel interior metal trim framework "
            f"surrounding the seats is finished in a solid liquid metallic theme, strictly zero blue panels, "
            f"zero red door accents. {window_lock}"
        )

    cabin_note = (
        "a standard two-row cabin with a single rear bench seat — not a three-row layout, no captain's "
        "chairs, no third row of any kind"
        if body_style == "suv"
        else "a standard sedan cabin with a single rear bench seat"
    )
    return (
        f"A high-fidelity studio detailed photograph taken inside the rear seat passenger row cabin area of a "
        f"{tier} {make} {model}, matching its real cabin width and seating layout — {cabin_note}. "
        f"{orientation_lock} Immaculate uniform leather backseat upholstery textures with quilted "
        f"diamond-stitching details. The rear bench is a single continuous forward-facing unit; it never splits "
        f"into individually rotated sections. The detailed backs of the front driver and passenger bucket "
        f"seats are clearly visible, normally positioned, and occupy the lower left and right foreground "
        f"corners of the frame layout. The floor area between the seating rows is an empty, realistic wide "
        f"spacious dark carpeted floor area. The painted steel interior metal trim framework surrounding the "
        f"seats is finished in a solid liquid metallic theme, strictly zero blue panels, zero red door accents. "
        f"{window_lock}"
    )
