#!/usr/bin/env python3
"""Mockups for docs/DESIGN_BAR_2026.md. Writes html/ next to this file; shoot.sh renders them with headless Chrome.

  python3 docs/design_bar/src/gen.py && bash docs/design_bar/src/shoot.sh
Static HTML + inline SVG icons, no dependencies. Images come from ../img (our own outputs: catalog photos, scene thumbnails, video frames).
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "html")
os.makedirs(OUT, exist_ok=True)
IMG = "../../img/"
MARK = "../../../brand/final/favicon.svg"

P = {
    "play": '<path d="M8 5.2v13.6L19.5 12z"/>', "pause": '<path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z"/>',
    "spark": '<path d="M12 2.5c.7 5.2 3 7.6 8.5 8.5-5.5.9-7.8 3.300-8.500 8.500-.7-5.200-3-7.600-8.500-8.500 5.500-.9 7.800-3.300 8.500-8.500z"/>',
    "bolt": '<path d="M13.200 2.500 5 13.500h5.600l-1 8 8.400-11.300h-5.700z"/>',
    "share": '<path d="M12 3.500v11M8 7.500l4-4 4 4M7 11H6a2 2 0 0 0-2 2v5.500a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V13a2 2 0 0 0-2-2h-1"/>',
    "save": '<path d="M12 4v11M8 11l4 4 4-4M5 19.500h14"/>',
    "edit": '<path d="M4.500 19.500h3.800L19 8.800 15.200 5 4.500 15.700zM13 7.200 16.800 11"/>',
    "info": '<circle cx="12" cy="12" r="8.500"/><path d="M12 11v5.500M12 7.700v.2"/>',
    "more": '<circle cx="5.500" cy="12" r="1.300"/><circle cx="12" cy="12" r="1.300"/><circle cx="18.500" cy="12" r="1.300"/>',
    "photo": '<rect x="3" y="5" width="18" height="14" rx="3.500"/><circle cx="8.500" cy="10" r="1.600"/><path d="m4 17 5-4.500 3.500 3 3-2.500 4.500 4"/>',
    "photoplus": '<path d="M20 12.500V17a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3V9a3 3 0 0 1 3-3h7"/><circle cx="8.500" cy="11" r="1.500"/><path d="m4 18 4.500-4 3.500 3 2.500-2 3.500 3M18 3v6M15 6h6"/>',
    "mic": '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.500 11.500a6.500 6.500 0 0 0 13 0M12 18v3"/>',
    "sliders": '<path d="M4 7.500h9M18 7.500h2M4 16.500h2M11 16.500h9"/><circle cx="15.500" cy="7.500" r="2.300"/><circle cx="8.500" cy="16.500" r="2.300"/>',
    "search": '<circle cx="11" cy="11" r="6.500"/><path d="m16 16 4.500 4.500"/>',
    "check": '<path d="m5 12.500 4.500 4.500L19 7.500"/>', "x": '<path d="M6 6l12 12M18 6 6 18"/>',
    "down": '<path d="m6 9.500 6 6 6-6"/>', "back": '<path d="M15 5l-7 7 7 7"/>',
    "film": '<rect x="3" y="5" width="18" height="14" rx="3.500"/><path d="M10 9.200v5.600l4.800-2.800z" fill="currentColor"/>',
    "images": '<rect x="6.500" y="3.500" width="14" height="12" rx="3"/><path d="M3.500 8.500v9a3 3 0 0 0 3 3h10"/><path d="m8 13 3.500-3 3 2.500 2-1.500 4 3.500"/>',
    "gear": '<circle cx="12" cy="12" r="3"/><path d="M12 3v2.500M12 18.500V21M3 12h2.500M18.500 12H21M5.600 5.600l1.800 1.800M16.600 16.600l1.800 1.800M5.600 18.400l1.800-1.800M16.600 7.400l1.800-1.800"/>',
    "folder": '<path d="M3.500 8a2.500 2.500 0 0 1 2.500-2.500h3.500l2 2.500H18a2.500 2.500 0 0 1 2.500 2.500V17a2.500 2.500 0 0 1-2.500 2.500H6A2.500 2.500 0 0 1 3.500 17zM12 11.500v4.500M9.700 13.700h4.600"/>',
    "trash": '<path d="M4.500 7h15M9.500 7V5a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1v2M6.500 7l1 12a1.500 1.500 0 0 0 1.500 1.400h6a1.500 1.500 0 0 0 1.500-1.400l1-12M10 11v5.500M14 11v5.500"/>',
    "replay": '<path d="M4.500 12a7.500 7.500 0 1 0 2.300-5.400M4.500 4.500v4.300h4.300"/>',
    "bell": '<path d="M6 16.500V11a6 6 0 0 1 12 0v5.500l1.500 2h-15zM10 20.500a2.200 2.200 0 0 0 4 0"/>',
    "vol": '<path d="M4 10v4h3.500L12 18V6L7.500 10zM15.500 9a4 4 0 0 1 0 6M18 6.500a7.500 7.500 0 0 1 0 11"/>',
    "full": '<path d="M4.500 9.500v-5h5M19.500 9.500v-5h-5M4.500 14.500v5h5M19.500 14.500v5h-5"/>',
    "pip": '<rect x="3" y="5" width="18" height="14" rx="3"/><rect x="12" y="11.500" width="6.500" height="5" rx="1.200" fill="currentColor"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "newvideo": '<path d="M6 6.800v12.400a.8.800 0 0 0 1.200.7l10.400-6.200a.8.800 0 0 0 0-1.400L7.200 6.100a.8.800 0 0 0-1.200.7z" fill="currentColor" stroke="none"/><path d="M19 1.500c.3 2.300 1.300 3.300 3.600 3.600-2.300.3-3.300 1.300-3.600 3.600-.3-2.300-1.300-3.300-3.600-3.600 2.300-.3 3.300-1.300 3.600-3.600z" fill="currentColor" stroke="none"/>',
    "upload": '<path d="M12 15.500V4.500M8 8.500l4-4 4 4M5 15.500v2a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-2"/>',
    "apple": '<path d="M16.400 12.700c0-2.100 1.700-3.100 1.800-3.200-1-1.400-2.500-1.600-3-1.700-1.300-.1-2.500.8-3.200.8-.7 0-1.700-.7-2.800-.7-1.400 0-2.800.8-3.500 2.100-1.500 2.600-.4 6.400 1.100 8.500.7 1 1.600 2.200 2.700 2.100 1.100 0 1.500-.7 2.800-.7 1.300 0 1.700.7 2.800.7 1.200 0 1.900-1 2.600-2.100.8-1.200 1.200-2.300 1.200-2.400-.1 0-2.500-1-2.500-3.400zM14.300 6.400c.6-.7 1-1.700.9-2.700-.9 0-1.900.6-2.500 1.300-.6.600-1 1.600-.9 2.600 1 .1 1.900-.5 2.500-1.200z"/>',
    "google": '<path d="M21 12.200c0-.6-.1-1.200-.2-1.800H12v3.500h5.100c-.2 1.200-.9 2.200-1.900 2.800v2.300h3c1.800-1.600 2.800-4 2.800-6.800z" fill="#4285F4"/><path d="M12 21.300c2.500 0 4.700-.8 6.200-2.300l-3-2.300c-.8.600-1.900.9-3.200.9-2.400 0-4.500-1.600-5.200-3.900H3.700V16c1.500 3.100 4.700 5.300 8.300 5.300z" fill="#34A853"/><path d="M6.800 13.700c-.2-.6-.3-1.100-.3-1.700s.1-1.200.3-1.700V8H3.700C3 9.200 2.700 10.600 2.700 12s.3 2.800 1 4z" fill="#FBBC05"/><path d="M12 6.400c1.400 0 2.600.5 3.600 1.400l2.700-2.700C16.700 3.600 14.500 2.700 12 2.700 8.400 2.700 5.200 4.900 3.700 8l3.100 2.300C7.500 8 9.600 6.400 12 6.400z" fill="#EA4335"/>',
}
FILL = {"play", "pause", "spark", "bolt", "apple", "google"}


def ic(n, style="", cls=""):
    p = P[n]
    f = " f" if n in FILL else ""
    return f'<svg class="i{f} {cls}" viewBox="0 0 24 24" style="{style}">{p}</svg>'


def page(body, w=None, extra=""):
    return f'<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="../base.css"><style>html,body{{background:transparent}}{extra}</style><body>{body}</body>'


SB = '<div class="island"></div><div class="sb"><span>9:41</span><span class="r"><i class="sig"></i><i class="bat"></i></span></div>'


def phone(theme, inner, label):
    return f'<div><div class="lab">{label}</div><div class="phone" data-theme="{theme}">{SB}{inner}<div class="homebar"></div></div></div>'


def board(items, dark=False):
    return f'<div class="board{" dk" if dark else ""}">' + "".join(items) + "</div>"


def tabbar(on="videos"):
    return (f'<div class="tabbar"><div class="tab {"on" if on == "videos" else ""}">{ic("film")}Videos</div>'
            f'<div class="tab {"on" if on == "media" else ""}">{ic("images")}Media</div></div>'
            f'<div class="fab grad" aria-label="New video">{ic("newvideo")}</div>')


# ------------------------------------------------------------------ phone screens
def s_signin(theme):
    fade = "#F7F7FA" if theme == "light" else "#06070D"
    apple = "inv"
    return f'''
<div style="position:absolute;inset:0 0 auto 0;height:500px"><img class="cover" src="{IMG}clip_01.jpg" style="object-position:40% 50%">
 <div style="position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.25) 0%,transparent 22%,transparent 46%,{fade} 96%)"></div>
 <div style="position:absolute;left:20px;right:20px;top:86px;display:flex;justify-content:center">
  <div style="display:inline-flex;align-items:center;gap:8px;height:40px;padding:0 16px;border-radius:20px;background:rgba(20,22,40,.55);backdrop-filter:blur(18px);color:#fff;font:500 15px/1 var(--font)">{ic("spark","width:15px;height:15px;color:#22D3EE")}“How a forest breathes”</div></div>
</div>
<div style="position:absolute;left:0;right:0;bottom:0;padding:0 24px 44px">
 <img src="{MARK}" style="width:56px;height:56px;border-radius:14px;box-shadow:0 10px 30px rgba(60,50,200,.4)">
 <div class="lt" style="margin-top:20px">Describe it.<br>We’ll make the video.</div>
 <div style="height:28px"></div>
 <div class="btn {apple}">{ic("apple","width:21px;height:21px;margin-top:-3px")}Continue with Apple</div>
 <div style="height:12px"></div>
 <div class="btn o">{ic("google","width:20px;height:20px")}Continue with Google</div>
 <div style="height:18px"></div>
 <div class="hl" style="text-align:center;color:var(--primary)">Use email</div>
 <div class="cp" style="text-align:center;margin-top:22px">By continuing you agree to the Terms and Privacy Policy.</div>
</div>'''


def making_card():
    tiles = "".join(f'<div style="width:46px;height:46px;border-radius:12px;overflow:hidden;box-shadow:inset 0 0 0 1px rgba(255,255,255,.2)"><img class="cover" src="{IMG}{n}.jpg"></div>' for n in ("p01", "p03", "p15", "p16"))
    tiles += '<div style="width:46px;height:46px;border-radius:12px;background:rgba(255,255,255,.22);position:relative"><div class="ring"></div></div>'
    tiles += '<div style="width:46px;height:46px;border-radius:12px;box-shadow:inset 0 0 0 1.500px rgba(255,255,255,.22)"></div>' * 2
    return f'''<div class="brandgrad" style="border-radius:28px;padding:18px 18px 18px;position:relative;overflow:hidden;box-shadow:0 14px 36px rgba(60,50,180,.35)">
 <div style="display:flex;justify-content:space-between;align-items:center"><div class="hl" style="color:#fff">How honey is made</div><div style="font:500 13px/1 var(--font);color:rgba(255,255,255,.8)">2 min left</div></div>
 <div style="display:flex;gap:6px;margin-top:14px">{tiles}</div>
 <div style="display:flex;align-items:center;gap:6px;margin-top:14px;font:500 13px/1 var(--font);color:rgba(255,255,255,.86)">{ic("spark","width:13px;height:13px;color:#22D3EE")}Scene 5 of 9 · finding the right footage</div>
</div>'''


def s_home(theme):
    return f'''
<div class="pad" style="display:flex;justify-content:space-between;align-items:center;margin-top:10px">
 <div class="lt">Videos</div>
 <div style="display:flex;gap:10px;align-items:center"><div class="pill" style="height:36px;padding:0 12px">{ic("bolt","width:15px;height:15px;color:var(--primary)")}12</div>
 <div style="width:36px;height:36px;border-radius:18px;background:var(--surface3);font:600 15px/36px var(--font);text-align:center;color:var(--text2)">C</div></div>
</div>
<div class="pad" style="margin-top:18px">{making_card()}</div>
<div class="pad" style="margin-top:22px">
 <div class="poster" style="height:197px;border-radius:24px"><img class="cover" src="{IMG}clip_01.jpg"><div class="dur">1:31</div></div>
 <div class="hl" style="margin-top:12px">How a forest breathes</div><div class="fn">Today</div>
</div>
<div class="pad" style="margin-top:20px;display:flex;gap:12px">
 <div style="flex:1"><div class="poster" style="height:172px;border-radius:22px"><img class="cover" src="{IMG}s_bees.jpg"><div class="dur">2:04</div></div><div class="hl" style="margin-top:10px">How bees make honey</div></div>
 <div style="width:118px"><div class="poster" style="height:172px;border-radius:22px"><img class="cover" src="{IMG}s_focus.jpg"><div class="dur">0:30</div><div class="asp">9:16</div></div><div class="hl" style="margin-top:10px">3 focus tips</div></div>
</div>
<div style="position:absolute;left:0;right:0;bottom:0;height:130px;background:linear-gradient(180deg,transparent,var(--bg) 55%)"></div>
{tabbar("videos")}'''


def composer_bottom(theme, cost="1", left="12 credits left"):
    return f'''<div style="position:absolute;left:0;right:0;bottom:0;padding:0 20px 40px">
 <div style="display:flex;gap:8px;align-items:center">
  <div class="ib s">{ic("photoplus")}</div><div class="ib s">{ic("mic")}</div><div style="flex:1"></div><div class="ib s">{ic("sliders")}</div>
 </div>
 <div style="display:flex;gap:8px;margin-top:14px">
  <div class="pill" style="padding:0 12px">YouTube{ic("down")}</div><div class="pill" style="padding:0 12px">1 min{ic("down")}</div><div class="pill" style="padding:0 12px">Auto look{ic("down")}</div>
 </div>
 <div class="btn p" style="margin-top:18px;justify-content:space-between;padding:0 22px 0 26px"><span>Create</span><span style="display:inline-flex;align-items:center;gap:4px;font-weight:600;opacity:.95">{ic("bolt","width:16px;height:16px")}{cost}</span></div>
 <div class="cp" style="text-align:center;margin-top:12px">{left}</div>
</div>'''


def s_create_empty(theme):
    chips = "".join(f'<div class="chip">{ic("spark")}{t}</div>' for t in ("How bees make honey", "3 focus tips", "Why forests matter"))
    return f'''
<div class="pad" style="display:flex;justify-content:space-between;margin-top:8px"><div class="ib s">{ic("x")}</div></div>
<div class="pad" style="margin-top:26px">
 <div style="font:600 30px/38px var(--font);letter-spacing:-.6px;color:var(--text3)"><span style="display:inline-block;width:2.500px;height:32px;background:var(--primary);vertical-align:-5px;margin-right:3px;border-radius:2px"></span>A video about…</div>
 <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:28px">{chips}</div>
</div>
{composer_bottom(theme)}'''


def s_create_submit(theme):
    thumbs = "".join(f'<div style="width:62px;height:62px;border-radius:16px;overflow:hidden;flex:none"><img class="cover" src="{IMG}{n}.jpg"></div>' for n in ("p08", "p09", "p10", "p05", "p17", "p13"))
    return f'''
<div class="aura"></div>
<div class="dim">
<div class="pad" style="display:flex;justify-content:space-between;margin-top:8px"><div class="ib s">{ic("x")}</div></div>
<div class="pad" style="margin-top:26px">
 <div style="font:600 26px/34px var(--font);letter-spacing:-.5px">How a forest breathes, and why forests matter. Calm and warm.</div>
 <div style="display:flex;gap:8px;margin-top:24px;overflow:hidden">{thumbs}</div>
 <div class="fn" style="margin-top:10px">45 photos</div>
 <div style="display:flex;gap:8px;margin-top:22px"><div class="pill">YouTube</div><div class="pill">2 min</div><div class="pill">Auto look</div></div>
</div></div>
<div style="position:absolute;left:0;right:0;bottom:0;padding:0 20px 40px">
 <div style="position:relative;height:64px;border-radius:32px;background:var(--surface);box-shadow:var(--shadow2);display:flex;align-items:center;gap:12px;padding:0 22px">
  <div class="ring"></div>
  {ic("spark","width:20px;height:20px;color:#7A4BE6")}
  <div style="flex:1"><div class="hl">Checking your request</div><div class="cp" style="margin-top:1px">A few seconds</div></div>
  <div style="width:22px;height:22px;border-radius:11px;border:2.500px solid var(--surface3);border-top-color:var(--primary)"></div>
 </div>
 <div class="hl" style="text-align:center;color:var(--text2);margin-top:18px;font-weight:500">Cancel</div>
</div>'''


def s_making(theme):
    done = "".join(f'<div style="width:38px;height:38px;border-radius:10px;overflow:hidden;flex:none"><img class="cover" src="{IMG}{n}.jpg"></div>' for n in ("clip_01", "clip_03", "clip_08", "clip_10"))
    cur = '<div style="width:38px;height:38px;border-radius:10px;background:var(--surface3);position:relative;flex:none"><div class="ring"></div></div>'
    todo = '<div style="width:38px;height:38px;border-radius:10px;box-shadow:inset 0 0 0 1.500px var(--line);flex:none"></div>' * 4
    return f'''
<div class="pad" style="display:flex;justify-content:space-between;align-items:center;margin-top:8px"><div class="ib s">{ic("back")}</div><div class="ib s">{ic("more")}</div></div>
<div class="pad" style="margin-top:22px">
 <div style="position:relative;border-radius:26px;height:197px;box-shadow:var(--shadow2)"><div class="ring" style="inset:-3px;padding:3px"></div>
  <div style="position:absolute;inset:0;border-radius:26px;overflow:hidden"><img class="cover" src="{IMG}clip_05.jpg"></div></div>
 <div class="t2" style="margin-top:26px">How a forest breathes</div>
 <div style="display:flex;align-items:center;gap:7px;margin-top:8px;font:500 15px/20px var(--font);color:var(--text2)">{ic("spark","width:15px;height:15px;color:var(--primary)")}Adding footage of sunlit canopies</div>
 <div style="display:flex;gap:6px;margin-top:26px">{done}{cur}{todo}</div>
 <div style="display:flex;justify-content:space-between;margin-top:12px" class="fn"><span>Scene 5 of 9</span><span>About 2 min</span></div>
 <div style="margin-top:44px;font:500 21px/30px var(--font);letter-spacing:-.3px;color:var(--text2)">“Sunlight pours through the canopy, and the forest <span style="color:var(--text)">breathes.</span>”</div>
</div>
<div class="pad" style="position:absolute;left:0;right:0;bottom:56px">
 <div style="display:flex;align-items:center;gap:14px;height:64px;padding:0 18px;border-radius:22px;background:var(--surface);box-shadow:var(--shadow1)">
  <div style="color:var(--primary)">{ic("bell")}</div><div class="hl" style="flex:1;font-weight:500">Tell me when it’s ready</div>
  <div style="width:51px;height:31px;border-radius:16px;background:#34C759;position:relative"><div style="position:absolute;right:2px;top:2px;width:27px;height:27px;border-radius:14px;background:#fff;box-shadow:0 2px 4px rgba(0,0,0,.2)"></div></div>
 </div>
 <div class="cp" style="text-align:center;margin-top:16px">You can leave. It keeps going.</div>
</div>'''


def s_player(theme):
    chips = "".join(f'<div class="chip">{ic("spark")}{t}</div>' for t in ("Make it a Short", "Spanish version", "30-second cut"))
    icons = "".join(f'<div class="ib s" style="width:54px;height:54px;border-radius:27px">{ic(n)}</div>' for n in ("save", "edit", "info", "more"))
    return f'''
<div class="pad" style="display:flex;justify-content:space-between;align-items:center;margin-top:8px"><div class="ib s">{ic("back")}</div></div>
<div style="margin:16px 12px 0;position:relative;height:206px;border-radius:26px;overflow:hidden;background:#000">
 <img class="cover" src="{IMG}clip_01.jpg" style="filter:brightness(.42) saturate(.9)">
 <div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;gap:14px">
  <div style="width:56px;height:56px;border-radius:28px;background:rgba(255,255,255,.18);backdrop-filter:blur(14px);display:flex;align-items:center;justify-content:center;color:#fff">{ic("replay")}</div>
  <div style="height:56px;padding:0 22px;border-radius:28px;background:#fff;color:#0B0C14;display:flex;align-items:center;gap:8px;font:600 16px/1 var(--font)">{ic("newvideo","width:22px;height:22px;color:#4B45E0")}New video</div>
 </div>
</div>
<div class="pad" style="margin-top:22px">
 <div class="t2">How a forest breathes</div>
 <div class="fn" style="margin-top:4px">1:31 · 1080p</div>
 <div style="display:flex;gap:10px;margin-top:22px;align-items:center">
  <div class="btn p" style="flex:1;height:54px">{ic("share","width:20px;height:20px")}Share</div>{icons}
 </div>
 <div class="cp" style="margin-top:34px;letter-spacing:.06em;text-transform:uppercase">Make another</div>
 <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:12px">{chips}</div>
</div>'''


PH = ["p01", "p02", "p03", "p04", "p05", "p06", "p07", "p08", "p09", "p10", "p11", "p12", "p13", "p14", "p15", "p16", "p17", "p18", "p19", "p20"]


def grid(names, sel=(), cols=3, gap=3, w=390, selecting=False):
    cell = (w - gap * (cols - 1)) / cols
    out = []
    for i, n in enumerate(names):
        mark = ""
        if selecting:
            if i in sel:
                mark = f'<div style="position:absolute;inset:0;box-shadow:inset 0 0 0 3px var(--primary);background:rgba(75,69,224,.16)"></div><div style="position:absolute;right:8px;bottom:8px;width:26px;height:26px;border-radius:13px;background:var(--primary);color:var(--bg);display:flex;align-items:center;justify-content:center">{ic("check","width:16px;height:16px;stroke-width:2.800")}</div>'
            else:
                mark = '<div style="position:absolute;right:8px;bottom:8px;width:26px;height:26px;border-radius:13px;box-shadow:inset 0 0 0 2px rgba(255,255,255,.9),0 1px 4px rgba(0,0,0,.3)"></div>'
        out.append(f'<div style="position:relative;width:{cell}px;height:{cell}px;overflow:hidden"><img class="cover" src="{IMG}{n}.jpg">{mark}</div>')
    return f'<div style="display:flex;flex-wrap:wrap;gap:{gap}px">' + "".join(out) + "</div>"


def s_media_idle(theme):
    return f'''
<div class="pad" style="display:flex;justify-content:space-between;align-items:center;margin-top:10px">
 <div class="lt">Media</div><div style="display:flex;gap:8px;align-items:center"><div class="hl" style="color:var(--primary);padding:0 6px">Select</div><div class="ib s" style="width:38px;height:38px">{ic("more")}</div></div>
</div>
<div class="pad" style="margin-top:16px;display:flex;gap:10px">
 <div class="pill" style="flex:1;height:46px;border-radius:23px;justify-content:flex-start;color:var(--text3);font-weight:400">{ic("search","width:18px;height:18px")}Search photos</div>
</div>
<div class="pad" style="margin-top:12px"><div class="btn t" style="height:50px">{ic("photoplus","width:21px;height:21px")}Add photos</div></div>
<div class="pad" style="display:flex;justify-content:space-between;align-items:baseline;margin:26px 0 12px"><div class="hl">November 2026</div><div class="fn">18</div></div>
{grid(PH[:12])}
{tabbar("media")}'''


def s_media_select(theme):
    return f'''
<div class="pad" style="display:flex;justify-content:space-between;align-items:center;margin-top:16px;height:40px">
 <div class="hl" style="color:var(--primary);font-weight:500">Cancel</div><div class="hl">3 selected</div><div class="hl" style="color:var(--primary);font-weight:500">Select all</div>
</div>
<div class="pad" style="display:flex;justify-content:space-between;align-items:baseline;margin:24px 0 12px"><div class="hl">November 2026</div><div class="fn">18</div></div>
{grid(PH[:15], sel=(1, 3, 7), selecting=True)}
<div style="position:absolute;left:0;right:0;bottom:0;height:150px;background:linear-gradient(180deg,transparent,var(--bg) 62%)"></div>
<div style="position:absolute;left:20px;right:20px;bottom:36px;display:flex;gap:10px;align-items:center;z-index:9">
 <div class="btn p" style="flex:1;height:58px;border-radius:29px">{ic("newvideo","width:22px;height:22px")}Make a video · 3</div>
 <div class="ib" style="width:58px;height:58px;border-radius:29px;box-shadow:inset 0 0 0 1px var(--glassLine),var(--shadow1)">{ic("folder")}</div>
 <div class="ib" style="width:58px;height:58px;border-radius:29px;color:var(--danger);box-shadow:inset 0 0 0 1px var(--glassLine),var(--shadow1)">{ic("trash")}</div>
</div>'''


PHONE = {
    "phone_1_signin": [("Sign in", s_signin)],
    "phone_2_videos": [("Videos", s_home)],
    "phone_3_create": [("Create · empty", s_create_empty), ("Create · after tapping Create", s_create_submit)],
    "phone_4_making": [("Making", s_making)],
    "phone_5_player": [("Player · end card", s_player)],
    "phone_6_media": [("Media", s_media_idle), ("Media · selecting", s_media_select)],
}
plines = []
for name, screens in PHONE.items():
    items = [phone(th, fn(th), f"{lab} · {th}") for th in ("light", "dark") for lab, fn in screens]
    open(os.path.join(OUT, name + ".html"), "w").write(page(board(items)))
    plines.append(f"{name} {112 + len(items) * 390 + (len(items) - 1) * 56} {112 + 844 + 29}")


# ------------------------------------------------------------------ web
def side(on):
    def n(key, icon, label):
        return f'<div class="nav {"on" if on == key else ""}">{ic(icon)}{label}</div>'
    return f'''<div class="side"><div class="logo"><img src="{MARK}">videomk</div>
{n("videos", "film", "Videos")}{n("media", "images", "Media")}{n("settings", "gear", "Settings")}
<div style="flex:1"></div>
<div style="padding:14px;border-radius:16px;background:var(--surface2)"><div style="display:flex;align-items:center;gap:6px;font:600 15px/1 var(--font)">{ic("bolt","width:15px;height:15px;color:var(--primary)")}12 credits</div><div class="vm" style="margin-top:6px">One more free tomorrow</div></div>
<div style="display:flex;align-items:center;gap:10px;padding:14px 10px 0"><div style="width:32px;height:32px;border-radius:16px;background:var(--surface3);font:600 14px/32px var(--font);text-align:center;color:var(--text2)">C</div><div style="font:500 14px/1 var(--font);color:var(--text2)">chris@example.com</div></div></div>'''


def vcard(img, title, meta, dur, asp=None, h=178):
    a = f'<div class="asp">{asp}</div>' if asp else ""
    return f'<div><div class="poster" style="height:{h}px"><img class="cover" src="{IMG}{img}.jpg">{a}<div class="dur">{dur}</div></div><div class="vt">{title}</div><div class="vm">{meta}</div></div>'


def w_videos(theme):
    tiles = "".join(f'<div style="width:64px;height:40px;border-radius:9px;overflow:hidden"><img class="cover" src="{IMG}{n}.jpg"></div>' for n in ("p01", "p03", "p15", "p16"))
    tiles += '<div style="width:64px;height:40px;border-radius:9px;background:rgba(255,255,255,.22);position:relative"><div class="ring"></div></div>' + '<div style="width:64px;height:40px;border-radius:9px;box-shadow:inset 0 0 0 1.500px rgba(255,255,255,.22)"></div>' * 4
    cards = [vcard("clip_01", "How a forest breathes", "Today · 16:9", "1:31"), vcard("s_bees", "How bees make honey", "Today · 16:9", "2:04"),
             vcard("s_pulpo", "Un pulpo escurriéndose por una grieta", "Yesterday · 16:9", "0:45"), vcard("team_frame", "A healthy plate, explained", "Yesterday · 16:9", "0:24"),
             vcard("s_jobs", "AI and jobs: what people expect", "Mon · 1:1", "1:00", "1:1"), vcard("forest_frame2", "Where forests store carbon", "Mon · 16:9", "1:12"),
             vcard("s_agents", "AI agents in production", "Sun · 4:5", "0:30", "4:5"), vcard("p12", "The Parthenon in two minutes", "Sun · 16:9", "2:00")]
    return f'''<div class="web" data-theme="{theme}">{side("videos")}<div class="main">
<div style="display:flex;align-items:center;gap:14px"><div class="wh1" style="flex:1">Videos</div>
 <div class="search" style="width:280px">{ic("search")}Search</div><div class="wbtn p">{ic("newvideo")}New video</div></div>
<div class="brandgrad" style="margin-top:30px;border-radius:26px;padding:22px 26px;display:flex;align-items:center;gap:26px;box-shadow:0 14px 36px rgba(60,50,180,.28)">
 <div style="flex:1"><div style="font:600 19px/24px var(--font);letter-spacing:-.3px">How honey is made</div>
 <div style="display:flex;align-items:center;gap:6px;margin-top:8px;font:500 14px/1 var(--font);color:rgba(255,255,255,.86)">{ic("spark","width:13px;height:13px;color:#22D3EE")}Scene 5 of 9 · finding the right footage</div></div>
 <div style="display:flex;gap:6px">{tiles}</div><div style="font:500 14px/1 var(--font);color:rgba(255,255,255,.8);width:80px;text-align:right">2 min left</div></div>
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:28px 24px;margin-top:36px">{"".join(cards)}</div>
</div></div>'''


def w_create(theme):
    thumbs = "".join(f'<div style="width:72px;height:72px;border-radius:16px;overflow:hidden;flex:none"><img class="cover" src="{IMG}{n}.jpg"></div>' for n in ("p08", "p09", "p10", "p05", "p17", "p13", "p01", "p14"))
    chips = "".join(f'<div class="chip" style="height:40px;border-radius:20px">{ic("spark")}{t}</div>' for t in ("How bees make honey", "3 focus tips for busy days", "Why forests matter", "The Parthenon in two minutes"))
    return f'''<div class="web" data-theme="{theme}">{side("videos")}
<div style="position:absolute;left:420px;right:170px;top:170px;height:520px;background:radial-gradient(closest-side at 30% 55%,rgba(122,75,230,.22),transparent),radial-gradient(closest-side at 74% 45%,rgba(34,211,238,.14),transparent);filter:blur(40px)"></div>
<div class="main" style="display:flex;flex-direction:column;align-items:center;padding-top:108px">
 <div style="font:700 48px/54px var(--font);letter-spacing:-1.400px;text-align:center">What’s the video about?</div>
 <div class="card" style="width:820px;margin-top:40px;border-radius:32px;padding:30px 30px 22px;box-shadow:var(--shadow2);position:relative">
  <div style="font:500 24px/34px var(--font);letter-spacing:-.4px;min-height:102px">How a forest breathes, and why forests matter. Calm and warm, with real footage of forests.<span style="display:inline-block;width:2.500px;height:28px;background:var(--primary);vertical-align:-5px;margin-left:3px;border-radius:2px"></span></div>
  <div style="display:flex;gap:10px;margin-top:6px;align-items:center">{thumbs}<div class="vm" style="margin:0 0 0 6px;font-size:14px">45 photos</div></div>
  <div style="height:1px;background:var(--line);margin:22px 0 18px"></div>
  <div style="display:flex;align-items:center;gap:8px">
   <div class="wib">{ic("photoplus")}</div><div class="wib">{ic("mic")}</div><div style="width:8px"></div>
   <div class="pill" style="height:44px;border-radius:22px"><span class="k">For</span>YouTube{ic("down")}</div><div class="pill" style="height:44px;border-radius:22px">2 min{ic("down")}</div><div class="pill" style="height:44px;border-radius:22px"><span class="k">Look</span>Auto{ic("down")}</div><div class="wib">{ic("sliders")}</div>
   <div style="flex:1"></div>
   <div class="wbtn p" style="height:50px;border-radius:25px;padding:0 22px 0 26px;font-size:16px;gap:16px">Create<span style="display:inline-flex;align-items:center;gap:4px">{ic("bolt","width:15px;height:15px")}2</span></div>
  </div>
 </div>
 <div style="display:flex;gap:10px;margin-top:30px;flex-wrap:wrap;justify-content:center;width:820px">{chips}</div>
</div></div>'''


def w_media(theme):
    def month(title, count, names, sel=()):
        cells = []
        for i, n in enumerate(names):
            m = ""
            if i in sel:
                m = f'<div style="position:absolute;inset:0;border-radius:14px;box-shadow:inset 0 0 0 3px var(--primary);background:rgba(75,69,224,.14)"></div><div style="position:absolute;right:10px;top:10px;width:26px;height:26px;border-radius:13px;background:var(--primary);color:var(--bg);display:flex;align-items:center;justify-content:center">{ic("check","width:16px;height:16px;stroke-width:2.800")}</div>'
            cells.append(f'<div style="position:relative;height:118px;border-radius:14px;overflow:hidden"><img class="cover" src="{IMG}{n}.jpg">{m}</div>')
        return f'<div style="display:flex;align-items:baseline;gap:10px;margin:34px 0 14px"><div style="font:600 19px/24px var(--font);letter-spacing:-.3px">{title}</div><div class="vm" style="margin:0">{count}</div></div><div style="display:grid;grid-template-columns:repeat(6,1fr);gap:8px">{"".join(cells)}</div>'
    return f'''<div class="web" data-theme="{theme}">{side("media")}<div class="main">
<div style="display:flex;align-items:center;gap:12px"><div class="wh1" style="flex:1">Media</div>
 <div class="search" style="width:320px">{ic("search")}Search photos: “beach at sunset”</div><div class="wbtn g">Select</div><div class="wbtn t">{ic("photoplus")}Add photos</div></div>
{month("November 2026", "18 photos", PH[:12], sel=(1, 2, 4, 7, 9))}
{month("August 2026", "42 photos", PH[8:20] )}
</div>
<div style="position:absolute;left:248px;right:0;bottom:0;height:150px;background:linear-gradient(180deg,transparent,var(--bg) 70%)"></div>
<div style="position:absolute;left:50%;margin-left:-126px;bottom:34px;display:flex;align-items:center;gap:10px;padding:10px 10px 10px 24px;border-radius:36px;background:var(--glass);backdrop-filter:blur(30px);box-shadow:inset 0 0 0 1px var(--glassLine),var(--shadow2)">
 <div style="font:600 15px/1 var(--font);margin-right:8px">5 selected</div><div class="wib" style="background:transparent">{ic("folder")}</div><div class="wib" style="background:transparent;color:var(--danger)">{ic("trash")}</div>
 <div class="wbtn p" style="height:50px;border-radius:25px;font-size:16px">{ic("newvideo")}Make a video · 5</div></div>
<div class="card" style="position:absolute;right:32px;bottom:34px;width:300px;padding:16px 18px;border-radius:20px;box-shadow:var(--shadow2)">
 <div style="display:flex;align-items:center;gap:10px"><div style="color:var(--primary)">{ic("upload")}</div><div style="flex:1;font:600 15px/1 var(--font)">Adding 12 of 45</div><div style="color:var(--text3)">{ic("pause","width:18px;height:18px")}</div></div>
 <div style="height:4px;border-radius:2px;background:var(--surface3);margin-top:14px"><div style="width:27%;height:4px;border-radius:2px;background:var(--primary)"></div></div></div>
</div>'''


def w_watch(theme):
    acts = "".join(f'<div class="wib" style="width:48px;height:48px;border-radius:24px">{ic(n)}</div>' for n in ("save", "edit", "more"))
    chips = "".join(f'<div class="chip" style="height:40px;border-radius:20px;justify-content:flex-start">{ic("spark")}{t}</div>' for t in ("Make it a Short", "Spanish version", "30-second cut"))
    ctl = f'''<div style="position:absolute;left:0;right:0;bottom:0;padding:60px 22px 18px;background:linear-gradient(180deg,transparent,rgba(0,0,0,.6));color:#fff">
 <div style="height:4px;border-radius:2px;background:rgba(255,255,255,.3)"><div style="width:38%;height:4px;border-radius:2px;background:#fff;position:relative"><div style="position:absolute;right:-6px;top:-4px;width:12px;height:12px;border-radius:6px;background:#fff"></div></div></div>
 <div style="display:flex;align-items:center;gap:16px;margin-top:14px">{ic("pause")}{ic("vol")}<span style="font:500 13px/1 var(--font);opacity:.9">0:35 / 1:31</span><div style="flex:1"></div><span style="font:600 13px/1 var(--font)">1×</span>{ic("pip")}{ic("full")}</div></div>'''
    return f'''<div class="web" data-theme="{theme}">{side("videos")}<div class="main" style="display:flex;gap:40px;padding-top:32px">
<div style="width:800px;flex:none">
 <div style="display:flex;align-items:center;gap:8px;color:var(--text2);font:500 15px/1 var(--font);margin-bottom:18px">{ic("back","width:18px;height:18px")}Videos</div>
 <div style="position:relative;height:450px;border-radius:26px;overflow:hidden;background:#000;box-shadow:var(--shadow2)"><img class="cover" src="{IMG}clip_01.jpg">{ctl}</div>
 <div style="display:flex;align-items:flex-start;gap:16px;margin-top:26px">
  <div style="flex:1"><div style="font:700 28px/34px var(--font);letter-spacing:-.6px">How a forest breathes</div><div class="vm" style="font-size:15px;margin-top:6px">1:31 · 1080p · Today</div></div>
  <div class="wbtn p" style="height:48px;border-radius:24px;padding:0 24px;font-size:16px">{ic("share")}Share</div>{acts}
 </div>
</div>
<div style="flex:1;padding-top:36px">
 <div class="cp" style="letter-spacing:.07em;text-transform:uppercase">The prompt</div>
 <div style="font:400 17px/27px var(--font);letter-spacing:-.2px;margin-top:12px">A calm explainer about how a forest breathes and why forests matter. Use real footage of forests wherever it fits. Warm, gentle tone.</div>
 <div class="hl" style="color:var(--primary);margin-top:14px;font-size:15px">Use this prompt again</div>
 <div style="height:1px;background:var(--line);margin:30px 0"></div>
 <div class="cp" style="letter-spacing:.07em;text-transform:uppercase">Make another</div>
 <div style="display:flex;flex-direction:column;gap:10px;margin-top:14px;align-items:flex-start">{chips}</div>
</div></div></div>'''


def w_home(theme):
    dark = theme == "dark"
    def tile(img, w, h, prompt, asp):
        return f'<div style="width:{w}px"><div class="poster" style="height:{h}px;border-radius:24px;box-shadow:var(--shadow1)"><img class="cover" src="{IMG}{img}.jpg"><div class="asp">{asp}</div><div style="position:absolute;right:12px;top:12px;width:40px;height:40px;border-radius:20px;background:rgba(20,22,40,.5);backdrop-filter:blur(12px);color:#fff;display:flex;align-items:center;justify-content:center">{ic("play","width:18px;height:18px;margin-left:2px")}</div></div><div style="font:400 15px/22px var(--font);color:var(--text2);margin-top:14px">“{prompt}”</div></div>'
    return f'''<div class="web" data-theme="{theme}" style="min-height:1880px">
<div style="position:absolute;left:0;right:0;top:0;height:760px;background:radial-gradient(60% 70% at 50% 0%,{"rgba(90,70,230,.30)" if dark else "rgba(110,90,240,.16)"},transparent 70%)"></div>
<div style="position:relative;display:flex;align-items:center;gap:34px;height:72px;padding:0 64px">
 <div style="display:flex;align-items:center;gap:10px;font:700 20px/1 var(--font);letter-spacing:-.4px;flex:1"><img src="{MARK}" style="width:32px;height:32px;border-radius:8px">videomk</div>
 <div style="font:500 15px/1 var(--font);color:var(--text2)">Gallery</div><div style="font:500 15px/1 var(--font);color:var(--text2)">Pricing</div><div style="font:500 15px/1 var(--font);color:var(--text2)">Help</div>
 <div style="font:500 15px/1 var(--font)">Sign in</div><div class="wbtn" style="background:var(--inv);color:var(--onInv);height:40px;border-radius:20px">Get the app</div></div>
<div style="position:relative;text-align:center;padding-top:76px">
 <div style="font:700 88px/92px var(--font);letter-spacing:-3.200px">Describe it.<br><span style="background:linear-gradient(100deg,{"#B7B4FF,#D9B8FF 60%,#7FE7F5" if dark else "#3B36C8,#7A4BE6 60%,#17A8C4"});-webkit-background-clip:text;color:transparent">Get the video.</span></div>
 <div style="font:400 22px/32px var(--font);letter-spacing:-.3px;color:var(--text2);margin-top:26px">One sentence becomes a narrated video, with pictures, clips and music.</div>
 <div style="display:inline-flex;align-items:center;gap:10px;width:640px;height:68px;margin-top:40px;padding:0 9px 0 28px;border-radius:34px;background:var(--surface);box-shadow:var(--shadow2);text-align:left">
  <div style="flex:1;font:400 19px/1 var(--font);color:var(--text3)">How is honey made?</div><div class="wib" style="background:transparent;color:var(--text3)">{ic("mic")}</div>
  <div class="wbtn p" style="height:50px;border-radius:25px;padding:0 26px;font-size:17px">Create</div></div>
 <div class="vm" style="margin-top:16px;font-size:14px">Free to start. No card.</div>
</div>
<div style="position:relative;width:1120px;margin:64px auto 0">
 <div style="position:relative;height:630px;border-radius:36px;overflow:hidden;box-shadow:0 40px 100px {"rgba(0,0,0,.7)" if dark else "rgba(30,30,90,.28)"}"><img class="cover" src="{IMG}clip_01.jpg">
  <div style="position:absolute;left:0;right:0;bottom:0;height:260px;background:linear-gradient(180deg,transparent,rgba(0,0,0,.62))"></div>
  <div style="position:absolute;left:36px;right:36px;bottom:32px;display:flex;align-items:flex-end;gap:24px;color:#fff">
   <div style="flex:1"><div style="font:600 12px/1 var(--font);letter-spacing:.1em;text-transform:uppercase;opacity:.7">The prompt</div>
   <div style="font:500 22px/31px var(--font);letter-spacing:-.3px;margin-top:10px;max-width:680px">“A calm explainer about how a forest breathes and why forests matter.”</div></div>
   <div class="wbtn" style="background:#fff;color:#0B0C14;height:50px;border-radius:25px;padding:0 24px;font-size:16px">{ic("spark","width:16px;height:16px;color:#4B45E0")}Try this prompt</div></div>
 </div>
</div>
<div style="position:relative;text-align:center;margin-top:120px">
 <div style="font:700 56px/62px var(--font);letter-spacing:-1.800px">One sentence in. Any shape out.</div>
 <div style="font:400 20px/30px var(--font);color:var(--text2);margin-top:16px">Real videos made with videomk. Each one started as the line under it.</div></div>
<div style="position:relative;width:1120px;margin:56px auto 0;display:flex;gap:24px;align-items:flex-start">
 {tile("s_bees", 569, 320, "How do bees make honey?", "16:9")}{tile("s_focus", 180, 320, "Three focus tips", "9:16")}{tile("s_jobs", 320, 320, "What do people expect from AI and jobs?", "1:1")}
</div>
</div>'''


WEB = {"web_1_home": (w_home, 1880), "web_2_videos": (w_videos, 900), "web_3_create": (w_create, 900), "web_4_media": (w_media, 900), "web_5_watch": (w_watch, 900)}
lines = []
for name, (fn, h) in WEB.items():
    for th in ("light", "dark"):
        open(os.path.join(OUT, f"{name}_{th}.html"), "w").write(page(fn(th)))
        lines.append(f"{name}_{th} 1440 {h}")
open(os.path.join(OUT, "phone.txt"), "w").write("\n".join(plines) + "\n")
open(os.path.join(OUT, "web.txt"), "w").write("\n".join(lines) + "\n")
print("wrote", len(PHONE), "phone boards and", len(lines), "web pages")
