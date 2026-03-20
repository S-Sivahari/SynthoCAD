"""Step Analyzer - Geometric Decompilation of STEP files.

Extracts exact geometric features (Cylinders, Planes, Cones, Tori)
from a STEP file using the OpenCascade Technology (OCP) kernel via CadQuery.
Also runs topology-aware block classification via ShapeRecognizer.

Returns a structured dictionary of features with exact dimensions,
which is then passed to the LLM for high-accuracy editing.
"""
import cadquery as cq
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import (
    GeomAbs_Cylinder, GeomAbs_Plane, GeomAbs_Cone,
    GeomAbs_Torus, GeomAbs_Sphere, GeomAbs_BSplineSurface,
    GeomAbs_SurfaceOfRevolution
)
from OCP.TopAbs import TopAbs_REVERSED
from typing import Dict, Any
import logging

from .shape_recognizer import ShapeRecognizer

_recognizer = ShapeRecognizer()

logger = logging.getLogger(__name__)


def _round(val: float, n: int = 4) -> float:
    return round(val, n)


def analyze(step_path: str) -> Dict[str, Any]:
    """
    Import a STEP file and extract all geometric features.

    Args:
        step_path: Absolute or relative path to the STEP file.

    Returns:
        A structured dict with keys: cylinders, planes, cones, tori,
        bounding_box, face_count, summary.
    """
    logger.info(f"Analyzing STEP: {step_path}")

    try:
        model = cq.importers.importStep(step_path)
        
    except Exception as e:
        raise ValueError(f"Failed to import STEP file '{step_path}': {e}")

    cylinders = []
    holes = []
    planes = []
    cones = []
    spheres = []
    tori = []
    other = []

    faces = model.faces().vals()
    logger.info(f"Found {len(faces)} faces to analyze.")

    for i, face in enumerate(faces):
        try:
            adaptor = BRepAdaptor_Surface(face.wrapped)
            surf_type = adaptor.GetType()

            if surf_type == GeomAbs_Cylinder:
                cyl = adaptor.Cylinder()
                radius = _round(cyl.Radius())
                loc = cyl.Location()
                ax = cyl.Axis()

                # Determine if this is an internal hole (face normal points
                # inward = REVERSED) or an external shaft/boss (FORWARD).
                is_hole = (face.wrapped.Orientation() == TopAbs_REVERSED)

                # Height of the cylinder from its bounding box.
                bb = face.BoundingBox()
                dx = _round(bb.xmax - bb.xmin)
                dy = _round(bb.ymax - bb.ymin)
                dz = _round(bb.zmax - bb.zmin)
                height = _round(max(dx, dy, dz))  # longest dim = cylinder axis

                cyl_entry = {
                    "id": f"f{i}",
                    "radius_mm": radius,
                    "height_mm": height,
                    "is_hole": is_hole,
                    "location": [_round(loc.X()), _round(loc.Y()), _round(loc.Z())],
                    "axis": [_round(ax.Direction().X()), _round(ax.Direction().Y()), _round(ax.Direction().Z())],
                }
                cylinders.append(cyl_entry)
                if is_hole:
                    holes.append({
                        **cyl_entry,
                        "type": "hole",
                    })

            elif surf_type == GeomAbs_Plane:
                pln = adaptor.Plane()
                ax = pln.Axis()
                bb = face.BoundingBox()

                # Take all three bbox dimensions; the near-zero one is the
                # face's thickness direction (the "flat" axis for a plane).
                dx = _round(bb.xmax - bb.xmin)
                dy = _round(bb.ymax - bb.ymin)
                dz = _round(bb.zmax - bb.zmin)

                # Sort descending, drop the smallest (≈0) → gives true 2D dims
                all_dims = sorted([dx, dy, dz], reverse=True)
                face_dims = [all_dims[0], all_dims[1]]  # two largest
                area = _round(face_dims[0] * face_dims[1])

                # Classify the face orientation by its normal
                nx = abs(_round(ax.Direction().X()))
                ny = abs(_round(ax.Direction().Y()))
                nz = abs(_round(ax.Direction().Z()))
                if nz > 0.9:
                    face_type = "horizontal"      # top / bottom
                elif nx > 0.9:
                    face_type = "vertical_x"      # left / right wall
                else:
                    face_type = "vertical_y"      # front / back wall

                # Use bounding box CENTER as location (instead of OCC's
                # arbitrary pln.Location() which is often a corner point)
                center = [
                    _round((bb.xmin + bb.xmax) / 2),
                    _round((bb.ymin + bb.ymax) / 2),
                    _round((bb.zmin + bb.zmax) / 2),
                ]

                planes.append({
                    "id": f"f{i}",
                    "location": center,
                    "normal": [_round(ax.Direction().X()), _round(ax.Direction().Y()), _round(ax.Direction().Z())],
                    "dims": face_dims,
                    "area_mm2": area,
                    "face_type": face_type,
                })

            elif surf_type == GeomAbs_Cone:
                cone = adaptor.Cone()
                loc = cone.Location()
                ax = cone.Axis()
                cones.append({
                    "id": f"f{i}",
                    "apex_radius_mm": _round(cone.RefRadius()),
                    "half_angle_deg": _round(cone.SemiAngle() * 180.0 / 3.141592653589793),
                    "location": [_round(loc.X()), _round(loc.Y()), _round(loc.Z())],
                    "axis": [_round(ax.Direction().X()), _round(ax.Direction().Y()), _round(ax.Direction().Z())],
                })

            elif surf_type == GeomAbs_Sphere:
                sph = adaptor.Sphere()
                loc = sph.Location()
                spheres.append({
                    "id": f"f{i}",
                    "radius_mm": _round(sph.Radius()),
                    "diameter_mm": _round(sph.Radius() * 2),
                    "location": [_round(loc.X()), _round(loc.Y()), _round(loc.Z())],
                })

            elif surf_type == GeomAbs_Torus:
                tor = adaptor.Torus()
                tori.append({
                    "id": f"f{i}",
                    "major_radius_mm": _round(tor.MajorRadius()),
                    "minor_radius_mm": _round(tor.MinorRadius()),
                })

            else:
                other.append({"id": f"f{i}", "type": str(surf_type)})

        except Exception as e:
            logger.warning(f"Could not analyze face {i}: {e}")
            other.append({"id": f"f{i}", "type": "error", "error": str(e)})

    # Overall bounding box
    try:
        bb = model.val().BoundingBox()
        bounding_box = {
            "x_mm": _round(bb.xmax - bb.xmin),
            "y_mm": _round(bb.ymax - bb.ymin),
            "z_mm": _round(bb.zmax - bb.zmin),
        }
    except Exception:
        bounding_box = {}

    # Build a human-readable summary for the LLM
    summary_parts = []
    if bounding_box:
        summary_parts.append(
            f"Overall bounding box: {bounding_box['x_mm']}mm x {bounding_box['y_mm']}mm x {bounding_box['z_mm']}mm."
        )
    if cylinders:
        radii = sorted(set(c["radius_mm"] for c in cylinders))
        summary_parts.append(f"{len(cylinders)} cylindrical face(s) with radii: {radii} mm.")
    if planes:
        summary_parts.append(f"{len(planes)} planar face(s).")
    if cones:
        summary_parts.append(f"{len(cones)} conical face(s).")
    if spheres:
        radii = sorted(set(s["radius_mm"] for s in spheres))
        summary_parts.append(f"{len(spheres)} spherical face(s) with radii: {radii} mm.")
    if holes:
        hole_radii = sorted(set(h["radius_mm"] for h in holes))
        summary_parts.append(f"{len(holes)} hole face(s) with radii: {hole_radii} mm.")
    if tori:
        summary_parts.append(f"{len(tori)} toroidal face(s) (e.g. fillets).")

    # -----------------------------------------------------------------
    # Topology-aware block recognition
    # Skip for large models: ShapeRecognizer builds an O(F²) adjacency
    # graph and re-imports the STEP file, which is prohibitively slow
    # and memory-intensive on assemblies with many faces.
    # -----------------------------------------------------------------
    _RECOGNIZER_FACE_LIMIT = 150
    blocks = []
    if len(faces) > _RECOGNIZER_FACE_LIMIT:
        logger.info(
            f"Skipping ShapeRecognizer for large model "
            f"({len(faces)} faces > {_RECOGNIZER_FACE_LIMIT} threshold)."
        )
    else:
        try:
            blocks = _recognizer.recognize(step_path)
            if blocks:
                summary_parts.append(
                    f"Recognised {len(blocks)} block(s): "
                    + ", ".join(b["summary"] for b in blocks)
                    + "."
                )
        except Exception as e:
            logger.warning(f"Shape recognition failed: {e}")

    # Fallback sphere detection:
    # Some STEP exporters represent spheres as trimmed/revolved surfaces that
    # don't show up as GeomAbs_Sphere per-face. If the topology recognizer
    # confidently identifies a sphere component, synthesize per-face sphere
    # entries so the viewer can classify clicked faces correctly.
    sphere_face_ids = {s["id"] for s in spheres}
    for block in blocks:
        if block.get("shape_type") != "sphere":
            continue

        params = block.get("parameters", {}) or {}
        bb = block.get("bounding_box", {}) or {}
        radius = params.get("radius")
        if radius is None:
            diameter = params.get("diameter")
            if diameter is not None:
                radius = diameter / 2.0

        if radius is None:
            dx = bb.get("dx", 0.0)
            dy = bb.get("dy", 0.0)
            dz = bb.get("dz", 0.0)
            radius = max(dx, dy, dz) / 2.0

        center = [
            _round((bb.get("xmin", 0.0) + bb.get("xmax", 0.0)) / 2.0),
            _round((bb.get("ymin", 0.0) + bb.get("ymax", 0.0)) / 2.0),
            _round((bb.get("zmin", 0.0) + bb.get("zmax", 0.0)) / 2.0),
        ]

        for fid in block.get("face_ids", []):
            if fid in sphere_face_ids:
                continue
            sphere_entry = {
                "id": fid,
                "radius_mm": _round(radius),
                "diameter_mm": _round(radius * 2),
                "location": center,
            }
            spheres.append(sphere_entry)
            sphere_face_ids.add(fid)

    result = {
        "cylinders": cylinders,
        "holes": holes,
        "planes": planes,
        "cones": cones,
        "spheres": spheres,
        "tori": tori,
        "other_faces": other,
        "bounding_box": bounding_box,
        "face_count": len(faces),
        "blocks": blocks,
        "summary": " ".join(summary_parts),
    }

    logger.info(f"Analysis complete: {len(cylinders)} cylinders, {len(planes)} planes, "
                f"{len(blocks)} block(s).")
    return result


if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python step_analyzer.py <path_to.step>")
        sys.exit(1)

    features = analyze(sys.argv[1])
    print(json.dumps(features, indent=2))
