"""Send prompts to Gemini and get back JSON that matches a schema.
"""

import functools
import json
import os
import time

import httpx
from google import genai
from google.genai import errors, types

API_KEY_ENV_VAR = "GEMINI_API_KEY"
MODEL_ENV_VAR = "REPOMENTOR_MODEL"
DEFAULT_MODEL = "gemini-3.5-flash-lite"

MAX_ATTEMPTS = 3
RETRY_WAIT_SECONDS = 60
RETRY_STATUS_CODES = {429, 500, 503}


class AIError(Exception):
    """Raised when the AI request fails or returns an unusable answer."""


def get_model() -> str:
    """Return the model name: REPOMENTOR_MODEL if set, otherwise the default."""
    return os.environ.get(MODEL_ENV_VAR) or DEFAULT_MODEL


@functools.cache
def get_client() -> genai.Client:
    """Create the Gemini client once and reuse it. The SDK reads GEMINI_API_KEY itself."""
    if not os.environ.get(API_KEY_ENV_VAR):
        raise AIError(
            f"{API_KEY_ENV_VAR} is not set. Create a key at https://aistudio.google.com/apikey, "
            f'run: setx {API_KEY_ENV_VAR} "your-key", then restart VS Code.'
        )
    return genai.Client()


def ask_json(prompt: str, schema: dict, instructions: str = "") -> dict:
    """Send a prompt and return the model's answer as a dict that follows the JSON schema.

    Rate limits and temporary server errors are retried a few times. Any other
    problem raises AIError with a short explanation.
    """
    model = get_model()
    config = types.GenerateContentConfig(
        system_instruction=instructions or None,
        response_mime_type="application/json",
        response_json_schema=schema,
    )

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = get_client().models.generate_content(model=model, contents=prompt, config=config)
            break
        except errors.APIError as error:
            if error.code not in RETRY_STATUS_CODES or attempt == MAX_ATTEMPTS:
                raise AIError(f"Gemini request failed ({error.code}): {error.message}") from error
            print(f"Gemini is busy or rate limited ({error.code}), waiting {RETRY_WAIT_SECONDS} seconds "
                  f"(attempt {attempt + 1} of {MAX_ATTEMPTS})")
            time.sleep(RETRY_WAIT_SECONDS)
        except httpx.TransportError as error:
            raise AIError(f"Could not reach Gemini. Check your internet connection. ({error})") from error

    if not response.text:
        raise AIError("Gemini returned an empty answer.")
    try:
        return json.loads(response.text)
    except json.JSONDecodeError as error:
        raise AIError("Gemini did not return valid JSON.") from error


def number_lines(text: str) -> str:
    """Prefix every line with its line number, so the model can refer to exact lines.

    Example: "import torch" on the first line becomes "1: import torch".
    """
    return "\n".join(f"{number}: {line}" for number, line in enumerate(text.splitlines(), start=1))