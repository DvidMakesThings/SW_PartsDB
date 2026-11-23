import json
import uuid
from flask import render_template, redirect, request, current_app, Response
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from db.models import BuildBatch, BuildPosting, DesignRelease, AssemblyDefinition, PhysicalUnit
from ui import ui_bp
from ui.routes_designs import engineering_route, get_or_404, integer, paginate
from services import build_service as builds


def signer():
    return URLSafeTimedSerializer(current_app.secret_key, salt="assembly-review-v1")


@ui_bp.route("/builds", methods=["GET", "POST"])
@engineering_route
def builds_index(db):
    if request.method == "POST":
        build = builds.create_build(db, integer("release_id"), request.form.get("quantity"), request.form.get("notes", ""))
        return redirect(f"/builds/{build.id}", 303)
    items, page, pages = paginate(db.query(BuildBatch).order_by(BuildBatch.id.desc()))
    releases = db.query(DesignRelease).join(AssemblyDefinition).filter(DesignRelease.status.in_(["released", "superseded"])).all()
    return render_template("builds.html", builds=items, releases=releases, page=page, pages=pages)


@ui_bp.route("/builds/<int:build_id>", methods=["GET", "POST"])
@engineering_route
def build_detail(db, build_id):
    build = get_or_404(db, BuildBatch, build_id)
    definition = db.query(AssemblyDefinition).filter_by(release_id=build.release_id).one()
    lines = json.loads(definition.lines_json)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "preview":
            substitutions = {str(i): {"part_id": request.form.get(f"part_{i}", ""), "reason": request.form.get(f"reason_{i}", "")}
                             for i in range(len(lines))}
            review = builds.plan(db, build.id, request.form.get("quantity"), substitutions,
                                 request.form.get("serials", "").splitlines())
            token = signer().dumps({"review": review, "key": uuid.uuid4().hex})
            return render_template("build_review.html", build=build, review=review, token=token)
        if action in {"assemble", "reserve"}:
            try:
                signed = signer().loads(request.form.get("review", ""), max_age=900)
            except (BadSignature, SignatureExpired):
                raise ValueError("Build review expired or is invalid; preview again") from None
            builds.apply(db, build.id, signed["review"], signed["key"], action)
        elif action == "cancel":
            builds.cancel(db, build.id, request.form.get("reason", ""), request.form.get("key", ""))
        elif action == "return":
            builds.return_material(db, build.id, integer("movement_id"), request.form.get("quantity", ""),
                                   request.form.get("reason", ""), request.form.get("key", ""))
        else:
            raise ValueError("Unknown build action")
        return redirect(request.path, 303)
    return render_template("build_detail.html", build=build, lines=lines,
        postings=db.query(BuildPosting).filter_by(build_id=build.id).order_by(BuildPosting.id.desc()).all(),
        units=db.query(PhysicalUnit).filter_by(build_id=build.id).order_by(PhysicalUnit.serial_key).all())


@ui_bp.route("/builds/bom-example.csv")
def bom_example():
    return Response('Reference,Quantity,DMTUID,Value,Footprint,DNP,Source\n"C1,C2",2,,100nF,C_0603,no,personal\nR1,1,,10k,R_0603,yes,personal\n',
                    mimetype="text/csv", headers={"Content-Disposition": 'attachment; filename="bom-example.csv"'})
