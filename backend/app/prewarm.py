"""Background cache pre-warming. Enumerates every render the current
inventory needs (generic placeholders, per-color previews and angle shots,
per-model cockpit/seating) and finds the next one missing from disk. Stateless
by design — recomputed from inventory + what's already on disk each time,
so it's automatically resumable across restarts with no separate queue table
to keep in sync.
"""

from . import chat_logic, image_cache, inventory as inv, config


def enumerate_needed_renders():
    """Returns [(cache_key, prompt, meta), ...] for every render the current
    inventory should have, in priority order (cheap/broadly-useful first)."""
    tasks = []

    # Generic body-style placeholders first: only 3 ever exist, and every
    # future session benefits from them immediately.
    for body_style in ("sedan", "suv", "truck"):
        tasks.append(
            (
                image_cache.cache_key("generic", body_style),
                chat_logic.generic_body_style_prompt(body_style),
                {"make": None, "model": None, "color": None, "category": f"generic_{body_style}"},
            )
        )

    seen_model_color = set()
    seen_model = set()

    for car in inv.load_inventory():
        make, model, color = car["make"], car["model"], car["color"]
        body_style = car["body_style"].lower()

        if (make, model, color) not in seen_model_color:
            seen_model_color.add((make, model, color))

            tasks.append(
                (
                    image_cache.cache_key(make, model, color, "preview"),
                    chat_logic.preview_card_prompt(make, model, body_style, color),
                    {"make": make, "model": model, "color": color, "category": "preview"},
                )
            )
            for angle in ("front_3q", "side", "rear_3q"):
                tasks.append(
                    (
                        image_cache.cache_key(make, model, color, angle),
                        chat_logic.exterior_angle_prompt(make, model, body_style, color, angle),
                        {"make": make, "model": model, "color": color, "category": angle},
                    )
                )

        if (make, model) not in seen_model:
            seen_model.add((make, model))
            tasks.append(
                (
                    image_cache.cache_key(make, model, "cockpit"),
                    chat_logic.interior_cockpit_prompt(make, model),
                    {"make": make, "model": model, "color": None, "category": "cockpit"},
                )
            )
            tasks.append(
                (
                    image_cache.cache_key(make, model, body_style, "seating"),
                    chat_logic.interior_seating_prompt(make, model, body_style),
                    {"make": make, "model": model, "color": None, "category": "seating"},
                )
            )

    return tasks


def next_missing_render():
    """Returns the first (key, prompt, meta) not yet on disk, or None if the
    cache is fully warm for the current inventory."""
    for key, prompt, meta in enumerate_needed_renders():
        filepath = config.IMAGE_CACHE_DIR / f"{key}.png"
        if not filepath.exists():
            return key, prompt, meta
    return None


def progress_summary():
    """Returns (generated_count, total_count) against the current inventory."""
    tasks = enumerate_needed_renders()
    total = len(tasks)
    generated = sum(1 for key, _, _ in tasks if (config.IMAGE_CACHE_DIR / f"{key}.png").exists())
    return generated, total
