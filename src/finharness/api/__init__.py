"""Local API package without eager application construction.

Importing a route module must not import every optional API surface through the
package initializer. Application construction lives at ``finharness.api.app``.
"""

from __future__ import annotations

__all__: list[str] = []
