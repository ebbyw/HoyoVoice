"""HoyoVoice dashboard — local web UI served from live.py.

Log (with voice used + screenshot hover-previews), casting with instant
re-read and per-character mute, pause/resume, test speech, analytics.
"""
import functools
import logging
import math
import os
import platform
import re
import socket
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from profiles import PROFILES, profile_choices

VERSION = "0.12.0"  # x-release-please-version


@functools.lru_cache(maxsize=1)
def _build_id():
    """VERSION plus the git commit it is actually running from —
    "0.11.0 (<sha>)", with "-dirty" when tracked files differ from it.

    LAZY and memoized, never at import: hoyovoice.py imports this module
    for two constants on every status/stop/log call, and the two git
    subprocesses measured ~180ms per CLI invocation — only a process
    that actually renders the dashboard or the log pays for the sha.

    VERSION only changes at release time, so a mid-cycle session
    otherwise reports the PREVIOUS release's number: the 2026-08-13
    Windows log said 0.10.4 while running ~45 commits past it, and the
    log couldn't say which fixes were actually in play. Git is how both
    machines deploy (fix in repo, push, pull), so it's present; anything
    going wrong falls back to the bare version. -uno on the dirty check:
    tracked modifications only — untracked local files (voices.json is
    gitignored anyway, but notes and scratch aren't) don't mean the CODE
    differs from the sha."""
    import shutil
    import subprocess
    # (imports local: this runs at most once, and CLI invocations that
    # never render skip it entirely)
    # absolute path, not bare "git": Windows CreateProcess searches the
    # application directory before PATH, so a git.exe dropped beside the
    # app would otherwise win
    git = shutil.which("git")
    if not git:
        return VERSION
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    kw = {"cwd": root, "capture_output": True, "text": True, "timeout": 5}
    if sys.platform == "win32":
        kw["creationflags"] = 0x08000000            # CREATE_NO_WINDOW
    try:
        # if this checkout is vendored inside some LARGER repo, rev-parse
        # walks up and reports that repo's sha and dirt — ours or nothing
        top = subprocess.run([git, "rev-parse", "--show-toplevel"],
                             **kw).stdout.strip()
        if not top or os.path.realpath(top) != os.path.realpath(root):
            return VERSION
        sha = subprocess.run([git, "rev-parse", "--short", "HEAD"],
                             **kw).stdout.strip()
        if not sha:
            return VERSION
        dirty = subprocess.run([git, "status", "--porcelain", "-uno"],
                               **kw).stdout.strip()
        return f"{VERSION} ({sha}{'-dirty' if dirty else ''})"
    except Exception:
        return VERSION


# single source of truth (hoyovoice.py reads it); env override lets
# tools/replay.py run beside a live instance without a port collision
DASHBOARD_PORT = int(os.environ.get("HOYOVOICE_PORT", "8470"))
# ffmpeg/format chatter that buries the interesting lines (hoyovoice.py
# imports this so the CLI and the download filter identically)
LOG_NOISE = re.compile(
    "pixel format|Supported|uyvy|yuyv|nv12|0rgb|bgr0|in#0|Fetching|vad: chunks")
LOG_TAIL_LINES = 4000
# ...and read at most this many bytes off the END of it. A session that
# runs all evening writes a console log of unbounded size, and the
# download read the whole thing into memory before filtering it down to
# the last 4000 lines — on the serving thread, with the dashboard polling
# it every second.
LOG_TAIL_BYTES = 8 << 20

VOICE_CATALOG = [
    "af_heart", "af_alloy", "af_aoede", "af_bella", "af_jessica", "af_kore",
    "af_nova", "af_river", "af_sarah", "af_sky",
    "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael",
    "am_onyx", "am_puck", "am_santa",
    "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
    "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
    # The model's non-English voices. Both runtimes pin the phonemizer to
    # American English (lang_code="a" / lang="en-us"), so these speak English
    # text as differently-accented speakers — a timbre choice, not a language
    # switch. Prefixes: e Spanish, f French, h Hindi, i Italian, j Japanese,
    # p Portuguese, z Mandarin.
    "ef_dora", "em_alex", "em_santa",
    "ff_siwis",
    "hf_alpha", "hf_beta", "hm_omega", "hm_psi",
    "if_sara", "im_nicola",
    "jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro", "jm_kumo",
    "pf_dora", "pm_alex", "pm_santa",
    "zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi",
    "zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang",
]  # af_nicole omitted: broken in the packaged model

