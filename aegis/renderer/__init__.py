"""Renderer package — exception taxonomy + (later) dispatcher chain.

Exceptions raised by individual renderer adapters; the Block 4 dispatcher walks
the CHAIN catching these and trying the next tier.
"""


class RendererError(Exception):
    """Base for all renderer-tier errors. Catch this if you want to fall back
    to the template renderer for any reason."""


class QuotaExhausted(RendererError):
    """Provider rejected the request because the per-day/per-minute budget is
    exhausted (HTTP 429 with quota signal, or local budget bookkeeping says no).
    Dispatcher should advance to the next tier and not retry this one until the
    bookkeeping says the window has rolled."""


class TransientError(RendererError):
    """Provider had a transient failure (HTTP 5xx, network timeout, DNS error,
    connection reset). Dispatcher should advance to the next tier; the next
    tick's call may succeed on this tier again."""
