from flask import Flask, render_template, request, redirect, url_for, session, abort
from profile_wizard import wizard_generate_questions, wizard_build_profile
from db import insert_profile
from config import settings
import json
from db import (
    init_db,
    list_ads, get_ad,
    list_profiles, get_profile,
    create_profile_from_form, update_profile_from_form, delete_profile,
    profile_to_form_defaults
)
from flask import Response, render_template_string
import threading
import time
import json
from events import create_run, get_queue, close_run

from scrape import scrape

app = Flask(__name__)
app.secret_key = settings.SECRET_KEY
init_db()
# ---- ADS ----

@app.get("/")
def index():
    min_score = request.args.get("min_score", default=None, type=float)
    profile_id = request.args.get("profile_id", default=None, type=int)

    ads = list_ads(limit=200, min_score=min_score, profile_id=profile_id)
    profiles = list_profiles()

    return render_template(
        "index.html",
        ads=ads,
        min_score=min_score,
        profiles=profiles,
        selected_profile_id=profile_id
    )


@app.get("/ad/<int:ad_id>")
def ad_detail(ad_id):
    ad = get_ad(ad_id)
    if not ad:
        return render_template("ad.html", ad=None)

    def jload(s):
        try:
            return json.loads(s) if s else None
        except Exception:
            return None

    ad["signals_positive"] = jload(ad.get("signals_positive"))
    ad["signals_negative"] = jload(ad.get("signals_negative"))
    ad["quick_tests"] = jload(ad.get("quick_tests"))
    ad["repair_items"] = jload(ad.get("repair_items"))
    return render_template("ad.html", ad=ad)
# ---- PROFILES CRUD ----

@app.get("/profiles")
def profiles_page():
    profiles = list_profiles()
    return render_template("profiles.html", profiles=profiles)

@app.route("/profiles/new", methods=["GET", "POST"])
def profile_new():
    if request.method == "POST":
        create_profile_from_form(
            request.form["name"],
            request.form.get("notes", ""),
            request.form.get("queries", ""),
            request.form.get("yes", ""),
            request.form.get("no", ""),
            request.form.get("questions", ""),
        )
        return redirect(url_for("profiles_page"))

    f = {"name":"", "notes":"", "queries_txt":"", "yes_txt":"", "no_txt":"", "questions_txt":""}
    return render_template("profile_form.html", title="New profile", f=f)

@app.route("/profiles/<int:profile_id>/edit", methods=["GET", "POST"])
def profile_edit(profile_id):
    p = get_profile(profile_id)
    if not p:
        abort(404)

    if request.method == "POST":
        update_profile_from_form(
            profile_id,
            request.form["name"],
            request.form.get("notes", ""),
            request.form.get("queries", ""),
            request.form.get("yes", ""),
            request.form.get("no", ""),
            request.form.get("questions", ""),
        )
        return redirect(url_for("profiles_page"))

    f = profile_to_form_defaults(p)
    return render_template("profile_form.html", title=f"Edit profile #{profile_id}", f=f)

@app.get("/profiles/<int:profile_id>/delete")
def profile_delete(profile_id):
    delete_profile(profile_id)
    return redirect(url_for("profiles_page"))

# ---- RUN ----

