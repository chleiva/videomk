#!/usr/bin/env python3
"""Fails when user-visible text is written as a string literal instead of tr("key") (docs/I18N.md).

Flags SwiftUI views and modifiers that take a literal with letters in it: Text("..."), Button("..."), Label("..."), .navigationTitle("..."),
.accessibilityLabel("...") and so on. Allowed: Text(verbatim:), anything inside #if DEBUG ... #endif, and a line that ends with `// i18n-ok`.
"""
import re, sys, glob, os
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
VIEWS = r'(?:Text|Button|Label|Section|Toggle|TextField|SecureField|Picker|ContentUnavailableView|LabeledContent|Link|DisclosureGroup|Menu|ProgressView|NavigationLink|ShareLink|Stepper)'
MODS = r'\.(?:navigationTitle|accessibilityLabel|accessibilityHint|accessibilityValue|alert|confirmationDialog|help|accessibilityAction\(named:)'
pat = re.compile(r'(?<![A-Za-z.])(?:%s|%s)\(\s*"((?:[^"\\]|\\.)*)"|prompt:\s*"((?:[^"\\]|\\.)*)"' % (VIEWS, MODS))
bad = []
for f in sorted(glob.glob(os.path.join(ROOT, 'VideoMK', '*.swift'))):
    dbg = 0
    for n, line in enumerate(open(f, encoding='utf-8').read().split('\n'), 1):
        st = line.strip()
        if st.startswith('#if DEBUG'): dbg += 1
        elif st.startswith('#endif') and dbg: dbg -= 1
        if dbg or st.startswith('//') or line.rstrip().endswith('// i18n-ok'): continue
        for m in pat.finditer(line):
            lit = m.group(1) if m.group(1) is not None else m.group(2)
            if re.search(r'[A-Za-z]{3}', re.sub(r'\\\([^)]*\)', '', lit)) and not re.fullmatch(r'[a-z0-9_.]+', lit):
                bad.append(f'{os.path.relpath(f, ROOT)}:{n}: {st[:140]}')
if bad:
    print('Hard-coded user-visible text (use tr("key") and add the key to Strings/Localizable.xcstrings):')
    print('\n'.join(bad)); sys.exit(1)
print('check_literals: ok')
