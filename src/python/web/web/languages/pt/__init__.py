"""European Portuguese: the tense catalogue, the cplp.org source, the adapter.

Everything in this package is pt-PT's alone. The drill reaches it only through
``PortugueseAdapter``, which the registry in ``languages/__init__.py``
publishes under ``CODE``.
"""

from .adapter import CODE, PortugueseAdapter

__all__ = ["CODE", "PortugueseAdapter"]
