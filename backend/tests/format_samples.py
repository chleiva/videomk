"""Deterministic sample scenes (props as the director would send them) for the format tests, previews and the 16:9 golden check."""
import copy
from typing import Any, Dict, List, Tuple

import numpy as np
from PIL import Image


def synth_image(key: str) -> Image.Image:
    """A deterministic 'photo': a diagonal gradient with a bright blob left of centre (so crops are visible) and some texture, landscape or portrait by key."""
    w, h = (1600, 900) if "port" not in key else (900, 1400)
    rng = np.random.RandomState(sum(map(ord, key)) % 997)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    base = np.stack([60 + 150 * xx / w, 90 + 100 * yy / h, 200 - 120 * xx / w], -1)
    blob = np.exp(-(((xx - w * 0.33) / (w * 0.12)) ** 2 + ((yy - h * 0.38) / (h * 0.18)) ** 2))[..., None] * np.array([120, 90, 60], np.float32)
    noise = rng.randn(h // 8 + 1, w // 8 + 1, 1).astype(np.float32) * 14
    noise = np.kron(noise, np.ones((8, 8, 1), np.float32))[:h, :w]
    return Image.fromarray(np.clip(base + blob + noise, 0, 255).astype(np.uint8), "RGB")


class FakeClip:
    fps = 30

    def __init__(self, portrait: bool = False):
        self.img = synth_image("clip" + ("port" if portrait else ""))

    def frame(self, i: int) -> Image.Image:
        return self.img


def image_loader(key: str):
    return synth_image(key)


def clip_loader(key: str):
    return FakeClip("port" in key)


_NODES = lambda labels: [{"id": chr(97 + i), "label": l} for i, l in enumerate(labels)]
_CHAIN = lambda n: [[chr(97 + i), chr(98 + i)] for i in range(n - 1)]

# name -> (scene type, props)
SAMPLES: Dict[str, Tuple[str, Dict[str, Any]]] = {
    "title": ("title", {"title": "Why the ocean is salty and the rivers are not", "subtitle": "A short tour of the water cycle"}),
    "title_short": ("title", {"title": "Hello"}),
    "bullets_rail": ("bullets", {"heading": "What makes a good habit", "style": "rail", "items": ["Start tiny so it feels easy", "Attach it to something you already do", "Make the cue obvious", "Celebrate right away"]}),
    "bullets_spotlight": ("bullets", {"heading": "Three rules", "style": "spotlight", "accent": "coral", "items": ["Keep it short", "Say one thing per slide", "Show, do not tell"]}),
    "bullets_icons": ("bullets", {"heading": "Why it works", "style": "icons", "accent": "teal", "items": ["Speed: results in days", "Safety: tested widely", "Cost: free to start", "Support: help any time", "Scale: grows with you"]}),
    "bullets_cards": ("bullets", {"heading": "Our plans", "style": "cards", "accent": "violet", "emphasis": 1, "items": ["Free forever for one person", "Team plan with shared folders", "Business with single sign on and audit logs", "Enterprise with a dedicated manager"]}),
    "bullets_keywords": ("bullets", {"heading": "The pillars", "style": "keywords", "accent": "amber", "items": ["Clarity: say what you mean", "Brevity: cut every extra word", "Rhythm: vary sentence length"]}),
    "diagram_cards": ("diagram", {"title": "How a request flows", "style": "cards", "nodes": _NODES(["Browser", "Load balancer", "App server", "Database"]), "edges": _CHAIN(4)}),
    "diagram_pills": ("diagram", {"title": "Plan to ship", "style": "pills", "accent": "emerald", "nodes": _NODES(["Plan", "Build", "Test"]), "edges": [["a", "b", "weekly"], ["b", "c"]]}),
    "diagram_ladder": ("diagram", {"title": "Maturity", "style": "ladder", "nodes": _NODES(["Crawl", "Walk", "Run", "Fly"]), "edges": _CHAIN(4)}),
    "diagram_stack": ("diagram", {"title": "The layers", "style": "stack", "accent": "rose", "nodes": _NODES(["Apps", "Services", "Runtime", "Hardware"]), "edges": _CHAIN(4)}),
    "diagram_snake": ("diagram", {"title": "Eight steps", "style": "cards", "nodes": _NODES(["Idea", "Draft", "Review", "Revise", "Approve", "Build", "Launch", "Learn"]), "edges": _CHAIN(8)}),
    "diagram_branch": ("diagram", {"title": "Decision", "nodes": _NODES(["Question", "Yes path", "No path", "Outcome"]), "edges": [["a", "b", "yes"], ["a", "c", "no"], ["b", "d"], ["c", "d"]]}),
    "stat_plain": ("stat", {"value": "$1,250", "label": "Saved by the average customer in the first year of using the plan"}),
    "stat_pct": ("stat", {"value": "73%", "label": "of people finish what they start when it is small"}),
    "quote": ("quote", {"text": "The best way to predict the future is to invent it, one small careful step at a time.", "attribution": "Alan Kay"}),
    "quote_short": ("quote", {"text": "Less, but better."}),
    "chart_bar": ("chart", {"title": "Revenue by quarter", "kind": "bar", "unit": "$", "labels": ["Q1", "Q2", "Q3", "Q4"], "values": [120, 180, 150, 240], "highlight": 3}),
    "chart_bar_many": ("chart", {"title": "Users by country", "kind": "bar", "unit": "M", "labels": ["Brazil", "India", "Germany", "Japan", "Spain", "Chile", "Peru"], "values": [42, 88, 31, 27, 19, 11, 8]}),
    "chart_line": ("chart", {"title": "Growth", "kind": "line", "unit": "%", "labels": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug"], "values": [2, 4, 3, 7, 9, 8, 12, 15]}),
    "timeline": ("timeline", {"title": "A brief history", "events": [{"date": "1969", "label": "First message sent on ARPANET"}, {"date": "1991", "label": "The web goes public"}, {"date": "2004", "label": "Social networks arrive"}, {"date": "2007", "label": "The smartphone era begins"}, {"date": "2022", "label": "Generative AI reaches everyone"}]}),
    "timeline_long": ("timeline", {"title": "Seven milestones", "events": [{"date": f"20{10 + i}", "label": f"Milestone number {i + 1} happened here"} for i in range(7)]}),
    "image": ("image", {"asset": "photo#1", "ken_burns": "in", "credit": "Photo: Someone", "word": "Wow"}),
    "image_user_portrait": ("image", {"asset": "photoport#1", "photo": True, "ken_burns": "in"}),
    "gallery": ("gallery", {"assets": ["photo#1", "photo#2", "photoport#3"], "credits": ["A", "B", "C"]}),
    "clip": ("clip", {"asset": "clip#1", "credit": "Pexels / Someone"}),
}

LIGHT = ("midnight", "paper")


def sample(name: str) -> Tuple[str, Dict[str, Any]]:
    t, p = SAMPLES[name]
    return t, copy.deepcopy(p)


def sample_cues(stype: str, props: Dict[str, Any], dur: float) -> Dict[str, Any]:
    return props
