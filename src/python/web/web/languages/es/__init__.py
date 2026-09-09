"""Spanish: the tense catalogue, the Reverso source, the adapter.

Everything in this package is Spanish's alone. The drill reaches it only
through ``SpanishAdapter``, which the registry in ``languages/__init__.py``
publishes under ``CODE``. The source itself is shared with Italian — see
``languages/reverso.py`` — because Reverso serves both from one template.
"""

from .adapter import CODE, SpanishAdapter

__all__ = ["CODE", "SpanishAdapter"]
