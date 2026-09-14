"""Visual tokens for the Diagram Base Capability.

The capability is domain-agnostic, so the theme is a plain, overridable
dataclass. Defaults follow the zihao raccoon visual identity
(cream ground, deep-blue ink, raccoon-gold accent) without importing any
project-specific business semantics.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DumbbellTheme:
    paper: str = "#FFF9EF"
    ink: str = "#174A7C"
    ink_strong: str = "#06213D"
    muted: str = "#6B7C8F"
    rule: str = "rgba(23,74,124,0.14)"
    rule_solid: str = "rgba(23,74,124,0.28)"
    accent: str = "#D79A36"
    accent_tint: str = "rgba(215,154,54,0.16)"
    entity_a: str = "#174A7C"
    entity_a_tint: str = "rgba(23,74,124,0.10)"
    entity_b: str = "#D79A36"
    entity_b_tint: str = "rgba(215,154,54,0.16)"
    brown: str = "#7A4A24"
    # Local typography follows the diagram-design profile: one local family
    # for Chinese, Latin, numbers, labels and headings; no remote fonts.
    font_sans: str = '"Noto Sans CJK SC", sans-serif'
    font_mono: str = '"Noto Sans CJK SC", sans-serif'
    font_serif: str = '"Noto Sans CJK SC", sans-serif'


DEFAULT_THEME = DumbbellTheme()
