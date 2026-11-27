import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
A = os.path.abspath(os.path.join(HERE, "..", "assets"))
CSS = """
:root{--bg:#fbfbfd;--surface:#fff;--surface-2:#f2f3f8;--line:rgba(17,20,43,.09);--text:#11142b;--t2:#565d78;--t3:#6a7090;--primary:#4f52e0;--on-primary:#fff;--primary-soft:#ececff;--live:#22d3ee;--ok:#127035;--shadow:0 1px 2px rgba(17,20,43,.04),0 12px 40px rgba(40,44,110,.10);--glass:rgba(251,251,253,.78);--g1:#5b5ef0;--g2:#8452f4;--making1:#2b2f9a;--making2:#6a3fc4}
[data-theme=dark]{--g1:#8f92ff;--g2:#ae8aff;--bg:#07091a;--surface:#10142b;--surface-2:#181d3a;--line:rgba(243,244,251,.10);--text:#f3f4fb;--t2:#a2a9c5;--t3:#8f97b6;--primary:#9ea0ff;--on-primary:#0a0d1f;--primary-soft:#23275a;--shadow:0 0 0 1px rgba(243,244,251,.08),0 20px 60px rgba(0,0,0,.5);--glass:rgba(7,9,26,.72)}
*{box-sizing:border-box;margin:0}
body{font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","SF Pro Text",Inter,system-ui,sans-serif;background:var(--bg);color:var(--text);-webkit-font-smoothing:antialiased;line-height:1.47;font-size:17px}
a{color:inherit;text-decoration:none}
.nav{position:sticky;top:0;z-index:5;background:var(--glass);backdrop-filter:saturate(180%) blur(20px);border-bottom:1px solid var(--line)}
.nav-in{max-width:1120px;margin:0 auto;height:56px;padding:0 24px;display:flex;align-items:center;gap:28px}
.brand{display:flex;align-items:center;gap:10px;font-weight:700;font-size:19px;letter-spacing:-.02em}
.brand img{width:28px;height:28px;border-radius:7px}
.links{display:flex;gap:24px;font-size:14px;color:var(--t2)}
.sp{flex:1}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;height:44px;padding:0 22px;border-radius:999px;font-weight:600;font-size:16px;border:0;background:linear-gradient(135deg,var(--g1),var(--g2));color:var(--on-primary);box-shadow:0 6px 18px rgba(79,82,224,.28)}
.btn.sm{height:36px;padding:0 16px;font-size:14px}.btn.ghost{background:transparent;color:var(--text);box-shadow:inset 0 0 0 1px var(--line)}.btn.soft{background:var(--primary-soft);color:var(--primary);box-shadow:none}
.wrap{max-width:1120px;margin:0 auto;padding:0 24px}
h1{font-size:clamp(40px,6.4vw,72px);line-height:1.04;letter-spacing:-.035em;font-weight:700;text-wrap:balance}
h2{font-size:clamp(28px,3.6vw,44px);letter-spacing:-.03em;line-height:1.1;font-weight:700;text-wrap:balance}
.lead{font-size:clamp(18px,2vw,22px);color:var(--t2);max-width:640px;margin:18px auto 0;letter-spacing:-.01em}
.card{background:var(--surface);border-radius:22px;box-shadow:var(--shadow)}
.thumb{position:relative;aspect-ratio:16/9;border-radius:16px;overflow:hidden;background:#222 center/cover}
.thumb .dur{position:absolute;right:8px;bottom:8px;background:rgba(10,13,31,.72);color:#fff;font-size:12px;font-weight:600;padding:2px 7px;border-radius:7px}
.play{position:absolute;inset:0;display:grid;place-items:center}.play i{width:68px;height:68px;border-radius:50%;background:rgba(255,255,255,.88);display:grid;place-items:center;box-shadow:0 8px 30px rgba(0,0,0,.3)}.play svg{margin-left:4px}
.prompt{display:flex;gap:10px;align-items:flex-start;font-size:15px;color:var(--t2);margin-top:12px}.prompt b{color:var(--text);font-weight:600}
.pill{display:inline-flex;align-items:center;gap:8px;height:36px;padding:0 14px;border-radius:999px;background:var(--surface-2);font-size:14px;font-weight:500;color:var(--text)}
.pill.on{background:var(--primary-soft);color:var(--primary)}
.eyebrow{font-size:13px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--t3)}
.small{font-size:14px;color:var(--t2)}
section{padding:96px 0}
footer{padding:40px 0 56px;color:var(--t3);font-size:13px;text-align:center}
footer a{margin:0 10px}
.ic{width:20px;height:20px;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
/* app shell */
.shell{display:grid;grid-template-columns:232px 1fr;min-height:100vh}
.side{border-right:1px solid var(--line);padding:20px 14px;display:flex;flex-direction:column;gap:4px;background:var(--bg);position:sticky;top:0;height:100vh}
.side .brand{padding:6px 10px 18px}
.item{display:flex;align-items:center;gap:12px;height:40px;padding:0 12px;border-radius:12px;font-size:15px;font-weight:500;color:var(--t2)}
.item.on{background:var(--surface-2);color:var(--text)}
.main{padding:28px 40px 60px;max-width:1180px;width:100%}
.top{display:flex;align-items:center;gap:14px;margin-bottom:26px}
.top h1{font-size:32px;letter-spacing:-.025em}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:22px}
.vcard .t{font-weight:600;font-size:15px;margin-top:10px;letter-spacing:-.01em}.vcard .m{font-size:13px;color:var(--t3)}
.making{background:linear-gradient(135deg,var(--making1),var(--making2));color:#fff;border-radius:16px;aspect-ratio:16/9;padding:16px;display:flex;flex-direction:column;justify-content:space-between}
.bar{display:flex;gap:6px}.bar i{flex:1;height:3px;border-radius:2px;background:rgba(255,255,255,.3)}.bar i.d{background:#fff}
.tabbar{display:none}
@media(max-width:760px){
 body{font-size:16px}
 .links{display:none}.nav-in{padding:0 16px}
 .wrap{padding:0 16px}section{padding:56px 0}
 .shell{grid-template-columns:1fr}.side{display:none}
 .main{padding:16px 16px 96px}.top h1{font-size:28px}
 .grid{grid-template-columns:1fr 1fr;gap:14px}
 .tabbar{display:flex;position:fixed;bottom:0;left:0;right:0;height:72px;background:var(--glass);backdrop-filter:saturate(180%) blur(20px);border-top:1px solid var(--line);justify-content:space-around;padding-top:8px;font-size:11px;color:var(--t3);z-index:9}
 .tabbar div{display:flex;flex-direction:column;align-items:center;gap:3px}.tabbar .on{color:var(--primary)}
}
"""
def icon(n):
    P={"play":'<path d="M8 5.5v13l11-6.5z" fill="currentColor" stroke="none"/>',"plus":'<path d="M12 5v14M5 12h14"/>',"img":'<rect x="3" y="4" width="18" height="16" rx="3"/><circle cx="9" cy="10" r="1.6"/><path d="m21 16-5-5-9 9"/>',"slides":'<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',"mic":'<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',"share":'<path d="M12 15V4M8 8l4-4 4 4M5 12v7h14v-7"/>',"dots":'<circle cx="5" cy="12" r="1.4" fill="currentColor"/><circle cx="12" cy="12" r="1.4" fill="currentColor"/><circle cx="19" cy="12" r="1.4" fill="currentColor"/>',"search":'<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',"bolt":'<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',"video":'<rect x="3" y="6" width="13" height="12" rx="3"/><path d="m16 10 5-3v10l-5-3"/>',"coin":'<circle cx="12" cy="12" r="9"/><path d="M12 7v10M9.5 9.5h4a1.8 1.8 0 0 1 0 3.5h-3a1.8 1.8 0 0 0 0 3.5h4"/>',"gear":'<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1"/>',"cc":'<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M10 10a2 2 0 1 0 0 4M17 10a2 2 0 1 0 0 4"/>',"full":'<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',"chev":'<path d="m6 9 6 6 6-6"/>',"check":'<path d="m5 12 5 5 9-10"/>',"arrow":'<path d="M5 12h14M13 6l6 6-6 6"/>'}
    return f'<svg class="ic" viewBox="0 0 24 24">{P[n]}</svg>'
