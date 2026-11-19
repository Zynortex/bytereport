import json
import re
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)
RAW_DUMP_DIR = Path("logs/raw_ai_responses")


def safe_json_loads(raw: str) -> dict:
    """Parse a JSON string returned by an LLM with multi-level repair."""
    text = raw.strip()

    # Level 1: strip markdown fences ```json ... ```
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)

    # Level 2: skip preamble / trailing prose — extract first { ... last }
    first, last = text.find('{'), text.rfind('}')
    if first != -1 and last != -1 and last > first:
        text = text[first:last + 1]

    # Level 3: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Level 4: remove invalid escape sequences.
    # Valid JSON escapes after \: " \ / b f n r t u
    # Everything else (\%, \_, \~, lone \) — drop the backslash, keep the char.
    # Applied only after a parse failure so legitimate \n etc. survive level 3.
    repaired = re.sub(r'\\(?!["\\/bfnrtu])', '', text)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # Level 5: fix trailing commas before } or ]
    repaired2 = re.sub(r',\s*([}\]])', r'\1', repaired)
    try:
        return json.loads(repaired2)
    except json.JSONDecodeError as e:
        RAW_DUMP_DIR.mkdir(parents=True, exist_ok=True)
        dump_path = RAW_DUMP_DIR / f"failed_{datetime.now():%Y%m%d_%H%M%S}.txt"
        dump_path.write_text(raw, encoding="utf-8")
        logger.error("JSON parse failed after all repairs: %s. Raw dumped to %s", e, dump_path)
        raise ValueError(
            f"AI вернул некорректный JSON. Сырой ответ сохранён: {dump_path}"
        ) from e