STYLE = """
body{font:14px -apple-system,sans-serif;background:#14151a;color:#e8e8ec;margin:0;padding:16px}
h1{font-size:18px;margin:0 0 12px}h2{font-size:14px;color:#9aa;margin:18px 0 6px}
h1 a{color:#8ab4f8;font-size:13px;font-weight:normal;text-decoration:none;margin-left:8px}
table{border-collapse:collapse;width:100%}td,th{padding:4px 8px;text-align:left;border-bottom:1px solid #26272e;vertical-align:top}
.act-spoken{color:#7ec97e}.act-skip{color:#888}.act-yield{color:#d9a441}.act-always{color:#888}
.act-choice{color:#8ab4f8}
select,input,button{background:#1e2027;color:#e8e8ec;border:1px solid #33353d;border-radius:6px;padding:4px 8px}
button{cursor:pointer}button:hover{border-color:#7ec97e}
a.btn{display:inline-block;background:#1e2027;color:#e8e8ec;border:1px solid #33353d;border-radius:6px;padding:4px 8px;font-size:13px;text-decoration:none}
a.btn:hover{border-color:#7ec97e}
.pill{display:inline-block;background:#1e2027;border-radius:10px;padding:2px 10px;margin:2px 6px 2px 0;font-size:12px}
#log.hidden{display:none}.muted{color:#778}.voice{color:#8ab4f8}
.live{color:#7ec97e}.paused{color:#e0605e}
.cols{display:flex;flex-wrap:wrap;gap:20px;align-items:flex-start;margin-top:8px}
.cols>div:first-child{flex:1;min-width:260px}
.cols>div:last-child{flex:0 1 480px;min-width:300px}
.castwrap{max-height:280px;overflow-y:auto;border:1px solid #26272e;border-radius:8px}
.castwrap table{margin:0}
#recordings{max-height:110px;overflow-y:auto;border:1px solid #26272e;border-radius:8px;padding:6px}
#recordings .pill{display:block;margin:2px 0;width:fit-content}
.shot{position:relative;text-decoration:none}
.shot img{display:none;position:absolute;right:0;bottom:22px;width:340px;border:1px solid #444;border-radius:6px;z-index:10}
.shot:hover img{display:block}
"""

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HoyoVoice</title><style>__STYLE__</style></head><body>
<h1>HoyoVoice <span class="muted" style="font-size:12px;font-weight:normal">v__VERSION__</span>
<button id="observeBtn" onclick="toggleObserve()">Pause</button>
<button id="recordBtn" onclick="toggleRecord()">⏺ Record</button></h1>

<div class="cols">
  <div>
    <div id="status" class="muted" style="font-size:16px;margin-bottom:10px"></div>
    <h2 style="margin-top:0">Analytics</h2><div id="metrics"></div>
    <h2>Casting <span class="muted">(muted = never speak for this character)</span></h2>
    <div style="margin-bottom:6px">
      <input id="castSearch" placeholder="search cast… (fuzzy: 'zhl' finds Zhongli)" size="28" autocomplete="off" oninput="filterCast()">
      <span id="castCount" class="muted"></span>
    </div>
    <div class="castwrap">
    <table id="casting"><thead><tr><th>character</th><th>voice</th><th>muted</th><th></th></tr></thead><tbody></tbody></table>
    </div>
    <div style="margin-top:8px">
      <span class="muted">Add cast</span>
      <input id="newChar" placeholder="exact nameplate name…" size="16" autocomplete="off">
      <select id="newVoice"></select>
      <button onclick="addChar()">Add</button>
    </div>
    <div style="margin-top:8px">
      <span class="muted">Test TTS</span>
      <input id="sayText" placeholder="type any line to hear it spoken…" size="28" autocomplete="off">
      <select id="sayVoice"></select>
      <button onclick="say()">Speak</button>
    </div>
    <div style="margin-top:8px">
      <a href="/voices" style="color:#8ab4f8" title="import Kokoro voice packs or blend the voices you have into new ones">Voice packs — add &amp; blend →</a>
    </div>
  </div>
  <div>
    <div style="margin-bottom:6px">
      <span class="muted">video</span> <select id="vidDev"></select>
      <span class="muted">audio</span> <select id="audDev"></select>
      <span class="muted" title="Where HoyoVoice speaks. Leave on System default to follow Windows.">speaks to</span>
      <select id="outDev"></select>
      <button onclick="applyDev()">Apply</button>
    </div>
    <div style="margin-bottom:6px">
      <span class="muted">game</span> <select id="gameSel" onchange="setGame()"></select>
      <span class="muted" id="gameActive"></span>
    </div>
    <a href="/live.jpg" target="_blank"><img id="preview" style="width:100%;border-radius:8px;border:1px solid #26272e"></a>
    <div id="previewOff" style="display:none;width:100%;aspect-ratio:16/9;border-radius:8px;border:1px solid #26272e;background:#0c0d10;color:#e0605e;align-items:center;justify-content:center;font-size:15px">feed paused</div>
    <div style="margin-top:6px"><span class="muted">recordings save to</span>
      <input id="recDir" size="24" autocomplete="off"><button onclick="setRecDir()">Set</button></div>
    <div id="recordings" class="muted" style="margin-top:6px">none yet</div>
  </div>
</div>

<h2>Log <button id="toggleLog" onclick="toggleLog()">Hide</button>
<button onclick="post('/api/clearlog',{})" title="Empty the log and forget the recent-lines window, so replayed content is read again instead of being skipped as a repeat">Clear</button>
<a class="btn" href="/log.txt" download title="Download this session's decisions + console log as a text file">⤓ Download log</a></h2>
<table id="log"><thead><tr><th>time</th><th>speaker</th><th>line</th><th>voice</th><th>action</th><th></th></tr></thead><tbody></tbody></table>

<script>
let hidden=false, observing=true, recOn=false, lastCastFp='';
let lastVoicesFp='', lastLogFp='';
function toggleRecord(){post('/api/record',{on:!recOn});}
function setRecDir(){post('/api/recdir',{dir:document.getElementById('recDir').value});}
function setGame(){post('/api/game',{game:document.getElementById('gameSel').value});}
function applyDev(){post('/api/device',{video:document.getElementById('vidDev').value,
  audio:document.getElementById('audDev').value,
  output:document.getElementById('outDev').value});}