def img(n): return f"file://{A}/{n}"
def bg(n): return f"background-image:url('{img(n)}')"
MARK = f"file://{A}/mark.svg"
def nav_marketing(lang="en"):
    return f'<header class="nav"><div class="nav-in"><a class="brand" href="#"><img src="{MARK}">videomk</a><nav class="links"><a>Gallery</a><a>Formats</a><a>Pricing</a><a>Help</a></nav><span class="sp"></span><a class="small" style="font-weight:500">Sign in</a><a class="btn sm">Open the app</a></div></header>'
SAMPLES=[
 ("How a forest breathes, for curious teenagers","1:31","16:9","forest_a.jpg","Narrated, pictures + AI clips"),
 ("Why is the sky blue? Explain it like a calm science teacher","1:00","16:9","cat_sky_1.jpg","Illustrations + diagram"),
 ("The history of the printing press in one minute","1:00","9:16","cat_history_1.jpg","Portrait for Reels and Shorts"),
 ("How compound interest grows €100 over 30 years","0:45","1:1","cat_money_1.jpg","Charts and counters"),
 ("A slow, soothing story about a lighthouse keeper","2:10","16:9","vector.jpg","Animated vector scenes"),
]
def sample_card(s, big=False, ar=None):
    p,d,a,i,m=s
    inner = {"16:9":"width:100%;aspect-ratio:16/9","9:16":"height:100%;aspect-ratio:9/16","1:1":"height:100%;aspect-ratio:1/1"}[a]
    return f'<div><div style="aspect-ratio:4/3;background:var(--surface-2);border-radius:20px;display:grid;place-items:center;overflow:hidden"><div class="thumb" style="{inner};{bg(i)};border-radius:{14 if a=="16:9" else 12}px"><div class="dur">{d}</div></div></div><div class="prompt"><span style="flex:1"><b>“{p}”</b><br><span class="small">{m} · {a}</span></span><a class="pill on" style="flex:none">Try {icon("arrow")}</a></div></div>'
