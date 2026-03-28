def short_exc(exc: Exception) -> str:
    msg = str(exc).strip()
    return f"{type(exc).__name__}: {msg[:180]}" if msg else type(exc).__name__


__all__ = ["short_exc"]
