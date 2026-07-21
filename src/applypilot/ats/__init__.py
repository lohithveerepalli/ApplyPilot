"""ATS adapters: detect platform + specialized apply strategies + board discovery."""

from applypilot.ats.detect import detect_ats, AtsInfo
from applypilot.ats.strategies import get_apply_strategy

__all__ = ["detect_ats", "AtsInfo", "get_apply_strategy"]
