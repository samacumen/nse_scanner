"""Load and validate config.txt (INI via stdlib configparser).

Blueprint 6: every knob lives in config.txt; parsed by configparser with
inline comments (# and ;). Types/ranges are validated here and exposed as
typed attributes (cfg.section.key). Blank value = "unset/default" (None).

Also holds the project-root path resolution (works on Linux and Windows,
pathlib only, resolved relative to this file - never the cwd).
"""
from __future__ import annotations

import configparser
from pathlib import Path
from types import SimpleNamespace

# Project root = parent of src/ . Resolved from THIS file, never the cwd,
# so both scripts and tests find config.txt/data/output on any OS.
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
CONFIG_PATH: Path = PROJECT_ROOT / "config.txt"


class ConfigError(ValueError):
    """Raised on a missing/malformed/out-of-range config value (clear message)."""


def _clean(raw: str | None) -> str | None:
    """Trim; treat blank as None (== 'unset/default')."""
    if raw is None:
        return None
    s = raw.strip()
    return s if s != "" else None


class _Section:
    """Typed accessors over one INI section.

    A missing section or key is NOT an error: it falls back to the built-in
    default defined in load_config(). This is what lets the everyday config.txt
    stay short - anything it omits comes from advanced_config.txt, and anything
    neither file sets uses the coded default.
    """

    def __init__(self, parser: configparser.ConfigParser, name: str):
        self._p = parser
        self._name = name

    def _raw(self, key: str) -> str | None:
        if not self._p.has_option(self._name, key):
            return None  # missing key -> use the coded default
        return _clean(self._p.get(self._name, key))

    def str_(self, key: str, default: str | None = None, allow_blank: bool = True):
        v = self._raw(key)
        if v is None:
            if allow_blank:
                return default
            raise ConfigError(f"[{self._name}] '{key}' must not be blank")
        return v

    def int_(self, key: str, default=None, lo=None, hi=None):
        v = self._raw(key)
        if v is None:
            return default
        try:
            n = int(v)
        except ValueError:
            raise ConfigError(f"[{self._name}] '{key}'={v!r} is not an integer")
        self._range(key, n, lo, hi)
        return n

    def float_(self, key: str, default=None, lo=None, hi=None):
        v = self._raw(key)
        if v is None:
            return default
        try:
            f = float(v)
        except ValueError:
            raise ConfigError(f"[{self._name}] '{key}'={v!r} is not a number")
        self._range(key, f, lo, hi)
        return f

    def bool_(self, key: str, default=None):
        v = self._raw(key)
        if v is None:
            return default
        low = v.lower()
        if low in ("true", "1", "yes", "on"):
            return True
        if low in ("false", "0", "no", "off"):
            return False
        raise ConfigError(f"[{self._name}] '{key}'={v!r} is not a boolean (true/false)")

    def list_(self, key: str, default=None, cast=str):
        v = self._raw(key)
        if v is None:
            return default
        out = []
        for item in v.split(","):
            item = item.strip()
            if item == "":
                continue
            try:
                out.append(cast(item))
            except ValueError:
                raise ConfigError(f"[{self._name}] '{key}' item {item!r} invalid")
        return out

    def choice_(self, key: str, allowed, default=None):
        v = self._raw(key)
        if v is None:
            return default
        if v not in allowed:
            raise ConfigError(
                f"[{self._name}] '{key}'={v!r} not in allowed {sorted(allowed)}"
            )
        return v

    def _range(self, key, n, lo, hi):
        if lo is not None and n < lo:
            raise ConfigError(f"[{self._name}] '{key}'={n} below minimum {lo}")
        if hi is not None and n > hi:
            raise ConfigError(f"[{self._name}] '{key}'={n} above maximum {hi}")


