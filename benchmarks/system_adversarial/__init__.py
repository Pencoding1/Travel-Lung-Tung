"""SYS098 bounded system/adversarial HTTP collector (offline implementation).

The package is inert on import.  :mod:`runner` is dry-run by default and
:mod:`qa_runtime` only installs its seam when the owned child launcher sets
``SYS098_ENABLE_QA=1`` and calls ``install()`` explicitly.
"""

__all__ = ["qa_runtime", "runner"]