async function loadDevices(){
  try{
    const d=await (await fetch('/api/devices')).json();
    const esc1=x=>x.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');
    const fill=(id,list,cur)=>{document.getElementById(id).innerHTML=
      list.map(x=>'<option'+(x===cur?' selected':'')+'>'+esc1(x)+'</option>').join('');};
    fill('vidDev',d.video,d.current_video);
    fill('audDev',d.audio,d.current_audio);
    // "" is a real option here: follow whatever Windows is set to
    const cur=d.current_output||'';
    let outs=d.output||[];
    // keep a chosen-but-missing device listed (unplugged headset) — dropping
    // it would silently reset the setting on the next Apply
    if(cur&&!outs.includes(cur)) outs=[cur+' (not found)'].concat(outs);
    document.getElementById('outDev').innerHTML=
      '<option value=""'+(cur?'':' selected')+'>System default</option>'+
      outs.map(x=>{const v=x.endsWith(' (not found)')?cur:x;
        return '<option value="'+esc1(v)+'"'+(v===cur?' selected':'')+
          '>'+esc1(x)+'</option>';}).join('');
  }catch(e){}
}
loadDevices();
setInterval(()=>{if(observing)document.getElementById('preview').src='/live.jpg?'+Date.now();},600);
function interacting(id){const el=document.getElementById(id);
  const a=document.activeElement;   // block only for open controls, not mere hover
  return a&&el.contains(a)&&(a.tagName==='SELECT'||a.tagName==='INPUT');}
function post(url,body){return fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});}
function toggleObserve(){post('/api/observe',{on:!observing});}
function toggleLog(){hidden=!hidden;document.getElementById('log').classList.toggle('hidden',hidden);
  document.getElementById('toggleLog').textContent=hidden?'Show':'Hide';}
function say(){post('/api/say',{text:document.getElementById('sayText').value,
  voice:document.getElementById('sayVoice').value});}
function addChar(){const n=document.getElementById('newChar').value.trim();
  if(!n) return;
  post('/api/assign',{character:n,voice:document.getElementById('newVoice').value});
  document.getElementById('newChar').value='';
  lastCastFp='';}
function replay(id){post('/api/replay',{id:id});}
// fuzzy match: substring anywhere, or query chars appearing in order
// ("zhl" finds Zhongli). Case-insensitive.
function fuzzy(q,s){
  if(s.includes(q)) return true;
  let i=0;
  for(const c of s){if(c===q[i])i++;}
  return i===q.length;}
function filterCast(){
  const q=document.getElementById('castSearch').value.trim().toLowerCase();
  let shown=0,total=0;
  for(const tr of document.querySelectorAll('#casting tbody tr')){
    total++;
    const hit=!q||fuzzy(q,decodeURIComponent(tr.dataset.ch||'').toLowerCase());
    tr.style.display=hit?'':'none';
    if(hit)shown++;}
  document.getElementById('castCount').textContent=
    q?(shown+' of '+total+(shown?'':' — no match')):'';}
