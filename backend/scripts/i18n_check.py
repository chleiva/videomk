#!/usr/bin/env python3
"""Checks the Spanish text against the English text (docs/I18N.md).

  python backend/scripts/i18n_check.py           # human report; exit 1 on errors
  python backend/scripts/i18n_check.py --strict  # warnings are errors too

Catalogs checked: the server (backend/lambdas/common/i18n.py: EN and ES) and the web (frontend/src/i18n/en.json, es.json).
Errors: a key missing in either language, placeholder names that differ ({name}, plural arguments), an empty string, different ICU plural shape.
Warnings: a Spanish text identical to the English one (allowed for a short list of names and numbers), a Spanish text that looks untranslated
(many common English words in it), 'vídeo' with an accent, words the glossary avoids (ordenador, computadora, móvil, celular), or a text more than
1.8 times longer than the English one (Spanish is about 25% longer; a lot more breaks a layout).
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "backend", "lambdas"))

SAME_OK = {"ok", "error", "email", "total", "youtube", "tiktok", "4k", "720p", "1080p", "x", "vertical", "apple", "google", "videomk", "instagram", "linkedin", "english", "español"}   # lower case: names and words that are the same in both languages
AVOID = re.compile(r"\b(ordenador|computadora|móvil|moviles|móviles|celular|vídeo|vídeos)\b", re.I)
EN_WORDS = re.compile(r"\b(the|and|your|you|please|try|again|with|this|that|have|failed|error|video|loading)\b", re.I)
PLACEHOLDER = re.compile(r"\{(\w+)(?:,\s*plural,[^{}]*(?:\{[^{}]*\}[^{}]*)*)?\}")
PLURAL_ARG = re.compile(r"\{(\w+),\s*plural,")
MAX_RATIO = 1.8


def placeholders(text: str) -> set:
    names = set(re.findall(r"\{(\w+)\}", text)) | set(PLURAL_ARG.findall(text))
    return names


def plural_shape(text: str):
    return sorted(re.findall(r"plural,\s*one\s*\{|other\s*\{", text))


def compare(name: str, en: dict, es: dict):
    errors, warnings = [], []
    for k in sorted(set(en) - set(es)):
        errors.append(f"{name}: '{k}' is missing in Spanish")
    for k in sorted(set(es) - set(en)):
        errors.append(f"{name}: '{k}' exists only in Spanish")
    for k in sorted(set(en) & set(es)):
        a, b = en[k], es[k]
        if not isinstance(a, str) or not isinstance(b, str):
            errors.append(f"{name}: '{k}' is not a string")
            continue
        if not b.strip():
            errors.append(f"{name}: '{k}' is empty in Spanish")
            continue
        if placeholders(a) != placeholders(b):
            errors.append(f"{name}: '{k}' placeholders differ: en {sorted(placeholders(a))} es {sorted(placeholders(b))}")
        if plural_shape(a) != plural_shape(b):
            errors.append(f"{name}: '{k}' plural forms differ")
        words = re.sub(r"videomk", "", re.sub(r"\{[^{}]*\}", "", a), flags=re.I)   # placeholders and the brand are not translatable text
        if a.strip() == b.strip() and a.strip().lower() not in SAME_OK and len(re.sub(r"[^A-Za-z]", "", words)) > 3:
            warnings.append(f"{name}: '{k}' is identical to English: {a!r}")
        elif len(EN_WORDS.findall(b)) >= 3:
            warnings.append(f"{name}: '{k}' looks untranslated: {b!r}")
        if AVOID.search(b):
            warnings.append(f"{name}: '{k}' uses a word the glossary avoids: {b!r}")
        if len(a) >= 24 and len(b) > MAX_RATIO * len(a):
            warnings.append(f"{name}: '{k}' is {len(b) / len(a):.1f}x longer than English")
    return errors, warnings


def check_all():
    errors, warnings = [], []
    from common import i18n
    e, w = compare("server", i18n.EN, i18n.ES)
    errors += e
    warnings += w
    web = os.path.join(ROOT, "frontend", "src", "i18n")
    if os.path.isdir(web):
        en = json.load(open(os.path.join(web, "en.json"), encoding="utf-8"))
        es = json.load(open(os.path.join(web, "es.json"), encoding="utf-8"))
        e, w = compare("web", en, es)
        errors += e
        warnings += w
    return errors, warnings


def main() -> int:
    strict = "--strict" in sys.argv
    errors, warnings = check_all()
    for line in errors:
        print("ERROR  ", line)
    for line in warnings:
        print("WARNING", line)
    print(f"{len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors or (strict and warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
