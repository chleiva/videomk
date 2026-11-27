# Generates the mockups of docs/UX_2026_REDESIGN.md (HTML -> PNG with headless Chrome). Run: python3 gen.py
import subprocess, os
D=os.path.dirname(os.path.abspath(__file__))
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BOLT='<svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M13 2 4 14h6l-1 8 9-12h-6z"/></svg>'
def ico(p,s=22,sw=1.8,fill="none"): return f'<svg width="{s}" height="{s}" viewBox="0 0 24 24" fill="{fill}" stroke="currentColor" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round">{p}</svg>'
I={
 "share":ico('<path d="M12 3v12M8 7l4-4 4 4M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-7"/>'),
 "save":ico('<path d="M12 4v12M7 11l5 5 5-5M5 20h14"/>'),
 "edit":ico('<path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/>'),
 "info":ico('<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.01"/>'),
 "more":ico('<circle cx="5" cy="12" r="1.2" fill="currentColor"/><circle cx="12" cy="12" r="1.2" fill="currentColor"/><circle cx="19" cy="12" r="1.2" fill="currentColor"/>'),
 "mic":ico('<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>'),
 "photo":ico('<rect x="3" y="4" width="18" height="16" rx="3"/><circle cx="9" cy="10" r="1.6"/><path d="M4 18l5-5 4 4 3-3 4 4"/>'),
 "close":ico('<path d="M6 6l12 12M18 6 6 18"/>'),
 "back":ico('<path d="M15 5l-7 7 7 7"/>'),
 "play":ico('<path d="M8 5v14l11-7z"/>',fill="currentColor",sw=0),
 "plus":ico('<path d="M12 5v14M5 12h14"/>',s=26,sw=2.2),
 "videos":ico('<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M10 9.5v5l4-2.5z" fill="currentColor"/>',s=24),
 "media":ico('<rect x="3" y="4" width="18" height="16" rx="3"/><circle cx="9" cy="10" r="1.6"/><path d="M4 18l5-5 4 4 3-3 4 4"/>',s=24),
 "chev":ico('<path d="M9 6l6 6-6 6"/>',s=16),
 "down":ico('<path d="M6 9l6 6 6-6"/>',s=14,sw=2.2),
 "clock":ico('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',s=17),
 "spark":ico('<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z"/>',s=17,sw=1.5),
 "screen":ico('<rect x="3" y="6" width="18" height="12" rx="2.5"/>',s=17),
 "person":ico('<circle cx="12" cy="8" r="4"/><path d="M4 21c1-4 4-6 8-6s7 2 8 6"/>',s=22),
 "gear":ico('<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1"/>',s=22),
}
CSS=open(D+"/tokens.css").read()+'''
body{margin:0;background:#d9dbe6}
.board{display:flex;gap:26px;padding:26px;align-items:flex-start;width:max-content}
.col h6{font:700 12px/1 system-ui;letter-spacing:.08em;text-transform:uppercase;color:#4a4f6a;margin:0 0 12px 10px}
.phone{width:390px;height:844px;border-radius:48px;background:var(--bg);color:var(--text);position:relative;overflow:hidden;box-shadow:0 0 0 10px #1b1d2e;margin-left:10px;font-size:15px}
[data-theme=dark].phone{box-shadow:0 0 0 10px #05060e}
.island{position:absolute;top:11px;left:50%;width:120px;height:34px;border-radius:20px;background:#000;transform:translateX(-50%);z-index:5}
.sb{height:54px;display:flex;justify-content:space-between;align-items:flex-end;padding:0 32px 8px;font:600 16px system-ui}
.pad{padding:0 16px}.row{display:flex;align-items:center}
.h1{font:700 32px/38px system-ui;letter-spacing:-.03em}
.h2{font:700 19px/24px system-ui}
.cap{font:500 13px/18px system-ui;color:var(--text2)}
.t3c{color:var(--text3)}
.ibtn{width:44px;height:44px;border-radius:22px;display:flex;align-items:center;justify-content:center;background:var(--glass);backdrop-filter:blur(20px);box-shadow:inset 0 0 0 .5px var(--outline);color:var(--text)}
.ibtn.pri{background:linear-gradient(135deg,var(--g1),var(--g2));color:var(--on-primary);box-shadow:var(--shadow2)}
.btn{display:flex;align-items:center;justify-content:center;gap:8px;height:54px;border-radius:27px;font:700 17px system-ui;color:var(--on-primary);background:linear-gradient(135deg,var(--g1),var(--g2));box-shadow:var(--shadow2)}
.card{background:var(--surface);border-radius:24px;box-shadow:var(--shadow2)}
.chip{display:inline-flex;align-items:center;gap:6px;height:38px;padding:0 14px;border-radius:19px;font:600 14px system-ui;background:var(--surface);color:var(--text);box-shadow:inset 0 0 0 1px var(--outline);white-space:nowrap}
.chip.sel{background:var(--primary-c);color:var(--primary);box-shadow:none}
.credit{display:inline-flex;align-items:center;gap:4px;height:36px;padding:0 12px;border-radius:18px;background:var(--surface);box-shadow:inset 0 0 0 1px var(--outline);font:700 15px system-ui}
.tabbar{position:absolute;left:16px;right:88px;bottom:24px;height:64px;border-radius:32px;background:var(--glass);backdrop-filter:blur(24px);box-shadow:var(--shadow3);display:flex;align-items:center;justify-content:space-around;padding:0 8px}
.tab{display:flex;flex-direction:column;align-items:center;gap:2px;font:600 11px system-ui;color:var(--text2);width:92px;height:52px;justify-content:center;border-radius:26px}
.tab.on{color:var(--primary);background:var(--primary-c)}
.fab{position:absolute;right:16px;bottom:24px;width:64px;height:64px;border-radius:32px;background:linear-gradient(135deg,var(--g1),var(--g2));color:var(--on-primary);display:flex;align-items:center;justify-content:center;box-shadow:var(--shadow3)}
.thumb{border-radius:14px;position:relative;overflow:hidden;flex:none}
.t1{background:linear-gradient(135deg,#f6b98a,#b0507a)}.t2{background:linear-gradient(135deg,#6ee7b7,#1f6b6b)}.t3{background:linear-gradient(135deg,#8b8cff,#2b1f6a)}.t4{background:linear-gradient(135deg,#fde68a,#d97706)}
.dur{position:absolute;right:6px;bottom:5px;font:600 11px system-ui;color:#fff;background:rgba(0,0,0,.55);padding:2px 6px;border-radius:6px}
.making{border-radius:24px;background:linear-gradient(135deg,var(--making1),var(--making2));color:#fff;padding:16px;margin:0 16px}
.bar{height:4px;border-radius:2px;background:rgba(255,255,255,.25);overflow:hidden}.bar i{display:block;height:100%;background:#fff;border-radius:2px}
.sheet{position:absolute;left:0;right:0;bottom:0;background:var(--bg);border-radius:34px 34px 0 0;box-shadow:var(--shadow3)}
.grab{width:36px;height:5px;border-radius:3px;background:var(--outline);margin:8px auto 10px}
.list{background:var(--surface);border-radius:20px;margin:0 16px}
.li{display:flex;align-items:center;gap:12px;min-height:52px;padding:0 16px;font:500 17px system-ui;border-bottom:.5px solid var(--outline)}.li:last-child{border:0}
.li .v{margin-left:auto;color:var(--text2);font-size:16px}
.tog{margin-left:auto;width:51px;height:31px;border-radius:16px;background:var(--primary);position:relative}.tog:after{content:"";position:absolute;right:2px;top:2px;width:27px;height:27px;border-radius:14px;background:#fff}
.mark{width:30px;height:30px;border-radius:9px;background:linear-gradient(135deg,var(--making1),var(--making2));display:flex;align-items:center;justify-content:center;color:#fff}
.note{position:absolute;font:700 11px system-ui;background:#ff3b6b;color:#fff;border-radius:11px;width:22px;height:22px;text-align:center;line-height:22px;z-index:9}
'''
def phone(inner,extra=""): return f'<div class="phone"><div class="island"></div><div class="sb"><span>9:41</span><span>5G ▮</span></div>{inner}{extra}</div>'
def tabs(sel=0): return f'<div class="tabbar"><div class="tab {"on" if sel==0 else ""}">{I["videos"]}Videos</div><div class="tab {"on" if sel==1 else ""}">{I["media"]}Media</div></div><div class="fab">{I["plus"]}</div>'
def top(): return f'<div class="pad row" style="justify-content:space-between;height:48px"><div class="mark">{I["play"].replace("width=\"22\" height=\"22\"","width=\"16\" height=\"16\"")}</div><div class="row" style="gap:10px"><span class="credit">{BOLT} 42</span><div class="ibtn" style="width:36px;height:36px">{I["person"]}</div></div></div>'
def vrow(c,t,m,dur): return f'<div class="row pad" style="gap:12px;margin-bottom:14px"><div class="thumb {c}" style="width:112px;height:63px;border-radius:12px"><span class=dur>{dur}</span></div><div><div style="font:600 16px/21px system-ui">{t}</div><div class=cap>{m}</div></div></div>'
def home():
    return phone(top()+f'<div class=pad><div class=h1 style="margin:6px 0 14px">Videos</div></div>'
     f'<div class=making><div class=row style="justify-content:space-between"><b style="font:600 17px/22px system-ui">Golden retriever’s first summer</b></div><div style="font:500 14px system-ui;opacity:.85;margin:4px 0 14px">Finding pictures · 3 of 7</div><div class=bar><i style="width:46%"></i></div></div>'
     f'<div style="height:18px"></div><div class="pad cap" style="margin-bottom:10px;font-weight:600">Yesterday</div>'+vrow("t2","Sunset over Lisbon","1 min","1:20")+
     f'<div class="row pad" style="gap:12px;margin-bottom:14px"><div class="thumb" style="width:112px;height:63px;border-radius:12px;background:var(--danger-c);color:var(--danger);display:flex;align-items:center;justify-content:center;font:700 22px system-ui">!</div><div><div style="font:600 16px/21px system-ui">Thailand highlights</div><div class=cap style="color:var(--danger)">Didn’t finish · <b style="color:var(--primary)">Try again</b></div></div></div>'
     +vrow("t3","The history of the bicycle","2 min","2:22")+vrow("t4","How bees make honey","1 min","1:05")+tabs(0))
