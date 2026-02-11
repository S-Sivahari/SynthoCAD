import re
from pathlib import Path
from typing import Dict, List, Any


class ParameterExtractor:
    
    def extract_from_python(self, py_file_path: str) -> Dict[str, Any]:
        
        py_path = Path(py_file_path)
        
        if not py_path.exists():
            raise FileNotFoundError(f"Python file not found: {py_file_path}")
            
        with open(py_path, 'r') as f:
            code = f.read()
            
        parameters = []
        
        number_pattern = r'([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)'
        
        circle_matches = re.finditer(r'\.circle\((' + number_pattern + r')\)', code)
        for idx, match in enumerate(circle_matches, 1):
            parameters.append({
                'name': f'circle_{idx}_radius',
                'value': float(match.group(1)),
                'type': 'float',
                'description': f'Circle {idx} radius',
                'unit': 'normalized',
                'min': 0.001,
                'max': 10.0
            })
            
        extrude_matches = re.finditer(r'\.extrude\((' + number_pattern + r')\)', code)
        for idx, match in enumerate(extrude_matches, 1):
            parameters.append({
                'name': f'extrude_{idx}_depth',
                'value': float(match.group(1)),
                'type': 'float',
                'description': f'Extrusion {idx} depth',
                'unit': 'normalized',
                'min': 0.001,
                'max': 10.0
            })
            
        moveto_matches = re.finditer(r'\.moveTo\((' + number_pattern + r'),\s*(' + number_pattern + r')\)', code)
        for idx, match in enumerate(moveto_matches, 1):
            parameters.append({
                'name': f'position_{idx}_x',
                'value': float(match.group(1)),
                'type': 'float',
                'description': f'Position {idx} X coordinate',
                'unit': 'normalized',
                'min': -5.0,
                'max': 5.0
            })
            parameters.append({
                'name': f'position_{idx}_y',
                'value': float(match.group(2)),
                'type': 'float',
                'description': f'Position {idx} Y coordinate',
                'unit': 'normalized',
                'min': -5.0,
                'max': 5.0
            })
            
        lineto_matches = re.finditer(r'\.lineTo\((' + number_pattern + r'),\s*(' + number_pattern + r')\)', code)
        for idx, match in enumerate(lineto_matches, 1):
            parameters.append({
                'name': f'line_{idx}_x',
                'value': float(match.group(1)),
                'type': 'float',
                'description': f'Line {idx} end X',
                'unit': 'normalized',
                'min': -5.0,
                'max': 5.0
            })
            parameters.append({
                'name': f'line_{idx}_y',
                'value': float(match.group(2)),
                'type': 'float',
                'description': f'Line {idx} end Y',
                'unit': 'normalized',
                'min': -5.0,
                'max': 5.0
            })
            
        fillet_matches = re.finditer(r'\.fillet\((' + number_pattern + r')\)', code)
        for idx, match in enumerate(fillet_matches, 1):
            parameters.append({
                'name': f'fillet_{idx}_radius',
                'value': float(match.group(1)),
                'type': 'float',
                'description': f'Fillet {idx} radius',
                'unit': 'normalized',
                'min': 0.001,
                'max': 1.0
            })
            
        chamfer_matches = re.finditer(r'\.chamfer\((' + number_pattern + r')\)', code)
        for idx, match in enumerate(chamfer_matches, 1):
            parameters.append({
                'name': f'chamfer_{idx}_distance',
                'value': float(match.group(1)),
                'type': 'float',
                'description': f'Chamfer {idx} distance',
                'unit': 'normalized',
                'min': 0.001,
                'max': 1.0
            })
            
        return {
            'file': str(py_path),
            'parameters': parameters,
            'total_count': len(parameters)
        }
        
    def generate_markdown(self, parameters_data: Dict[str, Any]) -> str:
        
        md_lines = [
            "# Model Parameters",
            "",
            f"**File:** `{Path(parameters_data['file']).name}`",
            f"**Total Parameters:** {parameters_data['total_count']}",
            "",
            "---",
            ""
        ]
        
        if not parameters_data['parameters']:
            md_lines.append("*No editable parameters found.*")
            return "\n".join(md_lines)
            
        md_lines.append("## Editable Parameters")
        md_lines.append("")
        
        for param in parameters_data['parameters']:
            md_lines.append(f"### {param['description']}")
            md_lines.append(f"- **Name:** `{param['name']}`")
            md_lines.append(f"- **Current Value:** {param['value']}")
            md_lines.append(f"- **Type:** {param['type']}")
            md_lines.append(f"- **Unit:** {param['unit']}")
            md_lines.append(f"- **Range:** {param['min']} to {param['max']}")
            md_lines.append("")
            
        return "\n".join(md_lines)
