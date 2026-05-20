"""Tabi - 旅のしおりアプリ (Flask 版)

Streamlit を使わず、ブラウザで使える軽量Webアプリです。
すべて無料のソフト（Flask + SQLite）で動き、データもPC内に保存されます。

起動方法:
    pip install -r requirements.txt
    python app.py
    → ブラウザで http://127.0.0.1:5000 を開く
"""

import uuid
from pathlib import Path

from flask import (
    Flask, render_template, request, redirect, url_for, flash, abort
)
from werkzeug.utils import secure_filename

import travel_db

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}

app = Flask(__name__)
app.secret_key = "tabi-local-secret"  # ローカル利用向けの簡易キー
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # アルバム複数枚に備えて32MB

# 読み込み時にテーブルを用意（PythonAnywhere等のWSGI起動でも作られる）
travel_db.init_db()


# ----- 写真ファイルのヘルパー -----

def _allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def _save_photo(file_storage):
    """アップロードされた写真を保存し、ファイル名を返す。保存しなければ空文字。"""
    if not file_storage or file_storage.filename == "":
        return ""
    if not _allowed_file(file_storage.filename):
        return ""
    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    name = f"{uuid.uuid4().hex}.{secure_filename(ext)}"
    file_storage.save(UPLOAD_DIR / name)
    return name


def _delete_file(filename):
    if filename:
        path = UPLOAD_DIR / filename
        if path.exists():
            path.unlink()


def _detail_url(trip_id, anchor=""):
    url = url_for("detail", trip_id=trip_id)
    return url + (("#" + anchor) if anchor else "")


# テンプレートから定数を使えるようにする
@app.context_processor
def inject_constants():
    return {
        "STATUS_CHOICES": travel_db.STATUS_CHOICES,
        "DETAIL_CATEGORIES": travel_db.DETAIL_CATEGORIES,
    }


# ----- 一覧 + 検索 -----

@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    status = request.args.get("status") or None
    trips = travel_db.get_trips(q=q or None, status=status)
    return render_template("index.html", trips=trips, q=q, current_status=status)


# ----- 旅行の追加 -----

@app.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        destination = request.form.get("destination", "").strip()
        if not title or not destination:
            flash("旅行名と行き先は必須です。")
            return render_template("form.html", trip=request.form,
                                   action=url_for("add"), heading="新しい旅をつくる")
        new_id = travel_db.add_trip(
            title=title,
            destination=destination,
            start_date=request.form.get("start_date", "").strip(),
            end_date=request.form.get("end_date", "").strip(),
            budget=request.form.get("budget", "0").strip() or "0",
            status=request.form.get("status", travel_db.STATUS_CHOICES[0]),
            memo=request.form.get("memo", "").strip(),
        )
        flash("旅を作成しました。旅程や写真を追加しましょう。")
        return redirect(url_for("detail", trip_id=new_id))

    return render_template("form.html", trip={}, action=url_for("add"),
                           heading="新しい旅をつくる")


# ----- 旅行の詳細（旅のしおり） -----

@app.route("/trip/<int:trip_id>")
def detail(trip_id):
    trip = travel_db.get_trip(trip_id)
    if not trip:
        abort(404)
    return render_template(
        "detail.html",
        trip=trip,
        schedule=travel_db.get_schedule(trip_id),
        details=travel_db.get_details(trip_id),
        photos=travel_db.get_photos(trip_id),
    )


# ----- 旅行の編集 -----

@app.route("/trip/<int:trip_id>/edit", methods=["GET", "POST"])
def edit(trip_id):
    trip = travel_db.get_trip(trip_id)
    if not trip:
        abort(404)
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        destination = request.form.get("destination", "").strip()
        if not title or not destination:
            flash("旅行名と行き先は必須です。")
            data = dict(request.form)
            data["id"] = trip_id
            return render_template("form.html", trip=data,
                                   action=url_for("edit", trip_id=trip_id),
                                   heading="旅を編集")
        travel_db.update_trip(
            trip_id,
            title=title,
            destination=destination,
            start_date=request.form.get("start_date", "").strip(),
            end_date=request.form.get("end_date", "").strip(),
            budget=request.form.get("budget", "0").strip() or "0",
            status=request.form.get("status", travel_db.STATUS_CHOICES[0]),
            memo=request.form.get("memo", "").strip(),
        )
        flash("更新しました。")
        return redirect(url_for("detail", trip_id=trip_id))

    return render_template("form.html", trip=trip,
                           action=url_for("edit", trip_id=trip_id),
                           heading="旅を編集")


@app.route("/trip/<int:trip_id>/delete", methods=["POST"])
def delete(trip_id):
    files = travel_db.delete_trip(trip_id)
    for f in files:
        _delete_file(f)
    flash("旅を削除しました。")
    return redirect(url_for("index"))


# ----- 旅程（スケジュール） -----

