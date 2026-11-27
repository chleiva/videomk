#!/usr/bin/env python3
"""Link check over a built site folder (backend/build/site or backend/build/app): every internal href/src must exist in the folder (a folder link needs its index.html);
links to the other site (videomk.com <-> app.videomk.com) must point at a page that exists in THAT site's build when it is given.
  python3 scripts/check_built_links.py build/site [--app build/app] [--site build/site]
Exit 1 and a list when anything is broken."""
import os
import re
import sys
from urllib.parse import urlsplit

SITE_HOSTS = {"videomk.com", "www.videomk.com"}
APP_HOST = "app.videomk.com"
ATTR = re.compile(r'(?:href|src|poster)=["\']([^"\'#][^"\']*)["\']', re.I)
SKIP = ("mailto:", "tel:", "data:", "javascript:", "blob:")


REDIRECTED_TO_SITE = re.compile(r"^(/es/?|(/es)?/(privacy|terms|support)/?)$")   # the app's CloudFront function sends these 301 to videomk.com


def exists(root, path):
    path = path.split("?")[0]
    p = os.path.join(root, path.lstrip("/"))
    if path.endswith("/") or not os.path.splitext(path)[1]:
        return os.path.isfile(os.path.join(p, "index.html")) or os.path.isfile(p)
    return os.path.isfile(p)


def check(root, own_host_roots, is_app=False):
    bad = []
    for dp, _, fs in os.walk(root):
        for f in fs:
            if not f.endswith(".html"):
                continue
            src = os.path.join(dp, f)
            page = "/" + os.path.relpath(src, root).replace("index.html", "")
            html = open(src, encoding="utf-8").read()
            for m in ATTR.finditer(html):
                u = m.group(1).strip()
                if u.startswith(SKIP) or u.startswith("//"):
                    continue
                sp = urlsplit(u)
                if sp.scheme in ("http", "https"):
                    target = own_host_roots.get(sp.netloc)
                    if target is None:
                        continue   # external
                    if not exists(target, sp.path or "/"):
                        bad.append((page, u))
                    continue
                path = sp.path if sp.path.startswith("/") else os.path.normpath(os.path.join(page, sp.path))
                if sp.path == "":
                    continue
                if is_app and REDIRECTED_TO_SITE.match(path):
                    continue
                if not exists(root, path):
                    bad.append((page, u))
    return bad


def main():
    args = sys.argv[1:]
    if not args:
        raise SystemExit(__doc__)
    root = args[0]
    site = args[args.index("--site") + 1] if "--site" in args else None
    app = args[args.index("--app") + 1] if "--app" in args else None
    hosts = {}
    if site:
        hosts.update({h: site for h in SITE_HOSTS})
    if app:
        hosts[APP_HOST] = app
    bad = check(root, hosts, is_app=bool(app) and os.path.abspath(root) == os.path.abspath(app))
    for page, u in bad:
        print(f"BROKEN {page} -> {u}")
    print(f"{len(bad)} broken link(s) in {root}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
