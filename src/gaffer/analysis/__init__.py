"""Deterministic stat functions over canonical match data.

These are the only place numbers come from — the LLM composes and interprets,
it never computes. All functions are pure: (Match, ...) -> report model.
"""

from gaffer.analysis import defending, passing, possession, shooting, summary

__all__ = ["defending", "passing", "possession", "shooting", "summary"]