def page_home(theme, phone):
    hero=SAMPLES[0]
    cards="".join(sample_card(s) for s in SAMPLES[1:])
    gal=f'<div style="display:grid;grid-template-columns:{"1fr" if phone else "repeat(2,1fr)"};gap:40px 28px;align-items:start">{cards}</div>'
    body=f'''<main>
<section style="padding-top:{56 if phone else 88}px;padding-bottom:40px;text-align:center"><div class="wrap">
<h1>Describe it.<br>Get the video.</h1>
<p class="lead">Type or say an idea. videomk writes it, narrates it and adds pictures, clips and music. Ready in minutes.</p>
<div class="card" style="max-width:720px;margin:36px auto 0;padding:10px 10px 10px 24px;display:flex;align-items:center;gap:12px;border-radius:999px"><span style="flex:1;text-align:left;color:var(--t3);font-size:{16 if phone else 18}px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">How do bees make honey?</span><a class="btn" style="height:48px">Create</a></div>
<p class="small" style="margin-top:14px">Free to start · 5 credits on sign-up · no card</p>
</div></section>
<section style="padding-top:24px;padding-bottom:24px"><div class="wrap">
<div class="card" style="padding:{12 if phone else 18}px;border-radius:28px"><div class="thumb" style="{bg(hero[3])};border-radius:20px"><div class="play"><i>{icon("play")}</i></div><div class="dur">{hero[1]}</div></div>
<div class="prompt" style="padding:6px 6px 4px;margin-top:14px;font-size:{15 if phone else 17}px"><span style="flex:1"><span class="eyebrow">The prompt</span><br><b>“{hero[0]}”</b></span><a class="btn sm" style="flex:none">Try this prompt</a></div></div></div></section>
<section><div class="wrap"><div style="text-align:center;margin-bottom:48px"><h2>One sentence in. Any style out.</h2><p class="lead">Every video below came from a single prompt. Tap Try to make your own version.</p></div>{gal}</div></section>
<section style="background:var(--surface-2)"><div class="wrap"><div style="text-align:center;margin-bottom:40px"><h2>For every screen</h2><p class="lead">Pick where it will play and videomk sets the format, length and resolution for you.</p></div>
<div style="display:flex;flex-wrap:wrap;gap:12px;justify-content:center"><span class="pill on">YouTube · 16:9 · up to 4K</span><span class="pill">TikTok · 9:16</span><span class="pill">Instagram · 4:5</span><span class="pill">LinkedIn · 1:1</span><span class="pill">Shorts · 9:16</span></div></div></section>
<section><div class="wrap" style="display:grid;grid-template-columns:{"1fr" if phone else "repeat(3,1fr)"};gap:32px;text-align:left">
{"".join(f'<div><div class="eyebrow">{n}</div><h3 style="font-size:24px;letter-spacing:-.02em;margin:8px 0">{t}</h3><p class="small" style="font-size:16px">{d}</p></div>' for n,t,d in [("01","Say it","One sentence, a few photos or a presentation."),("02","We make it","Script, voice, pictures, clips and music, in minutes."),("03","Share it","Edit any scene, then post or save it.")])}</div></section>
<section style="background:var(--surface-2)"><div class="wrap" style="text-align:center"><h2>Simple credits</h2><p class="lead">1 credit makes up to a minute of video. New accounts get 5 credits, plus 1 free every day.</p><p style="margin-top:28px"><a class="btn">Start free</a></p></div></section>
<section><div class="wrap" style="max-width:760px"><h2 style="text-align:center;margin-bottom:32px">Questions</h2>{"".join(f'<div style="padding:20px 0;border-top:1px solid var(--line)"><b style="font-size:18px">{q}</b><p class="small" style="font-size:16px;margin-top:6px">{a}</p></div>' for q,a in [("Who owns my videos?","You do. Images and clips come from licensed sources or ones we create."),("Which languages?","English and Spanish narration, in the app and on the web."),("Can I use my own photos?","Yes, up to 100 per video, or a PowerPoint or PDF.")])}</div></section>
</main><footer><div class="wrap"><a>Privacy</a><a>Terms</a><a>Support</a><a>Delete account</a><a>English · Español</a><p style="margin-top:14px">A product of Agilegency Ltd · Registered in England, 16838077</p></div></footer>'''
    return nav_marketing()+body