function esc(s){const d=document.createElement('div');d.textContent=s??'';return d.innerHTML;}
document.addEventListener('change',e=>{
  const t=e.target;
  if(t.dataset.role==='cast'&&t.value)
    post('/api/assign',{character:decodeURIComponent(t.dataset.ch),voice:t.value});
  if(t.dataset.role==='default'&&t.value)
    post('/api/default',{slot:t.dataset.slot,voice:t.value});
  if(t.dataset.role==='mute')
    post('/api/mute',{character:decodeURIComponent(t.dataset.ch),muted:t.checked});
});
document.addEventListener('click',e=>{
  if(e.target.dataset.role==='del'){
    e.target.blur();
    lastCastFp='';   // force re-render on next poll
    post('/api/delete',{character:decodeURIComponent(e.target.dataset.ch)});
  }
});
async function tick(){
  try{
    const s=await (await fetch('/api/state')).json();
    observing=s.observing;
    document.getElementById('preview').style.display=observing?'':'none';
    document.getElementById('previewOff').style.display=observing?'none':'flex';
    document.getElementById('observeBtn').textContent=observing?'Pause':'Resume';
    const st=document.getElementById('status');
    st.textContent=(observing?'· live · ':'· PAUSED · ')+s.metrics.uptime;
    st.className=observing?'live':'paused';
    const gs=document.getElementById('gameSel');
    if(!gs.options.length)
      gs.innerHTML=s.game.choices.map(g=>'<option value="'+g[0]+'">'+esc(g[1])+'</option>').join('');
    if(document.activeElement!==gs) gs.value=s.game.setting;
    // in auto mode the detected game is what actually matters — show it
    document.getElementById('gameActive').textContent=
      s.game.setting==='auto'?'· reading as '+s.game.active:'';
    recOn=s.recording;
    const rb=document.getElementById('recordBtn');
    rb.textContent=recOn?'⏹ Stop recording':'⏺ Record';
    rb.style.borderColor=recOn?'#e0605e':'';
    const rd=document.getElementById('recDir');
    if(document.activeElement!==rd) rd.value=s.rec_dir;
    document.getElementById('recordings').innerHTML=
      s.recordings.length?s.recordings.map(r=>'<a class="pill" href="/recordings/'+
      encodeURIComponent(r.name)+'" download>'+r.name+' ('+r.mb+' MB)</a>').join(''):'none yet';
    const m=s.metrics;
    document.getElementById('metrics').innerHTML=
      ['vad '+m.vad,'spoken '+m.spoken,'skipped(voiced) '+m.skipped_voiced,'yielded '+m.yielded,
       'synth avg '+m.synth_avg_ms+'ms','ocr avg '+m.ocr_avg_ms+'ms',
       'ocr saved '+m.ocr_skipped,'lost frames '+m.lost_frames,
       'fused reads '+m.fused_reads,'snapped '+m.snapped,
       'anchor avg '+m.anchor_avg_ms+'ms','roi crops '+m.roi_crops,
       'lines/min '+m.lines_per_min].map(x=>'<span class="pill">'+x+'</span>').join('');
    const vname=x=>{const i=x.indexOf('_');
      return x.charAt(i+1).toUpperCase()+x.slice(i+2)+' ('+x.slice(0,i).toUpperCase()+')';};
    const opts=v=>s.voices.map(x=>'<option value="'+x+'"'+(x===v?' selected':'')+'>'+vname(x)+'</option>').join('');
    const row=(ch,voice,assigned,auto)=>{
      const enc=encodeURIComponent(ch), muted=s.always_voiced.includes(ch);
      return '<tr data-ch="'+enc+'"><td>'+esc(ch)+(assigned?(auto?' <span class="muted">(auto)</span>':''):' <span class="muted">(unassigned)</span>')+'</td>'+
        '<td><select data-role="cast" data-ch="'+enc+'">'+(assigned?'':'<option></option>')+opts(voice)+'</select></td>'+
        '<td><input type="checkbox" data-role="mute" data-ch="'+enc+'"'+(muted?' checked':'')+'></td>'+
        '<td><button data-role="del" data-ch="'+enc+'" title="delete">✕</button></td></tr>';};
    // the default slots, pinned above the cast: who speaks when no
    // character owns the line (narrator), and the seeds auto-casting
    // hands a newly met character (female / male)
    const slotTitle={narrator:'narration, lore cards, loading tips and any line with no speaker',
      female:'fallback voice for unnamed female speakers; seeds auto-casting',
      male:'fallback voice for unnamed male speakers; seeds auto-casting'};
    const defRow=(slot,voice)=>
      '<tr data-ch="'+encodeURIComponent(slot)+'"><td title="'+slotTitle[slot]+'"><i>'+slot+'</i> <span class="muted">(default)</span></td>'+
      '<td><select data-role="default" data-slot="'+slot+'">'+opts(voice)+'</select></td>'+
      '<td></td><td></td></tr>';
    const castFp=JSON.stringify([s.characters,s.unknown,s.always_voiced,s.defaults]);
    if(castFp!==lastCastFp&&!interacting('casting')){
      lastCastFp=castFp;
      let rows='';
      for(const slot of ['narrator','female','male'])
        if(s.defaults&&s.defaults[slot]) rows+=defRow(slot,s.defaults[slot]);
      for(const [ch,c] of Object.entries(s.characters)) rows+=row(ch,c.voice,true,c.auto);
      for(const ch of s.unknown) if(!(ch in s.characters)) rows+=row(ch,'',false,false);
      for(const ch of s.always_voiced)
        if(!(ch in s.characters)&&!s.unknown.includes(ch)) rows+=row(ch,'',false,false);
      document.querySelector('#casting tbody').innerHTML=rows;
      filterCast();   // rebuild wipes row visibility — re-apply the search
    }
    const voicesFp=s.voices.join(',');
    for(const id of ['sayVoice','newVoice']){
      const el=document.getElementById(id);
      // rebuilt when a voice is installed or removed; the current pick survives
      if(!el.options.length||voicesFp!==lastVoicesFp) el.innerHTML=opts(el.value||'af_heart');
    }
    if(voicesFp!==lastVoicesFp){lastVoicesFp=voicesFp; lastCastFp='';}
    // Rebuilt only when the log actually changed, and held while a
    // screenshot preview is open or the user is selecting text to copy.
    // The table was rebuilt on every poll, and each row that has a shot
    // carries a full-size hover-preview <img>: a session at the 200-event
    // cap threw away and re-created ~200 image elements a second, which
    // Firefox-based browsers turn into a page that scrolls in lurches and
    // a preview that reloads mid-gesture. The fingerprint is a string
    // compare of a payload already parsed this tick.
    const sel=window.getSelection();
    const selInLog=sel&&!sel.isCollapsed&&document.getElementById('log').contains(sel.anchorNode);
    const logFp=JSON.stringify(s.events);
    if(logFp!==lastLogFp&&!document.querySelector('#log .shot:hover')&&!selInLog){
      lastLogFp=logFp;
      document.querySelector('#log tbody').innerHTML=s.events.slice().reverse().map(e=>
      '<tr><td class="muted">'+e.t+'</td><td>'+esc(e.speaker||'—')+'</td><td>'+esc(e.text)+'</td>'+
      '<td class="voice">'+(e.voice||'')+(e.speed&&e.speed!==1?' ×'+e.speed:'')+'</td>'+
      '<td class="act-'+e.cls+'">'+e.action+'</td>'+
      '<td>'+(e.shot?'<a class="shot" href="/shots/'+e.id+'.jpg" target="_blank">📷<img loading="lazy" src="/shots/'+e.id+'.jpg"></a> ':'')+
      (e.can_replay?'<button onclick="replay('+e.id+')">↻</button>':'')+'</td></tr>').join('');
    }
  }catch(err){document.getElementById('status').textContent='· disconnected';}
  setTimeout(tick,1000);
}
document.getElementById('sayText').value='';
tick();
</script></body></html>""".replace("__STYLE__", STYLE)

VOICES_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HoyoVoice — voice packs</title><style>__STYLE__</style></head><body>
<h1>Voice packs <span class="muted" style="font-size:12px;font-weight:normal">v__VERSION__</span>
<a href="/">← dashboard</a></h1>
<div style="max-width:680px">
<div id="voiceMsg" class="muted" style="min-height:18px"></div>

<h2>Add voice file</h2>
<div>
  <input type="file" id="voiceFile" accept=".pt,.pth,.safetensors,.npy,.npz,.bin"
         style="max-width:220px" title="a Kokoro voice pack: .pt, .safetensors, .npy, .npz or .bin">
  <input id="voiceName" placeholder="name (optional)" size="12" autocomplete="off">
  <input id="voiceKey" placeholder="voice in pack" size="10" autocomplete="off"
         title="only for a file holding several voices — the name of the one you want">
  <button onclick="addVoice()">Add &amp; verify</button>
</div>
<div class="muted" style="margin-top:4px">a Kokoro voice pack: .pt, .safetensors, .npy, .npz or .bin —
verified by actually synthesizing with it, then auditioned out loud. Leave the picker empty to type a
path on the machine running HoyoVoice instead.</div>

<h2>Blend voices</h2>
<div class="muted" style="margin-bottom:6px">a weighted mix of any voices in the menu, saved as a new
voice. Weights are relative and get normalized — 3 and 1 mean 75% and 25%.</div>
<div id="blendRows"></div>
<div style="margin-top:6px">
  <button onclick="addRow()">+ voice</button>
  <input id="blendName" placeholder="name (optional)" size="12" autocomplete="off">
  <button onclick="blend()">Blend &amp; verify</button>
</div>

<h2>Installed <span class="muted">(hover one for its source)</span></h2>
<div id="customVoices" class="muted">none yet</div>

<h2>Test a voice</h2>
<div>
  <input id="sayText" placeholder="type any line to hear it spoken…" size="28" autocomplete="off">
  <select id="sayVoice"></select>
  <button onclick="say()">Speak</button>
</div>
</div>
<script>
let voices=[], lastVoicesFp='', lastVoiceMsg=null;
function post(url,body){return fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});}
function esc(s){const d=document.createElement('div');d.textContent=s??'';return d.innerHTML;}
const vname=x=>{const i=x.indexOf('_');
  return x.charAt(i+1).toUpperCase()+x.slice(i+2)+' ('+x.slice(0,i).toUpperCase()+')';};
const opts=v=>voices.map(x=>'<option value="'+x+'"'+(x===v?' selected':'')+'>'+vname(x)+'</option>').join('');
function fillSelect(el){
  if(!voices.length||document.activeElement===el) return;
  if(!el.options.length||el.dataset.fp!==lastVoicesFp){el.innerHTML=opts(el.value||'af_heart');el.dataset.fp=lastVoicesFp;}}
function addRow(){
  const d=document.createElement('div');d.className='part';d.style.marginTop='4px';
  d.innerHTML='<select></select> <span class="muted">weight</span> '+
    '<input type="number" step="0.05" min="0.01" value="1" style="width:70px"> '+
    '<button data-role="rmrow" title="remove this voice from the mix">✕</button>';
  document.getElementById('blendRows').appendChild(d);
  fillSelect(d.querySelector('select'));
}
function blend(){
  const parts=[...document.querySelectorAll('#blendRows .part')].map(d=>({
    voice:d.querySelector('select').value, weight:parseFloat(d.querySelector('input').value)}));
  const msg=document.getElementById('voiceMsg');
  if(parts.some(p=>!p.voice||!(p.weight>0))){
    msg.textContent='every row needs a voice and a positive weight'; msg.className='paused'; return;}
  msg.textContent='blending…'; msg.className='muted';
  post('/api/blendvoice',{name:document.getElementById('blendName').value.trim(),parts:parts})
    .then(async r=>{if(!r.ok){const j=await r.json().catch(()=>({}));
      throw new Error(j.error||'blend failed');}})
    .catch(e=>{msg.textContent=e.message; msg.className='paused';});
}
function addVoice(){
  const f=document.getElementById('voiceFile');
  const fd=new FormData();
  if(f.files.length) fd.append('file',f.files[0]);
  else{const p=prompt('Path to a voice-pack file on this machine:'); if(!p) return; fd.append('path',p);}
  fd.append('name',document.getElementById('voiceName').value.trim());
  fd.append('key',document.getElementById('voiceKey').value.trim());
  const msg=document.getElementById('voiceMsg');
  msg.textContent='uploading…'; msg.className='muted';
  fetch('/api/addvoice',{method:'POST',body:fd})
    .then(r=>{if(!r.ok) throw new Error(r.status===413?'that file is too large':'upload failed');
              f.value='';})
    .catch(e=>{msg.textContent=e.message; msg.className='paused';});
}
function say(){post('/api/say',{text:document.getElementById('sayText').value,
  voice:document.getElementById('sayVoice').value});}
document.addEventListener('click',e=>{
  const t=e.target;
  if(t.dataset.role==='rmrow'&&document.querySelectorAll('#blendRows .part').length>2)
    t.closest('.part').remove();
  if(t.dataset.role==='delvoice'){e.preventDefault();
    const v=decodeURIComponent(t.dataset.v);
    if(confirm('Remove '+v+'? Characters cast to it are re-cast to a built-in voice.'))
      post('/api/delvoice',{voice:v});}
});
async function tick(){
  try{
    const s=await (await fetch('/api/state')).json();
    voices=s.voices; lastVoicesFp=voices.join(',');
    for(const el of document.querySelectorAll('#blendRows select, #sayVoice')) fillSelect(el);
    const vi=s.voice_import||{};
    if(vi.msg!==lastVoiceMsg){lastVoiceMsg=vi.msg;
      const m=document.getElementById('voiceMsg');
      m.textContent=vi.msg||'';
      m.className=vi.state==='error'?'paused':(vi.state==='ok'?'live':'muted');}
    const cs=s.custom_sources||{};
    document.getElementById('customVoices').innerHTML=s.custom_voices.length
      ? s.custom_voices.map(v=>'<span class="pill" title="'+esc(cs[v]||'')+'">'+esc(v)+
        ' <a href="#" data-role="delvoice" data-v="'+encodeURIComponent(v)+'" title="remove">✕</a></span>').join('')
      : 'none yet';
  }catch(err){}
  setTimeout(tick,1000);
}
addRow(); addRow();
tick();
</script></body></html>""".replace("__STYLE__", STYLE)


