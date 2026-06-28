from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types

from . import config

_client: Optional[genai.Client] = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        if not config.GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Add it to your environment (see .env.example)."
            )
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def _build_contents(history: list[dict], new_message: str) -> list:
    """Replays prior turns from the DB into a Gemini contents list. Doing it
    this way (stateless, from stored history) rather than holding a live
    chats.create() object in memory means a session survives a container
    restart and can be resumed from any process — which is what 'continue
    your chat later' actually requires.
    """
    contents = []
    for turn in history:
        role = "model" if turn["role"] == "assistant" else "user"
        contents.append(types.Content(role=role, parts=[types.Part(text=turn["content"])]))
    contents.append(types.Content(role="user", parts=[types.Part(text=new_message)]))
    return contents


def send_chat_turn(system_instruction: str, history: list[dict], new_message: str, schema):
    client = get_client()
    response = client.models.generate_content(
        model=config.CHAT_MODEL,
        contents=_build_contents(history, new_message),
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0.2,
        ),
    )
    return schema.model_validate_json(response.text)


def generate_image(prompt: str, output_path: Path) -> bool:
    client = get_client()
    response = client.models.generate_content(
        model=config.IMAGE_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(aspect_ratio="16:9"),
        ),
    )
    for part in response.parts:
        if part.inline_data:
            image = part.as_image()
            image.save(str(output_path))
            return True
    return False
