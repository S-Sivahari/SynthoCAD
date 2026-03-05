"""Geometric Interpreter - Converts OCP features to CAD design intent.

This module bridges the gap between low-level geometric analysis (cylinders, planes)
and high-level CAD operations (boxes, holes, extrusions). It infers design intent
from geometric primitives, making it much easier for LLMs to generate valid SCL JSON.

Flow: OCP Features (+ ShapeRecognizer blocks) → GeometricInterpreter → Intermediate Design → LLM → SCL JSON

When `ocp_features["blocks"]` is present (populated by ShapeRecognizer), the
interpreter uses the richer topology-aware classification for the primary geometry
and falls back to the legacy plane/cylinder analysis only when needed.
"""

import logging
from typing import Dict, Any, List, Tuple, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Block-type → SCL operation mapping
# ---------------------------------------------------------------------------
_BLOCK_OP_MAP: Dict[str, str] = {
    "box":                 "extrude_rectangle",
    "filleted_box":        "extrude_rectangle",
    "cylinder":            "extrude_circle",
    "chamfered_cylinder":  "extrude_circle",
    "cone":                "extrude_profile",
    "sphere":              "revolve_arc",
    "torus":               "revolve_circle",
    "tube":                "extrude_annulus",
    "disc":                "extrude_annulus",
    "pipe_bend":           "sweep_circle",
    "spur_gear":           "extrude_gear_profile",
    "hex_prism":           "extrude_polygon",
    "flange":              "extrude_annulus",
    "threaded_rod":        "extrude_circle",
    "splined_shaft":       "extrude_spline_profile",
    "L_bracket":           "extrude_L_profile",
    "generic_solid":       "extrude_rectangle",
}