def empty():
    return phone(top()+f'<div class=pad style="margin-top:96px"><div class=h1 style="font-size:34px;line-height:40px">Describe it.<br>We’ll make the video.</div></div>'
     f'<div class=pad style="margin-top:28px"><div class=card style="padding:18px 18px 14px;height:150px;position:relative"><span class=t3c style="font:400 19px/26px system-ui">A video about…</span><div style="position:absolute;right:12px;bottom:12px" class=ibtn>{I["mic"]}</div></div></div>'
     f'<div class=pad style="margin-top:16px;display:flex;gap:8px;flex-wrap:wrap"><span class=chip>How bees make honey</span><span class=chip>A lighthouse story</span><span class=chip>History of the bicycle</span></div>'+tabs(0))
def create():
    return phone(f'<div class="pad row" style="justify-content:space-between;height:48px"><div class=ibtn>{I["close"]}</div></div>'
     f'<div class=pad style="margin-top:6px"><div style="font:400 24px/32px system-ui;letter-spacing:-.01em;min-height:150px">How bees make honey, explained for kids<span style="color:var(--primary)">|</span></div></div>'
     f'<div class="pad row" style="justify-content:space-between;margin-top:8px"><div class="ibtn" style="position:relative">{I["photo"]}</div><div class=ibtn>{I["mic"]}</div></div>'
     f'<div style="display:flex;gap:8px;padding:22px 16px 0;overflow:hidden"><span class=chip>{I["screen"]} Video {I["down"]}</span><span class=chip>{I["clock"]} 2 min {I["down"]}</span><span class=chip>{I["spark"]} Auto {I["down"]}</span></div>'
     f'<div style="position:absolute;left:16px;right:16px;bottom:28px"><div class=btn>Create · {BOLT} 2</div><div class=cap style="text-align:center;margin-top:10px">40 credits left</div></div>')
