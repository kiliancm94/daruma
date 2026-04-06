"""Parsing helpers for task environment variables."""


def _parse_pair(pair: str) -> tuple[str, str]:
    """Parse a single KEY=VALUE string. Raises ValueError if no '='."""
    if "=" not in pair:
        raise ValueError(f"Invalid env var (expected KEY=VALUE): {pair}")
    key, _, value = pair.partition("=")
    return key, value


def parse_env_pairs(pairs: tuple[str, ...]) -> dict[str, str] | None:
    """Parse CLI --env KEY=VALUE pairs into a dict."""
    if not pairs:
        return None
    return dict(_parse_pair(p) for p in pairs)


def parse_env_text(text: str) -> dict[str, str] | None:
    """Parse UI textarea (one KEY=VALUE per line) into a dict."""
    if not text.strip():
        return None
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    return dict(_parse_pair(line) for line in lines)
