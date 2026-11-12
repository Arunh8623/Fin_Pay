from decimal import Decimal, InvalidOperation

MINOR = 100  # 2 decimal places (paise)


def to_minor(amount: Decimal) -> int:
    return int((amount * MINOR).to_integral_exact())


def from_minor(minor: int) -> Decimal:
    return (Decimal(minor) / MINOR).quantize(Decimal("0.01"))


def parse_amount(value) -> Decimal | None:
    """Return a finite Decimal or None if the value is not a number."""
    if value is None or isinstance(value, bool):
        return None
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() else None
