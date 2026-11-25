#!/usr/bin/env python3
"""Builds the human review sheet from the saved audit runs (no network, no cost).

  python backend/scripts/audit_review.py      ->  docs/audit/2026-11-25/review.html (self-contained, offline) and review.md (plain fallback)
"""
import html
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "docs", "audit", "2026-11-25")
sys.path.insert(0, HERE)
import quality_audit as qa  # noqa: E402

RUBRIC = [
    ("accuracy", "Accuracy", "5 = every fact you can check is right and nothing looks invented. 3 = mostly right, one doubtful or vague claim. 1 = wrong facts a viewer would repeat."),
    ("depth", "Depth", "5 = I learned something I could not have guessed, right for the length. 3 = correct but generic. 1 = filler."),
    ("flow", "Clarity / flow", "5 = clear order, each part builds on the last, easy to follow by ear. 3 = understandable but uneven or repetitive. 1 = confusing."),
    ("hook_ending", "Hook / ending", "5 = the first line makes me want to hear more and the ending lands. 3 = ordinary start or a recap ending. 1 = greeting / 'thanks for watching' / abrupt."),
    ("naturalness", "Naturalness (Spanish only)", "5 = indistinguishable from a native writer. 3 = understandable, a few stiff or translated phrases. 1 = clearly machine translated."),
]


def card_data(run):
    plan = run.get("plan") or {}
    rules = run.get("rules") or {}
    judge = run.get("judge") or {}
    return {
        "id": run["id"], "category": run["category"], "language": run["language"], "minutes": run["minutes"], "difficulty": run.get("difficulty"), "prompt": run["prompt"],
        "title": plan.get("title"), "error": run.get("error"),
        "beats": [{"n": i + 1, "scene": (b.get("scene") or {}).get("type"), "chapter": b.get("chapter"), "text": b.get("narration", "")} for i, b in enumerate(plan.get("beats") or [])],
        "sources": [{"title": s.get("title"), "url": s.get("url")} for s in plan.get("sources") or []],
        "research": {k: (run.get("research") or {}).get(k) for k in ("mode", "searches", "reads", "notes_len")},
        "auto": {"flags": rules.get("flags", []), "words": (rules.get("length") or {}).get("words"), "expected_words": (rules.get("length") or {}).get("expected_words"),
                 "ungrounded_share": (rules.get("grounding") or {}).get("ungrounded_share"), "ungrounded": ((rules.get("grounding") or {}).get("ungrounded_numbers") or [])[:8] + ((rules.get("grounding") or {}).get("ungrounded_entities") or [])[:8],
                 "scene_types": (rules.get("variety") or {}).get("distinct"), "cost": (run.get("cost") or {}).get("total"), "seconds": (run.get("timings") or {}).get("total_s"),
                 "judge": {k: v["score"] for k, v in (judge.get("scores") or {}).items()}, "judge_mean": judge.get("mean"), "judge_publish": judge.get("would_publish"),
                 "judge_summary": judge.get("summary"), "defects": [f"[{d.get('severity')}] \"{d.get('quote')}\": {d.get('issue')}" for d in (judge.get("defects") or [])[:6]]},
    }


def ordered(runs):
    ok = [r for r in runs if r.get("plan")]
    return sorted(ok, key=lambda r: (r["language"] != "es", r["category"], r["id"]))


HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>videomk quality review</title>
<style>
:root{--bg:#fafaf7;--fg:#1d1d1b;--mut:#66665f;--card:#fff;--line:#dcdcd4;--acc:#1f5fbf;--es:#c2410c;--ok:#15803d;--bad:#b91c1c}
@media (prefers-color-scheme:dark){:root{--bg:#161614;--fg:#ecece6;--mut:#a0a09a;--card:#1f1f1c;--line:#3a3a35;--acc:#7aa7ff;--es:#fb923c;--ok:#4ade80;--bad:#f87171}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 16px;display:flex;flex-wrap:wrap;gap:10px;align-items:center}
header h1{font-size:18px;margin:0 8px 0 0}.bar{flex:1;min-width:140px;height:8px;background:var(--line);border-radius:4px;overflow:hidden}.bar i{display:block;height:100%;background:var(--ok);width:0}
button,select,textarea{font:inherit;color:inherit}button{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:6px 12px;cursor:pointer}button:hover{border-color:var(--acc)}
main{max-width:900px;margin:0 auto;padding:16px}.intro{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin-bottom:16px;font-size:14px}
.intro dt{font-weight:600;margin-top:6px}.intro dd{margin:0;color:var(--mut)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:0 0 18px;break-inside:avoid}.card.done{border-left:5px solid var(--ok)}
.meta{display:flex;flex-wrap:wrap;gap:6px;font-size:13px;color:var(--mut);margin-bottom:6px}.tag{border:1px solid var(--line);border-radius:999px;padding:1px 9px}.tag.es{color:var(--es);border-color:var(--es);font-weight:600}
.prompt{font-size:17px;font-weight:600;margin:4px 0}.title{color:var(--mut);margin:0 0 8px}
details{margin:8px 0}summary{cursor:pointer;color:var(--acc);font-weight:600}.beat{padding:6px 0;border-top:1px dashed var(--line)}.beat b{display:inline-block;min-width:96px;color:var(--mut);font-weight:500;font-size:13px}
.chap{font-weight:700;margin-top:8px}.src a{color:var(--acc);word-break:break-all}.flags span{display:inline-block;background:color-mix(in srgb,var(--bad) 14%,transparent);color:var(--bad);border-radius:6px;padding:0 7px;margin:2px 4px 2px 0;font-size:13px}
.rate{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:12px}.rate label{font-size:13px;color:var(--mut);display:block}
.rate .row{display:flex;gap:4px;margin-top:3px}.rate .row button{padding:4px 0;flex:1;min-width:0}.rate .row button.on{background:var(--acc);color:#fff;border-color:var(--acc)}
.pub{margin-top:10px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}.pub button.on.yes{background:var(--ok);color:#fff;border-color:var(--ok)}.pub button.on.no{background:var(--bad);color:#fff;border-color:var(--bad)}
textarea{width:100%;min-height:64px;margin-top:10px;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:8px}
.es-note{color:var(--es);font-weight:600;font-size:13px}.small{font-size:13px;color:var(--mut)}.hidden{display:none}
@media print{header{position:static}header button{display:none}.card{border:1px solid #999}body{background:#fff;color:#000}}
</style></head><body>
<header><h1>Quality review</h1><span id="count" class="small"></span><div class="bar"><i id="barfill"></i></div>
<button id="onlyes">Spanish only</button><button id="todo">Unrated only</button><button id="expand">Expand all</button><button id="exj">Export JSON</button><button id="exc">Export CSV</button><button id="imp">Import JSON</button><input type="file" id="file" accept=".json" class="hidden"></header>
<main>
<div class="intro"><b>How to use.</b> One card per video script. Read the prompt, open the narration, and score what you see. Your answers save in this browser automatically; you can close the page and continue later. Use <b>Export</b> when you finish (and now and then as a backup). The automatic scores are hidden under each card so they do not bias you: open them after rating.
<dl id="rubric"></dl></div>
<div id="cards"></div></main>
<script id="data" type="application/json">__DATA__</script>
<script id="rubricdata" type="application/json">__RUBRIC__</script>
<script>
(function(){
var CARDS=JSON.parse(document.getElementById('data').textContent), RUB=JSON.parse(document.getElementById('rubricdata').textContent);
var KEY='videomk-quality-review-2026-11-25', S={};
try{S=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){S={}}
function save(){try{localStorage.setItem(KEY,JSON.stringify(S))}catch(e){}}
function el(t,c,x){var e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e}
var dl=document.getElementById('rubric');RUB.forEach(function(r){dl.appendChild(el('dt',null,r[1]));dl.appendChild(el('dd',null,r[2]))});
var wrap=document.getElementById('cards');
function isDone(c){var s=S[c.id]||{};var need=['accuracy','depth','flow','hook_ending'].concat(c.language==='es'?['naturalness']:[]);return need.every(function(k){return s[k]})&&!!s.publish}
function progress(){var n=CARDS.filter(isDone).length;document.getElementById('count').textContent=n+' / '+CARDS.length+' done';document.getElementById('barfill').style.width=(100*n/CARDS.length)+'%'}
CARDS.forEach(function(c,idx){
  var card=el('section','card');card.id='c-'+c.id;card.dataset.lang=c.language;
  var m=el('div','meta');m.appendChild(el('span','tag',(idx+1)+'/'+CARDS.length));m.appendChild(el('span','tag'+(c.language==='es'?' es':''),c.language==='es'?'ESPAÑOL - please check naturalness':'English'));
  m.appendChild(el('span','tag',c.category));m.appendChild(el('span','tag',c.minutes+' min'));m.appendChild(el('span','tag',c.id));card.appendChild(m);
  card.appendChild(el('div','prompt',c.prompt));card.appendChild(el('div','title','Generated title: '+(c.title||'-')));
  var d=el('details');d.appendChild(el('summary',null,'Narration ('+c.beats.length+' beats)'));
  c.beats.forEach(function(b){if(b.chapter)d.appendChild(el('div','chap',b.chapter));var r=el('div','beat');r.appendChild(el('b',null,b.n+'. ['+b.scene+']'));r.appendChild(document.createTextNode(' '+b.text));d.appendChild(r)});
  card.appendChild(d);
  var sd=el('details');sd.appendChild(el('summary',null,'Sources ('+c.sources.length+') and research'));
  var ri=el('div','small','Research: '+(c.research.mode||'?')+', '+(c.research.searches||0)+' searches, '+(c.research.reads||0)+' page reads, notes '+(c.research.notes_len||0)+' characters');sd.appendChild(ri);
  c.sources.forEach(function(s){var p=el('div','src');p.appendChild(document.createTextNode(s.title+' - '));var a=el('a',null,s.url);a.href=s.url;a.target='_blank';a.rel='noopener noreferrer';p.appendChild(a);sd.appendChild(p)});
  if(!c.sources.length)sd.appendChild(el('div','small','No sources cited.'));card.appendChild(sd);
  var ad=el('details');ad.appendChild(el('summary',null,'Automatic scores (open after you rate)'));var a=c.auto;
  var jl=Object.keys(a.judge||{}).map(function(k){return k+' '+a.judge[k]}).join(' | ');
  ad.appendChild(el('div','small','Words '+a.words+' of about '+a.expected_words+' expected; scene types '+a.scene_types+'; ungrounded numbers/names '+Math.round((a.ungrounded_share||0)*100)+'%; cost $'+(a.cost||0).toFixed(3)+'; '+Math.round(a.seconds||0)+' s'));
  var fl=el('div','flags');(a.flags||[]).forEach(function(f){fl.appendChild(el('span',null,f))});ad.appendChild(fl);
  if(a.ungrounded&&a.ungrounded.length)ad.appendChild(el('div','small','Not found in the research notes: '+a.ungrounded.join(', ')));
  ad.appendChild(el('div','small','Judge (1-5): '+(jl||'none')+(a.judge_mean?' | mean '+a.judge_mean:'')+(a.judge_publish===false?' | would not publish':'')));
  if(a.judge_summary)ad.appendChild(el('div','small',a.judge_summary));
  (a.defects||[]).forEach(function(x){ad.appendChild(el('div','small','- '+x))});card.appendChild(ad);
  var rate=el('div','rate');var s=S[c.id]=S[c.id]||{};
  RUB.forEach(function(r){if(r[0]==='naturalness'&&c.language!=='es')return;var box=el('div');var lb=el('label',null,r[1]);lb.title=r[2];box.appendChild(lb);var row=el('div','row');
    for(var v=1;v<=5;v++)(function(v){var b=el('button',s[r[0]]===v?'on':'',String(v));b.type='button';b.onclick=function(){s[r[0]]=(s[r[0]]===v?0:v);save();Array.prototype.forEach.call(row.children,function(x,i){x.className=(s[r[0]]===i+1?'on':'')});upd()};row.appendChild(b)})(v);
    box.appendChild(row);rate.appendChild(box)});card.appendChild(rate);
  var pub=el('div','pub');pub.appendChild(el('b',null,'Would you publish this?'));
  ['yes','no'].forEach(function(v){var b=el('button',(s.publish===v?'on ':'')+v,v);b.type='button';b.onclick=function(){s.publish=(s.publish===v?'':v);save();Array.prototype.forEach.call(pub.querySelectorAll('button'),function(x){x.className=(s.publish===x.textContent?'on ':'')+x.textContent});upd()};pub.appendChild(b)});card.appendChild(pub);
  var ta=el('textarea');ta.placeholder='Comment: what is wrong or great, quote the line if you can';ta.value=s.comment||'';ta.oninput=function(){s.comment=ta.value;save()};card.appendChild(ta);
  card._upd=function(){card.className='card'+(isDone(c)?' done':'')};card._upd();wrap.appendChild(card)});
function upd(){Array.prototype.forEach.call(wrap.children,function(c){c._upd()});progress();filt()}
var onlySp=false,onlyTodo=false;function filt(){CARDS.forEach(function(c){var e=document.getElementById('c-'+c.id);e.classList.toggle('hidden',(onlySp&&c.language!=='es')||(onlyTodo&&isDone(c)))})}
document.getElementById('onlyes').onclick=function(){onlySp=!onlySp;this.style.borderColor=onlySp?'var(--acc)':'';filt()};
document.getElementById('todo').onclick=function(){onlyTodo=!onlyTodo;this.style.borderColor=onlyTodo?'var(--acc)':'';filt()};
var ex=false;document.getElementById('expand').onclick=function(){ex=!ex;Array.prototype.forEach.call(document.querySelectorAll('details'),function(d){d.open=ex});this.textContent=ex?'Collapse all':'Expand all'};
function dl_(name,text,type){var a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type:type}));a.download=name;document.body.appendChild(a);a.click();setTimeout(function(){URL.revokeObjectURL(a.href);a.remove()},500)}
function rows(){return CARDS.map(function(c){var s=S[c.id]||{};return {id:c.id,language:c.language,category:c.category,minutes:c.minutes,prompt:c.prompt,title:c.title,accuracy:s.accuracy||'',depth:s.depth||'',flow:s.flow||'',hook_ending:s.hook_ending||'',naturalness:c.language==='es'?(s.naturalness||''):'',publish:s.publish||'',comment:s.comment||'',judge_mean:c.auto.judge_mean||'',flags:(c.auto.flags||[]).join(' ')}})}
document.getElementById('exj').onclick=function(){dl_('review-answers.json',JSON.stringify(rows(),null,1),'application/json')};
document.getElementById('exc').onclick=function(){var r=rows(),k=Object.keys(r[0]);var q=function(v){return '"'+String(v).replace(/"/g,'""')+'"'};dl_('review-answers.csv','﻿'+[k.join(',')].concat(r.map(function(x){return k.map(function(h){return q(x[h])}).join(',')})).join('\n'),'text/csv')};
document.getElementById('imp').onclick=function(){document.getElementById('file').click()};
document.getElementById('file').onchange=function(){var f=this.files[0];if(!f)return;var rd=new FileReader();rd.onload=function(){try{JSON.parse(rd.result).forEach(function(x){var s=S[x.id]=S[x.id]||{};['accuracy','depth','flow','hook_ending','naturalness'].forEach(function(k){if(x[k])s[k]=Number(x[k])});if(x.publish)s.publish=x.publish;if(x.comment)s.comment=x.comment});save();location.reload()}catch(e){alert('Not a valid export file')}};rd.readAsText(f)};
window.addEventListener('beforeprint',function(){Array.prototype.forEach.call(document.querySelectorAll('details'),function(d){d.open=true})});
progress();
})();
</script></body></html>"""


def build_html(runs):
    cards = [card_data(r) for r in ordered(runs)]
    data = json.dumps(cards, ensure_ascii=False).replace("</", "<\\/")
    rub = json.dumps(RUBRIC, ensure_ascii=False).replace("</", "<\\/")
    return HTML.replace("__DATA__", data).replace("__RUBRIC__", rub)


def build_md(runs):
    out = ["# Human review sheet (plain fallback)", "",
           "Fill the scores after each script. Scale 1 to 5 (anchors below). Spanish items come first. For the interactive version open `review.html`.", ""]
    for key, name, anchor in RUBRIC:
        out.append(f"- **{name}**: {anchor}")
    out.append("")
    for i, r in enumerate(ordered(runs), 1):
        c = card_data(r)
        out += [f"---", "", f"## {i}. [{c['id']}] {c['prompt']}", "", f"{'ESPAÑOL - revisar naturalidad. ' if c['language'] == 'es' else ''}Category: {c['category']} | {c['minutes']} min | language: {c['language']}", "",
                f"Generated title: **{c['title']}**", "", "Narration:", ""]
        for b in c["beats"]:
            out.append(f"{b['n']}. `{b['scene']}`{(' (chapter: ' + b['chapter'] + ')') if b.get('chapter') else ''} {b['text']}")
        out += ["", "Sources: " + ("; ".join(f"{s['title']} <{s['url']}>" for s in c["sources"]) or "none cited"), "",
                f"Automatic: flags = {', '.join(c['auto']['flags']) or 'none'}; judge mean = {c['auto']['judge_mean']}; ungrounded numbers/names = {round((c['auto']['ungrounded_share'] or 0) * 100)}%", "",
                "| Accuracy | Depth | Clarity/flow | Hook/ending | Naturalness (ES) | Publish? |", "|---|---|---|---|---|---|", "| | | | | " + ("" if c["language"] == "es" else "n/a") + " | yes / no |", "", "Comment:", "", ""]
    return "\n".join(out)


def main():
    runs = qa.load_runs()
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "review.html"), "w", encoding="utf-8") as f:
        f.write(build_html(runs))
    with open(os.path.join(OUT, "review.md"), "w", encoding="utf-8") as f:
        f.write(build_md(runs))
    print(f"review sheet for {len(ordered(runs))} scripts written to {os.path.abspath(OUT)}")


if __name__ == "__main__":
    main()