@app.get("/events/<run_id>")
def events_stream(run_id):
    q = get_queue(run_id)
    if not q:
        abort(404)

    def gen():
        # kickstart (un comment SSE)
        yield ": connected\n\n"
        last_ping = time.time()
        while True:
            try:
                msg = q.get(timeout=1.0)
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                if msg.get("type") == "done":
                    break
            except Exception:
                if time.time() - last_ping > 10:
                    yield "event: ping\ndata: {}\n\n"
                    last_ping = time.time()

    return Response(
        gen(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


LIVE_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Live Run</title>
<style>
body{font-family:system-ui,Arial;margin:18px}
.wrap{display:flex;gap:14px}
.col{flex:1;border:1px solid #ddd;border-radius:12px;padding:12px;height:80vh;overflow:auto}
.title{font-weight:700;margin-bottom:8px}
.sec{margin-top:10px;padding-top:10px;border-top:1px dashed #ddd}
.kv{color:#222}
.muted{color:#666}
pre{white-space:pre-wrap;margin:0}
.chip{display:inline-block;padding:2px 8px;border:1px solid #ddd;border-radius:999px;font-size:12px;margin-right:6px}
</style></head>
<body>
<h2>Live Run <span class="muted">({{ run_id }})</span></h2>
<div class="wrap">
  <div class="col" id="log"><div class="title">Log</div></div>
  <div class="col" id="llm">
    <div class="title">LLM stream</div>
    <div class="muted">INTENT / MINIMAL / VERBOSE curg token cu token.</div>
    <div class="sec" id="llm_out"></div>
  </div>
</div>
<script>
const logEl = document.getElementById("log");
const llmOut = document.getElementById("llm_out");

function addLog(html){
  const d = document.createElement("div");
  d.innerHTML = html;
  logEl.appendChild(d);
  logEl.scrollTop = logEl.scrollHeight;
}

const llmState = {}; // label -> {inThink, thinkEl, outEl, lastActivityTs, typing}

function ensureLLMBox(label){
  if (llmState[label]) return llmState[label];

  const box = document.createElement("div");
  box.className = "sec";

  const chip = document.createElement("div");
  chip.className = "chip";
  chip.textContent = label;
  box.appendChild(chip);

  const thinkTitle = document.createElement("div");
  thinkTitle.className = "muted";
  thinkTitle.style.margin = "6px 0 4px";
  thinkTitle.textContent = "THINK";
  box.appendChild(thinkTitle);

  const thinkPre = document.createElement("pre");
  box.appendChild(thinkPre);

  const outTitle = document.createElement("div");
  outTitle.className = "muted";
  outTitle.style.margin = "10px 0 4px";
  outTitle.textContent = "OUTPUT";
  box.appendChild(outTitle);

  const outPre = document.createElement("pre");
  box.appendChild(outPre);

  llmOut.appendChild(box);

  llmState[label] = {
    inThink: false,
    thinkEl: thinkPre,
    outEl: outPre,
    lastActivityTs: Date.now(),
    typing: false
  };
  return llmState[label];
}

// typing indicator (pulsează dacă nu vin chunks)
setInterval(function(){
  const now = Date.now();
  for (const label in llmState) {
    const st = llmState[label];
    if (st.typing && (now - st.lastActivityTs) > 900) {
      if (!st.outEl.textContent.endsWith("...")) st.outEl.textContent += "...";
      st.lastActivityTs = now;
      llmOut.scrollTop = llmOut.scrollHeight;
    }
  }
}, 800);

const es = new EventSource("/events/{{ run_id }}");

es.onmessage = function(ev){
  const msg = JSON.parse(ev.data);
  const t = msg.type;
  const d = msg.data || {};

  if (t === "section") {
    addLog('<div class="sec"><b>' + (d.title || "") + '</b></div>');
    return;
  }
  if (t === "kv") {
    addLog('<div class="kv">' + (d.key || "") + ': <span class="muted">' + String(d.value) + '</span></div>');
    return;
  }
  if (t === "block") {
    addLog('<div class="kv"><b>' + (d.label || "") + '</b><pre>' + (d.content || "") + '</pre></div>');
    return;
  }

  if (t === "llm") {
    const label = d.label || "LLM";
    const st = ensureLLMBox(label);
    st.lastActivityTs = Date.now();

    if (d.kind === "prompt") {
      st.inThink = false;
      st.typing = true;
      st.thinkEl.textContent = "";
      st.outEl.textContent = "";
      st.outEl.textContent += "[PROMPT]\\n" + (d.prompt || "") + "\\n\\n[OUTPUT]\\n";
      llmOut.scrollTop = llmOut.scrollHeight;
      return;
    }

    if (d.kind === "chunk") {
      st.typing = true;
      let txt = d.text || "";

      while (txt.length) {
        if (!st.inThink) {
          const i = txt.indexOf("<think>");
          if (i === -1) { st.outEl.textContent += txt; break; }
          st.outEl.textContent += txt.slice(0, i);
          txt = txt.slice(i + 7); // len("<think>") = 7
          st.inThink = true;
        } else {
          const j = txt.indexOf("</think>");
          if (j === -1) { st.thinkEl.textContent += txt; break; }
          st.thinkEl.textContent += txt.slice(0, j);
          txt = txt.slice(j + 8); // len("</think>") = 8
          st.inThink = false;
        }
      }

      llmOut.scrollTop = llmOut.scrollHeight;
      return;
    }

    if (d.kind === "done") {
      st.typing = false;
      llmOut.scrollTop = llmOut.scrollHeight;
      return;
    }

    if (d.kind === "error") {
  st.typing = false;
  st.outEl.textContent += "\\n\\n[ERROR]\\n" + (d.error || "");
  llmOut.scrollTop = llmOut.scrollHeight;
  return;
}

  }

  if (t === "done") {
    addLog('<div class="sec"><b>DONE</b></div>');
    es.close();
    return;
  }
};

es.addEventListener("ping", function(){});

es.onerror = function(){
  // EventSource se reconectează singur; nu spamăm UI.
  console.warn("SSE reconnecting...");
};
</script>

</body></html>"""

@app.get("/run/live/<run_id>")
def run_live(run_id):
    return render_template_string(LIVE_HTML, run_id=run_id)

@app.route("/run", methods=["GET", "POST"])
def run_page():
    profiles = list_profiles()
    if not profiles:
        return redirect(url_for("profile_new"))

    if request.method == "POST":
        profile_id = int(request.form["profile_id"])
        model = (request.form.get("model") or settings.DEFAULT_MODEL).strip()
        pages = int(request.form.get("pages") or 2)
        max_ads = int(request.form.get("max_ads") or 10)

        prof = get_profile(profile_id)
        if not prof:
            abort(400)

        run_id = create_run()

        def worker():
            try:
                for q in prof["queries"]:
                    scrape(query=q, model=model, profile_id=profile_id, max_pages=pages, max_ads=max_ads, run_id=run_id)
            finally:
                close_run(run_id)

        threading.Thread(target=worker, daemon=True).start()
        return redirect(url_for("run_live", run_id=run_id))

    return render_template("run.html", profiles=profiles, default_model=settings.DEFAULT_MODEL)

@app.route("/profiles/wizard", methods=["GET", "POST"])
def profile_wizard_start():
    if request.method == "POST":
        goal = request.form.get("goal","").strip()
        model = (request.form.get("model") or settings.DEFAULT_MODEL).strip()

        try:
            qs = wizard_generate_questions(model, goal)
        except Exception as e:
            return render_template("wizard_start.html", default_model=settings.DEFAULT_MODEL, error=str(e))

        session["wiz_goal"] = goal
        session["wiz_model"] = model
        session["wiz_questions"] = qs
        return redirect(url_for("profile_wizard_answer"))

    return render_template("wizard_start.html", default_model=settings.DEFAULT_MODEL)

@app.route("/profiles/wizard/answers", methods=["GET", "POST"])
def profile_wizard_answer():
    goal = session.get("wiz_goal")
    model = session.get("wiz_model")
    questions = session.get("wiz_questions", [])

    if not goal or not model or not questions:
        return redirect(url_for("profile_wizard_start"))

    if request.method == "POST":
        answers = {}
        for q in questions:
            answers[q["id"]] = request.form.get(q["id"], "").strip()

        prof = wizard_build_profile(model, goal, answers)
        insert_profile(prof)  # salvează în DB
        return redirect(url_for("profiles_page"))

    return render_template("wizard_answers.html", goal=goal, model=model, questions=questions)

if __name__ == "__main__":
    app.run(debug=True, port=5005, use_reloader=False, threaded=True)
