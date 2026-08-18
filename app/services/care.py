def evaluate_financial_care(
    *, cash: float | None, buffer: float, immediate_cost: float = 0.0
) -> tuple[str, str]:
    if cash is None:
        return "review", "liquid cash unknown"

    projected = cash - max(immediate_cost, 0.0)
    if projected < buffer:
        return "blocked", f"would reduce liquid cash below safety buffer ({buffer:.2f})"

    return "approved", "within declared financial safety buffer"
