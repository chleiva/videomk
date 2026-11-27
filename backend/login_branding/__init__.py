"""Branding of the Cognito sign-in page (Managed Login), shared by the CDK stack and the preview script.

Managed Login (the newer hosted sign-in) needs the user pool on the Essentials or Plus feature plan (both pools are on Essentials: included, free up to
10,000 monthly active users, then USD 0.015 per MAU) and the pool domain on `NEWER_MANAGED_LOGIN`. Everything here is plain data so it can be tested:

  settings()        the branding settings document (light and dark, DYNAMIC follows the device)
  assets()          [{category, color_mode, extension, bytes(base64)}]

Design rules come from docs/brand/README.md: indigo-violet gradient and white, cyan only on dark surfaces, the lockup (Sparklet Trio tile + wordmark) above
the form, one primary button, 12-20 px radii, generous spacing, no heading clutter, no side graphics. Colours are RRGGBBAA.
Texts are Cognito's own and follow the browser language or the `lang` query parameter (en, es): the apps pass `lang`, see docs/AUTH_SOCIAL.md.
"""
import base64
import copy
import json
import os
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))

INK, MUTED = "11142bff", "5a607aff"
LIGHT = dict(page="f6f7fcff", card="ffffffff", card_border="e3e5f2ff", input_border="c3c7dcff", placeholder="7a8099ff", primary="4a3fc4ff", primary_hover="372e9fff",
             primary_active="2b2f9aff", link="4a3fc4ff", link_hover="2b2f9aff", focus="4a3fc4ff", divider="e3e5f2ff")
DARK = dict(page="0a0d1fff", card="141833ff", card_border="262b52ff", input_border="3a4075ff", placeholder="8a90b0ff", primary="6a3fc4ff", primary_hover="7d55d6ff",
            primary_active="6a3fc4ff", link="b8c0ffff", link_hover="ffffffff", focus="22d3eeff", divider="262b52ff")


def _read(name: str, mode: str = "rb") -> bytes:
    with open(os.path.join(HERE, name), mode) as f:
        return f.read()


def _merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def settings(color_scheme: str = "DYNAMIC") -> Dict[str, Any]:
    s = json.loads(_read("default_settings.json", "r"))   # Cognito's own defaults (snapshot), then our overrides: unspecified keys stay valid
    L, D = LIGHT, DARK
    btn = lambda c: {"defaults": {"backgroundColor": c["primary"], "textColor": "ffffffff"}, "hover": {"backgroundColor": c["primary_hover"], "textColor": "ffffffff"},
                     "active": {"backgroundColor": c["primary_active"], "textColor": "ffffffff"}, "disabled": {"backgroundColor": c["divider"], "borderColor": c["divider"]}}
    sec = lambda c: {"defaults": {"backgroundColor": "00000000", "borderColor": c["primary"], "textColor": c["link"]}, "hover": {"backgroundColor": "4a3fc41a", "borderColor": c["link_hover"], "textColor": c["link_hover"]},
                     "active": {"backgroundColor": "4a3fc426", "borderColor": c["link_hover"], "textColor": c["link_hover"]}}
    idp = lambda c, text: {"defaults": {"backgroundColor": c["card"], "borderColor": c["input_border"], "textColor": text}, "hover": {"backgroundColor": c["page"], "borderColor": c["link"], "textColor": text},
                           "active": {"backgroundColor": c["page"], "borderColor": c["link"], "textColor": text}}
    over = {
        "components": {
            "form": {"borderRadius": 20.0, "logo": {"enabled": True, "location": "CENTER", "position": "TOP", "formInclusion": "OUT"},
                     "lightMode": {"backgroundColor": L["card"], "borderColor": L["card_border"]}, "darkMode": {"backgroundColor": D["card"], "borderColor": D["card_border"]}},
            "pageBackground": {"image": {"enabled": True}, "lightMode": {"color": L["page"]}, "darkMode": {"color": D["page"]}},
            "pageText": {"lightMode": {"bodyColor": MUTED, "headingColor": INK, "descriptionColor": MUTED}, "darkMode": {"bodyColor": "c9cde6ff", "headingColor": "f3f4fbff", "descriptionColor": "c9cde6ff"}},
            "primaryButton": {"lightMode": btn(L), "darkMode": btn(D)},
            "secondaryButton": {"lightMode": sec(L), "darkMode": sec(D)},
            "idpButton": {"standard": {"lightMode": idp(L, INK), "darkMode": idp(D, "f3f4fbff")}, "custom": {}},
            "alert": {"borderRadius": 12.0},
            "favicon": {"enabledTypes": ["ICO", "SVG"]},
        },
        "componentClasses": {
            "buttons": {"borderRadius": 14.0},
            "input": {"borderRadius": 12.0,
                      "lightMode": {"defaults": {"backgroundColor": L["card"], "borderColor": L["input_border"]}, "placeholderColor": L["placeholder"]},
                      "darkMode": {"defaults": {"backgroundColor": "0d1129ff", "borderColor": D["input_border"]}, "placeholderColor": D["placeholder"]}},
            "inputLabel": {"lightMode": {"textColor": INK}, "darkMode": {"textColor": "f3f4fbff"}},
            "inputDescription": {"lightMode": {"textColor": MUTED}, "darkMode": {"textColor": "aab0d0ff"}},
            "link": {"lightMode": {"defaults": {"textColor": L["link"]}, "hover": {"textColor": L["link_hover"]}}, "darkMode": {"defaults": {"textColor": D["link"]}, "hover": {"textColor": D["link_hover"]}}},
            "focusState": {"lightMode": {"borderColor": L["focus"]}, "darkMode": {"borderColor": D["focus"]}},
            "divider": {"lightMode": {"borderColor": L["divider"]}, "darkMode": {"borderColor": D["divider"]}},
            "dropDown": {"borderRadius": 12.0},
            "optionControls": {"lightMode": {"selected": {"backgroundColor": L["primary"], "foregroundColor": "ffffffff"}}, "darkMode": {"selected": {"backgroundColor": D["primary"], "foregroundColor": "ffffffff"}}},
        },
        "categories": {
            "global": {"colorSchemeMode": color_scheme, "spacingDensity": "REGULAR", "pageHeader": {"enabled": False}, "pageFooter": {"enabled": False}},
            "form": {"displayGraphics": False, "instructions": {"enabled": False}, "languageSelector": {"enabled": False}, "location": {"horizontal": "CENTER", "vertical": "CENTER"}},
        },
    }
    return _merge(s, over)


def assets() -> List[Dict[str, str]]:
    b64 = lambda name: base64.b64encode(_read(name)).decode("ascii")
    out = []
    for mode, logo, bg in (("LIGHT", "logo-light.svg", "page-bg-light.svg"), ("DARK", "logo-dark.svg", "page-bg-dark.svg")):
        out += [{"category": "FORM_LOGO", "color_mode": mode, "extension": "SVG", "bytes": b64(logo)},
                {"category": "PAGE_BACKGROUND", "color_mode": mode, "extension": "SVG", "bytes": b64(bg)},
                {"category": "FAVICON_SVG", "color_mode": mode, "extension": "SVG", "bytes": b64("favicon.svg")},
                {"category": "FAVICON_ICO", "color_mode": mode, "extension": "ICO", "bytes": b64("favicon.ico")}]
    return out
