"""USD estimates at owner-supplied prices; not a provider billing guarantee."""
from decimal import Decimal, ROUND_CEILING

MAX_INPUT_TOKENS = 32768
MAX_OUTPUT_TOKENS = 1000


def price(settings: dict, input_tokens: int, output_tokens: int) -> int | None:
    a, b = settings.get("input_usd_per_million"), settings.get("output_usd_per_million")
    if a is None or b is None:
        return None
    # USD/million multiplied by tokens gives micro-USD. Always round upward.
    return int((Decimal(str(a))*input_tokens + Decimal(str(b))*output_tokens).to_integral_value(rounding=ROUND_CEILING))


def allowance(settings: dict) -> int | None:
    value = settings.get("daily_budget_usd")
    return int(Decimal(str(value))*1_000_000) if value is not None else None
