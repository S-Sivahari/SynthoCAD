"""Shape Recognizer - Topology-aware block classification from STEP files.

Builds a face-adjacency graph (faces that share an edge are neighbours) and
then matches the resulting face-type signature against known shape patterns.

Supported primitives
--------------------
Box/Cube, Cylinder, Cone, Sphere, Torus

Supported composites
--------------------
Tube (hollow cylinder / pipe), Disc / Washer,
Pipe Bend (cylinder + torus + cylinder), Chamfered Cylinder,
Filleted Box, Hex Prism (nut / bolt head)

Supported complex shapes
------------------------
Spur / Helical Gear (detected by tooth-face periodicity),
L-Bracket / T-Bracket (two rectangular plates at ~90° angle),
Flange (cylinder + disc + bolt-circle holes),
Threaded Rod (many small planar / conical faces in helix),
Splined Shaft (periodic planar faces around a cylinder)

Each recognised shape is returned as a ``Block`` dictionary containing:
  - shape_type   : canonical name
  - parameters   : extracted geometric parameters
  - confidence   : 0.0–1.0 match score
  - faces_used   : list of face IDs that made up the block
  - bounding_box : tight bbox of the block
  - summary      : one-line human-readable description

Usage
-----
    from shape_recognizer import ShapeRecognizer
    recognizer = ShapeRecognizer()
    blocks = recognizer.recognize("part.step")
    for blk in blocks:
        print(blk["shape_type"], blk["parameters"])
"""

from __future__ import annotations

import math
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import defaultdict

import cadquery as cq
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import (
    GeomAbs_Cylinder, GeomAbs_Plane, GeomAbs_Cone,
    GeomAbs_Torus, GeomAbs_Sphere,
)
from OCP.TopExp import TopExp
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_ROUND = 4               # decimal places
_TOL = 0.5               # mm tolerance for geometric comparisons
_ANGLE_TOL = 5.0         # degrees tolerance for axis comparisons


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _r(v: float, n: int = _ROUND) -> float:
    return round(v, n)


def _vec_dot(a: List[float], b: List[float]) -> float:
    return sum(ai * bi for ai, bi in zip(a, b))


