#!/usr/bin/env python3
"""Fails when the brand name is written any way but "VideoMK" where a person reads it (docs/BRAND.md).

Scans the Swift sources, both string catalogs, Info.plist, project.yml and the README. Lowercase "videomk" is allowed only as an
identifier: videomk.com, hello@videomk.com, com.videomk.app, string keys (videos.videomk), task and file names (videomk.ready), and a
whole quoted token "videomk" that is not a catalog value.
"""
import glob, os, re, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
WRONG = re.compile(r'(?<![\w@./:\-])videomk(?![\w]|[.\-_/:]\w)', re.I)
TOKEN = re.compile(r'''(["'])videomk\1''')
VISIBLE = re.compile(r'''("value"\s*:\s*|accessibilityLabel\(|Text\(|CFBundleDisplayName:\s*|CFBundleName:\s*)["']?videomk["']?\s*\)?$''', re.I)


def mistakes(text):
    bad = []
    for n, line in enumerate(text.split('\n'), 1):
        st = line.strip()
        if VISIBLE.search(st.replace('VideoMK', '')) and 'VideoMK' not in st:
            bad.append(n); continue
        if WRONG.search(TOKEN.sub('', line.replace('VideoMK', ''))):
            bad.append(n)
    return bad


def files():
    pats = ['VideoMK/*.swift', 'VideoMK/*.xcstrings', 'VideoMK/Info.plist', 'VideoMKUITests/*.swift', 'project.yml', 'README.md',
            'Packages/VideoMKCore/Sources/**/*.swift', 'Packages/VideoMKCore/Sources/**/*.xcstrings', 'Packages/VideoMKCore/Tests/**/*.swift']
    for p in pats:
        yield from sorted(glob.glob(os.path.join(ROOT, p), recursive=True))


if __name__ == '__main__':
    assert mistakes('Rate videomk') == [1] and mistakes('"value" : "videomk"') == [1] and mistakes('Enjoying Videomk?') == [1]
    assert mistakes('VideoMK at videomk.com, com.videomk.app, tr("videos.videomk"), withName: "videomk.ready"') == []
    bad = [f'{os.path.relpath(f, ROOT)}:{n}' for f in files() for n in mistakes(open(f, encoding='utf-8').read())]
    if bad:
        print('The brand name is written "VideoMK" (docs/BRAND.md). Fix:')
        print('\n'.join(bad)); sys.exit(1)
    print('check_brand: ok')
