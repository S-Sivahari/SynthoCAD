import re
from typing import Dict, Tuple, Optional


class PromptValidator:
    
    def __init__(self, min_length: int = 10, max_length: int = 5000):
        self.min_length = min_length
        self.max_length = max_length
        
        self.cad_keywords = [
            'cylinder', 'box', 'cube', 'sphere', 'cone', 'tube', 'pipe',
            'bracket', 'flange', 'shaft', 'gear', 'plate', 'rod',
            'hole', 'cut', 'extrude', 'revolve', 'fillet', 'chamfer',
            'diameter', 'radius', 'length', 'width', 'height', 'depth',
            'mm', 'cm', 'inch', 'meter', 'millimeter', 'centimeter',
            'round', 'square', 'rectangular', 'circular', 'hollow',
            'mounting', 'base', 'top', 'bottom', 'side', 'edge', 'face'
        ]
        
    def validate(self, prompt: str) -> Tuple[bool, Optional[str], Optional[Dict]]:
        
        if not prompt or not isinstance(prompt, str):
            return False, "Prompt cannot be empty", None
            
        prompt_clean = prompt.strip()
        
        if len(prompt_clean) < self.min_length:
            return False, f"Prompt too short. Minimum {self.min_length} characters required. Please describe the CAD model in more detail.", None
            
        if len(prompt_clean) > self.max_length:
            return False, f"Prompt too long. Maximum {self.max_length} characters allowed.", None
            
        if not re.search(r'[a-zA-Z]', prompt_clean):
            return False, "Prompt must contain alphabetic characters.", None
            
        prompt_lower = prompt_clean.lower()
        
        has_cad_keyword = any(keyword in prompt_lower for keyword in self.cad_keywords)
        
        if not has_cad_keyword:
            return False, "Prompt does not describe a CAD model. Please use geometric terms like 'cylinder', 'box', 'bracket', or dimensions like 'mm', 'diameter', etc.", {
                "suggestion": "Try templates",
                "templates": ["cylinder", "box", "l_bracket", "flange"]
            }
            
        digits_count = len(re.findall(r'\d', prompt_clean))
        if digits_count == 0:
            return False, "Please include dimensions in your prompt (e.g., '100mm', '5 inches', '2cm diameter').", {
                "suggestion": "Add numerical dimensions"
            }
            
        suspicious_patterns = [
            r'<script',
            r'javascript:',
            r'eval\(',
            r'exec\(',
            r'__import__',
            r'system\(',
            r'popen\('
        ]
        
        for pattern in suspicious_patterns:
            if re.search(pattern, prompt_lower):
                return False, "Invalid input detected. Please describe your CAD model without code or scripts.", None
                
        metadata = {
            "length": len(prompt_clean),
            "has_dimensions": bool(re.search(r'\d+\s*(mm|cm|inch|meter|m)', prompt_lower)),
            "cad_keywords_found": [kw for kw in self.cad_keywords if kw in prompt_lower]
        }
        
        return True, None, metadata
        
    def suggest_templates(self, prompt: str) -> list:
        prompt_lower = prompt.lower()
        suggestions = []
        
        template_keywords = {
            'cylinder': ['cylinder', 'rod', 'shaft', 'circular', 'round'],
            'box': ['box', 'cube', 'rectangular', 'square', 'block'],
            'tube': ['tube', 'pipe', 'hollow cylinder', 'hollow'],
            'l_bracket': ['bracket', 'l-bracket', 'angle', 'corner'],
            'flange': ['flange', 'mounting plate', 'adapter'],
            'shaft': ['shaft', 'axle', 'spindle']
        }
        
        for template, keywords in template_keywords.items():
            if any(kw in prompt_lower for kw in keywords):
                suggestions.append(template)
                
        return suggestions[:3]
