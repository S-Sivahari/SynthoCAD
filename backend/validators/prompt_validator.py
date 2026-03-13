import re
import json
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional


class PromptValidator:

    # Keywords pulled directly from template final_name and final_shape texts
    # so that any named part in the template library is immediately recognisable.
    _TEMPLATE_COMPONENT_KEYWORDS: List[str] = [
        # ── Engine / ICE ────────────────────────────────────────────────────
        "engine", "motor", "internal combustion", "ice", "v6", "v8", "v4",
        "inline", "4-cylinder", "six cylinder", "diesel", "petrol", "gasoline",
        "piston", "connecting rod", "con rod", "conrod",
        "crankshaft", "crank", "crankcase", "crankpin",
        "camshaft", "cam lobe", "cam",
        "valve", "poppet", "intake valve", "exhaust valve",
        "valve guide", "valve seat", "valve spring", "valve retainer",
        "cylinder head", "head casting", "head gasket",
        "cylinder liner", "wet liner", "dry liner",
        "spark plug", "sparkplug", "ignition",
        "fuel injector", "injector", "fuel rail",
        "intake manifold", "exhaust manifold", "manifold runner",
        "turbocharger", "turbo", "turbine", "compressor housing", "volute",
        "wastegate", "waste gate", "intercooler", "charge air cooler",
        "throttle body", "throttle plate", "throttle bore",
        "oil pan", "sump", "oil pump", "gerotor", "geronter",
        "oil filter", "oil pressure", "dipstick",
        "water pump", "impeller", "coolant pump",
        "radiator", "header tank", "thermostat",
        "timing chain", "timing belt", "timing sprocket", "timing pulley",
        "chain guide", "belt tensioner", "tensioner arm",
        "idler pulley", "serpentine belt", "harmonic balancer",
        "rocker arm", "pushrod", "lifter", "tappet", "hydraulic lifter",
        "balance shaft",
        "crankshaft pulley", "crankshaft web", "main journal",
        "main bearing cap", "bearing cap",
        "piston pin", "wrist pin", "gudgeon pin",
        "piston ring", "compression ring",
        "alternator", "starter motor", "starter pinion",
        "egr", "exhaust gas recirculation",
        "catalytic converter", "cat converter", "muffler", "baffle",
        "vvt", "variable valve timing", "phaser",
        "crankcase breather", "pcv",
        "engine mount",
        # ── Drivetrain / Transmission ────────────────────────────────────────
        "gearbox", "transmission", "differential", "driveshaft", "axle",
        "clutch", "flywheel", "torque converter", "cv joint",
        "propshaft", "half shaft", "output shaft",
        # ── Chassis / Suspension / Braking ──────────────────────────────────
        "suspension", "spring", "shock absorber", "damper", "strut",
        "control arm", "wishbone", "sway bar", "anti-roll",
        "brake", "caliper", "rotor", "drum", "brake pad", "brake disc",
        "steering rack", "tie rod", "knuckle",
        # ── Structural / Extrusion ───────────────────────────────────────────
        "t-slot", "v-slot", "extruded aluminium", "aluminium extrusion",
        "angle bracket", "corner bracket", "gusset", "din rail",
        "square tubing", "rectangular tubing", "hollow section",
        "mounting boss", "pcb standoff", "cable gland", "grommet",
        "snap fit", "heatsink", "fin array",
        # ── Fluid Power / Piping ────────────────────────────────────────────
        "hydraulic", "pneumatic", "manifold", "check valve", "solenoid valve",
        "piston rod", "hydraulic cylinder", "ram",
        "spray tip", "nozzle", "venturi",
        "filter housing", "expansion tank", "pressure gauge",
        "o-ring groove", "oil seal", "lip seal",
        "pipe fitting", "elbow", "tee", "cross fitting",
        # ── Power Transmission ───────────────────────────────────────────────
        "gear", "spur gear", "helical gear", "bevel gear", "worm gear",
        "sprocket", "chain sprocket", "timing gear",
        "pulley", "v-belt pulley", "flat belt pulley",
        "coupling", "jaw coupling", "oldham coupling",
        "flange coupling", "flexible coupling",
        "belt", "chain", "drive shaft",
        # ── Fasteners ───────────────────────────────────────────────────────
        "bolt", "screw", "nut", "washer", "fastener",
        "hex bolt", "socket head", "cap screw", "set screw", "grub screw",
        "stud", "rivet", "dowel pin", "clevis pin",
        # ── Body / Interior / Aero ───────────────────────────────────────────
        "a-pillar", "b-pillar", "rocker panel", "quarter panel",
        "bumper beam", "door impact beam", "hood inner", "door hinge",
        "spoiler", "diffuser", "air scoop", "heat shield", "skid plate",
        "fender liner", "headlight", "mirror housing", "grille",
        "seat frame", "steering wheel", "dashboard",
        "window regulator", "wiper pivot", "tail light",
        "sunroof", "fuse box", "wiring channel",
    ]

    def __init__(self, min_length: int = 10, max_length: int = 5000,
                 templates_root: Optional[str] = None):
        self.min_length = min_length
        self.max_length = max_length

        # Core geometric / dimensional CAD vocabulary
        self.cad_keywords: List[str] = [
            "cylinder", "box", "cube", "sphere", "cone", "tube", "pipe",
            "bracket", "flange", "shaft", "gear", "plate", "rod",
            "hole", "cut", "extrude", "revolve", "fillet", "chamfer",
            "diameter", "radius", "length", "width", "height", "depth", "thick",
            "mm", "cm", "inch", "meter", "millimeter", "centimeter",
            "round", "square", "rectangular", "circular", "hollow",
            "mounting", "base", "top", "bottom", "side", "edge", "face",
            "bolt", "nut", "screw", "washer", "pin", "dowel", "rivet",
            "bearing", "bushing", "coupling", "collar", "pulley",
            "clamp", "gasket", "seal", "ring", "o-ring",
            "elbow", "fitting", "cap", "plug", "cover", "lid",
            "standoff", "spacer", "gusset", "brace", "rib",
            "slot", "groove", "keyway", "notch", "pocket",
            "taper", "draft", "thread", "knurl",
            "hexagonal", "hex", "octagonal", "triangular",
            "wall", "shell", "housing", "enclosure", "case",
            "rail", "channel", "extrusion", "profile",
            "counterbore", "countersink", "tapped",
            "pattern", "array", "symmetric", "mirror",
            "assembly", "part", "component", "feature",
        ] + self._TEMPLATE_COMPONENT_KEYWORDS

        # Shape → template category mapping (used for suggest_templates)
        self.shape_keywords: Dict[str, List[str]] = {
            "cylinder": ["cylinder", "rod", "shaft", "pipe", "tube", "pin", "bar", "column"],
            "box": ["box", "cube", "block", "plate", "slab", "brick", "beam"],
            "bracket": ["bracket", "l-bracket", "angle", "corner", "mount", "brace"],
            "flange": ["flange", "disk", "plate", "adapter", "ring"],
            "gear": ["gear", "spur", "teeth", "cog", "sprocket", "timing gear"],
            "fastener": ["bolt", "nut", "screw", "washer", "rivet", "pin", "dowel"],
            "bearing": ["bearing", "bushing", "sleeve", "journal"],
            "housing": ["housing", "enclosure", "case", "shell", "box"],
            "fitting": ["elbow", "tee", "coupling", "fitting", "adapter", "connector"],
            # Engine family
            "engine/piston": [
                "piston", "connecting rod", "con rod", "conrod",
                "wrist pin", "piston pin", "gudgeon pin", "piston ring", "compression ring",
            ],
            "engine/crankshaft": [
                "crankshaft", "crank", "crankpin", "main journal",
                "crankshaft web", "crankshaft pulley", "harmonic balancer",
            ],
            "engine/valvetrain": [
                "valve", "intake valve", "exhaust valve", "valve guide", "valve seat",
                "valve spring", "valve retainer", "rocker arm", "pushrod", "lifter",
                "tappet", "camshaft", "cam lobe", "vvt", "phaser",
            ],
            "engine/head": [
                "cylinder head", "head casting", "head gasket",
                "spark plug", "fuel injector", "intake manifold", "exhaust manifold",
            ],
            "engine/oiling": [
                "oil pan", "sump", "oil pump", "gerotor", "oil filter",
                "oil pressure", "dipstick", "crankcase breather", "pcv",
            ],
            "engine/cooling": [
                "water pump", "impeller", "radiator", "thermostat", "coolant",
            ],
            "engine/timing": [
                "timing chain", "timing belt", "timing sprocket",
                "chain guide", "tensioner", "idler pulley",
            ],
            "engine/induction": [
                "turbocharger", "turbo", "intercooler", "throttle body",
                "wastegate", "manifold runner", "air scoop",
            ],
            "engine/misc": [
                "engine mount", "alternator", "starter", "serpentine belt",
                "balance shaft", "egr", "catalytic converter", "muffler",
            ],
        }

        # Build template lookup from disk if path provided (or auto-detect)
        self._template_entries: List[Dict] = []
        root = templates_root or self._find_templates_root()
        if root:
            self._template_entries = self._load_template_entries(root)

    # ── Private helpers ────────────────────────────────────────────────────

    @staticmethod
    def _find_templates_root() -> Optional[str]:
        """Walk up from this file to find the templates/ directory."""
        here = Path(__file__).resolve()
        for parent in [here.parent, here.parent.parent, here.parent.parent.parent]:
            candidate = parent / "templates"
            if candidate.is_dir():
                return str(candidate)
        return None

    @staticmethod
    def _load_template_entries(templates_root: str) -> List[Dict]:
        """Scan all JSON template files and return lightweight lookup entries."""
        entries: List[Dict] = []
        for path in Path(templates_root).rglob("*.json"):
            try:
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
                name = data.get("final_name", "")
                shape = data.get("final_shape", "")
                category = data.get("_template_category", "")
                if name:
                    # Tokenise name and shape into searchable terms
                    tokens = re.findall(r"[a-z]+", (name + " " + shape).lower())
                    entries.append({
                        "name": name,
                        "shape": shape,
                        "category": category,
                        "file": str(path.relative_to(templates_root)),
                        "tokens": set(tokens),
                    })
            except Exception:
                pass
        return entries

    def _match_templates(self, prompt_lower: str, max_results: int = 5) -> List[Dict]:
        """Return the best-matching template entries for a prompt."""
        prompt_tokens = set(re.findall(r"[a-z]+", prompt_lower))
        scored: List[Tuple[int, Dict]] = []
        for entry in self._template_entries:
            overlap = len(prompt_tokens & entry["tokens"])
            if overlap > 0:
                scored.append((overlap, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:max_results]]

    # ── Public API ─────────────────────────────────────────────────────────

    def validate(self, prompt: str) -> Tuple[bool, Optional[str], Optional[Dict]]:
        if not prompt or not isinstance(prompt, str):
            return False, "Prompt cannot be empty", None

        prompt_clean = prompt.strip()

        if len(prompt_clean) < self.min_length:
            return False, (
                f"Prompt too short. Minimum {self.min_length} characters required. "
                "Please describe the CAD model in more detail."
            ), None

        if len(prompt_clean) > self.max_length:
            return False, f"Prompt too long. Maximum {self.max_length} characters allowed.", None

        if not re.search(r"[a-zA-Z]", prompt_clean):
            return False, "Prompt must contain alphabetic characters.", None

        # ── Injection guard ────────────────────────────────────────────────
        for pattern in (r"<script", r"javascript:", r"eval\(", r"exec\(",
                        r"__import__", r"system\(", r"popen\("):
            if re.search(pattern, prompt_clean, re.IGNORECASE):
                return False, (
                    "Invalid input detected. "
                    "Please describe your CAD model without code or scripts."
                ), None

        prompt_lower = prompt_clean.lower()

        # ── Keyword check ─────────────────────────────────────────────────
        has_cad_keyword = any(kw in prompt_lower for kw in self.cad_keywords)

        # Also check against loaded template tokens for richer matching
        template_matches = self._match_templates(prompt_lower)
        has_template_match = bool(template_matches)

        if not has_cad_keyword and not has_template_match:
            return False, (
                "Prompt does not describe a CAD model. "
                "Please use geometric or component terms such as 'piston', 'crankshaft', "
                "'cylinder', 'bracket', or dimensions like 'mm', 'diameter', etc."
            ), {
                "suggestion": "Try a template name",
                "templates": ["piston", "crankshaft", "cylinder_head", "valve", "cylinder"],
            }

        # ── Dimension check ───────────────────────────────────────────────
        has_dimension = bool(
            re.search(r"\d+\.?\d*\s*(mm|cm|inch|in|meter|m\b|feet|ft)", prompt_lower)
        )
        has_number = bool(re.search(r"\d", prompt_clean))

        # Dimension is recommended but not required when the prompt clearly names
        # a known component (engine part, etc.) — LLM will use template defaults.
        if not has_number and not has_cad_keyword and not has_template_match:
            return False, (
                "Please include dimensions or a component name in your prompt "
                "(e.g., 'piston 86mm', 'crankshaft 100mm stroke')."
            ), {"suggestion": "Add numerical dimensions or a component name"}

        # ── Collect metadata ──────────────────────────────────────────────
        keywords_found = [kw for kw in self.cad_keywords if kw in prompt_lower]
        detected_shape = self._detect_shape(prompt_lower)

        metadata = {
            "length": len(prompt_clean),
            "has_dimensions": has_dimension,
            "has_numbers": has_number,
            "cad_keywords_found": keywords_found[:20],   # cap for payload size
            "detected_shape": detected_shape,
            "complexity_hint": self._estimate_complexity(prompt_lower),
            "template_matches": [
                {"name": t["name"], "category": t["category"]}
                for t in template_matches
            ],
        }

        return True, None, metadata

    def suggest_templates(self, prompt: str) -> List[Dict]:
        """Return template suggestions relevant to the given prompt."""
        if not prompt:
            return []
        prompt_lower = prompt.strip().lower()
        matched = self._match_templates(prompt_lower, max_results=5)
        if matched:
            return [
                {"name": t["name"], "category": t["category"], "file": t["file"]}
                for t in matched
            ]
        # Fallback: return engine starter suggestions when no match found
        return [
            {"name": "Automotive_Piston_86mm", "category": "automotive/engine"},
            {"name": "Crankshaft_Main_Journal", "category": "automotive/engine"},
            {"name": "Cylinder_Head_Casting",  "category": "automotive/engine"},
            {"name": "Connecting_Rod_140mm",   "category": "automotive/engine"},
            {"name": "Intake_Valve_33mm",      "category": "automotive/engine"},
        ]

    def _detect_shape(self, prompt_lower: str) -> str:
        """Detect the primary shape / component category from the prompt."""
        for shape, keywords in self.shape_keywords.items():
            if any(kw in prompt_lower for kw in keywords):
                return shape
        return "unknown"

    def _estimate_complexity(self, prompt_lower: str) -> str:
        """Estimate model complexity from prompt."""
        complex_indicators = [
            "pattern", "array", "holes", "bolt circle",
            "assembly", "multiple", "with", "and",
            "counterbore", "countersink", "fillet", "chamfer",
            "thread", "gear teeth",
        ]
        matches = sum(1 for ind in complex_indicators if ind in prompt_lower)
        if matches >= 3:
            return "complex"
        elif matches >= 1:
            return "moderate"
        return "simple"