# /api/state polls at 1 Hz per open tab, and the recordings list only
# changes when a file lands in or leaves the directory — keyed on the
# dir's own mtime (adding/removing a file bumps it; a finished file's
# size never changes) so the glob + per-file stat() walk runs on change,
# not on every poll. One (key, list) tuple rebound atomically: Flask
# serves threaded, and a two-field update could interleave as
# old-list/new-key, latching stale until the NEXT dir change.
_REC_CACHE = (None, [])


def _recordings(shared):
    global _REC_CACHE
    rd = shared["rec_dir"]["path"]
    raw = (Path(shared["recording"]["raw"]).name
           if shared["recording"]["on"] and shared["recording"].get("raw")
           else None)
    try:
        rkey = (str(rd), rd.stat().st_mtime, raw)
    except OSError:
        rkey = (str(rd), None, raw)
    cached_key, cached_list = _REC_CACHE
    if cached_key != rkey:
        cached_list = sorted(
            ({"name": p.name, "mb": round(p.stat().st_size / 1e6, 1)}
             for ext in ("*.mp4", "*.mkv") for p in rd.glob(ext)
             # hide the raw file only while it's still being written
             if p.name != raw),
            key=lambda r: r["name"], reverse=True)
        _REC_CACHE = (rkey, cached_list)
    return cached_list