def side(active):
    items=[("video","Videos"),("img","Media"),("coin","Credits"),("gear","Settings")]
    s="".join(f'<a class="item{" on" if n==active else ""}">{icon(i)}{n}</a>' for i,n in items)
    return f'<aside class="side"><a class="brand"><img src="{MARK}">videomk</a>{s}<span class="sp"></span><a class="item" style="color:var(--text)">{icon("bolt")}3 credits</a><a class="item">chris@example.com</a></aside>'
def tabbar(active):
    items=[("video","Videos"),("img","Media"),("plus","New"),("coin","Credits"),("gear","Settings")]
    return '<div class="tabbar">'+"".join(f'<div class="{"on" if n==active else ""}">{icon(i)}{n}</div>' for i,n in items)+"</div>"
def page_videos(theme, phone):
    vids=[("Why the sky is blue","2 h ago · 1:31","cat_sky_1.jpg"),("The history of the printing press","5 h ago · 3:02","cat_history_1.jpg"),("What is photosynthesis","2 days · 1:00","cat_nature_1.jpg"),("Mortgage rates for first-time buyers","3 days · 5:12","cat_money_1.jpg"),("A lighthouse keeper's story","4 days · 2:10","vector.jpg"),("How bees make honey","5 days · 1:15","cat_animals_1.jpg")]
    making='<div class="making"><div style="display:flex;justify-content:space-between;font-size:13px;font-weight:600"><span>Making</span><span style="opacity:.8">about 3 min</span></div><div><div style="font-weight:600;font-size:16px;margin-bottom:10px">How a forest breathes</div><div class="bar"><i class="d"></i><i></i><i></i><i></i></div><div style="font-size:12px;opacity:.85;margin-top:6px">Writing the script</div></div></div>'
    cards="".join(f'<div class="vcard"><div class="thumb" style="{bg(i)}"><div class="dur">{m.split("· ")[1]}</div></div><div class="t">{t}</div><div class="m">{m.split(" ·")[0]}</div></div>' for t,m,i in vids)
    srch="" if phone else '<span class="pill">'+icon("search")+'Search</span>'
    head=f'<div class="top"><h1>Videos</h1><span class="sp"></span>{srch}<a class="btn sm">{icon("plus")}New video</a></div>'
    main=f'<div class="main">{head}<div class="grid"><div>{making}<div class="vcard"><div class="t">How a forest breathes</div></div></div>{cards}</div></div>'
    return f'<div class="shell">{side("Videos")}{main}</div>{tabbar("Videos")}'
