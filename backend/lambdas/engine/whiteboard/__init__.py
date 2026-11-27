"""The whiteboard look (docs/WHITEBOARD.md): boards of marker drawings and handwriting that appear along a pen path, in time with the narration.

Runtime only: Pillow, NumPy and resvg (the engine layer). Everything that needs SciPy or a tracer (cutting sheets, thinning, vectorising, the letters' centre
lines) is done offline by backend/scripts/whiteboard_proto and arrives as data: drawing packages in the catalog bucket (`w/<id>.json`) and the glyph tables
in engine/assets/whiteboard.
"""
