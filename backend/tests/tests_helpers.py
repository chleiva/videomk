PLAN_WITH_IMAGE = {
    "legit": True, "title": "How Rainbows Form", "description": "Why rainbows appear after rain.", "mood": "calm", "theme": "midnight",
    "beats": [
        {"chapter": "Intro", "narration": "Ever wondered why a rainbow always shows up opposite the sun in the sky?", "scene": {"type": "title", "props": {"title": "How Rainbows Form", "subtitle": "Light, water and geometry"}}},
        {"chapter": "The path of light", "narration": "Sunlight enters a raindrop, bends, reflects off the back, and bends again as it leaves.", "scene": {"type": "diagram", "props": {"nodes": [{"id": "s", "label": "Sunlight"}, {"id": "d", "label": "Raindrop"}, {"id": "e", "label": "Your eye"}], "edges": [["s", "d"], ["d", "e", "bent light"]]}}},
        {"chapter": "Colors", "narration": "Each color bends by a slightly different amount, which spreads white light into a spectrum.", "scene": {"type": "chart", "props": {"kind": "bar", "labels": ["Red", "Green", "Violet"], "values": [42, 41, 40], "unit": "°", "title": "Bend angle"}}},
        {"narration": "That is why you see a bow of colors high in the sky after a summer storm passes.", "scene": {"type": "image", "props": {"image_query": "rainbow over field", "alt": "A rainbow"}}},
    ],
}
