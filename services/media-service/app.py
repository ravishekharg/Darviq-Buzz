import os

from flask import Flask, jsonify, request, send_from_directory

from metrics import init_metrics
from models import MediaAsset, SessionLocal, init_db
from storage import LOCAL_UPLOAD_DIR, save_image

app = Flask(__name__)
init_metrics(app)
init_db()


def current_username() -> str | None:
    return request.headers.get("X-User-Username")


@app.get("/health")
def health():
    return jsonify(status="ok", service="media-service")


@app.post("/media/upload")
def upload():
    uploader = current_username()
    if not uploader:
        return jsonify(error={"message": "Authentication required"}), 401

    file = request.files.get("file")
    if file is None or not file.filename:
        return jsonify(error={"message": "No file provided"}), 400

    try:
        url, backend, size_bytes = save_image(file.stream, file.filename)
    except ValueError as e:
        return jsonify(error={"message": str(e)}), 400

    asset = MediaAsset(
        uploader_username=uploader, original_filename=file.filename, content_type=file.mimetype,
        size_bytes=size_bytes, storage_backend=backend, url=url,
    )
    db = SessionLocal()
    try:
        db.add(asset)
        db.commit()
        return jsonify(asset.to_dict()), 201
    finally:
        db.close()


@app.get("/media/<asset_id>")
def get_asset(asset_id):
    db = SessionLocal()
    try:
        asset = db.get(MediaAsset, asset_id)
        if asset is None:
            return jsonify(error={"message": "Asset not found"}), 404
        return jsonify(asset.to_dict())
    finally:
        db.close()


# Serves the local-disk fallback path (/media/uploads/<file>) referenced by
# save_image() above when S3 isn't reachable -- reachable from the browser
# through the gateway's "/api/media" -> media-service mapping.
@app.get("/media/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(LOCAL_UPLOAD_DIR, filename)


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5009)), debug=debug_mode, threaded=True)