def options():
    sw=lambda c,l,sel=False:f'<div style="text-align:center;font:600 12px system-ui;color:var(--text2)"><div class="thumb {c}" style="width:68px;height:68px;margin:0 auto 6px;{"outline:3px solid var(--primary);outline-offset:2px" if sel else ""}"></div>{l}</div>'
    seg=lambda a,sel:"".join(f'<div style="flex:1;text-align:center;height:38px;line-height:38px;border-radius:12px;font:600 14px system-ui;{"background:var(--surface);box-shadow:var(--shadow2)" if x==sel else "color:var(--text2)"}">{x}</div>' for x in a)
    return phone(f'<div style="opacity:.35;padding:20px"><div style="font:400 24px/32px system-ui">How bees make honey, explained for kids</div></div>'
     f'<div class=sheet style="top:150px"><div class=grab></div><div class="pad row" style="justify-content:space-between;height:44px"><b class=h2>Options</b><span style="color:var(--primary);font:600 17px system-ui">Done</span></div>'
     f'<div class=pad style="margin-top:8px"><div class=cap style="font-weight:700;margin-bottom:8px">FOR</div><div style="display:flex;gap:8px;flex-wrap:wrap"><span class=chip>YouTube</span><span class=chip>LinkedIn</span><span class=chip>X</span><span class="chip sel">Video</span><span class=chip>Shorts · Reels</span><span class=chip>Instagram</span></div>'
     f'<div class=cap style="font-weight:700;margin:20px 0 8px">LOOK</div><div style="display:flex;justify-content:space-between">{sw("t3","Auto",True)}{sw("t3","Midnight")}{sw("t4","Paper")}{sw("t1","Sunrise")}</div>'
     f'<div class=cap style="font-weight:700;margin:20px 0 8px">QUALITY</div><div style="display:flex;background:var(--surface2);border-radius:14px;padding:3px">{seg(["720p","1080p","4K"],"1080p")}</div>'
     f'</div><div class=list style="margin-top:20px"><div class=li>Subtitles<div class=tog></div></div><div class=li>Language<span class=v>Auto {I["chev"]}</span></div></div><div style="height:34px"></div></div>')
