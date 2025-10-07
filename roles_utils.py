"""Utility helpers for working with role lists in configuration profiles."""

from __future__ import annotations

from typing import Iterable, List, Sequence


def normalize_roles(raw: object) -> List[str]:
    """Return a cleaned list of role strings from arbitrary input.

    The GUI historically stored role information as a list of strings, but some
    configurations may contain other structures (e.g. a single string such as
    "admin" or nested sequences).  This helper normalises such inputs by:

    * Accepting strings, sequences or any iterable value.
    * Stripping whitespace from each item and dropping empty entries.
    * Preserving the original order while removing duplicates.

    Parameters
    ----------
    raw:
        Value read from a configuration file or GUI widget.

    Returns
    -------
    list[str]
        A list containing the cleaned role names.
    """

    roles: List[str] = []
    seen = set()

    def _append(candidate: object) -> None:
        if candidate is None:
            return
        if isinstance(candidate, str):
            parts: Sequence[str] = candidate.splitlines() or [candidate]
        elif isinstance(candidate, Iterable) and not isinstance(candidate, (bytes, bytearray)):
            for item in candidate:
                _append(item)
            return
        else:
            parts = [str(candidate)]

        for part in parts:
            text = str(part).strip()
            if not text:
                continue
            if text in seen:
                continue
            seen.add(text)
            roles.append(text)

    _append(raw)
    return roles