def start_webui(shared, port=DASHBOARD_PORT):
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    app = Flask("hoyovoice")
    # a Kokoro voice pack is ~0.5 MB; this only has to stop a misdropped
    # model file from being buffered into memory before anyone looks at it
    app.config["MAX_CONTENT_LENGTH"] = 64 << 20

    def catalog():
        """Voices that may be cast: the packaged ones plus installed packs."""
        return VOICE_CATALOG + sorted(shared["voices"].get("custom_voices", {}))

    @app.get("/")
    def index():
        return PAGE.replace("__VERSION__", _build_id())

    @app.get("/voices")
    def voices_page():
        return VOICES_PAGE.replace("__VERSION__", _build_id())

    @app.get("/shots/<path:name>")
    def shot(name):
        return send_from_directory(shared["shots_dir"], name)

    @app.get("/live.jpg")
    def live():
        # ffmpeg rewrites this file continuously and replaces it by rename;
        # on Windows, opening it in the instant between the two raises
        # PermissionError rather than returning stale bytes, which turned a
        # dashboard preview refresh into a 500 and a Flask traceback in the
        # log. One retry covers the rename window.
        for attempt in range(2):
            try:
                resp = send_from_directory(shared["frame_dir"],
                                           "live_frame.jpg")
                resp.headers["Cache-Control"] = "no-store"
                return resp
            except PermissionError:
                if attempt:
                    return ("", 503)          # caller just refreshes
                time.sleep(0.05)

    @app.get("/recordings/<path:name>")
    def rec(name):
        return send_from_directory(str(shared["rec_dir"]["path"]), name)

    @app.get("/log.txt")
    def log_txt():
        """One downloadable file with everything needed to debug a session:
        environment, live analytics, casting, the decision log that the
        dashboard shows, and the filtered console log. Beats a screenshot —
        the text is searchable and complete.

        Nothing in here may raise. A 500 is a dead end on this route: the
        browser is left on an error page, the file never arrives, and the
        traceback explaining why went to the console log the user was
        trying to download. Anything that goes wrong is written INTO the
        file instead and the partial log is still served.
        """
        out = []
        try:
            # Snapshot first. Everything below is a Python-level loop over
            # structures the capture thread mutates — the decision log
            # grows a line at a time, casting gains a character the moment
            # one is auto-cast — and iterating them live raises RuntimeError
            # ("deque mutated during iteration") in the middle of the
            # download. Each of these is one C-level call, so it cannot be
            # interrupted the way the loops can.
            events = list(shared["events"])
            characters = dict(shared["voices"]["characters"])
            always = list(shared["voices"].get("always_voiced", []))
            unknown = sorted(set(shared["unknown"]))
            m = shared["metrics_fn"]()
            out += [
                f"HoyoVoice {_build_id()} session log",
                f"generated   {datetime.now().isoformat(timespec='seconds')}",
                f"platform    {platform.platform()}  "
                f"python {platform.python_version()}",
                f"observing   {shared['observing']['on']}   recording "
                f"{shared['recording']['on']}",
                f"devices     video={shared['devices']['video']!r} "
                f"audio={shared['devices']['audio']!r} "
                f"output={shared['devices'].get('output') or 'system default'!r}",
                f"game        {'auto' if shared['game'].auto else 'fixed'} — "
                f"reading as {shared['game'].profile.label}",
                "",
                "ANALYTICS",
                "  " + "   ".join(f"{k}={v}" for k, v in m.items()),
                "",
                "CASTING",
            ]
            for ch, c in characters.items():
                out.append(f"  {ch:28s} {c.get('voice',''):12s}"
                           f"{'  [muted]' if ch in always else ''}"
                           f"{'  (auto)' if c.get('auto') else ''}")
            unassigned = [u for u in unknown if u not in characters]
            if unassigned:
                out.append("  unassigned: " + ", ".join(unassigned))

            out += ["", "DECISION LOG (oldest first)", ""]
            for e in events:
                speed = f" x{e['speed']}" if e.get("speed") else ""
                # the event id, shown only when a shot was actually saved:
                # it names the files under captures/shots/ (<id>.jpg,
                # <id>.json), which is what a bug report needs relayed —
                # "which shot ids?" was previously unanswerable from the
                # log alone
                shot = f"  shot #{e['id']}" if e.get("shot") else ""
                out.append(f"  {e['t']}  {(e['speaker'] or '—'):20.20s} "
                           f"{e['action']:34.34s} {(e['voice'] or ''):10s}"
                           f"{speed}{shot}")
                out.append(f"            {e['text']}")
                if e.get("spoken"):   # the line as the synthesizer heard it
                    out.append(f"            ↳ synth heard: {e['spoken']}")

            out += ["", "CONSOLE LOG (noise filtered)", ""]
            path = Path(shared.get("log_path", ""))
            try:
                # Tail, never the whole file: this is the launcher's
                # capture of live.py's stdout and it grows for as long as
                # the session runs. Reading it whole to keep the last 4000
                # lines put the entire thing in memory on the serving
                # thread, which is also the thread answering the
                # dashboard's once-a-second poll.
                with open(path, "rb") as fh:
                    fh.seek(0, os.SEEK_END)
                    size = fh.tell()
                    fh.seek(max(0, size - LOG_TAIL_BYTES))
                    raw = fh.read()
                if size > LOG_TAIL_BYTES:
                    raw = raw.split(b"\n", 1)[-1]     # drop the cut line
                    out.append(f"  … first {size - LOG_TAIL_BYTES} bytes "
                               "omitted …")
                lines = [ln for ln in raw.decode("utf-8", "replace").splitlines()
                         if not LOG_NOISE.search(ln)]
                if len(lines) > LOG_TAIL_LINES:
                    out.append(f"  … {len(lines) - LOG_TAIL_LINES} earlier "
                               "lines omitted …")
                    lines = lines[-LOG_TAIL_LINES:]
                out += ["  " + ln for ln in lines]
            except OSError as exc:
                out.append(f"  (console log unavailable: {exc})")
        except Exception:
            # Straight into the file, and into the console log too: a
            # download that half-works is still a bug report, and this is
            # the one failure the user cannot read any other way.
            note = ("!!! this log is INCOMPLETE — assembling it raised, "
                    "traceback below")
            out = [note, ""] + out + ["", note, "", traceback.format_exc()]
            print("dashboard: /log.txt failed\n" + traceback.format_exc(),
                  flush=True)

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        resp = Response("\n".join(out) + "\n", mimetype="text/plain")
        resp.headers["Content-Disposition"] = (
            f'attachment; filename="hoyovoice-{stamp}.log"')
        # so "I clicked download and nothing happened" is answerable from
        # the next log: this line says the server built and served one
        print(f"dashboard: served log.txt ({len(out)} lines)", flush=True)
        return resp

    @app.get("/api/state")
    def state():
        return jsonify({
            "events": list(shared["events"]),
            "characters": shared["voices"]["characters"],
            "defaults": shared["voices"].get("defaults", {}),
            "always_voiced": shared["voices"].get("always_voiced", []),
            "unknown": sorted(shared["unknown"]),
            "voices": catalog(),
            "custom_voices": sorted(shared["voices"].get("custom_voices", {})),
            "custom_sources": {
                k: v.get("source", "") for k, v in
                shared["voices"].get("custom_voices", {}).items()},
            "voice_import": dict(shared["voice_import"]),
            "metrics": shared["metrics_fn"](),
            "observing": shared["observing"]["on"],
            "recording": shared["recording"]["on"],
            "game": {
                "setting": "auto" if shared["game"].auto
                           else shared["game"].profile.name,
                "active": shared["game"].profile.label,
                "choices": profile_choices(),
            },
            "rec_dir": str(shared["rec_dir"]["path"]),
            "recordings": _recordings(shared),
        })

    @app.post("/api/game")
    def game():
        g = (request.get_json().get("game") or "").lower()
        if g == "auto" or g in PROFILES:
            shared["commands"].put(("game", g))
        return jsonify(ok=True)

    @app.post("/api/record")
    def record():
        shared["commands"].put(("record", bool(request.get_json().get("on"))))
        return jsonify(ok=True)

    @app.get("/api/devices")
    def devices():
        vid, aud, out = shared["list_devices_fn"]()
        return jsonify(video=vid, audio=aud, output=out,
                       current_video=shared["devices"]["video"],
                       current_audio=shared["devices"]["audio"],
                       current_output=shared["devices"].get("output", ""))

    @app.post("/api/device")
    def device():
        d = request.get_json()
        # output: "" is the system default, a real choice — pass it through,
        # unlike a blank video/audio name, which live.py ignores
        want = {"video": d.get("video"), "audio": d.get("audio")}
        if d.get("output") is not None:
            want["output"] = d["output"]
        shared["commands"].put(("setdevice", want))
        return jsonify(ok=True)

    @app.post("/api/recdir")
    def recdir():
        d = request.get_json().get("dir", "").strip()
        if d:
            shared["commands"].put(("recdir", d))
        return jsonify(ok=True)

    @app.post("/api/assign")
    def assign():
        d = request.get_json()
        if d.get("character") and d.get("voice") in catalog():
            shared["commands"].put(("assign", d["character"], d["voice"]))
        return jsonify(ok=True)

    @app.post("/api/addvoice")
    def addvoice():
        """Take a voice-pack file and hand it to the orchestrator to verify.

        Two ways in, because a dashboard reached from another machine and
        one open on the machine running the game want different things: a
        browser upload (multipart), or a path typed into the box, which
        skips the copy when the file is already sitting on this disk.

        Only queues the work. Verification needs the TTS engine, which
        lives on the orchestrator thread — the result comes back through
        /api/state.
        """
        name = (request.form.get("name") or "").strip() or None
        key = (request.form.get("key") or "").strip() or None
        upload = request.files.get("file")
        if upload and upload.filename:
            dest_dir = Path(shared["uploads_dir"])
            dest_dir.mkdir(parents=True, exist_ok=True)
            # the browser supplies this name; keep only a leaf filename, and
            # only the suffix is load-bearing (it picks the reader)
            safe = re.sub(r"[^A-Za-z0-9._-]", "_",
                          Path(upload.filename).name)[-64:] or "upload"
            src = dest_dir / safe
            upload.save(src)
            name = name or Path(upload.filename).stem
        else:
            typed = (request.form.get("path") or "").strip()
            if not typed:
                return jsonify(ok=False, error="no file"), 400
            src = Path(typed).expanduser()
        shared["voice_import"].update(
            state="busy", voice=None,
            msg=f"verifying {Path(src).name}…")
        shared["commands"].put(("addvoice", str(src), name, key))
        return jsonify(ok=True)

    @app.post("/api/blendvoice")
    def blendvoice():
        """Mix voices already in the menu into a new one.

        Only validates and queues: the style tensors and the engine that
        proves the result synthesizes both live on the orchestrator
        thread. The result comes back through /api/state, same as an
        imported pack.
        """
        d = request.get_json() or {}
        try:
            parts = [(str(p["voice"]), float(p["weight"]))
                     for p in (d.get("parts") or [])]
        except (TypeError, KeyError, ValueError):
            return jsonify(ok=False, error="malformed blend request"), 400
        if not 2 <= len(parts) <= 8:
            return jsonify(ok=False, error="a blend needs 2–8 voices"), 400
        known = catalog()
        for v, w in parts:
            if v not in known:
                return jsonify(ok=False, error=f"unknown voice {v!r}"), 400
            if not math.isfinite(w) or w <= 0:
                return jsonify(ok=False,
                               error="weights must be positive numbers"), 400
        name = (d.get("name") or "").strip() or None
        shared["voice_import"].update(
            state="busy", voice=None, msg="blending…")
        shared["commands"].put(("blendvoice", name, parts))
        return jsonify(ok=True)

    @app.post("/api/delvoice")
    def delvoice():
        v = (request.get_json() or {}).get("voice")
        if v in shared["voices"].get("custom_voices", {}):
            shared["commands"].put(("delvoice", v))
        return jsonify(ok=True)

    @app.post("/api/default")
    def set_default():
        """Re-cast one of the default voice slots (narrator / female /
        male). Validated here the way /api/say validates, because a bad
        voice id in `defaults` doesn't fail loudly — it silences every
        line that falls back to that slot."""
        d = request.get_json() or {}
        slot, v = d.get("slot"), d.get("voice")
        if slot in shared["voices"].get("defaults", {}) and v in catalog():
            shared["commands"].put(("setdefault", slot, v))
        return jsonify(ok=True)

    @app.post("/api/mute")
    def mute():
        d = request.get_json()
        if d.get("character"):
            shared["commands"].put(("mute", d["character"], bool(d.get("muted"))))
        return jsonify(ok=True)

    @app.post("/api/delete")
    def delete():
        d = request.get_json()
        if d.get("character"):
            shared["commands"].put(("delete", d["character"]))
        return jsonify(ok=True)

    @app.post("/api/replay")
    def replay():
        shared["commands"].put(("replay", request.get_json().get("id")))
        return jsonify(ok=True)

    @app.post("/api/say")
    def say():
        d = request.get_json()
        if d.get("text") and d.get("voice") in catalog():
            shared["commands"].put(("say", d["text"], d["voice"]))
        return jsonify(ok=True)

    @app.post("/api/clearlog")
    def clearlog():
        shared["commands"].put(("clearlog",))
        return jsonify(ok=True)

    @app.post("/api/observe")
    def observe():
        shared["commands"].put(("observe", bool(request.get_json().get("on"))))
        return jsonify(ok=True)

    # default localhost-only (no auth!); set settings.dashboard_bind to
    # "0.0.0.0" to reach the dashboard from other machines you trust
    bind = shared["voices"].get("settings", {}).get(
        "dashboard_bind", "127.0.0.1")

    # fail LOUDLY if the port is taken (usually an orphaned instance) —
    # otherwise the serving thread dies silently and the app runs headless.
    #
    # SO_REUSEADDR because that is what the real server does (werkzeug sets
    # it), and without it the probe answers a DIFFERENT question than the
    # one that matters. A dashboard tab left open holds established
    # connections; when the app exits, those sockets sit in TIME_WAIT for a
    # minute or two, and a plain bind() to the listening address fails with
    # EADDRINUSE even though nothing is listening. Restarting promptly with
    # the dashboard open — the normal way to restart after a fix — killed
    # the new instance at startup with "another HoyoVoice instance is still
    # running" while no such instance existed (2026-08-12, twice).
    # SO_REUSEADDR steps over the TIME_WAIT remains and still refuses a port
    # some other process is really LISTENing on, which is the case this
    # check was written for.
    probe = socket.socket()
    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        probe.bind((bind if bind != "0.0.0.0" else "", port))
        probe.close()
    except OSError:
        print(f"FATAL: dashboard port {port} is already in use — another "
              "HoyoVoice instance is still running (check Task Manager / "
              "Activity Monitor for stray python or ffmpeg, or run the "
              "launcher's stop command), then start again", flush=True)
        sys.exit(1)

    def serve():
        try:
            app.run(host=bind, port=port, debug=False, use_reloader=False)
        except Exception as e:
            print(f"FATAL: dashboard server died: {e}", flush=True)

    threading.Thread(target=serve, daemon=True).start()
    if bind != "127.0.0.1":
        print(f"dashboard reachable on all interfaces (bind {bind})",
              flush=True)
    return port