def player():
    return phone(f'<div class="pad row" style="justify-content:space-between;height:48px"><div class=ibtn>{I["back"]}</div><b style="font:600 17px system-ui">Sunset over Lisbon</b><div style="width:44px"></div></div>'
     f'<div style="margin-top:10px;height:219px;background:linear-gradient(135deg,#3b6d57,#142c24);position:relative"><div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center"><div style="width:60px;height:60px;border-radius:30px;background:rgba(255,255,255,.22);backdrop-filter:blur(14px);display:flex;align-items:center;justify-content:center;color:#fff">{I["play"].replace("22","28")}</div></div><div style="position:absolute;left:14px;right:14px;bottom:12px;height:3px;background:rgba(255,255,255,.3);border-radius:2px"><i style="display:block;width:34%;height:100%;background:#fff;border-radius:2px"></i></div></div>'
     f'<div class=pad style="margin-top:16px"><div class=h2 style="font-size:22px">Sunset over Lisbon</div><div class=cap style="margin-top:2px">1:20 · 1080p</div></div>'
     f'<div class="pad row" style="justify-content:space-between;margin-top:22px"><div class="ibtn pri" style="width:56px;height:56px;border-radius:28px">{I["share"]}</div><div class=ibtn>{I["save"]}</div><div class=ibtn>{I["edit"]}</div><div class=ibtn>{I["info"]}</div><div class=ibtn>{I["more"]}</div></div>'
     )
