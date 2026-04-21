"""Canonical in-site service paths and repair for model-hallucinated domains (e.g. kcpext.com)."""

from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

# Shown in LLM system prompts: relative paths work on any production host (Netlify custom domain, etc.)
INTERNAL_SERVICE_CTA_BLOCK = """
**KC Pest Experts on-site links (use ONLY these relative paths; never invent a domain or /services/... URL):**
- General pest: [/pest-and-wildlife-services/local-pest-control-experts](/pest-and-wildlife-services/local-pest-control-experts)
- Rodent control: [/pest-and-wildlife-services/rodent-pest-control-service](/pest-and-wildlife-services/rodent-pest-control-service)
- Termite control: [/pest-and-wildlife-services/termite-control-service](/pest-and-wildlife-services/termite-control-service)
- Pre-construction termite: [/pest-and-wildlife-services/pre-construction-termite-treatments](/pest-and-wildlife-services/pre-construction-termite-treatments)
- Bed bugs: [/pest-and-wildlife-services/bed-bug-service](/pest-and-wildlife-services/bed-bug-service)
- Carpenter ants: [/pest-and-wildlife-services/carpenter-ants-pest-control](/pest-and-wildlife-services/carpenter-ants-pest-control)
- Spiders: [/pest-and-wildlife-services/spider-pest-control-service](/pest-and-wildlife-services/spider-pest-control-service)
- Mosquitoes & ticks: [/pest-and-wildlife-services/mosquitos-ticks-pest-control](/pest-and-wildlife-services/mosquitos-ticks-pest-control)
- Wildlife: [/pest-and-wildlife-services/wildlife-control-services](/pest-and-wildlife-services/wildlife-control-services)
- Attic & insulation cleanup: [/pest-and-wildlife-services/attic-disinfectant-insulation-cleanup](/pest-and-wildlife-services/attic-disinfectant-insulation-cleanup)
- Request service / contact: [/pest-control-service#request-form](/pest-control-service#request-form)
Do not use kcpext.com, kcpext, or any `https://` URL for our own site except real external authority links (CDC, EPA, .edu) in ## Sources."""


_KCPEXT_URL_RE = re.compile(
    r"https?://(?:www\.)?kcpext\.com[^\s)]+",
    re.IGNORECASE,
)


def _map_loose_path_to_service(path: str) -> str:
    """Map a bad URL path (e.g. /services/rodent-control) to a real site path."""
    p = unquote(path or "").lower()
    if "pre-construction" in p or "preconstruction" in p:
        return "/pest-and-wildlife-services/pre-construction-termite-treatments"
    if "rodent" in p or "mice" in p or "rat" in p:
        return "/pest-and-wildlife-services/rodent-pest-control-service"
    if "bed" in p and "bug" in p:
        return "/pest-and-wildlife-services/bed-bug-service"
    if "carpenter" in p and "ant" in p:
        return "/pest-and-wildlife-services/carpenter-ants-pest-control"
    if "spider" in p:
        return "/pest-and-wildlife-services/spider-pest-control-service"
    if "mosquito" in p or "tick" in p:
        return "/pest-and-wildlife-services/mosquitos-ticks-pest-control"
    if "wildlife" in p:
        return "/pest-and-wildlife-services/wildlife-control-services"
    if "attic" in p or "insulation" in p or "disinfect" in p:
        return "/pest-and-wildlife-services/attic-disinfectant-insulation-cleanup"
    if "termite" in p or "inspection" in p:
        return "/pest-and-wildlife-services/termite-control-service"
    if "local" in p or "general" in p or "expert" in p:
        return "/pest-and-wildlife-services/local-pest-control-experts"
    return "/pest-and-wildlife-services/local-pest-control-experts"


def sanitize_fabricated_kcpext_urls(text: str) -> str:
    """Replace hallucinated kcpext.com links with the correct relative service path."""

    def _sub(m: re.Match[str]) -> str:
        raw = m.group(0)
        parsed = urlparse(raw)
        return _map_loose_path_to_service(parsed.path or "/")

    return _KCPEXT_URL_RE.sub(_sub, text)
