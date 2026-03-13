"""Edit Pipeline - Orchestrates the full STEP editing workflow.

Flow:
    STEP file
        → step_analyzer  (exact geometry: cylinders, planes, bbox)
        → call_gemini  (new SCL JSON synthesis)
        → SynthoCadPipeline.process_from_json  (generate new STEP)
"""
import os
import sys
import json
import uuid
import shutil
import logging
from pathlib import Path
from typing import Dict, Any, Optional

sys.path.append(str(Path(__file__).parent.parent))

from step_editor import step_analyzer
from services.gemini_service import call_gemini
from core.main import SynthoCadPipeline
from core import config
from core.schema_loader import build_edit_prompt

logger = logging.getLogger(__name__)

def _build_edit_prompt(features: Dict, user_prompt: str) -> str:
    """Build the full LLM prompt combining geometric features and user intent."""
    parts = [build_edit_prompt()]

    parts.append("\n\n=== GEOMETRIC FEATURE REPORT (EXACT) ===")
    parts.append(f"Summary: {features.get('summary', 'N/A')}")
    parts.append(f"Bounding Box: {json.dumps(features.get('bounding_box', {}))}")

    if features.get("cylinders"):
        parts.append(f"\nCylindrical Features ({len(features['cylinders'])} total):")
        for c in features["cylinders"]:
            parts.append(
                f"  - ID {c['id']}: radius={c['radius_mm']}mm, "
                f"axis={c['axis']}, location={c['location']}"
            )

    if features.get("planes"):
        all_planes = features["planes"]
        # Group: horizontal (Z-normal), vertical (X or Y normal), other
        z_faces = [p for p in all_planes if abs(p["normal"][2]) > 0.9]
        x_faces = [p for p in all_planes if abs(p["normal"][0]) > 0.9]
        y_faces = [p for p in all_planes if abs(p["normal"][1]) > 0.9]
        other   = [p for p in all_planes
                    if abs(p["normal"][0]) <= 0.9 and abs(p["normal"][1]) <= 0.9
                    and abs(p["normal"][2]) <= 0.9]

        if z_faces:
            parts.append(f"\nHorizontal Faces ({len(z_faces)}, normal ≈ Z):")
            for p in z_faces:
                parts.append(f"  - ID {p['id']}: dims={p['dims']}mm at z={p['location'][2]:.3f}mm")
        if x_faces:
            parts.append(f"\nVertical Faces ({len(x_faces)}, normal ≈ X):")
            for p in x_faces:
                parts.append(f"  - ID {p['id']}: dims={p['dims']}mm at x={p['location'][0]:.3f}mm")
        if y_faces:
            parts.append(f"\nVertical Faces ({len(y_faces)}, normal ≈ Y):")
            for p in y_faces:
                parts.append(f"  - ID {p['id']}: dims={p['dims']}mm at y={p['location'][1]:.3f}mm")
        if other:
            parts.append(f"\nAngled Faces ({len(other)}):")
            for p in other:
                parts.append(f"  - ID {p['id']}: normal={p['normal']}, dims={p['dims']}mm")

    if features.get("cones"):
        parts.append(f"\nConical Features ({len(features['cones'])} total - likely countersinks):")
        for c in features["cones"]:
            parts.append(f"  - ID {c['id']}: half_angle={c['half_angle_deg']}°")

    parts.append(f"\n\n=== USER EDIT REQUEST ===\n{user_prompt}")
    parts.append("\n\nGenerate the SCL JSON output:")

    return "\n".join(parts)


# ─── Main Entry Point ──────────────────────────────────────────────────────────

def edit_step(step_path: str, user_prompt: str) -> Dict[str, Any]:
    """
    Run the full STEP editing pipeline.

    Args:
        step_path:    Path to the uploaded STEP file.
        user_prompt:  Natural language description of the desired change.

    Returns:
        Result dict from SynthoCadPipeline (status, step_file, py_file, etc.)
        with an extra key "features" containing the analysis report.
    """
    logger.info(f"[EditPipeline] Starting edit: '{user_prompt}' on {step_path}")

    # 1. Geometric Decompilation
    logger.info("[EditPipeline] Step 1: Analyzing geometry...")
    try:
        features = step_analyzer.analyze(step_path)
    except Exception as e:
        return {"status": "error", "error": {"code": "ANALYSIS_FAILED", "message": str(e)}}

    # 2. LLM Synthesis
    logger.info(f"[EditPipeline] Step 2: Synthesizing new SCL JSON via {config.LLM_PROVIDER}...")
    full_prompt = _build_edit_prompt(features, user_prompt)

    try:
        raw_response = call_gemini(full_prompt, max_tokens=8192, temperature=0.15)
    except Exception as e:
        return {"status": "error", "error": {"code": "LLM_FAILED", "message": f"Gemini failed: {str(e)}"}}

    # 3. Parse JSON from LLM response
    import re
    raw_response = raw_response.strip()
    if raw_response.startswith("```"):
        raw_response = "\n".join(raw_response.split("\n")[1:])
        raw_response = raw_response.split("```")[0].strip()
    match = re.search(r"\{[\s\S]*\}", raw_response)
    if match:
        raw_response = match.group()

    try:
        scl_json = json.loads(raw_response)
    except json.JSONDecodeError as e:
        return {
            "status": "error",
            "error": {"code": "JSON_PARSE_FAILED", "message": str(e), "raw": raw_response[:500]},
        }

    # 4. Generate the new STEP via existing pipeline
    logger.info("[EditPipeline] Step 3: Generating new STEP file...")
    from core import config as _cfg
    pipeline = SynthoCadPipeline(rag_provider=_cfg.get_rag_provider())
    result = pipeline.process_from_json(scl_json)

    # 5. Attach analysis features to result
    result["features"] = features

    logger.info(f"[EditPipeline] Done. Status: {result.get('status')}")
    return result