def making():
    th=lambda c:f'<div class="thumb {c}" style="width:62px;height:62px;border-radius:12px;border:2px solid rgba(255,255,255,.35)"></div>'
    return phone(f'<div class="pad row" style="justify-content:space-between;height:48px"><div class=ibtn>{I["back"]}</div></div><div class=pad style="margin-top:8px"><div class=h1 style="font-size:30px;line-height:36px">Golden retriever’s first summer</div></div>'
     f'<div class=making style="margin-top:22px;padding:18px"><div style="font:600 20px/26px system-ui">Finding pictures</div><div style="font:500 14px system-ui;opacity:.85;margin:4px 0 16px">Scene 3 of 7 · about 2 min</div><div style="display:flex;gap:8px;margin-bottom:16px">{th("t1")}{th("t4")}{th("t2")}<div style="width:62px;height:62px;border-radius:12px;background:rgba(255,255,255,.14)"></div></div><div class=bar><i style="width:46%"></i></div></div>'
     f'<div class="pad cap" style="margin-top:14px;text-align:center">You can leave. We’ll tell you when it’s ready.</div>')
def settings():
    ic=lambda s:f'<span style="width:28px;height:28px;border-radius:8px;background:var(--primary-c);color:var(--primary);display:flex;align-items:center;justify-content:center">{s}</span>'
    return phone(f'<div class="pad row" style="justify-content:space-between;height:48px"><b style="font:700 32px system-ui;letter-spacing:-.03em">Settings</b><span style="color:var(--primary);font:600 17px system-ui">Done</span></div>'
     f'<div class=list style="margin-top:14px"><div class=li>{ic(I["person"].replace("22","16"))}demo@example.com</div><div class=li style="color:var(--primary)">Sign out</div></div>'
     f'<div class=list style="margin-top:18px"><div class=li>Language<span class=v>Auto {I["chev"]}</span></div><div class=li>Photo dates<div class=tog></div></div><div class=li>Photo locations<div class=tog></div></div></div>'
     f'<div class=list style="margin-top:18px"><div class=li>Send feedback<span class=v>{I["chev"]}</span></div><div class=li>Support<span class=v>{I["chev"]}</span></div><div class=li>About<span class=v>1.0 {I["chev"]}</span></div></div>'
     f'<div class="list" style="margin-top:18px"><div class=li style="color:var(--danger)">Delete account</div></div>')
SCREENS=[("Home",home),("First run",empty),("Create",create),("Options",options),("Video (player)",player),("Making",making),("Settings",settings)]
for theme in ("light","dark"):
    cols="".join(f'<div class=col><h6>{n}</h6>{f()}</div>' for n,f in SCREENS)
    open(f"{D}/board_{theme}.html","w").write(f'<!doctype html><meta charset=utf-8><style>{CSS}</style><body data-theme="{theme}" style="background:{"#d9dbe6" if theme=="light" else "#1b1d2e"}"><div class=board data-theme="{theme}">{cols}</div>'.replace('<div class="phone">',f'<div class="phone" data-theme="{theme}">'))
    for i,(n,f) in enumerate(SCREENS):
        pass
    subprocess.run([CHROME,"--headless=new","--disable-gpu","--hide-scrollbars","--force-device-scale-factor=1","--window-size=%d,900"%(len(SCREENS)*416+80)+",960" if False else "--window-size=%d,960"%(len(SCREENS)*416+90),f"--screenshot={D}/board_{theme}.png",f"file://{D}/board_{theme}.html"],capture_output=True)
print("ok")
