"""Schema Loader — single source of truth for SCL schema and LLM prompts.

Loads ``scl_schema.json`` once at import time and exposes helpers that build
context-specific LLM prompts from the real schema (definitions, examples,
llm_instructions, validation_rules, etc.).

Every module that needs the schema or an LLM prompt should import from here
instead of hardcoding its own copy.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# ── Load schema once ────────────────────────────────────────────────────────

_SCHEMA_PATH = Path(__file__).parent / "scl_schema.json"

def _load_schema() -> Dict[str, Any]:
    """Read and parse the canonical SCL schema JSON."""
    if not _SCHEMA_PATH.exists():
        raise FileNotFoundError(f"SCL schema not found at {_SCHEMA_PATH}")
    with open(_SCHEMA_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)

SCL_SCHEMA: Dict[str, Any] = _load_schema()

# ── Prompt builders ─────────────────────────────────────────────────────────

def _format_definitions(schema: Dict[str, Any]) -> str:
    """Render the definitions block into a human-readable section."""
    defs = schema.get("definitions", {})
    if not defs:
        return ""
    lines = ["=== SCL JSON DEFINITIONS ==="]
    for name, defn in defs.items():
        desc = defn.get("description", "")
        lines.append(f"\n{name}: {desc}")
        props = defn.get("properties", {})
        for prop_name, prop_info in props.items():
            prop_desc = prop_info.get("description", "")
            prop_type = prop_info.get("type", prop_info.get("$ref", ""))
            enum_vals = prop_info.get("enum", [])
            constraint = ""
            if enum_vals:
                constraint = f"  enum={enum_vals}"
            elif prop_info.get("minimum") is not None or prop_info.get("maximum") is not None:
                constraint = f"  range=[{prop_info.get('minimum', '')}, {prop_info.get('maximum', '')}]"
            lines.append(f"  • {prop_name} ({prop_type}){constraint}: {prop_desc}")
        # oneOf constraints
        one_of = defn.get("oneOf", [])
        if one_of:
            lines.append("  oneOf constraints:")
            for alt in one_of:
                req = alt.get("required", [])
                lines.append(f"    - requires: {req}")
    return "\n".join(lines)


def _format_examples(schema: Dict[str, Any]) -> str:
    """Render the embedded examples into a prompt section."""
    examples = schema.get("examples", [])
    if not examples:
        return ""
    lines = ["\n=== SCHEMA EXAMPLES ==="]
    for i, ex in enumerate(examples, 1):
        comment = ex.get("_comment", f"Example {i}")
        lines.append(f"\n--- {comment} ---")
        clean = {k: v for k, v in ex.items() if k != "_comment"}
        lines.append(json.dumps(clean, indent=2))
    return "\n".join(lines)


def _format_llm_instructions(schema: Dict[str, Any]) -> str:
    """Render the llm_instructions section into a structured prompt."""
    instructions = schema.get("llm_instructions", {})
    if not instructions:
        return ""
    lines = ["\n=== LLM INSTRUCTIONS ==="]

    # Overview
    overview = instructions.get("overview", "")
    if overview:
        lines.append(f"\n{overview}")

    # NL to JSON conversion steps
    nl_steps = instructions.get("nl_to_json_conversion", {})
    if nl_steps:
        lines.append("\n--- NL-to-JSON Conversion Steps ---")
        for step_key in sorted(nl_steps.keys()):
            step = nl_steps[step_key]
            desc = step.get("description", "")
            lines.append(f"\n{step_key}: {desc}")
            for sub_key, sub_val in step.items():
                if sub_key == "description":
                    continue
                if isinstance(sub_val, dict):
                    for k, v in sub_val.items():
                        lines.append(f"  {k}: {v}")
                elif isinstance(sub_val, list):
                    for item in sub_val:
                        lines.append(f"  - {item}")
                else:
                    lines.append(f"  {sub_key}: {sub_val}")

    # Parametric modeling philosophy
    philosophy = instructions.get("parametric_modeling_philosophy", {})
    if philosophy:
        lines.append("\n--- Parametric Modeling Philosophy ---")
        for key, val in philosophy.items():
            if isinstance(val, dict):
                lines.append(f"\n{key}:")
                for k, v in val.items():
                    if isinstance(v, list):
                        for item in v:
                            lines.append(f"    {item}")
                    elif isinstance(v, dict):
                        for kk, vv in v.items():
                            lines.append(f"    {kk}: {vv}")
                    else:
                        lines.append(f"  {k}: {v}")
            else:
                lines.append(f"  {key}: {val}")

    # Advanced inference rules
    rules = instructions.get("advanced_inference_rules", {})
    if rules:
        lines.append("\n--- Advanced Rules ---")
        for rule_key, rule_val in rules.items():
            desc = rule_val.get("description", "")
            lines.append(f"\n{rule_key}: {desc}")
            for k, v in rule_val.items():
                if k == "description":
                    continue
                if isinstance(v, dict):
                    for kk, vv in v.items():
                        lines.append(f"  {kk}: {vv}")
                elif isinstance(v, list):
                    for item in v:
                        lines.append(f"  - {item}")
                else:
                    lines.append(f"  {k}: {v}")

    # Common patterns catalog
    patterns = instructions.get("common_patterns_catalog", {})
    if patterns:
        lines.append("\n--- Common Patterns ---")
        for name, info in patterns.items():
            use_case = info.get("use_case", "")
            parts = info.get("parts", "")
            lines.append(f"  {name}: {parts} part(s) — {use_case}")

    # Troubleshooting
    troubleshooting = instructions.get("troubleshooting", {})
    if troubleshooting:
        lines.append("\n--- Troubleshooting ---")
        for issue, fix in troubleshooting.items():
            lines.append(f"  {issue}: {fix}")

    return "\n".join(lines)


def _format_validation_rules(schema: Dict[str, Any]) -> str:
    """Render validation rules into a checklist section."""
    instructions = schema.get("llm_instructions", {})
    rules = instructions.get("validation_rules", [])
    if not rules:
        return ""
    lines = ["\n=== VALIDATION RULES ==="]
    for rule in rules:
        lines.append(f"  {rule}")
    return "\n".join(lines)


# ── Public prompt builders ──────────────────────────────────────────────────

def build_generation_prompt() -> str:
    """Build the system prompt for NL → SCL JSON generation.

    This replaces the old hardcoded ``LLM_SYSTEM_PROMPT`` in main.py.
    It feeds the LLM the full schema definitions, examples, conversion
    instructions, and validation rules from ``scl_schema.json``.
    """
    preamble = (
        "You are an expert parametric CAD engineer. Convert natural language "
        "descriptions into valid SCL (SynthoCAD Language) JSON.\n\n"
        "CRITICAL OUTPUT RULES:\n"
        "1. Output ONLY valid raw JSON — no markdown, no explanation, no comments.\n"
        "2. Always include \"units\" field (default: \"mm\").\n"
        "3. First part (part_1) MUST use \"NewBodyFeatureOperation\".\n"
        "4. Parts numbered sequentially: part_1, part_2, part_3...\n"
        "5. Each part needs EXACTLY ONE of: sketch+extrusion, revolve_profile+revolve, or hole_feature.\n"
        "6. Sketch coordinates are normalized (0.0-1.0), then sketch_scale converts to real mm.\n"
        "7. Output ONLY raw JSON starting with { and ending with }.\n"
    )
    sections = [
        preamble,
        _format_definitions(SCL_SCHEMA),
        _format_examples(SCL_SCHEMA),
        _format_llm_instructions(SCL_SCHEMA),
        _format_validation_rules(SCL_SCHEMA),
    ]
    return "\n".join(s for s in sections if s)


def build_edit_prompt() -> str:
    """Build the system prompt for STEP-editing workflows.

    This replaces the old hardcoded ``EDIT_SYSTEM_PROMPT`` in
    ``step_editor/edit_pipeline.py``.  It includes the full schema context
    so the LLM can produce accurate SCL JSON when transforming existing
    STEP geometry.
    """
    preamble = (
        "You are an expert parametric CAD engineer converting existing STEP "
        "geometry into editable SCL (SynthoCAD Language) JSON.\n\n"
        "CRITICAL OUTPUT RULES:\n"
        "1. Output ONLY valid raw JSON — no markdown, no explanation, no comments.\n"
        "2. The JSON MUST have a \"parts\" key with at least \"part_1\".\n"
        "3. \"part_1\" MUST use \"NewBodyFeatureOperation\".\n"
        "4. Each part needs EXACTLY ONE of: sketch+extrusion, revolve_profile+revolve, or hole_feature.\n"
        "5. Sketch coordinates are normalized (0.0-1.0), then sketch_scale converts to real mm.\n"
        "6. Always include \"units\": \"mm\".\n"
        "7. Output ONLY raw JSON starting with { and ending with }.\n"
    )
    sections = [
        preamble,
        _format_definitions(SCL_SCHEMA),
        _format_examples(SCL_SCHEMA),
        _format_llm_instructions(SCL_SCHEMA),
        _format_validation_rules(SCL_SCHEMA),
    ]
    return "\n".join(s for s in sections if s)


def get_schema() -> Dict[str, Any]:
    """Return the loaded SCL schema dict (read-only reference)."""
    return SCL_SCHEMA