def load_config(path: Path | str | None = None) -> SimpleNamespace:
    """Parse + validate config.txt; return nested SimpleNamespace.

    Access like: cfg.macd.fast, cfg.divergence.trough_detection, ...
    Also cfg.raw (the flat dict of section->key->str for the report echo).
    """
    p = Path(path) if path is not None else CONFIG_PATH
    if not p.exists():
        raise ConfigError(f"config file not found: {p}")

    parser = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    # Preserve key case (SERIES etc. are lower here, but be safe/predictable).
    parser.optionxform = str
    # The everyday settings live in config.txt; the rarely-changed method/tuning
    # knobs live in an OPTIONAL advanced_config.txt next to it. Read advanced
    # first so config.txt wins on any shared key; if advanced is absent, the
    # coded defaults apply. Either file may omit any key.
    advanced = p.parent / "advanced_config.txt"
    to_read = ([str(advanced)] if advanced.exists() else []) + [str(p)]
    parser.read(to_read, encoding="utf-8")

    U = _Section(parser, "universe")
    D = _Section(parser, "data")
    M = _Section(parser, "macd")
    V = _Section(parser, "divergence")
    W = _Section(parser, "weekly")
    R = _Section(parser, "rsi")
    L = _Section(parser, "liquidity")
    K = _Section(parser, "ranking")
    O = _Section(parser, "output")

    universe = SimpleNamespace(
        series=U.list_("series", default=["EQ"]) or ["EQ"],
        include_sme=U.bool_("include_sme", default=False),
        index_filter=U.str_("index_filter", default=None),
        max_symbols=U.int_("max_symbols", default=None, lo=1),
        symbols_override=U.list_("symbols_override", default=None),
    )
    data = SimpleNamespace(
        history_years=D.int_("history_years", default=6, lo=1, hi=30),
        price_adjustment=D.choice_(
            "price_adjustment", {"split_only", "total_return"}, default="split_only"
        ),
        request_throttle_sec=D.float_("request_throttle_sec", default=0.5, lo=0.0),
        min_rows_daily=D.int_("min_rows_daily", default=1000, lo=1),
        refresh_if_older_than_hours=D.float_(
            "refresh_if_older_than_hours", default=120.0, lo=0.0
        ),
        prune_stale=D.bool_("prune_stale", default=True),
    )
    macd = SimpleNamespace(
        fast=M.int_("fast", default=12, lo=1),
        slow=M.int_("slow", default=26, lo=1),
        signal=M.int_("signal", default=9, lo=1),
    )
    if macd.fast >= macd.slow:
        raise ConfigError("[macd] fast must be < slow")

    divergence = SimpleNamespace(
        lookback_days=V.int_("lookback_days", default=60, lo=2),
        price_window_k=V.int_("price_window_k", default=3, lo=0),
        trough_detection=V.choice_(
            "trough_detection", {"prominence", "strict"}, default="prominence"
        ),
        min_segment_len=V.int_("min_segment_len", default=1, lo=1),
        prominence_frac=V.float_("prominence_frac", default=0.10, lo=0.0),
        divergence_scope=V.choice_(
            "divergence_scope",
            {"two_most_recent", "recent_vs_deepest_prior"},
            default="two_most_recent",
        ),
        min_trough_sep=V.int_("min_trough_sep", default=7, lo=1),
        tolerance_pct=V.float_("tolerance_pct", default=0.01, lo=0.0),
        price_field=V.choice_("price_field", {"Low", "Close"}, default="Low"),
        require_confirmation=V.bool_("require_confirmation", default=True),
        confirm_bars=V.int_("confirm_bars", default=3, lo=1),
        recency_bars=V.int_("recency_bars", default=20, lo=1),
    )
    weekly = SimpleNamespace(
        ema_set=W.list_("ema_set", default=[11, 22, 50], cast=int) or [11, 22, 50],
        zone_test=W.choice_(
            "zone_test", {"range_overlap", "close_in_band"}, default="range_overlap"
        ),
        min_weekly_bars_for_zone=W.int_(
            "min_weekly_bars_for_zone", default=200, lo=1
        ),
    )
    rsi = SimpleNamespace(
        period=R.int_("period", default=14, lo=2),
        smoothing=R.choice_("smoothing", {"wilder", "sma"}, default="wilder"),
        lower_band=R.float_("lower_band", default=30.0, lo=0.0, hi=100.0),
    )
    liquidity = SimpleNamespace(
        apply_as_filter=L.bool_("apply_as_filter", default=True),
        window=L.int_("window", default=20, lo=1),
        min_median_traded_value_inr=L.float_(
            "min_median_traded_value_inr", default=5e7, lo=0.0
        ),
        min_price=L.float_("min_price", default=20.0, lo=0.0),
    )
    ranking = SimpleNamespace(
        top_n=K.int_("top_n", default=10, lo=1),
        weight_momentum=K.float_("weight_momentum", default=0.30),
        weight_zone_confluence=K.float_("weight_zone_confluence", default=0.20),
        weight_rsi_quality=K.float_("weight_rsi_quality", default=0.15),
        weight_liquidity=K.float_("weight_liquidity", default=0.15),
        weight_recency=K.float_("weight_recency", default=0.10),
        weight_volume_expansion=K.float_("weight_volume_expansion", default=0.10),
        min_score=K.float_("min_score", default=None),
    )
    output = SimpleNamespace(
        dir=O.str_("dir", default="output") or "output",
        write_full_flagged_csv=O.bool_("write_full_flagged_csv", default=True),
    )

    # Flat echo for the report header (exact strings the user set, comments stripped).
    raw = {}
    for sec in parser.sections():
        raw[sec] = {k: _clean(parser.get(sec, k)) for k in parser.options(sec)}

    return SimpleNamespace(
        universe=universe,
        data=data,
        macd=macd,
        divergence=divergence,
        weekly=weekly,
        rsi=rsi,
        liquidity=liquidity,
        ranking=ranking,
        output=output,
        raw=raw,
        project_root=PROJECT_ROOT,
    )
