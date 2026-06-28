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
        "- If the user requests a model we don't have, tell them it is unavailable and offer options from our "
        "inventory. Do NOT set 'detected_model' to the unavailable name until they accept an available option.\n"
        "- If the user explicitly states 'new' or 'used', set 'already_asked_condition' to true.\n"
        "- If they select a vehicle that lists a color, capture it in 'detected_stock_color'.\n"
        "- Once a clear Make and Model are determined, summarize cleanly and set 'is_ready_for_finance' to true."
    )


def body_desc(make: str, model: str, body_style: str) -> str:
    if body_style == "truck":
        return (
            f"generic unbranded crew-cab pickup truck with a standard rear cargo bed box matching a modern "
            f"mid-size {make} {model} truck footprint"
        )
    if body_style == "suv":
        return f"generic unbranded mid-size luxury {make} {model} SUV crossover chassis body profile"
    return (
        "generic unbranded mid-size sedan chassis geometry capturing the signature elongated wheelbase "
        "proportions"
    )


def color_modifier(color: str) -> str:
    if color.lower() == "grey":
        return "non-reflective dark charcoal gunmetal grey metallic panel finish with deep low-key diffuse shadows"
    return f"flawless glossy deep metallic {color} paint coat finish"


def grey_clay_prompt(make: str, model: str, body_style: str) -> str:
    desc = body_desc(make, model, body_style)
    return (
        f"A crisp, clear studio product photograph of a {desc}. The entire car body is completely wrapped in a "
        f"uniform, smooth matte unpolished light-grey vinyl film coating. All four wheels, multi-spoke rims, and "
        f"rubber tires are fully detailed and visible. Completely de-badged. A uniform 3/4 front passenger-side "
        f"perspective view angle. All window elements are clear unreflective glass. {STUDIO_PRESET}"
    )


def preview_card_prompt(make: str, model: str, body_style: str, color: str) -> str:
    desc = body_desc(make, model, body_style)
    return (
        f"An immaculate photorealistic studio product photograph of a {desc}. {color_modifier(color)}, "
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
        f"An immaculate photorealistic studio product photograph of a {desc}. {color_modifier(color)}, "
        f"glistening clear coat layer. All wheels and trim details fully rendered. Completely emblem-free. "
        f"{_ANGLE_TEXT[angle]} {WINDOW_LOCK_RULE} {STUDIO_PRESET}"
    )


def interior_cockpit_prompt(make: str, model: str) -> str:
    return (
        f"A premium studio first-person cockpit view looking directly forward from the driver's seat eye-line "
        f"perspective inside a luxury {make} {model}. A prominent fully detailed black leather-wrapped modern "
        f"steering wheel is positioned directly in front of the center field of view. Directly behind the "
        f"steering wheel, a fully active digital instrumentation gauge cluster and binnacle display is "
        f"completely visible showing illuminated driver metrics. Premium soft saddle-brown stitched leather "
        f"dashboard inserts flank the active multimedia screen array. The sunroof opening reveals a solid "
        f"uniform soft diffuse studio illumination light box sky ceiling, strictly zero blue sky or clouds "
        f"permitted. The view looking through the front windshield and all side window panes reveals nothing but "
        f"a solid, completely uniform, boundless flat light-grey studio infinity cove backdrop with strictly zero "
        f"external vehicles, zero structures, and zero background shapes permitted. Both wing mirrors visible "
        f"through the windows are modified to be completely solid, blank, opaque matte black plastic textures "
        f"containing zero reflections."
    )


def interior_seating_prompt(make: str, model: str, body_style: str) -> str:
    if body_style == "suv":
        return (
            f"A high-fidelity studio detailed photograph taken inside the middle seat passenger cabin area of a "
            f"modern luxury {make} {model} SUV. The middle passenger row features an immaculate, standalone set "
            f"of premium saddle-brown leather captain's chairs with crisp diamond-quilted stitching. A clear, "
            f"wide, completely empty dark carpeted center aisle pathway separates the chairs, and the third-row "
            f"seating architecture is safely constrained far in the background distance. The detailed backs of "
            f"the premium front driver and passenger bucket seats are clearly visible, normally positioned, and "
            f"occupy the lower left and right foreground corners of the frame layout. The painted steel interior "
            f"metal trim framework surrounding the seats is finished in a solid liquid metallic theme, strictly "
            f"zero blue panels, zero red door accents. All side window profiles are heavily dark smoke tinted "
            f"glass surfaces."
        )
    return (
        f"A high-fidelity studio detailed photograph taken inside the rear seat passenger row cabin area of a "
        f"modern luxury {make} {model}. Immaculate uniform saddle-brown leather backseat upholstery textures "
        f"with premium quilted diamond-stitching details. The detailed backs of the premium front driver and "
        f"passenger bucket seats are clearly visible, normally positioned, and occupy the lower left and right "
        f"foreground corners of the frame layout. The floor area between the seating rows is an empty, "
        f"realistic wide spacious dark carpeted floor area. The painted steel interior metal trim framework "
        f"surrounding the seats is finished in a solid liquid metallic theme, strictly zero blue panels, zero red "
        f"door accents. All side window profiles are heavily dark smoke tinted glass surfaces."
    )
