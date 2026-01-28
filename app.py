from flask import Flask, render_template, request
from db import init_db, list_ads, get_ad

app = Flask(__name__)
init_db()

@app.get("/")
def index():
    min_score = request.args.get("min_score", default=None, type=float)
    ads = list_ads(limit=200, min_score=min_score)
    return render_template("index.html", ads=ads, min_score=min_score)

@app.get("/ad/<int:ad_id>")
def ad_detail(ad_id):
    ad = get_ad(ad_id)
    return render_template("ad.html", ad=ad)

if __name__ == "__main__":
    app.run(debug=True, port=5005)