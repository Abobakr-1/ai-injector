"""ai-injector — offensive prompt-injection testing harness.

Two specialized modules are shipped in v1.0:

* :mod:`ai_injector.modules.direct`   -- direct prompt injection
* :mod:`ai_injector.modules.indirect` -- indirect prompt injection

Everything they share (adapters, payloads, oracle, engine, evidence, reports)
lives in this package.
"""

__version__ = "1.0.0"
__all__ = ["__version__"]