class GeometricInterpreter:
    """Interprets raw OCP geometric features into parametric design intent."""
    
    def __init__(self):
        self.tolerance = 0.1  # mm tolerance for geometric comparisons
    
    def interpret(self, ocp_features: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert OCP features into intermediate design representation.

        When ``ocp_features["blocks"]`` is present (populated by ShapeRecognizer),
        the topology-aware block data is used to produce a richer intermediate.
        Falls back to legacy plane/cylinder analysis otherwise.

        Args:
            ocp_features: Output from step_analyzer.analyze()

        Returns:
            Intermediate design dictionary with inferred intent
        """
        logger.info("Interpreting geometric features into design intent...")

        # --- Prefer block-level data from ShapeRecognizer when available ---
        blocks = ocp_features.get("blocks", [])
        if blocks:
            return self.interpret_blocks(ocp_features)

        # --- Legacy path ---------------------------------------------------
        cylinders = ocp_features.get('cylinders', [])
        planes = ocp_features.get('planes', [])
        bbox = ocp_features.get('bounding_box', {})

        plane_groups = self._classify_planes(planes)
        base_geometry = self._detect_base_geometry(plane_groups, bbox)
        features = self._detect_features(cylinders, planes, base_geometry)
        design_type = self._infer_design_type(base_geometry, features)

        intermediate = {
            "design_type": design_type,
            "units": "mm",
            "base_geometry": base_geometry,
            "features": features,
            "metadata": {
                "face_count": ocp_features.get('face_count', 0),
                "bounding_box": bbox,
                "interpretation_confidence": self._calculate_confidence(base_geometry, features),
                "source": "legacy_plane_cylinder_analysis",
            }
        }

        logger.info(f"Interpreted (legacy) as: {design_type} with {len(features)} features")
        return intermediate

    # ------------------------------------------------------------------
    def interpret_blocks(self, ocp_features: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build an intermediate design from ShapeRecognizer block data.

        Each recognised block becomes either the primary ``base_geometry`` or
        an entry in ``features`` depending on its role.

        Args:
            ocp_features: Output from step_analyzer.analyze(), must contain
                          the ``"blocks"`` key.

        Returns:
            Intermediate design dictionary compatible with the SCL prompt.
        """
        blocks: List[Dict] = ocp_features.get("blocks", [])
        bbox = ocp_features.get("bounding_box", {})
        overall_bb = {
            "dx": bbox.get("x_mm", 0),
            "dy": bbox.get("y_mm", 0),
            "dz": bbox.get("z_mm", 0),
        }

        if not blocks:
            return self.interpret(ocp_features)

        # Sort by face count descending – largest block is the primary body
        sorted_blocks = sorted(blocks, key=lambda b: b.get("face_count", 0), reverse=True)
        primary = sorted_blocks[0]
        secondary = sorted_blocks[1:]

        base_geometry = self._block_to_base_geometry(primary, overall_bb)
        features = [self._block_to_feature(b, base_geometry) for b in secondary]

        # Also harvest cylindrical holes from the legacy analysis that the
        # block recogniser may not have split out explicitly
        legacy_features = self._detect_features(
            ocp_features.get("cylinders", []),
            ocp_features.get("planes", []),
            base_geometry,
        )
        # De-dup: only add legacy features whose type isn't already covered
        covered_types = {f.get("type") for f in features}
        for lf in legacy_features:
            if lf.get("type") not in covered_types:
                features.append(lf)

        design_type = self._infer_design_type_from_block(primary, features)

        intermediate = {
            "design_type": design_type,
            "units": "mm",
            "base_geometry": base_geometry,
            "features": features,
            "blocks": blocks,              # raw recogniser output preserved
            "metadata": {
                "face_count": ocp_features.get("face_count", 0),
                "bounding_box": bbox,
                "interpretation_confidence": primary.get("confidence", 0.5),
                "source": "shape_recognizer",
                "primary_block_type": primary.get("shape_type", "unknown"),
            }
        }

        logger.info(
            "Interpreted (block-aware) as: %s with %d feature(s) "
            "(primary block confidence=%.2f)",
            design_type, len(features), primary.get("confidence", 0.0)
        )
        return intermediate

    # ------------------------------------------------------------------
    def _block_to_base_geometry(self, block: Dict, overall_bb: Dict) -> Dict[str, Any]:
        """Convert a ShapeRecognizer block into a base_geometry dict."""
        shape = block.get("shape_type", "generic_solid")
        params = block.get("parameters", {})
        bb = block.get("bounding_box", {})
        op = _BLOCK_OP_MAP.get(shape, "extrude_rectangle")

        dx = bb.get("dx", overall_bb.get("dx", 10))
        dy = bb.get("dy", overall_bb.get("dy", 10))
        dz = bb.get("dz", overall_bb.get("dz", 10))
        cx = bb.get("xmin", 0) + dx / 2
        cy = bb.get("ymin", 0) + dy / 2
        cz = bb.get("zmin", 0) + dz / 2

        # ---- box / filleted_box ----
        if shape in ("box", "filleted_box", "L_bracket", "generic_solid"):
            geo = {
                "type": shape,
                "operation": op,
                "dimensions": {
                    "width": params.get("width", dx),
                    "depth": params.get("depth", dy),
                    "height": params.get("height", dz),
                },
                "center": [cx, cy, cz],
                "orientation": "standard",
            }
            if shape == "filleted_box":
                geo["fillet_radius"] = params.get("fillet_radius", 0)
            return geo

        # ---- cylinder / chamfered_cylinder ----
        if shape in ("cylinder", "chamfered_cylinder"):
            return {
                "type": shape,
                "operation": op,
                "dimensions": {
                    "radius": params.get("radius", dx / 2),
                    "diameter": params.get("diameter", dx),
                    "height": params.get("height", dz),
                },
                "axis": params.get("axis", [0, 0, 1]),
                "center": [cx, cy, cz],
            }

        # ---- tube ----
        if shape == "tube":
            return {
                "type": "tube",
                "operation": op,
                "dimensions": {
                    "outer_radius": params.get("outer_radius", dx / 2),
                    "inner_radius": params.get("inner_radius", 0),
                    "outer_diameter": params.get("outer_diameter", dx),
                    "inner_diameter": params.get("inner_diameter", 0),
                    "wall_thickness": params.get("wall_thickness", 0),
                    "height": params.get("height", dz),
                },
                "axis": params.get("axis", [0, 0, 1]),
                "center": [cx, cy, cz],
            }

        # ---- disc / washer ----
        if shape == "disc":
            return {
                "type": "disc",
                "operation": op,
                "dimensions": {
                    "outer_radius": params.get("outer_radius", dx / 2),
                    "inner_radius": params.get("inner_radius", 0),
                    "thickness": params.get("thickness", dz),
                },
                "center": [cx, cy, cz],
            }

        # ---- cone ----
        if shape == "cone":
            return {
                "type": "cone",
                "operation": op,
                "dimensions": {
                    "base_radius": params.get("base_radius", dx / 2),
                    "tip_radius": params.get("tip_radius", 0),
                    "height": params.get("height", dz),
                    "half_angle_deg": params.get("half_angle_deg", 0),
                },
                "axis": params.get("axis", [0, 0, 1]),
                "center": [cx, cy, cz],
            }

        # ---- sphere ----
        if shape == "sphere":
            return {
                "type": "sphere",
                "operation": op,
                "dimensions": {
                    "radius": params.get("radius", dx / 2),
                    "diameter": params.get("diameter", dx),
                },
                "center": [cx, cy, cz],
            }

        # ---- torus ----
        if shape == "torus":
            return {
                "type": "torus",
                "operation": op,
                "dimensions": {
                    "major_radius": params.get("major_radius", dx / 2),
                    "minor_radius": params.get("minor_radius", 1),
                },
                "axis": params.get("axis", [0, 0, 1]),
                "center": [cx, cy, cz],
            }

        # ---- pipe_bend ----
        if shape == "pipe_bend":
            return {
                "type": "pipe_bend",
                "operation": op,
                "dimensions": {
                    "pipe_radius": params.get("pipe_radius", 5),
                    "pipe_diameter": params.get("pipe_diameter", 10),
                    "bend_radius": params.get("bend_radius", dx / 2),
                    "bend_angle_deg": params.get("bend_angle_deg", 90),
                },
                "center": [cx, cy, cz],
            }

        # ---- spur_gear / helical_gear ----
        if shape == "spur_gear":
            return {
                "type": params.get("gear_type", "spur_gear"),
                "operation": op,
                "dimensions": {
                    "outer_radius": params.get("outer_radius", dx / 2),
                    "bore_radius": params.get("bore_radius", 0),
                    "face_width": params.get("face_width", dz),
                    "num_teeth": params.get("num_teeth", 0),
                },
                "center": [cx, cy, cz],
            }

        # ---- hex_prism ----
        if shape == "hex_prism":
            return {
                "type": "hex_prism",
                "operation": op,
                "dimensions": {
                    "across_flats": params.get("across_flats", dx),
                    "height": params.get("height", dz),
                    "sides": params.get("sides", 6),
                },
                "center": [cx, cy, cz],
            }

        # ---- flange ----
        if shape == "flange":
            return {
                "type": "flange",
                "operation": op,
                "dimensions": {
                    "flange_radius": params.get("flange_radius", dx / 2),
                    "bore_radius": params.get("bore_radius", 0),
                    "thickness": params.get("thickness", dz),
                    "pcd_radius": params.get("pcd_radius", 0),
                    "bolt_holes": params.get("bolt_holes", 0),
                    "bolt_hole_diameter": params.get("bolt_hole_diameter", 0),
                },
                "center": [cx, cy, cz],
            }

        # ---- threaded_rod ----
        if shape == "threaded_rod":
            return {
                "type": "threaded_rod",
                "operation": op,
                "dimensions": {
                    "major_diameter": params.get("major_diameter", dx),
                    "minor_diameter": params.get("minor_diameter", dx * 0.8),
                    "length": params.get("length", dz),
                    "pitch": params.get("pitch", 0),
                    "thread_count": params.get("thread_count", 0),
                },
                "center": [cx, cy, cz],
            }

        # ---- splined_shaft ----
        if shape == "splined_shaft":
            return {
                "type": "splined_shaft",
                "operation": op,
                "dimensions": {
                    "diameter": params.get("diameter", dx),
                    "length": params.get("length", dz),
                    "num_splines": params.get("num_splines", 0),
                },
                "center": [cx, cy, cz],
            }

        # Fallback
        return {
            "type": "generic_solid",
            "operation": "extrude_rectangle",
            "dimensions": {"width": dx, "depth": dy, "height": dz},
            "center": [cx, cy, cz],
            "orientation": "standard",
        }

    def _block_to_feature(self, block: Dict, base_geometry: Dict) -> Dict[str, Any]:
        """Convert a secondary ShapeRecognizer block into a feature dict."""
        shape = block.get("shape_type", "unknown")
        params = block.get("parameters", {})
        bb = block.get("bounding_box", {})
        dx = bb.get("dx", 0)
        dz = bb.get("dz", 0)
        cx = bb.get("xmin", 0) + dx / 2
        cy = bb.get("ymin", 0) + bb.get("dy", 0) / 2
        cz = bb.get("zmin", 0) + dz / 2

        feat = {
            "type": shape,
            "block_index": block.get("component_index", -1),
            "confidence": block.get("confidence", 0.5),
            "operation": "CutFeatureOperation",
            "parameters": {**params, "location": [cx, cy, cz]},
            "summary": block.get("summary", ""),
        }

        # Cylinders inside a primary body are almost always holes
        if shape in ("cylinder", "tube", "disc"):
            feat["operation"] = "CutFeatureOperation"
            feat["classification"] = "hole"
        else:
            feat["operation"] = "JoinFeatureOperation"
            feat["classification"] = "added_feature"

        return feat

    @staticmethod
    def _infer_design_type_from_block(primary: Dict, features: List[Dict]) -> str:
        """Infer a human-readable design type from the primary block + features."""
        shape = primary.get("shape_type", "generic_solid")
        n = len(features)

        design_map = {
            "box":             "solid_block" if n == 0 else "block_with_features",
            "filleted_box":    "filleted_block",
            "cylinder":        "solid_cylinder" if n == 0 else "cylinder_with_features",
            "chamfered_cylinder": "chamfered_cylinder",
            "tube":            "tube" if n == 0 else "tube_with_features",
            "disc":            "disc_or_washer",
            "cone":            "cone",
            "sphere":          "sphere",
            "torus":           "torus",
            "pipe_bend":       "pipe_bend",
            "spur_gear":       "spur_gear",
            "hex_prism":       "hex_prism",
            "flange":          "flange",
            "threaded_rod":    "threaded_rod",
            "splined_shaft":   "splined_shaft",
            "L_bracket":       "L_bracket",
            "generic_solid":   "generic_part",
        }
        return design_map.get(shape, "generic_part")
    
    def _classify_planes(self, planes: List[Dict]) -> Dict[str, List[Dict]]:
        """Group planes by orientation (horizontal, vertical_x, vertical_y)."""
        groups = {
            'horizontal': [],
            'vertical_x': [],
            'vertical_y': [],
            'other': []
        }
        
        for plane in planes:
            face_type = plane.get('face_type', 'other')
            groups.get(face_type, groups['other']).append(plane)
        
        return groups
    
    def _detect_base_geometry(self, plane_groups: Dict, bbox: Dict) -> Dict[str, Any]:
        """
        Detect the main body geometry from planar faces.
        
        Returns a structured representation of the base geometry
        (box, cylinder, plate, etc.)
        """
        horizontal = plane_groups.get('horizontal', [])
        vertical_x = plane_groups.get('vertical_x', [])
        vertical_y = plane_groups.get('vertical_y', [])
        
        # Check if it's a rectangular box (6 faces: top, bottom, 4 sides)
        if len(horizontal) >= 2 and len(vertical_x) >= 2 and len(vertical_y) >= 2:
            # It's likely a box
            width = bbox.get('x_mm', 0)
            depth = bbox.get('y_mm', 0)
            height = bbox.get('z_mm', 0)
            
            # Find the bottom plane (lowest Z)
            bottom_plane = min(horizontal, key=lambda p: p['location'][2], default=None)
            center_x = bbox.get('x_mm', 0) / 2 if bbox else 0
            center_y = bbox.get('y_mm', 0) / 2 if bbox else 0
            center_z = bottom_plane['location'][2] + height / 2 if bottom_plane else height / 2
            
            return {
                "type": "rectangular_box",
                "operation": "extrude_rectangle",
                "dimensions": {
                    "width": width,
                    "depth": depth,
                    "height": height
                },
                "center": [center_x, center_y, center_z],
                "orientation": "standard"  # aligned with axes
            }
        
        # Check if it's a flat plate (large horizontal faces, thin height)
        elif len(horizontal) >= 2:
            width = bbox.get('x_mm', 0)
            depth = bbox.get('y_mm', 0)
            height = bbox.get('z_mm', 0)
            
            if height < min(width, depth) / 5:  # Thickness < 20% of smallest dimension
                bottom_plane = min(horizontal, key=lambda p: p['location'][2], default=None)
                center_z = bottom_plane['location'][2] + height / 2 if bottom_plane else height / 2
                
                return {
                    "type": "rectangular_plate",
                    "operation": "extrude_rectangle",
                    "dimensions": {
                        "width": width,
                        "depth": depth,
                        "thickness": height
                    },
                    "center": [width/2, depth/2, center_z],
                    "orientation": "standard"
                }
        
        # Fallback: generic box based on bounding box
        return {
            "type": "generic_solid",
            "operation": "extrude_rectangle",
            "dimensions": {
                "width": bbox.get('x_mm', 10),
                "depth": bbox.get('y_mm', 10),
                "height": bbox.get('z_mm', 10)
            },
            "center": [bbox.get('x_mm', 10)/2, bbox.get('y_mm', 10)/2, bbox.get('z_mm', 10)/2],
            "orientation": "standard"
        }
    
    def _detect_features(self, cylinders: List[Dict], planes: List[Dict], 
                        base_geometry: Dict) -> List[Dict]:
        """
        Detect features (holes, pockets, bosses) from cylindrical faces.
        
        Features are modifications to the base geometry.
        """
        features = []
        
        # Group cylinders by radius to detect patterns
        radius_groups = defaultdict(list)
        for cyl in cylinders:
            radius = round(cyl.get('radius_mm', 0), 2)
            radius_groups[radius].append(cyl)
        
        # Detect patterns of identical holes
        for radius, cyls in radius_groups.items():
            if len(cyls) > 1:
                # Check if they form a pattern (linear or circular)
                pattern_type = self._detect_pattern_type(cyls)
                
                if pattern_type != 'none':
                    # Add as a single patterned feature
                    base_cyl = cyls[0]
                    axis = base_cyl.get('axis', [0, 0, 1])
                    
                    feature = {
                        "type": "patterned_holes",
                        "operation": "cut_cylinder",
                        "pattern_type": pattern_type,
                        "count": len(cyls),
                        "parameters": {
                            "diameter": radius * 2,
                            "radius": radius,
                            "depth": base_geometry.get('dimensions', {}).get('height', 10),
                            "locations": [c.get('location', [0, 0, 0]) for c in cyls],
                            "axis": axis
                        },
                        "classification": "patterned_through_holes"
                    }
                    features.append(feature)
                    continue
        
        # Add individual cylinders not in patterns
        for cyl in cylinders:
            # Check if already added as part of a pattern
            already_added = False
            for feat in features:
                if feat.get('type') == 'patterned_holes':
                    locs = feat['parameters']['locations']
                    if cyl.get('location') in locs:
                        already_added = True
                        break
            
            if already_added:
                continue
            
            # Add as individual feature
            axis = cyl.get('axis', [0, 0, 1])
            radius = cyl.get('radius_mm', 0)
            location = cyl.get('location', [0, 0, 0])
            
            # Check if cylinder is vertical (aligned with Z axis)
            is_vertical = abs(axis[2]) > 0.9
            
            if is_vertical:
                # Likely a vertical hole or boss
                base_height = base_geometry.get('dimensions', {}).get('height', 10)
                
                feature = {
                    "type": "cylindrical_hole",
                    "operation": "cut_cylinder",
                    "id": cyl.get('id', 'unknown'),
                    "parameters": {
                        "diameter": radius * 2,
                        "radius": radius,
                        "depth": base_height,
                        "location": location,
                        "axis": axis
                    },
                    "classification": "through_hole"
                }
            else:
                # Horizontal or angled hole
                feature = {
                    "type": "cylindrical_hole",
                    "operation": "cut_cylinder",
                    "id": cyl.get('id', 'unknown'),
                    "parameters": {
                        "diameter": radius * 2,
                        "radius": radius,
                        "depth": base_geometry.get('dimensions', {}).get('width', 10),
                        "location": location,
                        "axis": axis
                    },
                    "classification": "side_hole"
                }
            
            features.append(feature)
        
        return features
    
    def _detect_pattern_type(self, cylinders: List[Dict]) -> str:
        """
        Detect if cylinders form a linear or circular pattern.
        
        Returns: 'linear', 'circular', or 'none'
        """
        if len(cylinders) < 2:
            return 'none'
        
        # Get locations, ignoring Z (assuming all at same height)
        locs_2d = [(c['location'][0], c['location'][1]) for c in cylinders]
        
        # Check for linear pattern (collinear points)
        if len(locs_2d) >= 2:
            # Calculate pairwise distances
            distances = []
            for i in range(len(locs_2d) - 1):
                dx = locs_2d[i+1][0] - locs_2d[i][0]
                dy = locs_2d[i+1][1] - locs_2d[i][1]
                dist = (dx**2 + dy**2) ** 0.5
                distances.append(dist)
            
            # Check if distances are consistent (linear equally-spaced)
            if distances and max(distances) - min(distances) < self.tolerance:
                return 'linear'
        
        # Check for circular pattern (equidistant from center)
        if len(locs_2d) >= 3:
            # Find average center point
            avg_x = sum(x for x, y in locs_2d) / len(locs_2d)
            avg_y = sum(y for x, y in locs_2d) / len(locs_2d)
            
            # Calculate radii from center
            radii = [((x - avg_x)**2 + (y - avg_y)**2)**0.5 for x, y in locs_2d]
            
            # Check if all radii are similar (circular pattern)
            if radii and max(radii) - min(radii) < self.tolerance * 2:
                return 'circular'
        
        return 'none'
    
    def _infer_design_type(self, base_geometry: Dict, features: List[Dict]) -> str:
        """Infer the overall design type from base geometry and features."""
        base_type = base_geometry.get('type', 'unknown')
        feature_count = len(features)
        
        if base_type == 'rectangular_plate':
            if feature_count == 0:
                return "simple_plate"
            elif feature_count <= 4:
                return "plate_with_holes"
            else:
                return "mounting_plate"
        
        elif base_type == 'rectangular_box':
            if feature_count == 0:
                return "solid_block"
            elif feature_count <= 2:
                return "block_with_holes"
            else:
                return "mounting_block"
        
        return "generic_part"
    
    def _calculate_confidence(self, base_geometry: Dict, features: List[Dict]) -> float:
        """Calculate confidence in the interpretation (0.0 to 1.0)."""
        confidence = 0.5  # Base confidence
        
        # Increase confidence if base geometry is well-defined
        if base_geometry.get('type') in ['rectangular_box', 'rectangular_plate']:
            confidence += 0.2
        
        # Increase confidence for recognized feature patterns
        if all(f.get('classification') in ['through_hole', 'side_hole'] for f in features):
            confidence += 0.2
        
        # Decrease confidence for ambiguous geometries
        if base_geometry.get('type') == 'generic_solid':
            confidence -= 0.1
        
        return min(1.0, max(0.0, confidence))
    
    def to_description(self, intermediate: Dict) -> str:
        """
        Generate human-readable description of the interpreted design.
        Useful for LLM context.
        """
        design_type = intermediate.get('design_type', 'unknown part')
        base = intermediate.get('base_geometry', {})
        features = intermediate.get('features', [])
        
        dims = base.get('dimensions', {})
        dim_str = f"{dims.get('width', 0):.1f}×{dims.get('depth', 0):.1f}×{dims.get('height', dims.get('thickness', 0)):.1f}mm"
        
        lines = [
            f"Design Type: {design_type.replace('_', ' ').title()}",
            f"Base Geometry: {base.get('type', 'unknown').replace('_', ' ').title()}",
            f"Dimensions: {dim_str}",
        ]
        
        if features:
            lines.append(f"\nFeatures ({len(features)}):")
            for i, feat in enumerate(features, 1):
                params = feat.get('parameters', {})
                feat_type = feat.get('type', 'unknown').replace('_', ' ')
                diameter = params.get('diameter', 0)
                loc = params.get('location', [0, 0, 0])
                lines.append(f"  {i}. {feat_type}: Ø{diameter:.1f}mm at [{loc[0]:.1f}, {loc[1]:.1f}, {loc[2]:.1f}]")
        
        return "\n".join(lines)


def create_intermediate_prompt() -> str:
    """
    Create the system prompt for converting intermediate design to SCL JSON.
    This is much simpler than converting raw OCP features.
    """
    return """You are a CAD translation expert converting intermediate design representations into valid SCL (SynthoCAD Language) JSON.

CRITICAL OUTPUT RULES:
1. Output ONLY valid raw JSON — no markdown, no explanation, no comments
2. Always include "units": "mm" field
3. First part (part_1) MUST use "NewBodyFeatureOperation"
4. Parts numbered sequentially: part_1, part_2, part_3...
5. Sketch coordinates are normalized (0.0-1.0), then sketch_scale converts to real mm
6. Output ONLY raw JSON starting with { and ending with }

TRANSLATION GUIDELINES:

1. BASE GEOMETRY TRANSLATION:
   - rectangular_box/rectangular_plate → sketch with rectangle + extrusion
   - Use center point to position the sketch
   - sketch_scale should match the largest dimension
   - Rectangle should be centered at (0.5, 0.5) in normalized coords

2. FEATURE TRANSLATION:
   - cylindrical_hole → part with hole_feature or sketch circle + cut extrusion
   - Use actual diameter/radius from parameters
   - Position using location coordinates
   - Use "JoinFeatureOperation" or "CutFeatureOperation" appropriately

3. COORDINATE CONVERSION:
   - Intermediate uses real-world mm coordinates
   - SCL sketches use normalized 0-1 coordinates
   - Use moveTo to position sketch origin at feature location
   - sketch_scale converts normalized coords to mm

4. OPERATION TYPES:
   - Base geometry: "NewBodyFeatureOperation"
   - Holes/cuts: "CutFeatureOperation"
   - Added material: "JoinFeatureOperation"

EXAMPLE:
Input (Intermediate):
{
  "design_type": "block_with_holes",
  "base_geometry": {
    "type": "rectangular_box",
    "dimensions": {"width": 50, "depth": 30, "height": 10}
  },
  "features": [{
    "type": "cylindrical_hole",
    "parameters": {"diameter": 5, "depth": 10, "location": [25, 15, 10]}
  }]
}

Output (SCL JSON):
{
  "final_name": "Block_with_Hole",
  "final_shape": "Block with cylindrical hole",
  "units": "mm",
  "parts": {
    "part_1": {
      "sketch": {
        "face_1": {
          "loop_1": {
            "rectangle_1": {"Width": 1.0, "Height": 0.6}
          }
        }
      },
      "extrusion": {
        "sketch_scale": 50,
        "extrude_depth_towards_normal": 0.2,
        "operation": "NewBodyFeatureOperation"
      }
    },
    "part_2": {
      "hole_feature": {
        "hole_type": "Simple",
        "diameter": 5,
        "depth": 10,
        "position": [0.5, 0.5, 1.0]
      },
      "operation": "CutFeatureOperation"
    }
  }
}

Now convert the following intermediate design into SCL JSON:"""


if __name__ == "__main__":
    # Test the interpreter
    import json
    
    test_features = {
        "cylinders": [
            {"id": "f0", "radius_mm": 2.5, "location": [10, 10, 10], "axis": [0, 0, -1]}
        ],
        "planes": [
            {"id": "f1", "location": [25, 15, 0], "dims": [50, 30], "face_type": "horizontal", "normal": [0, 0, 1]},
            {"id": "f2", "location": [25, 15, 10], "dims": [50, 30], "face_type": "horizontal", "normal": [0, 0, -1]},
        ],
        "bounding_box": {"x_mm": 50, "y_mm": 30, "z_mm": 10},
        "face_count": 7
    }
    
    interpreter = GeometricInterpreter()
    intermediate = interpreter.interpret(test_features)
    
    print("=== INTERPRETED DESIGN ===")
    print(json.dumps(intermediate, indent=2))
    print("\n=== DESCRIPTION ===")
    print(interpreter.to_description(intermediate))
