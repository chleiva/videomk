# Code and math elements (`code`, `equation`)

Module: `backend/lambdas/engine/scenes/elements/code_math.py`. Tests: `backend/tests/test_el_code_math.py`. Pillow and numpy only, no new dependency.

## Fonts bundled (engine/assets/fonts)
| File | Used for | Licence (file) |
|---|---|---|
| DejaVuSansMono.ttf, DejaVuSansMono-Bold.ttf (340 KB, 332 KB) | code panel | Bitstream Vera / DejaVu free licence (`DejaVu-LICENSE.txt`) |
| STIXGeneral.ttf, STIXGeneralItalic.ttf, STIXGeneralBol.ttf (448, 175, 237 KB) | equations (Greek, operators, italic variables) | SIL OFL 1.1 (`STIX-LICENSE.txt`) |

Copied from the matplotlib distribution (the STIX files there are the OTF-to-TTF conversion described in `STIX-LICENSE.txt`). STIX italic has no operator glyphs, so operators and big symbols (sum, product, integral) use the upright face. Inter (already bundled) is still used for titles and notes.

## `code`
For the director: real, correct, short code only. Never pseudo-random or unverified code, never invented terminal output; keep it under 18 lines (the sanitizer also caps 70 columns and 900 characters, and tabs become 4 spaces). Modes: `code`, `terminal` (`$ ` lines are typed, other lines are output), `diff` (`+`, `-` or a space first). The syntax colouring is a hand-written regex tokenizer (python, bash, sql, json, html, and a C-like family for javascript, typescript, java, c, cpp, csharp, go, rust, css); the panel is dark on all three themes, only the highlight band and badge use the theme accent. Over 11 lines the title moves into the window bar to leave room.

## `equation`
Linear notation, no LaTeX. Supported: `+ - * = < > <= >= != ~= ->`, `a/b` (numerator and denominator are the glued run on each side: `n(n+1)/2`, `1/2 m v^2` is one half times m v squared), `^` and `_` with `{}` or `()` groups, `sqrt(...)`, `sum`, `prod`, `int` with limits (`sum_{i=1}^{n}`), Greek by name (`pi`, `theta`, `Delta`) or as characters, functions `sin cos tan log ln exp lim max min ...`, `inf`, `pm`, `times`, `cdot`, parentheses and brackets (drawn to fit their content). A formula that does not parse (unbalanced brackets, `x^`, unknown characters, backslashes, too wide) raises `ValueError`, which makes the whole scene a title card.
