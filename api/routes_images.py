"""
api.routes_images - /api/v1/parts/<dmtuid>/images endpoints.

Upload, list, and delete part images.  Max 5 images per part.
Supports multipart file upload and URL-based download.
"""

import os
import re
import uuid
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from flask import request, jsonify, abort

from api import api_bp
from db import get_session
from db.models import Part, PartImage
import config

MAX_IMAGES = 5
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _safe_ext(filename: str) -> str:
    """Return lowercase extension if allowed, else empty string."""
    ext = Path(filename).suffix.lower()
    return ext if ext in ALLOWED_EXT else ""


def _ensure_dir(dmtuid: str) -> Path:
    """Create and return the image directory for a part."""
    d = config.PART_IMAGES_DIR / dmtuid
    d.mkdir(parents=True, exist_ok=True)
    return d


@api_bp.route("/parts/<dmtuid>/images", methods=["GET"])
def list_images(dmtuid: str):
    """List all images for a part."""
    session = get_session()
    try:
        imgs = session.query(PartImage).filter(
            PartImage.dmtuid == dmtuid
        ).order_by(PartImage.position).all()
        return jsonify([
            {
                "id": img.id,
                "filename": img.filename,
                "position": img.position,
                "url": f"/part_images/{dmtuid}/{img.filename}",
            }
            for img in imgs
        ])
    finally:
        session.close()


@api_bp.route("/parts/<dmtuid>/images", methods=["POST"])
def upload_image(dmtuid: str):
    """
    Upload an image via multipart file or JSON with image_url.
    Returns the new image record.
    """
    session = get_session()
    try:
        part = session.query(Part).filter(Part.dmtuid == dmtuid).first()
        if not part:
            abort(404, description="Part not found")

        count = session.query(PartImage).filter(
            PartImage.dmtuid == dmtuid
        ).count()
        if count >= MAX_IMAGES:
            return jsonify({"error": f"Maximum {MAX_IMAGES} images allowed"}), 400

        img_dir = _ensure_dir(dmtuid)
        next_pos = count

        # --- File upload ---
        if "file" in request.files:
            f = request.files["file"]
            if not f or not f.filename:
                return jsonify({"error": "No file provided"}), 400

            ext = _safe_ext(f.filename)
            if not ext:
                return jsonify({"error": f"Unsupported format. Allowed: {', '.join(ALLOWED_EXT)}"}), 400

            # Read and check size
            data = f.read()
            if len(data) > MAX_FILE_SIZE:
                return jsonify({"error": "File too large (max 10 MB)"}), 400

            safe_name = f"{uuid.uuid4().hex[:12]}{ext}"
            dest = img_dir / safe_name
            dest.write_bytes(data)

        # --- URL download ---
        elif request.is_json and request.json.get("image_url"):
            url = request.json["image_url"]
            # Basic URL validation
            if not re.match(r'^https?://', url):
                return jsonify({"error": "URL must start with http:// or https://"}), 400

            try:
                req = Request(url, headers={"User-Agent": "DMTDB/1.0"})
                resp = urlopen(req, timeout=15)  # noqa: S310 — validated scheme above
                content_type = resp.headers.get("Content-Type", "")
                data = resp.read(MAX_FILE_SIZE + 1)
                if len(data) > MAX_FILE_SIZE:
                    return jsonify({"error": "Image too large (max 10 MB)"}), 400
            except (URLError, HTTPError) as e:
                return jsonify({"error": f"Failed to fetch image: {e}"}), 400
            ext_map = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/gif": ".gif",
                "image/webp": ".webp",
            }
            ext = ""
            for ct, e in ext_map.items():
                if ct in content_type:
                    ext = e
                    break
            if not ext:
                # Try from URL path
                ext = _safe_ext(url.split("?")[0].split("#")[0])
            if not ext:
                ext = ".jpg"  # fallback

            safe_name = f"{uuid.uuid4().hex[:12]}{ext}"
            dest = img_dir / safe_name
            dest.write_bytes(data)

        else:
            return jsonify({"error": "Provide a file upload or image_url"}), 400

        img = PartImage(
            dmtuid=dmtuid,
            filename=safe_name,
            position=next_pos,
        )
        session.add(img)
        session.commit()

        return jsonify({
            "id": img.id,
            "filename": img.filename,
            "position": img.position,
            "url": f"/part_images/{dmtuid}/{img.filename}",
        }), 201

    finally:
        session.close()


@api_bp.route("/parts/<dmtuid>/images/<int:image_id>", methods=["DELETE"])
def delete_image(dmtuid: str, image_id: int):
    """Delete an image and its file."""
    session = get_session()
    try:
        img = session.query(PartImage).filter(
            PartImage.id == image_id,
            PartImage.dmtuid == dmtuid,
        ).first()
        if not img:
            abort(404, description="Image not found")

        # Delete file
        fpath = config.PART_IMAGES_DIR / dmtuid / img.filename
        if fpath.is_file():
            fpath.unlink()

        session.delete(img)

        # Re-number positions
        remaining = session.query(PartImage).filter(
            PartImage.dmtuid == dmtuid
        ).order_by(PartImage.position).all()
        for i, r in enumerate(remaining):
            r.position = i

        session.commit()
        return jsonify({"success": True})
    finally:
        session.close()
