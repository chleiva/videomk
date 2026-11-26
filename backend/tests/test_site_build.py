"""The public website build (scripts/site.sh build): English at /, Spanish at /es/, hreflang pairs, a language switcher, no broken internal links, no app script.

Builds into a scratch folder (SITE_OUT / SITE_ASTRO_OUT): no AWS account is touched. Skipped when node or the frontend dependencies are not installed."""
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PAGES = ["privacy", "terms", "support", "delete-account"]

pytestmark = pytest.mark.skipif(not shutil.which("npx") or not os.path.isdir(os.path.join(ROOT, "frontend", "node_modules")), reason="node and frontend dependencies needed")


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    base = tmp_path_factory.mktemp("site")
    env = {**os.environ, "SITE_OUT": str(base / "out"), "SITE_ASTRO_OUT": str(base / "astro")}
    r = subprocess.run(["bash", os.path.join(ROOT, "backend", "scripts", "site.sh"), "build"], cwd=os.path.join(ROOT, "backend"), env=env, capture_output=True, text=True, timeout=240)
    assert r.returncode == 0, r.stderr[-2000:]
    return str(base / "out")


def read(site, rel):
    return open(os.path.join(site, rel), encoding="utf-8").read()


def test_both_languages_of_every_public_page_are_published(site):
    for p in PAGES:
        for prefix in ("", "es/"):
            assert os.path.isfile(os.path.join(site, prefix, p, "index.html")), f"{prefix}{p}"
    assert os.path.isfile(os.path.join(site, "es", "index.html")) and os.path.isfile(os.path.join(site, "index.html"))
    assert 'lang="es"' in read(site, "es/index.html")[:200] and 'lang="en"' in read(site, "index.html")[:200]
    for p in PAGES:
        assert '<html lang="es"' in read(site, f"es/{p}/index.html") and '<html lang="en"' in read(site, f"{p}/index.html")


def test_hreflang_pairs_are_reciprocal(site):
    for p in [""] + [f"{x}/" for x in PAGES]:
        en, es = read(site, f"{p}index.html"), read(site, f"es/{p}index.html")
        en_url, es_url = f"https://videomk.com/{p}", f"https://videomk.com/es/{p}"
        for html in (en, es):   # each language lists both, plus x-default = English
            assert f'hreflang="en" href="{en_url}"' in html and f'hreflang="es" href="{es_url}"' in html and f'hreflang="x-default" href="{en_url}"' in html
        assert f'rel="canonical" href="{en_url}"' in en and f'rel="canonical" href="{es_url}"' in es
    sm = read(site, "sitemap.xml")
    assert sm.count("<url>") == 10 and "https://videomk.com/es/privacy/" in sm and 'hreflang="es"' in sm


def test_spanish_pages_are_spanish_and_have_the_switcher(site):
    for p in PAGES:
        es = read(site, f"es/{p}/index.html")
        assert "Ir al contenido" in es and "Eliminar cuenta" in es and 'data-lang-option="en"' in es and 'href="/%s/"' % p in es   # the switcher points back to the English page
        assert "prevalece la versión en inglés" in es
        en = read(site, f"{p}/index.html")
        assert "Skip to content" in en and 'data-lang-option="es"' in en and 'href="/es/%s/"' % p in en and "the English version prevails" in en
    assert "Privacidad" in read(site, "es/index.html") and 'href="/es/privacy/"' in read(site, "es/index.html")


def test_no_app_script_on_public_pages(site):
    for root, _dirs, files in os.walk(site):
        for f in files:
            if f.endswith(".html"):
                assert "<script" not in open(os.path.join(root, f), encoding="utf-8").read(), os.path.join(root, f)


def _resolves(site, href):
    """The CloudFront rewrite of site_stack.py: a folder path serves its index.html."""
    path = href.split("#")[0].split("?")[0]
    if not path.startswith("/"):
        return True
    rel = path.lstrip("/")
    candidates = [rel] if "." in os.path.basename(rel) else [os.path.join(rel, "index.html")]
    return any(os.path.isfile(os.path.join(site, c)) for c in candidates)


def test_no_broken_internal_links(site):
    seen = 0
    for root, _dirs, files in os.walk(site):
        for f in files:
            if not f.endswith(".html"):
                continue
            html = open(os.path.join(root, f), encoding="utf-8").read()
            for href in re.findall(r'(?:href|src)="([^"]+)"', html):
                if href.startswith(("http", "mailto:", "#", "data:")):
                    continue
                seen += 1
                assert _resolves(site, href), f"{os.path.join(root, f)}: broken {href}"
    assert seen > 50
