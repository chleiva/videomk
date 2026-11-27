#!/usr/bin/env python3
"""Catalog gate for the iPhone app (docs/I18N.md). Exit 1 on any error.

Checks Strings/Localizable.xcstrings (the single catalog, read at runtime through `tr(...)`) and VideoMK/InfoPlist.xcstrings:
  * every key has English and Spanish, state `translated` (no needs_review / new / stale), no empty value
  * Spanish and English have the same placeholders (by position and type), and the same plural forms (one and other)
  * every literal tr("key") in the Swift sources exists in the catalog; unused keys are reported
  * Spanish text identical to the English one is an error unless it is a proper noun, a code or listed in ALLOW_SAME
  * Spanish avoids the words docs/I18N.md forbids (vídeo, móvil, ordenador, Configuración, ...)
  * `--pseudo` writes a longest-string report (Spanish more than 1.8 times longer than English)
"""
import json, re, sys, os, glob
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
CATALOG = os.path.join(ROOT, 'Packages/VideoMKCore/Sources/VideoMKCore/Strings/Localizable.xcstrings')
INFOPLIST = os.path.join(ROOT, 'VideoMK/InfoPlist.xcstrings')
# identical in both languages on purpose: brand and product names, units, symbols, words that are the same in Spanish
ALLOW_SAME = {'%lld%%', 'VideoMK', 'Beta', 'Pro', 'Auto', 'Vertical', 'Video', 'Videos', 'Plan', 'Info', 'Original', 'Vertical.', '%1$@ %2$@, beta'}
FORBIDDEN = [r'vídeo', r'\bmóvil', r'celular', r'ordenador', r'computadora', r'Configuración', r'\busted', r'\bprompt\b', r'renderiz', r'Generaciones', r'Mis medios', r'\bBorrar (cuenta|video|foto)', r'\btenés\b']
ph = re.compile(r'%(?:(\d+)\$)?(@|lld|d|ld)')

def placeholders(s):
    out, n = [], 0
    for m in ph.finditer(s):
        n += 1
        out.append((int(m.group(1)) if m.group(1) else n, 'n' if m.group(2) in ('lld', 'd', 'ld') else '@'))
    return sorted(out)

def values(loc):
    """-> {form: text}; form is '' for a plain string."""
    if 'stringUnit' in loc: return {'': loc['stringUnit']}
    plural = loc.get('variations', {}).get('plural', {})
    return {f: v['stringUnit'] for f, v in plural.items() if 'stringUnit' in v}

def check_catalog(path, errors, warns, report=None):
    cat = json.load(open(path, encoding='utf-8'))
    if cat.get('sourceLanguage') != 'en': errors.append(f'{path}: sourceLanguage must be en')
    for key, entry in cat['strings'].items():
        locs = entry.get('localizations', {})
        for lang in ('en', 'es'):
            if lang not in locs: errors.append(f'{key}: missing {lang}'); continue
            for form, unit in values(locs[lang]).items():
                if unit.get('state') != 'translated': errors.append(f'{key}[{lang}{form and ":" + form}]: state is {unit.get("state")}, must be translated')
                if not unit.get('value', '').strip(): errors.append(f'{key}[{lang}]: empty value')
        if 'en' not in locs or 'es' not in locs: continue
        en, es = values(locs['en']), values(locs['es'])
        if set(en) != set(es): errors.append(f'{key}: plural forms differ en={sorted(en)} es={sorted(es)}')
        if set(en) not in ({''}, {'one', 'other'}): errors.append(f'{key}: plural variations must be exactly one and other')
        for form in en:
            if form not in es: continue
            e, s = en[form]['value'], es[form]['value']
            if placeholders(e) != placeholders(s): errors.append(f'{key}[{form}]: placeholders differ: "{e}" vs "{s}"')
            if e == s and e not in ALLOW_SAME and re.search(r'[A-Za-z]{3}', re.sub(r'\[[^\]]*\]\([^)]*\)|https?://\S+', '', e)):
                errors.append(f'{key}: Spanish is identical to English: "{e}"')
            for bad in FORBIDDEN:
                if re.search(bad, s, re.I if bad[0] != 'C' else 0): errors.append(f'{key}: Spanish uses a word the glossary avoids ({bad}): "{s}"')
            if report is not None and len(e) > 12 and len(s) > 1.8 * len(e): warns.append(f'{key}: Spanish is {len(s) / len(e):.1f}x longer ({len(e)} -> {len(s)})')
            if report is not None and '  ' in s: warns.append(f'{key}: double space')
        if not re.fullmatch(r'[a-z0-9_]+(\.[a-z0-9_]+)+', key) and path == CATALOG: errors.append(f'{key}: key must look like area.name')
    return cat

def used_keys(catalog_keys):
    keys = {}
    srcs = glob.glob(os.path.join(ROOT, 'VideoMK/*.swift')) + glob.glob(os.path.join(ROOT, 'Packages/VideoMKCore/Sources/VideoMKCore/*.swift'))
    for f in srcs:
        for n, line in enumerate(open(f, encoding='utf-8').read().split('\n'), 1):
            for m in re.finditer(r'\btr\(\s*"([^"]+)"', line): keys.setdefault(m.group(1), f'{os.path.basename(f)}:{n}')
            if 'tr(' in line:
                for m in re.finditer(r'"([a-z0-9_]+(?:\.[a-z0-9_]+)+)"', line):
                    if m.group(1) in catalog_keys: keys.setdefault(m.group(1), f'{os.path.basename(f)}:{n}')
    return keys

if __name__ == '__main__':
    errors, warns = [], []
    cat = check_catalog(CATALOG, errors, warns, report=True if '--pseudo' in sys.argv else None)
    check_catalog(INFOPLIST, errors, warns)
    used = used_keys(set(cat['strings']))
    # keys built from a prefix at run time (tr("look." + id)): keep them listed here
    dynamic = ('look.', 'organize_pref.', 'platform.', 'aspect.')
    for k, where in used.items():
        if k not in cat['strings'] and not k.endswith('.') : errors.append(f'{where}: tr("{k}") is not in the catalog')
    unused = [k for k in cat['strings'] if k not in used and not k.startswith(dynamic)]
    print(f'{len(cat["strings"])} keys, {len(used)} used in code, {len(unused)} unused')
    for k in unused: warns.append(f'unused key {k}')
    if warns and ('--pseudo' in sys.argv or '--warnings' in sys.argv): print('\n'.join('warning: ' + w for w in warns))
    if errors:
        print('\n'.join('ERROR: ' + e for e in errors)); sys.exit(1)
    print('check_strings: ok')
