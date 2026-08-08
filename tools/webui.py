"""HoyoVoice dashboard — local web UI served from live.py.

Log (with voice used + screenshot hover-previews), casting with instant
re-read and per-character mute, pause/resume, test speech, analytics.
"""
import logging
import os
import platform
import re
import socket
import sys
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from profiles import PROFILES, profile_choices

VERSION = "0.7.0"
# single source of truth (hoyovoice.py reads it); env override lets
# tools/replay.py run beside a live instance without a port collision
DASHBOARD_PORT = int(os.environ.get("HOYOVOICE_PORT", "8470"))
# ffmpeg/format chatter that buries the interesting lines (hoyovoice.py
# imports this so the CLI and the download filter identically)
LOG_NOISE = re.compile(
    "pixel format|Supported|uyvy|yuyv|nv12|0rgb|bgr0|in#0|Fetching|vad: chunks")
LOG_TAIL_LINES = 4000

VOICE_CATALOG = [
    "af_heart", "af_alloy", "af_aoede", "af_bella", "af_jessica", "af_kore",
    "af_nova", "af_river", "af_sarah", "af_sky",
    "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael",
    "am_onyx", "am_puck", "am_santa",
    "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
    "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
]  # af_nicole omitted: broken in the packaged model

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HoyoVoice</title><style>
body{font:14px -apple-system,sans-serif;background:#14151a;color:#e8e8ec;margin:0;padding:16px}
h1{font-size:18px;margin:0 0 12px}h2{font-size:14px;color:#9aa;margin:18px 0 6px}
table{border-collapse:collapse;width:100%}td,th{padding:4px 8px;text-align:left;border-bottom:1px solid #26272e;vertical-align:top}
.act-spoken{color:#7ec97e}.act-skip{color:#888}.act-yield{color:#d9a441}.act-always{color:#888}
.act-choice{color:#8ab4f8}
select,input,button{background:#1e2027;color:#e8e8ec;border:1px solid #33353d;border-radius:6px;padding:4px 8px}
button{cursor:pointer}button:hover{border-color:#7ec97e}
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
</style></head><body>
<h1>HoyoVoice <span class="muted" style="font-size:12px;font-weight:normal">v__VERSION__</span>
<button id="observeBtn" onclick="toggleObserve()">Pause</button>
<button id="recordBtn" onclick="toggleRecord()">⏺ Record</button></h1>

<div class="cols">
  <div>
    <div id="status" class="muted" style="font-size:16px;margin-bottom:10px"></div>
    <h2 style="margin-top:0">Analytics</h2><div id="metrics"></div>
    <h2>Casting <span class="muted">(muted = never speak for this character)</span></h2>
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
  </div>
  <div>
    <div style="margin-bottom:6px">
      <span class="muted">video</span> <select id="vidDev"></select>
      <span class="muted">audio</span> <select id="audDev"></select>
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
<button onclick="post('/api/clearlog',{})">Clear</button>
<button onclick="window.location='/log.txt'" title="Download this session's decisions + console log as a text file">⤓ Download log</button></h2>
<table id="log"><thead><tr><th>time</th><th>speaker</th><th>line</th><th>voice</th><th>action</th><th></th></tr></thead><tbody></tbody></table>

<script>
let hidden=false, observing=true, recOn=false, lastCastFp='';
function toggleRecord(){post('/api/record',{on:!recOn});}
function setRecDir(){post('/api/recdir',{dir:document.getElementById('recDir').value});}
function setGame(){post('/api/game',{game:document.getElementById('gameSel').value});}
function applyDev(){post('/api/device',{video:document.getElementById('vidDev').value,
  audio:document.getElementById('audDev').value});}
async function loadDevices(){
  try{
    const d=await (await fetch('/api/devices')).json();
    const fill=(id,list,cur)=>{document.getElementById(id).innerHTML=
      list.map(x=>'<option'+(x===cur?' selected':'')+'>'+x.replace(/</g,'&lt;')+'</option>').join('');};
    fill('vidDev',d.video,d.current_video);
    fill('audDev',d.audio,d.current_audio);
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
function esc(s){const d=document.createElement('div');d.textContent=s??'';return d.innerHTML;}
document.addEventListener('change',e=>{
  const t=e.target;
  if(t.dataset.role==='cast'&&t.value)
    post('/api/assign',{character:decodeURIComponent(t.dataset.ch),voice:t.value});
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
       'lost frames '+m.lost_frames,
       'lines/min '+m.lines_per_min].map(x=>'<span class="pill">'+x+'</span>').join('');
    const vname=x=>{const i=x.indexOf('_');
      return x.charAt(i+1).toUpperCase()+x.slice(i+2)+' ('+x.slice(0,i).toUpperCase()+')';};
    const opts=v=>s.voices.map(x=>'<option value="'+x+'"'+(x===v?' selected':'')+'>'+vname(x)+'</option>').join('');
    const row=(ch,voice,assigned,auto)=>{
      const enc=encodeURIComponent(ch), muted=s.always_voiced.includes(ch);
      return '<tr><td>'+esc(ch)+(assigned?(auto?' <span class="muted">(auto)</span>':''):' <span class="muted">(unassigned)</span>')+'</td>'+
        '<td><select data-role="cast" data-ch="'+enc+'">'+(assigned?'':'<option></option>')+opts(voice)+'</select></td>'+
        '<td><input type="checkbox" data-role="mute" data-ch="'+enc+'"'+(muted?' checked':'')+'></td>'+
        '<td><button data-role="del" data-ch="'+enc+'" title="delete">✕</button></td></tr>';};
    const castFp=JSON.stringify([s.characters,s.unknown,s.always_voiced]);
    if(castFp!==lastCastFp&&!interacting('casting')){
      lastCastFp=castFp;
      let rows='';
      for(const [ch,c] of Object.entries(s.characters)) rows+=row(ch,c.voice,true,c.auto);
      for(const ch of s.unknown) if(!(ch in s.characters)) rows+=row(ch,'',false,false);
      for(const ch of s.always_voiced)
        if(!(ch in s.characters)&&!s.unknown.includes(ch)) rows+=row(ch,'',false,false);
      document.querySelector('#casting tbody').innerHTML=rows;
    }
    for(const id of ['sayVoice','newVoice']){
      const el=document.getElementById(id);
      if(!el.options.length) el.innerHTML=opts('af_heart');
    }
    // log refreshes every poll; held while a screenshot preview is open
    // or while the user is selecting text to copy
    const sel=window.getSelection();
    const selInLog=sel&&!sel.isCollapsed&&document.getElementById('log').contains(sel.anchorNode);
    if(!document.querySelector('#log .shot:hover')&&!selInLog){
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
</script></body></html>"""


def start_webui(shared, port=DASHBOARD_PORT):
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    app = Flask("hoyovoice")

    @app.get("/")
    def index():
        return PAGE.replace("__VERSION__", VERSION)

    @app.get("/shots/<path:name>")
    def shot(name):
        return send_from_directory(shared["shots_dir"], name)

    @app.get("/live.jpg")
    def live():
        resp = send_from_directory(shared["frame_dir"], "live_frame.jpg")
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/recordings/<path:name>")
    def rec(name):
        return send_from_directory(str(shared["rec_dir"]["path"]), name)

    @app.get("/log.txt")
    def log_txt():
        """One downloadable file with everything needed to debug a session:
        environment, live analytics, casting, the decision log that the
        dashboard shows, and the filtered console log. Beats a screenshot —
        the text is searchable and complete."""
        m = shared["metrics_fn"]()
        out = [
            f"HoyoVoice {VERSION} session log",
            f"generated   {datetime.now().isoformat(timespec='seconds')}",
            f"platform    {platform.platform()}  python {platform.python_version()}",
            f"observing   {shared['observing']['on']}   recording "
            f"{shared['recording']['on']}",
            f"devices     video={shared['devices']['video']!r} "
            f"audio={shared['devices']['audio']!r}",
            f"game        {'auto' if shared['game'].auto else 'fixed'} — "
            f"reading as {shared['game'].profile.label}",
            "",
            "ANALYTICS",
            "  " + "   ".join(f"{k}={v}" for k, v in m.items()),
            "",
            "CASTING",
        ]
        always = shared["voices"].get("always_voiced", [])
        for ch, c in shared["voices"]["characters"].items():
            out.append(f"  {ch:28s} {c.get('voice',''):12s}"
                       f"{'  [muted]' if ch in always else ''}"
                       f"{'  (auto)' if c.get('auto') else ''}")
        unknown = [u for u in sorted(shared["unknown"])
                   if u not in shared["voices"]["characters"]]
        if unknown:
            out.append("  unassigned: " + ", ".join(unknown))

        out += ["", "DECISION LOG (oldest first)", ""]
        for e in shared["events"]:
            speed = f" x{e['speed']}" if e.get("speed") else ""
            out.append(f"  {e['t']}  {(e['speaker'] or '—'):20.20s} "
                       f"{e['action']:34.34s} {(e['voice'] or ''):10s}{speed}")
            out.append(f"            {e['text']}")

        out += ["", "CONSOLE LOG (noise filtered)", ""]
        path = Path(shared.get("log_path", ""))
        try:
            lines = [ln for ln in path.read_text(
                         encoding="utf-8", errors="replace").splitlines()
                     if not LOG_NOISE.search(ln)]
            if len(lines) > LOG_TAIL_LINES:
                out.append(f"  … {len(lines) - LOG_TAIL_LINES} earlier lines "
                           "omitted …")
                lines = lines[-LOG_TAIL_LINES:]
            out += ["  " + ln for ln in lines]
        except OSError as exc:
            out.append(f"  (console log unavailable: {exc})")

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        resp = Response("\n".join(out) + "\n", mimetype="text/plain")
        resp.headers["Content-Disposition"] = (
            f'attachment; filename="hoyovoice-{stamp}.log"')
        return resp

    @app.get("/api/state")
    def state():
        return jsonify({
            "events": list(shared["events"]),
            "characters": shared["voices"]["characters"],
            "always_voiced": shared["voices"].get("always_voiced", []),
            "unknown": sorted(shared["unknown"]),
            "voices": VOICE_CATALOG,
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
            "recordings": sorted(
                ({"name": p.name, "mb": round(p.stat().st_size / 1e6, 1)}
                 for ext in ("*.mp4", "*.mkv")
                 for p in shared["rec_dir"]["path"].glob(ext)
                 # hide the raw file only while it's still being written
                 if not (shared["recording"]["on"]
                         and shared["recording"].get("raw")
                         and p.name == Path(shared["recording"]["raw"]).name)),
                key=lambda r: r["name"], reverse=True),
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
        vid, aud = shared["list_devices_fn"]()
        return jsonify(video=vid, audio=aud,
                       current_video=shared["devices"]["video"],
                       current_audio=shared["devices"]["audio"])

    @app.post("/api/device")
    def device():
        d = request.get_json()
        shared["commands"].put(("setdevice",
                                {"video": d.get("video"),
                                 "audio": d.get("audio")}))
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
        if d.get("character") and d.get("voice") in VOICE_CATALOG:
            shared["commands"].put(("assign", d["character"], d["voice"]))
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
        if d.get("text") and d.get("voice") in VOICE_CATALOG:
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
    # otherwise the serving thread dies silently and the app runs headless
    probe = socket.socket()
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
