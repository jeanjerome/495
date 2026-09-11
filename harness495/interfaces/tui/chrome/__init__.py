"""The four surfaces that are on screen whatever the view: identity, attention, pipeline, keys."""

from harness495.interfaces.tui.chrome.band import attention_band
from harness495.interfaces.tui.chrome.footer import footer_bar, vitals
from harness495.interfaces.tui.chrome.header import header
from harness495.interfaces.tui.chrome.logo import LogoMark, still
from harness495.interfaces.tui.chrome.nav import nav_bar

__all__ = ["LogoMark", "attention_band", "footer_bar", "header", "nav_bar", "still", "vitals"]