def page_create(theme, phone, popover=False):
    pop=''
    if popover and not phone:
        pop=f'''<div class="card" style="position:absolute;left:24px;top:calc(100% + 10px);width:380px;padding:20px;z-index:3"><div class="eyebrow" style="margin-bottom:10px">Made for</div><div style="display:flex;gap:8px;flex-wrap:wrap"><span class="pill on">YouTube</span><span class="pill">TikTok</span><span class="pill">Instagram</span><span class="pill">LinkedIn</span></div>
<div class="eyebrow" style="margin:18px 0 10px">Length</div><div style="display:flex;gap:8px;flex-wrap:wrap"><span class="pill">30 s</span><span class="pill">1 min</span><span class="pill">2 min</span><span class="pill on">5 min</span><span class="pill">10 min</span></div>
<div class="eyebrow" style="margin:18px 0 10px">Quality</div><div style="display:flex;gap:8px"><span class="pill">720p</span><span class="pill on">1080p</span><span class="pill">4K · 2x</span></div>
<div style="display:flex;justify-content:space-between;align-items:center;margin-top:20px;padding-top:16px;border-top:1px solid var(--line)"><span>Captions</span><span style="width:46px;height:28px;border-radius:99px;background:var(--primary);position:relative"><i style="position:absolute;right:3px;top:3px;width:22px;height:22px;border-radius:50%;background:#fff"></i></span></div>
<p class="small" style="margin-top:12px">Voice, music and style are chosen for you. Change them later in the editor.</p></div>'''
    comp=f'''<div style="position:relative;max-width:760px;margin:0 auto"><div class="card" style="padding:22px 22px 16px;border-radius:28px">
<div style="font-size:{22 if phone else 26}px;letter-spacing:-.02em;min-height:{110 if phone else 130}px;color:var(--text)">How a forest breathes, for curious teenagers<span style="display:inline-block;width:2px;height:1.1em;background:var(--primary);vertical-align:text-bottom;margin-left:2px"></span></div>
<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap"><span class="pill" style="width:36px;padding:0;justify-content:center" title="Photos">{icon("img")}</span><span class="pill" style="width:36px;padding:0;justify-content:center" title="Presentation">{icon("slides")}</span><span class="pill" style="width:36px;padding:0;justify-content:center" title="Dictate">{icon("mic")}</span><span class="pill{" on" if popover else ""}">YouTube · 5 min · 1080p {icon("chev")}</span><span class="sp"></span><a class="btn" style="height:44px">Create · 5 {icon("bolt")}</a></div></div>{pop}</div>'''
    sugg='<div style="display:flex;gap:10px;flex-wrap:wrap;justify-content:center;margin-top:'+("200px" if popover and not phone else "28px")+'">'+"".join(f'<span class="pill">{t}</span>' for t in ["How bees make honey, for kids","A calm story about a lighthouse keeper","How a bank loan works"])+"</div>"
    main=f'<div class="main" style="margin:0 auto;padding-top:{40 if phone else 120}px"><div style="text-align:center;margin-bottom:{28 if phone else 40}px"><h1 style="font-size:{34 if phone else 52}px">What should we make?</h1></div>{comp}{sugg}</div>'
    return f'<div class="shell">{side("Videos")}{main}</div>{tabbar("New")}'
def page_player(theme, phone):
    ctrl=f'<div style="position:absolute;left:0;right:0;bottom:0;padding:14px 18px;background:linear-gradient(transparent,rgba(0,0,0,.6));display:flex;align-items:center;gap:14px;color:#fff"><span>{icon("play")}</span><span style="font-size:13px;font-variant-numeric:tabular-nums">0:13</span><span style="flex:1;height:4px;border-radius:2px;background:rgba(255,255,255,.35);position:relative"><i style="position:absolute;left:0;top:0;bottom:0;width:14%;background:#fff;border-radius:2px"></i></span><span style="font-size:13px">1:31</span><span>{icon("cc")}</span><span>{icon("full")}</span></div>'
    player=f'<div class="thumb" style="{bg("forest_a.jpg")};border-radius:20px;box-shadow:var(--shadow)">{ctrl}</div>'
    scenes="".join(f'<div style="display:flex;gap:12px;align-items:center;padding:8px 0"><div class="thumb" style="width:84px;flex:none;border-radius:10px;{bg(i)}"></div><div style="flex:1"><div style="font-size:14px;font-weight:600">{t}</div><div class="m small">{s}</div></div></div>' for t,s,i in [("Intro","0:00","forest_a.jpg"),("Leaves breathe","0:12","clip05.jpg"),("The carbon cycle","0:38","forest_b.jpg"),("Why it matters","1:05","clip08.jpg")])
    side_col=f'<div><div class="eyebrow">The prompt</div><p style="margin-top:6px;font-size:16px">“How a forest breathes, for curious teenagers”</p><a class="small" style="color:var(--primary);font-weight:600;display:inline-block;margin-top:8px">Make another version</a><div class="eyebrow" style="margin-top:26px">Scenes</div><div style="margin-top:6px">{scenes}</div></div>'
    actions=f'<div style="display:flex;gap:10px;align-items:center;margin-top:18px"><a class="btn">{icon("share")}Share</a><a class="btn ghost">Save video</a><a class="btn ghost" style="width:44px;padding:0">{icon("dots")}</a></div>'
    head=f'<div style="margin-bottom:16px"><a class="small">‹ Videos</a><h1 style="font-size:{26 if phone else 34}px;letter-spacing:-.025em;margin-top:6px">How a forest breathes</h1><div class="small">1:31 · 1080p · English · 4 credits</div></div>'
    grid=f'<div style="display:grid;grid-template-columns:{"1fr" if phone else "minmax(0,1fr) 320px"};gap:36px">{"<div>"+player+actions+"</div>"}{side_col}</div>'
    return f'<div class="shell">{side("Videos")}<div class="main">{head}{grid}</div></div>{tabbar("Videos")}'