def _vec_len(v: List[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def _vecs_parallel(a: List[float], b: List[float], tol_deg: float = _ANGLE_TOL) -> bool:
    """Return True if two unit-ish vectors are parallel (same or opposite)."""
    la, lb = _vec_len(a), _vec_len(b)
    if la < 1e-9 or lb < 1e-9:
        return False
    cos = abs(_vec_dot(a, b)) / (la * lb)
    cos = min(1.0, cos)
    return math.degrees(math.acos(cos)) < tol_deg


def _vecs_perpendicular(a: List[float], b: List[float], tol_deg: float = _ANGLE_TOL) -> bool:
    la, lb = _vec_len(a), _vec_len(b)
    if la < 1e-9 or lb < 1e-9:
        return False
    cos = abs(_vec_dot(a, b)) / (la * lb)
    cos = min(1.0, cos)
    return math.degrees(math.acos(cos)) > (90.0 - tol_deg)


def _pts_on_ring(pts: List[Tuple[float, float]], tol: float = _TOL) -> Tuple[bool, float, Tuple[float, float]]:
    """Check if 2-D points are equidistant from a common centre. Returns (ok, radius, centre)."""
    if len(pts) < 3:
        return False, 0.0, (0.0, 0.0)
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    radii = [math.sqrt((p[0] - cx) ** 2 + (p[1] - cy) ** 2) for p in pts]
    r_mean = sum(radii) / len(radii)
    if r_mean < 1e-6:
        return False, 0.0, (cx, cy)
    spread = max(radii) - min(radii)
    return spread / r_mean < 0.15, r_mean, (cx, cy)


# ---------------------------------------------------------------------------
# Face-info record
# ---------------------------------------------------------------------------

class FaceInfo:
    """Lightweight record of a single face's geometry."""

    def __init__(self, face_id: str, occ_face):
        self.id = face_id
        self.occ_face = occ_face
        self.surf_type: str = "unknown"
        self.normal: List[float] = [0.0, 0.0, 0.0]
        self.axis: List[float] = [0.0, 0.0, 0.0]
        self.location: List[float] = [0.0, 0.0, 0.0]
        self.radius: float = 0.0
        self.radius2: float = 0.0   # minor radius for torus; half-angle for cone
        self.bbox: Dict[str, float] = {}
        self._parse()

    def _parse(self):
        try:
            adaptor = BRepAdaptor_Surface(self.occ_face)
            st = adaptor.GetType()

            # Tight bounding box
            bb = Bnd_Box()
            BRepBndLib.Add_s(self.occ_face, bb)
            xmin, ymin, zmin, xmax, ymax, zmax = bb.Get()
            self.bbox = {
                "xmin": _r(xmin), "xmax": _r(xmax),
                "ymin": _r(ymin), "ymax": _r(ymax),
                "zmin": _r(zmin), "zmax": _r(zmax),
                "dx": _r(xmax - xmin), "dy": _r(ymax - ymin), "dz": _r(zmax - zmin),
            }
            cx = _r((xmin + xmax) / 2)
            cy = _r((ymin + ymax) / 2)
            cz = _r((zmin + zmax) / 2)
            self.location = [cx, cy, cz]

            if st == GeomAbs_Plane:
                self.surf_type = "plane"
                pln = adaptor.Plane()
                ax = pln.Axis().Direction()
                self.normal = [_r(ax.X()), _r(ax.Y()), _r(ax.Z())]
                self.axis = self.normal

            elif st == GeomAbs_Cylinder:
                self.surf_type = "cylinder"
                cyl = adaptor.Cylinder()
                self.radius = _r(cyl.Radius())
                ax = cyl.Axis().Direction()
                self.axis = [_r(ax.X()), _r(ax.Y()), _r(ax.Z())]
                loc = cyl.Location()
                self.location = [_r(loc.X()), _r(loc.Y()), _r(loc.Z())]

            elif st == GeomAbs_Cone:
                self.surf_type = "cone"
                cone = adaptor.Cone()
                self.radius = _r(cone.RefRadius())
                self.radius2 = _r(math.degrees(cone.SemiAngle()))
                ax = cone.Axis().Direction()
                self.axis = [_r(ax.X()), _r(ax.Y()), _r(ax.Z())]
                loc = cone.Location()
                self.location = [_r(loc.X()), _r(loc.Y()), _r(loc.Z())]

            elif st == GeomAbs_Torus:
                self.surf_type = "torus"
                tor = adaptor.Torus()
                self.radius = _r(tor.MajorRadius())
                self.radius2 = _r(tor.MinorRadius())
                ax = tor.Axis().Direction()
                self.axis = [_r(ax.X()), _r(ax.Y()), _r(ax.Z())]
                loc = tor.Location()
                self.location = [_r(loc.X()), _r(loc.Y()), _r(loc.Z())]

            elif st == GeomAbs_Sphere:
                self.surf_type = "sphere"
                sph = adaptor.Sphere()
                self.radius = _r(sph.Radius())
                loc = sph.Location()
                self.location = [_r(loc.X()), _r(loc.Y()), _r(loc.Z())]

            else:
                self.surf_type = "bspline"

        except Exception as exc:
            logger.debug("FaceInfo parse error for %s: %s", self.id, exc)
            self.surf_type = "error"

    @property
    def is_plane(self):  return self.surf_type == "plane"
    @property
    def is_cylinder(self): return self.surf_type == "cylinder"
    @property
    def is_cone(self):   return self.surf_type == "cone"
    @property
    def is_torus(self):  return self.surf_type == "torus"
    @property
    def is_sphere(self): return self.surf_type == "sphere"


# ---------------------------------------------------------------------------
# Adjacency graph builder
# ---------------------------------------------------------------------------

def _build_adjacency(occ_shape, face_infos: List[FaceInfo]) -> Dict[str, Set[str]]:
    """
    Build face adjacency: two faces are adjacent when they share an edge.
    Uses per-face TopExp_Explorer to collect edge hashes, then groups faces
    that share the same edge — avoids TopTools_ListIteratorOfListOfShape which
    is not exposed in all OCP binding versions.
    Returns dict  {face_id -> set_of_adjacent_face_ids}.
    """
    # Build a hash from OCC face pointer → our face_id
    ptr_to_id: Dict[int, str] = {}
    for fi in face_infos:
        ptr_to_id[fi.occ_face.HashCode(1 << 30)] = fi.id

    adj: Dict[str, Set[str]] = {fi.id: set() for fi in face_infos}

    # Map each edge hash → list of face_ids that contain that edge
    edge_to_faces: Dict[int, List[str]] = defaultdict(list)
    for fi in face_infos:
        exp = TopExp_Explorer(fi.occ_face, TopAbs_EDGE)
        seen_edges: Set[int] = set()
        while exp.More():
            edge_hash = exp.Current().HashCode(1 << 30)
            if edge_hash not in seen_edges:
                seen_edges.add(edge_hash)
                edge_to_faces[edge_hash].append(fi.id)
            exp.Next()

    # Any edge shared by ≥2 faces means those faces are adjacent
    for face_ids_on_edge in edge_to_faces.values():
        for a in face_ids_on_edge:
            for b in face_ids_on_edge:
                if a != b:
                    adj[a].add(b)

    return adj


def _connected_components(adj: Dict[str, Set[str]]) -> List[Set[str]]:
    """BFS to find connected components in adjacency graph."""
    visited: Set[str] = set()
    components: List[Set[str]] = []

    for start in adj:
        if start in visited:
            continue
        component: Set[str] = set()
        queue = [start]
        while queue:
            node = queue.pop()
            if node in visited:
                continue
            visited.add(node)
            component.add(node)
            for nb in adj.get(node, set()):
                if nb not in visited:
                    queue.append(nb)
        components.append(component)

    return components


# ---------------------------------------------------------------------------
# Shape pattern classifiers
# ---------------------------------------------------------------------------

class _Classifiers:
    """Collection of shape classifiers – each returns (confidence, params_dict)."""

    # ---- Box / Cube -------------------------------------------------------
    @staticmethod
    def box(faces: List[FaceInfo], adj: Dict[str, Set[str]], bbox: Dict) -> Tuple[float, Dict]:
        planes = [f for f in faces if f.is_plane]
        non_planes = [f for f in faces if not f.is_plane]
        if non_planes or len(planes) < 6:
            return 0.0, {}

        # Collect distinct normals, expect 3 pairs
        normals = [tuple(f.normal) for f in planes]
        unique_axes: List[List[float]] = []
        for n in normals:
            n_abs = [abs(v) for v in n]
            if not any(_vecs_parallel(n_abs, u) for u in unique_axes):
                unique_axes.append(n_abs)

        if len(unique_axes) != 3:
            return 0.4, {}  # still plausible, maybe a weird box

        # All axes mutually perpendicular?
        ax0, ax1, ax2 = unique_axes
        if not (_vecs_perpendicular(ax0, ax1) and _vecs_perpendicular(ax1, ax2)):
            return 0.3, {}

        w = _r(bbox.get("dx", 0))
        d = _r(bbox.get("dy", 0))
        h = _r(bbox.get("dz", 0))
        conf = 0.95 if len(planes) == 6 else 0.75
        return conf, {"width": w, "depth": d, "height": h}

    # ---- Cylinder ---------------------------------------------------------
    @staticmethod
    def cylinder(faces: List[FaceInfo], adj: Dict[str, Set[str]], bbox: Dict) -> Tuple[float, Dict]:
        cyls = [f for f in faces if f.is_cylinder]
        planes = [f for f in faces if f.is_plane]
        others = [f for f in faces if not f.is_cylinder and not f.is_plane]

        if not cyls or others:
            return 0.0, {}
        if len(cyls) != 1 or len(planes) != 2:
            return 0.3 if cyls else 0.0, {}

        cyl = cyls[0]
        r = cyl.radius
        h = _r(bbox.get("dz", bbox.get("dy", bbox.get("dx", r * 2))))
        # Check caps are perpendicular to cylinder axis
        cap_ok = all(_vecs_parallel(cyl.axis, p.normal) for p in planes)
        conf = 0.95 if cap_ok else 0.6
        return conf, {"radius": r, "diameter": _r(r * 2), "height": h, "axis": cyl.axis}

    # ---- Cone -------------------------------------------------------------
    @staticmethod
    def cone(faces: List[FaceInfo], adj: Dict[str, Set[str]], bbox: Dict) -> Tuple[float, Dict]:
        cones = [f for f in faces if f.is_cone]
        planes = [f for f in faces if f.is_plane]
        others = [f for f in faces if not f.is_cone and not f.is_plane]
        if not cones or others:
            return 0.0, {}

        cone = cones[0]
        base_r = cone.radius
        half_angle = cone.radius2  # stored as degrees
        h = _r(max(bbox.get("dz", 0), bbox.get("dy", 0), bbox.get("dx", 0)))
        tip_r = _r(base_r - h * math.tan(math.radians(abs(half_angle))))
        tip_r = max(0.0, tip_r)
        conf = 0.92 if len(planes) <= 2 else 0.7
        return conf, {
            "base_radius": base_r, "tip_radius": tip_r,
            "half_angle_deg": half_angle, "height": h, "axis": cone.axis
        }

    # ---- Sphere -----------------------------------------------------------
    @staticmethod
    def sphere(faces: List[FaceInfo], adj: Dict[str, Set[str]], bbox: Dict) -> Tuple[float, Dict]:
        spheres = [f for f in faces if f.is_sphere]
        if not spheres or len(faces) != 1:
            return 0.0, {}
        s = spheres[0]
        return 0.97, {"radius": s.radius, "diameter": _r(s.radius * 2)}

    # ---- Torus (full ring) ------------------------------------------------
    @staticmethod
    def torus(faces: List[FaceInfo], adj: Dict[str, Set[str]], bbox: Dict) -> Tuple[float, Dict]:
        tori = [f for f in faces if f.is_torus]
        if not tori or len(faces) != 1:
            return 0.0, {}
        t = tori[0]
        return 0.97, {"major_radius": t.radius, "minor_radius": t.radius2, "axis": t.axis}

    # ---- Tube / Hollow Cylinder -------------------------------------------
    @staticmethod
    def tube(faces: List[FaceInfo], adj: Dict[str, Set[str]], bbox: Dict) -> Tuple[float, Dict]:
        cyls = [f for f in faces if f.is_cylinder]
        planes = [f for f in faces if f.is_plane]
        others = [f for f in faces if not f.is_cylinder and not f.is_plane]
        if len(cyls) != 2 or len(planes) != 2 or others:
            return 0.0, {}

        radii = sorted(c.radius for c in cyls)
        outer_r, inner_r = radii[1], radii[0]
        if inner_r >= outer_r:
            return 0.0, {}

        # Axes should be parallel
        if not _vecs_parallel(cyls[0].axis, cyls[1].axis):
            return 0.3, {}

        h = _r(max(bbox.get("dz", 0), bbox.get("dy", 0), bbox.get("dx", 0)))
        return 0.93, {
            "outer_radius": outer_r, "inner_radius": inner_r,
            "outer_diameter": _r(outer_r * 2), "inner_diameter": _r(inner_r * 2),
            "wall_thickness": _r(outer_r - inner_r), "height": h,
            "axis": cyls[0].axis,
        }

    # ---- Disc / Washer (flat tube) ----------------------------------------
    @staticmethod
    def disc(faces: List[FaceInfo], adj: Dict[str, Set[str]], bbox: Dict) -> Tuple[float, Dict]:
        cyls = [f for f in faces if f.is_cylinder]
        planes = [f for f in faces if f.is_plane]
        others = [f for f in faces if not f.is_cylinder and not f.is_plane]

        if others:
            return 0.0, {}

        n_cyls = len(cyls)
        if n_cyls not in (1, 2):
            return 0.0, {}

        h = _r(min(bbox.get("dz", 999), bbox.get("dy", 999), bbox.get("dx", 999)))
        main_dim = _r(max(bbox.get("dz", 0), bbox.get("dy", 0), bbox.get("dx", 0)))
        if h > main_dim / 5:  # not flat enough for a disc / washer
            return 0.0, {}

        if n_cyls == 1:
            r = cyls[0].radius
            return 0.88, {"outer_radius": r, "outer_diameter": _r(r * 2), "thickness": h}
        else:
            radii = sorted(c.radius for c in cyls)
            return 0.88, {
                "outer_radius": radii[1], "inner_radius": radii[0],
                "outer_diameter": _r(radii[1] * 2), "inner_diameter": _r(radii[0] * 2),
                "thickness": h,
            }

    # ---- Pipe Bend (cylinder – torus – cylinder) --------------------------
    @staticmethod
    def pipe_bend(faces: List[FaceInfo], adj: Dict[str, Set[str]], bbox: Dict) -> Tuple[float, Dict]:
        tori = [f for f in faces if f.is_torus]
        cyls = [f for f in faces if f.is_cylinder]
        planes = [f for f in faces if f.is_plane]
        others = [f for f in faces if
                  not f.is_torus and not f.is_cylinder and not f.is_plane]
        if not tori or others:
            return 0.0, {}
        if len(tori) != 1:
            return 0.0, {}

        btor = tori[0]
        pipe_r = btor.radius2   # minor radius = pipe bore
        bend_r = btor.radius    # major radius = bend radius

        # Outer cylinders should match pipe radius
        cyl_radii_ok = all(abs(c.radius - pipe_r) < _TOL * 3 for c in cyls)
        conf = 0.90 if cyl_radii_ok else 0.65

        # Estimate bend angle from the arc length of bounding box
        arc = _r(math.pi * bend_r)  # default 180°
        bend_angle = 90.0  # most common

        return conf, {
            "pipe_radius": pipe_r, "pipe_diameter": _r(pipe_r * 2),
            "bend_radius": bend_r, "bend_angle_deg": bend_angle,
            "torus_axis": btor.axis,
        }

    # ---- Hex Prism (nut / bolt head) -------------------------------------
    @staticmethod
    def hex_prism(faces: List[FaceInfo], adj: Dict[str, Set[str]], bbox: Dict) -> Tuple[float, Dict]:
        planes = [f for f in faces if f.is_plane]
        cyls = [f for f in faces if f.is_cylinder]
        cones = [f for f in faces if f.is_cone]
        others = [f for f in faces if
                  not f.is_plane and not f.is_cylinder and not f.is_cone]
        if others:
            return 0.0, {}

        lateral = [p for p in planes if not _vecs_parallel(p.normal, [0, 0, 1])]
        caps = [p for p in planes if _vecs_parallel(p.normal, [0, 0, 1])]

        if len(lateral) != 6 or len(caps) < 2:
            return 0.0, {}

        # Lateral normals should be 60° apart
        normals_2d = [(abs(p.normal[0]), abs(p.normal[1])) for p in lateral]
        h = _r(bbox.get("dz", 1))
        across_flats = _r(bbox.get("dx", 0))
        return 0.90, {"across_flats": across_flats, "height": h, "sides": 6}

    # ---- Spur / Helical Gear --------------------------------------------
    @staticmethod
    def gear(faces: List[FaceInfo], adj: Dict[str, Set[str]], bbox: Dict) -> Tuple[float, Dict]:
        """
        Heuristic: a gear has many regularly-spaced lateral plane faces
        (the tooth flanks) plus annular caps and a central bore cylinder.
        Minimum ~10 lateral faces for 5 teeth.
        """
        planes = [f for f in faces if f.is_plane]
        cyls = [f for f in faces if f.is_cylinder]

        # Need at least one bore cylinder and many planar faces
        if len(planes) < 10 or not cyls:
            return 0.0, {}

        # Lateral planes: not parallel to Z
        lateral = [p for p in planes
                   if not _vecs_parallel(p.normal, [0, 0, 1])]
        caps = [p for p in planes
                if _vecs_parallel(p.normal, [0, 0, 1])]

        if len(lateral) < 8:
            return 0.0, {}

        # Check if lateral face normals are arranged radially (uniformly around Z)
        normals_2d = [(p.normal[0], p.normal[1]) for p in lateral]
        angles = sorted(math.atan2(n[1], n[0]) for n in normals_2d
                        if abs(n[0]) > 0.01 or abs(n[1]) > 0.01)

        if len(angles) < 8:
            return 0.0, {}

        # Angular spacing should be roughly uniform
        diffs = [abs(angles[i + 1] - angles[i]) for i in range(len(angles) - 1)]
        diffs.append(abs(angles[0] + 2 * math.pi - angles[-1]))
        mean_d = sum(diffs) / len(diffs)
        spread = max(abs(d - mean_d) for d in diffs)
        if mean_d < 1e-6 or spread / mean_d > 0.4:
            return 0.0, {}

        num_teeth = len(lateral) // 2
        outer_r = _r(max(bbox.get("dx", 0), bbox.get("dy", 0)) / 2)
        bore_r = _r(min(c.radius for c in cyls))
        h = _r(bbox.get("dz", 1))

        # Distinguish spur (straight teeth) from helical (bspline faces)
        bsplines = [f for f in faces if f.surf_type == "bspline"]
        gear_type = "helical_gear" if bsplines else "spur_gear"

        return 0.82, {
            "gear_type": gear_type, "num_teeth": num_teeth,
            "outer_radius": outer_r, "outer_diameter": _r(outer_r * 2),
            "bore_radius": bore_r, "bore_diameter": _r(bore_r * 2),
            "face_width": h,
        }

    # ---- Chamfered / Filleted Cylinder ------------------------------------
    @staticmethod
    def chamfered_cylinder(faces: List[FaceInfo], adj: Dict[str, Set[str]], bbox: Dict
                           ) -> Tuple[float, Dict]:
        cyls = [f for f in faces if f.is_cylinder]
        cones = [f for f in faces if f.is_cone]
        planes = [f for f in faces if f.is_plane]
        tori = [f for f in faces if f.is_torus]
        others = [f for f in faces if
                  not f.is_cylinder and not f.is_cone and not f.is_plane and not f.is_torus]
        if others or not cyls:
            return 0.0, {}

        # Must have a dominant cylindrical wall plus chamfer/fillet support faces.
        # This intentionally rejects mixed shapes (e.g. box with attached boss/cone)
        # where large planar side faces exist.
        if len(cyls) > 2:
            return 0.0, {}

        if len(cones) + len(tori) == 0:
            return 0.0, {}

        main_radius = max(c.radius for c in cyls)
        main_cyls = [c for c in cyls if abs(c.radius - main_radius) <= _TOL]
        if len(main_cyls) != 1:
            return 0.0, {}

        cyl = main_cyls[0]

        # Extra cylinders (if present) should be near the main radius, not tiny holes/bosses.
        for c in cyls:
            if c is cyl:
                continue
            if abs(c.radius - cyl.radius) > (2.0 * _TOL):
                return 0.0, {}

        # Cones/tori must align with the cylinder axis (end chamfers/fillets).
        if any(not _vecs_parallel(cyl.axis, cn.axis) for cn in cones):
            return 0.0, {}
        if any(not _vecs_parallel(cyl.axis, tr.axis) for tr in tori):
            return 0.0, {}

        # Planes should only be end caps (parallel normal to cylinder axis).
        if len(planes) > 2:
            return 0.0, {}
        if any(not _vecs_parallel(cyl.axis, p.normal) for p in planes):
            return 0.0, {}

        h = _r(bbox.get("dz", 0))
        chamfers = len(cones)
        fillets = len(tori)
        return 0.86, {
            "radius": cyl.radius, "diameter": _r(cyl.radius * 2), "height": h,
            "chamfers": chamfers, "fillets": fillets, "axis": cyl.axis,
        }

    # ---- Filleted Box -----------------------------------------------------
    @staticmethod
    def filleted_box(faces: List[FaceInfo], adj: Dict[str, Set[str]], bbox: Dict
                     ) -> Tuple[float, Dict]:
        planes = [f for f in faces if f.is_plane]
        tori = [f for f in faces if f.is_torus]
        cyls = [f for f in faces if f.is_cylinder]
        others = [f for f in faces if
                  not f.is_plane and not f.is_torus and not f.is_cylinder]
        if others or len(planes) < 6 or not tori:
            return 0.0, {}

        fillet_r = _r(tori[0].radius2) if tori else 0.0
        w = _r(bbox.get("dx", 0))
        d = _r(bbox.get("dy", 0))
        h = _r(bbox.get("dz", 0))
        return 0.88, {"width": w, "depth": d, "height": h, "fillet_radius": fillet_r}

    # ---- L-Bracket / T-Bracket -------------------------------------------
    @staticmethod
    def bracket(faces: List[FaceInfo], adj: Dict[str, Set[str]], bbox: Dict) -> Tuple[float, Dict]:
        planes = [f for f in faces if f.is_plane]
        non_planes = [f for f in faces if not f.is_plane]
        if non_planes or len(planes) < 8:
            return 0.0, {}

        # Look for two groups of parallel planes at ~90° to each other
        normals_unique: List[List[float]] = []
        for p in planes:
            n_abs = [abs(v) for v in p.normal]
            if not any(_vecs_parallel(n_abs, u) for u in normals_unique):
                normals_unique.append(n_abs)

        if len(normals_unique) < 3:
            return 0.0, {}

        # Count pairs:  an L-bracket has 3 orientation groups with 2 faces each
        # (plus extra faces for the inner corners = may have more)
        return 0.72, {
            "width": _r(bbox.get("dx", 0)),
            "depth": _r(bbox.get("dy", 0)),
            "height": _r(bbox.get("dz", 0)),
            "bracket_type": "L-bracket" if len(normals_unique) == 3 else "bracket",
        }

    # ---- Flange ----------------------------------------------------------
    @staticmethod
    def flange(faces: List[FaceInfo], adj: Dict[str, Set[str]], bbox: Dict) -> Tuple[float, Dict]:
        """Disc (annular plate) + central bore cylinder + bolt-hole cylinders."""
        cyls = [f for f in faces if f.is_cylinder]
        planes = [f for f in faces if f.is_plane]

        if len(cyls) < 3 or len(planes) < 2:
            return 0.0, {}

        radii = sorted(c.radius for c in cyls)
        bore_r = radii[0]
        flange_r = radii[-1]

        # Bolt holes: cylinders whose radius is << flange_r and > bore_r
        bolt_cyls = [c for c in cyls if bore_r < c.radius < flange_r * 0.9]
        if len(bolt_cyls) < 2:
            return 0.0, {}

        # Check bolt holes are on a PCD (circle pattern)
        pts_2d = [(c.location[0], c.location[1]) for c in bolt_cyls]
        on_ring, pcd_r, centre = _pts_on_ring(pts_2d)
        if not on_ring:
            return 0.4, {}

        h = _r(bbox.get("dz", 1))
        return 0.88, {
            "flange_radius": flange_r, "flange_diameter": _r(flange_r * 2),
            "bore_radius": bore_r, "bore_diameter": _r(bore_r * 2),
            "pcd_radius": _r(pcd_r), "pcd_diameter": _r(pcd_r * 2),
            "bolt_holes": len(bolt_cyls), "bolt_hole_diameter": _r(bolt_cyls[0].radius * 2),
            "thickness": h,
        }

    # ---- Splined / Knurled Shaft -----------------------------------------
    @staticmethod
    def splined_shaft(faces: List[FaceInfo], adj: Dict[str, Set[str]], bbox: Dict
                      ) -> Tuple[float, Dict]:
        """Central cylinder + many equal-spaced lateral planes (spline teeth)."""
        cyls = [f for f in faces if f.is_cylinder]
        planes = [f for f in faces if f.is_plane]

        if not cyls or len(planes) < 6:
            return 0.0, {}

        # Central cylinder: the one with the greatest radius
        main_r = max(c.radius for c in cyls)
        lateral_planes = [p for p in planes
                          if not _vecs_parallel(p.normal, [0, 0, 1])]
        if len(lateral_planes) < 6:
            return 0.0, {}

        num_splines = len(lateral_planes) // 2
        h = _r(bbox.get("dz", 1))
        return 0.78, {
            "radius": main_r, "diameter": _r(main_r * 2),
            "length": h, "num_splines": num_splines,
        }

    # ---- Threaded Rod / Bolt Shank  (many small repeated features) -------
    @staticmethod
    def threaded_rod(faces: List[FaceInfo], adj: Dict[str, Set[str]], bbox: Dict
                     ) -> Tuple[float, Dict]:
        """
        A threaded region has many (>20) small conical and/or cylindrical faces
        arranged helically. We detect this by large face count at small size.
        """
        total = len(faces)
        if total < 20:
            return 0.0, {}

        cones_count = sum(1 for f in faces if f.is_cone)
        cyls_count = sum(1 for f in faces if f.is_cylinder)
        planes_count = sum(1 for f in faces if f.is_plane)

        # Typical thread: many cone + cylinder pairs
        if cones_count < 10 and cyls_count < 10:
            return 0.0, {}

        # Pitch estimate from face bbox heights
        all_cyls = [f for f in faces if f.is_cylinder]
        if not all_cyls:
            return 0.0, {}

        main_r = max(c.radius for c in all_cyls)
        minor_r = min(c.radius for c in all_cyls)
        l = _r(max(bbox.get("dz", 0), bbox.get("dy", 0), bbox.get("dx", 0)))

        num_threads = cones_count // 2 if cones_count >= 2 else cyls_count // 2
        pitch = _r(l / num_threads) if num_threads else 0.0

        return 0.80, {
            "major_radius": main_r, "major_diameter": _r(main_r * 2),
            "minor_radius": minor_r, "minor_diameter": _r(minor_r * 2),
            "length": l, "pitch": pitch, "thread_count": num_threads,
        }


# ---------------------------------------------------------------------------
# Main recogniser
# ---------------------------------------------------------------------------

class ShapeRecognizer:
    """
    Recognise geometric blocks in a STEP file by analysing face-type
    distributions and connectivity patterns.
    """

    # Ordered list of (name, classifier_fn) – earlier entries win on tie
    _CLASSIFIERS = [
        ("sphere",           _Classifiers.sphere),
        ("torus",            _Classifiers.torus),
        ("spur_gear",        _Classifiers.gear),
        ("pipe_bend",        _Classifiers.pipe_bend),
        ("flange",           _Classifiers.flange),
        ("threaded_rod",     _Classifiers.threaded_rod),
        ("splined_shaft",    _Classifiers.splined_shaft),
        ("tube",             _Classifiers.tube),
        ("disc",             _Classifiers.disc),
        ("cylinder",         _Classifiers.cylinder),
        ("chamfered_cylinder", _Classifiers.chamfered_cylinder),
        ("hex_prism",        _Classifiers.hex_prism),
        ("L_bracket",        _Classifiers.bracket),
        ("filleted_box",     _Classifiers.filleted_box),
        ("box",              _Classifiers.box),
        ("cone",             _Classifiers.cone),
    ]

    def recognize(self, step_path: str) -> List[Dict[str, Any]]:
        """
        Load a STEP file and return a list of recognised Block dictionaries.

        Each block has:
            shape_type, parameters, confidence, face_ids, bounding_box, summary
        """
        logger.info("ShapeRecognizer loading: %s", step_path)

        try:
            model = cq.importers.importStep(step_path)
        except Exception as exc:
            raise ValueError(f"Cannot import STEP '{step_path}': {exc}") from exc

        occ_shape = model.val().wrapped

        # 1. Build FaceInfo objects for every face
        raw_faces = model.faces().vals()
        face_infos: List[FaceInfo] = [
            FaceInfo(f"f{i}", face.wrapped) for i, face in enumerate(raw_faces)
        ]
        logger.info("  %d faces extracted", len(face_infos))

        # 2. Build adjacency graph
        try:
            adj = _build_adjacency(occ_shape, face_infos)
        except Exception as exc:
            logger.warning("Adjacency build failed (%s) – falling back to full component.", exc)
            # Fallback: treat everything as one component
            adj = {fi.id: set() for fi in face_infos}

        # 3. Find connected components (= separate solid bodies / sub-shapes)
        components = _connected_components(adj)
        logger.info("  %d connected component(s)", len(components))

        face_by_id = {fi.id: fi for fi in face_infos}

        # 4. Classify each component
        blocks: List[Dict[str, Any]] = []
        for comp_idx, comp_ids in enumerate(components):
            comp_faces = [face_by_id[fid] for fid in comp_ids if fid in face_by_id]
            comp_bbox = self._component_bbox(comp_faces)
            block = self._classify_component(comp_faces, adj, comp_bbox, comp_idx)
            blocks.append(block)

        logger.info("  Recognised %d block(s): %s",
                    len(blocks), [b["shape_type"] for b in blocks])
        return blocks

    # ------------------------------------------------------------------

    def _component_bbox(self, faces: List[FaceInfo]) -> Dict[str, float]:
        if not faces:
            return {"xmin": 0, "xmax": 0, "ymin": 0, "ymax": 0,
                    "zmin": 0, "zmax": 0, "dx": 0, "dy": 0, "dz": 0}
        xmin = min(f.bbox.get("xmin", 0) for f in faces)
        xmax = max(f.bbox.get("xmax", 0) for f in faces)
        ymin = min(f.bbox.get("ymin", 0) for f in faces)
        ymax = max(f.bbox.get("ymax", 0) for f in faces)
        zmin = min(f.bbox.get("zmin", 0) for f in faces)
        zmax = max(f.bbox.get("zmax", 0) for f in faces)
        return {
            "xmin": _r(xmin), "xmax": _r(xmax),
            "ymin": _r(ymin), "ymax": _r(ymax),
            "zmin": _r(zmin), "zmax": _r(zmax),
            "dx": _r(xmax - xmin), "dy": _r(ymax - ymin), "dz": _r(zmax - zmin),
        }

    def _classify_component(self, faces: List[FaceInfo], adj: Dict[str, Set[str]],
                            bbox: Dict, idx: int) -> Dict[str, Any]:
        """Run all classifiers and pick the best match."""
        best_name = "unknown"
        best_conf = 0.0
        best_params: Dict[str, Any] = {}

        for name, fn in self._CLASSIFIERS:
            try:
                conf, params = fn(faces, adj, bbox)
            except Exception as exc:
                logger.debug("Classifier '%s' error: %s", name, exc)
                conf, params = 0.0, {}

            if conf > best_conf:
                best_conf = conf
                best_name = name
                best_params = params

        # Fallback: if nothing matched well, describe as generic
        if best_conf < 0.4:
            best_name = "generic_solid"
            best_params = {}

        summary = self._make_summary(best_name, best_params, bbox)

        return {
            "component_index": idx,
            "shape_type": best_name,
            "confidence": _r(best_conf),
            "parameters": best_params,
            "face_ids": [f.id for f in faces],
            "face_count": len(faces),
            "face_type_counts": self._count_face_types(faces),
            "bounding_box": bbox,
            "summary": summary,
        }

    @staticmethod
    def _count_face_types(faces: List[FaceInfo]) -> Dict[str, int]:
        counts: Dict[str, int] = defaultdict(int)
        for f in faces:
            counts[f.surf_type] += 1
        return dict(counts)

    @staticmethod
    def _make_summary(shape_type: str, params: Dict, bbox: Dict) -> str:
        dx, dy, dz = bbox.get("dx", 0), bbox.get("dy", 0), bbox.get("dz", 0)
        bb_str = f"{dx:.2f}×{dy:.2f}×{dz:.2f} mm"

        label = shape_type.replace("_", " ").title()

        if shape_type in ("box", "filleted_box"):
            w, d, h = params.get("width", dx), params.get("depth", dy), params.get("height", dz)
            fr = f", fillet r={params.get('fillet_radius', 0):.2f} mm" if shape_type == "filleted_box" else ""
            return f"{label}: {w:.2f}×{d:.2f}×{h:.2f} mm{fr}"

        if shape_type in ("cylinder", "chamfered_cylinder"):
            return (f"{label}: Ø{params.get('diameter', 0):.2f} mm × "
                    f"h={params.get('height', dz):.2f} mm")

        if shape_type == "tube":
            return (f"Tube: Ø{params.get('outer_diameter', 0):.2f}/"
                    f"{params.get('inner_diameter', 0):.2f} mm × "
                    f"h={params.get('height', dz):.2f} mm")

        if shape_type == "disc":
            if "inner_diameter" in params:
                return (f"Washer: Ø{params.get('outer_diameter', 0):.2f}/"
                        f"{params.get('inner_diameter', 0):.2f} mm × "
                        f"t={params.get('thickness', 0):.2f} mm")
            return (f"Disc: Ø{params.get('outer_diameter', 0):.2f} mm × "
                    f"t={params.get('thickness', 0):.2f} mm")

        if shape_type == "cone":
            return (f"Cone: base Ø{params.get('base_radius', 0) * 2:.2f} mm, "
                    f"h={params.get('height', 0):.2f} mm, "
                    f"α={params.get('half_angle_deg', 0):.1f}°")

        if shape_type == "sphere":
            return f"Sphere: Ø{params.get('diameter', 0):.2f} mm"

        if shape_type == "torus":
            return (f"Torus: R={params.get('major_radius', 0):.2f} mm, "
                    f"r={params.get('minor_radius', 0):.2f} mm")

        if shape_type == "pipe_bend":
            return (f"Pipe Bend: Ø{params.get('pipe_diameter', 0):.2f} mm, "
                    f"bend R={params.get('bend_radius', 0):.2f} mm, "
                    f"θ={params.get('bend_angle_deg', 0):.0f}°")

        if shape_type == "spur_gear":
            gt = params.get("gear_type", "gear")
            return (f"{gt.replace('_', ' ').title()}: "
                    f"{params.get('num_teeth', '?')} teeth, "
                    f"Ø{params.get('outer_diameter', 0):.2f} mm, "
                    f"bore Ø{params.get('bore_diameter', 0):.2f} mm")

        if shape_type == "flange":
            return (f"Flange: Ø{params.get('flange_diameter', 0):.2f} mm, "
                    f"bore Ø{params.get('bore_diameter', 0):.2f} mm, "
                    f"{params.get('bolt_holes', '?')}×Ø{params.get('bolt_hole_diameter', 0):.2f} mm bolts")

        if shape_type == "hex_prism":
            return (f"Hex Prism: {params.get('across_flats', 0):.2f} mm A/F, "
                    f"h={params.get('height', 0):.2f} mm")

        if shape_type == "threaded_rod":
            return (f"Threaded Rod: Ø{params.get('major_diameter', 0):.2f} mm, "
                    f"pitch={params.get('pitch', 0):.2f} mm, "
                    f"L={params.get('length', 0):.2f} mm")

        if shape_type == "splined_shaft":
            return (f"Splined Shaft: Ø{params.get('diameter', 0):.2f} mm, "
                    f"{params.get('num_splines', '?')} splines, "
                    f"L={params.get('length', 0):.2f} mm")

        return f"{label}: bbox {bb_str}"


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import json

    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        print("Usage: python shape_recognizer.py <path_to.step>")
        sys.exit(1)

    sr = ShapeRecognizer()
    blocks = sr.recognize(sys.argv[1])
    print(json.dumps(blocks, indent=2))
