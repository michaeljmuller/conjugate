"""Italian: the tense catalogue, the Reverso source, the adapter.

Everything in this package is Italian's alone. The drill reaches it only
through ``ItalianAdapter``, which the registry in ``languages/__init__.py``
publishes under ``CODE``.
"""

from .adapter import CODE, ItalianAdapter

__all__ = ["CODE", "ItalianAdapter"]