def page_media(theme, phone):
    ims=[f"cat_{c}_{n}.jpg" for c in ["nature","sky","travel","food","city","animals","science","mood","work","history"] for n in (1,)]+["cat_nature_2.jpg","cat_sky_2.jpg"]
    tiles="".join(f'<div class="thumb" style="aspect-ratio:1;border-radius:12px;{bg(i)}"></div>' for i in ims*2)
    chips='<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:20px"><span class="pill on">All</span><span class="pill">2026</span><span class="pill">Thailand</span><span class="pill">Collections</span></div>'
    head=f'<div class="top"><h1>Media</h1><span class="sp"></span><a class="btn sm">{icon("plus")}Add photos</a></div><div class="pill" style="width:100%;height:46px;border-radius:14px;margin-bottom:16px;color:var(--t3)">{icon("search")}Search your photos, “Thailand 2024”</div>{chips}'
    g=f'<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax({96 if phone else 150}px,1fr));gap:6px">{tiles}</div>'
    sel='<div class="card" style="position:fixed;left:50%;transform:translateX(-50%);bottom:'+("88px" if phone else "28px")+';padding:10px 14px;display:flex;gap:10px;align-items:center;border-radius:999px"><b style="font-size:14px;padding:0 6px">12 selected</b><a class="btn sm">Make a video</a><a class="btn sm ghost">Add to collection</a></div>'
    return f'<div class="shell">{side("Media")}<div class="main">{head}{g}</div></div>{sel}{tabbar("Media")}'
def page_signin(theme, phone):
    left=f'<div style="{bg("forest_a.jpg")};background-size:cover;min-height:{240 if phone else 100}vh;position:relative"><div style="position:absolute;left:32px;bottom:32px;right:32px;color:#fff;text-shadow:0 2px 20px rgba(0,0,0,.4);font-size:22px;letter-spacing:-.02em">“How a forest breathes, for curious teenagers”<div style="font-size:14px;opacity:.85;margin-top:6px">Made with videomk</div></div></div>'
    form=f'<div style="display:flex;flex-direction:column;justify-content:center;padding:{32 if phone else 72}px;max-width:520px;margin:0 auto;width:100%;min-height:{"auto" if phone else "100vh"}"><a class="brand" style="margin-bottom:32px"><img src="{MARK}">videomk</a><h1 style="font-size:38px;letter-spacing:-.03em">Welcome</h1><p class="small" style="font-size:17px;margin:8px 0 28px">Sign in to make and keep your videos.</p><a class="btn ghost" style="height:50px;margin-bottom:12px">Continue with Google</a><a class="btn ghost" style="height:50px;margin-bottom:12px">Continue with Apple</a><div class="small" style="text-align:center;margin:10px 0">or</div><a class="btn" style="height:50px">Continue with email</a><p class="small" style="margin-top:24px;font-size:13px">By continuing you accept the Terms and the Privacy Policy.</p></div>'
    if phone: return f'<div>{form}{left.replace("min-height:240vh","min-height:260px")}</div>'
    return f'<div style="display:grid;grid-template-columns:1.1fr 1fr">{left}{form}</div>'
PAGES={"home":page_home,"videos":page_videos,"create":page_create,"create_options":lambda t,p:page_create(t,p,True),"player":page_player,"media":page_media,"signin":page_signin}
if __name__=="__main__":
    out=sys.argv[1]; os.makedirs(out,exist_ok=True)
    for name,fn in PAGES.items():
        for theme in ("light","dark"):
            for phone in (False,True):
                if name=="create_options" and phone: continue
                html=f'<!doctype html><html data-theme="{theme}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>{CSS}</style></head><body>{fn(theme,phone)}</body></html>'
                open(f"{out}/{name}__{'phone' if phone else 'desktop'}__{theme}.html","w").write(html)
    print("ok")
