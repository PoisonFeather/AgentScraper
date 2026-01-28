from flask import Flask, render_template, request, redirect, url_for, session
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
from config import settings
from scrape import scrape

app = Flask(__name__)
init_db()
app.secret_key = "dev-secret" # TEMP, ok pentru local
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

        for q in prof["queries"]:
            scrape(query=q, model=model, profile_id=profile_id, max_pages=pages, max_ads=max_ads)

        return redirect(url_for("index", profile_id=profile_id))

    return render_template("run.html", profiles=profiles, default_model=settings.DEFAULT_MODEL)
from flask import session
from profile_wizard import wizard_generate_questions, wizard_build_profile
from db import insert_profile  # funcție nouă în db.py

app.secret_key = "dev"  # pentru session

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
    app.run(debug=True, port=5005)