@app.route("/trip/<int:trip_id>/schedule/add", methods=["POST"])
def add_schedule(trip_id):
    if not travel_db.get_trip(trip_id):
        abort(404)
    activity = request.form.get("activity", "").strip()
    if activity:
        travel_db.add_schedule(
            trip_id,
            day=request.form.get("day", "1").strip() or "1",
            time=request.form.get("time", "").strip(),
            activity=activity,
        )
    else:
        flash("予定の内容を入力してください。")
    return redirect(_detail_url(trip_id, "schedule"))


@app.route("/schedule/<int:item_id>/delete", methods=["POST"])
def delete_schedule(item_id):
    trip_id = travel_db.delete_schedule(item_id)
    if not trip_id:
        abort(404)
    return redirect(_detail_url(trip_id, "schedule"))


@app.route("/schedule/<int:item_id>/edit", methods=["GET", "POST"])
def edit_schedule(item_id):
    item = travel_db.get_schedule_item(item_id)
    if not item:
        abort(404)
    trip = travel_db.get_trip(item["trip_id"])
    if request.method == "POST":
        activity = request.form.get("activity", "").strip()
        if not activity:
            flash("予定の内容を入力してください。")
            return redirect(url_for("edit_schedule", item_id=item_id))
        travel_db.update_schedule(
            item_id,
            day=request.form.get("day", "1").strip() or "1",
            time=request.form.get("time", "").strip(),
            activity=activity,
        )
        flash("予定を更新しました。")
        return redirect(_detail_url(item["trip_id"], "schedule"))
    return render_template("schedule_edit.html", item=item, trip=trip)


# ----- 詳細情報 -----

@app.route("/trip/<int:trip_id>/detail/add", methods=["POST"])
def add_detail(trip_id):
    if not travel_db.get_trip(trip_id):
        abort(404)
    name = request.form.get("name", "").strip()
    category = request.form.get("category", travel_db.DETAIL_CATEGORIES[0])
    if name:
        travel_db.add_detail(
            trip_id,
            category=category,
            name=name,
            info=request.form.get("info", "").strip(),
            cost=request.form.get("cost", "0").strip() or "0",
            url=request.form.get("url", "").strip(),
            subtype=request.form.get("subtype", "").strip(),
            place_from=request.form.get("place_from", "").strip(),
            place_to=request.form.get("place_to", "").strip(),
            time_from=request.form.get("time_from", "").strip(),
            time_to=request.form.get("time_to", "").strip(),
        )
    else:
        flash("項目名を入力してください。")
    return redirect(_detail_url(trip_id, "details"))


@app.route("/detail/<int:item_id>/delete", methods=["POST"])
def delete_detail(item_id):
    trip_id = travel_db.delete_detail(item_id)
    if not trip_id:
        abort(404)
    return redirect(_detail_url(trip_id, "details"))


@app.route("/detail/<int:item_id>/edit", methods=["GET", "POST"])
def edit_detail(item_id):
    item = travel_db.get_detail(item_id)
    if not item:
        abort(404)
    trip = travel_db.get_trip(item["trip_id"])
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("項目名を入力してください。")
            return redirect(url_for("edit_detail", item_id=item_id))
        travel_db.update_detail(
            item_id,
            category=request.form.get("category", travel_db.DETAIL_CATEGORIES[0]),
            name=name,
            info=request.form.get("info", "").strip(),
            cost=request.form.get("cost", "0").strip() or "0",
            url=request.form.get("url", "").strip(),
            subtype=request.form.get("subtype", "").strip(),
            place_from=request.form.get("place_from", "").strip(),
            place_to=request.form.get("place_to", "").strip(),
            time_from=request.form.get("time_from", "").strip(),
            time_to=request.form.get("time_to", "").strip(),
        )
        flash("詳細を更新しました。")
        return redirect(_detail_url(item["trip_id"], "details"))
    return render_template("detail_edit.html", item=item, trip=trip)


# ----- アルバム（写真） -----

@app.route("/trip/<int:trip_id>/photo/add", methods=["POST"])
def add_photo(trip_id):
    if not travel_db.get_trip(trip_id):
        abort(404)
    files = request.files.getlist("photos")
    caption = request.form.get("caption", "").strip()
    saved = 0
    for f in files:
        name = _save_photo(f)
        if name:
            travel_db.add_photo(trip_id, name, caption)
            saved += 1
    if saved == 0:
        flash("写真を選んでください（png/jpg/jpeg/gif/webp）。")
    return redirect(_detail_url(trip_id, "album"))


@app.route("/photo/<int:photo_id>/delete", methods=["POST"])
def delete_photo(photo_id):
    trip_id, filename = travel_db.delete_photo(photo_id)
    if not trip_id:
        abort(404)
    _delete_file(filename)
    return redirect(_detail_url(trip_id, "album"))


if __name__ == "__main__":
    app.run(debug=True)
