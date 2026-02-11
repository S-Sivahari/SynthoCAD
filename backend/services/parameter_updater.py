import re
from pathlib import Path
from typing import Dict, Any, Tuple, Optional


class ParameterUpdater:
    
    def update_python_file(self, py_file_path: str, parameters: Dict[str, float]) -> bool:
        
        py_path = Path(py_file_path)
        
        if not py_path.exists():
            raise FileNotFoundError(f"Python file not found: {py_file_path}")
            
        with open(py_path, 'r') as f:
            code = f.read()
            
        updated_code = code
        
        for param_name, new_value in parameters.items():
            if param_name.startswith('circle_') and param_name.endswith('_radius'):
                idx = param_name.split('_')[1]
                pattern = r'(\.circle\()[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?(\))'
                matches = list(re.finditer(pattern, updated_code))
                
                try:
                    circle_idx = int(idx) - 1
                    if circle_idx < len(matches):
                        match = matches[circle_idx]
                        updated_code = (
                            updated_code[:match.start()] +
                            f'.circle({new_value})' +
                            updated_code[match.end():]
                        )
                except (ValueError, IndexError):
                    continue
                    
            elif param_name.startswith('extrude_') and param_name.endswith('_depth'):
                idx = param_name.split('_')[1]
                pattern = r'(\.extrude\()[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?(\))'
                matches = list(re.finditer(pattern, updated_code))
                
                try:
                    extrude_idx = int(idx) - 1
                    if extrude_idx < len(matches):
                        match = matches[extrude_idx]
                        updated_code = (
                            updated_code[:match.start()] +
                            f'.extrude({new_value})' +
                            updated_code[match.end():]
                        )
                except (ValueError, IndexError):
                    continue
                    
            elif param_name.startswith('position_') and ('_x' in param_name or '_y' in param_name):
                parts = param_name.split('_')
                idx = parts[1]
                coord = parts[2]
                
                pattern = r'\.moveTo\(([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?),\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\)'
                matches = list(re.finditer(pattern, updated_code))
                
                try:
                    pos_idx = int(idx) - 1
                    if pos_idx < len(matches):
                        match = matches[pos_idx]
                        x_val = float(match.group(1))
                        y_val = float(match.group(2))
                        
                        if coord == 'x':
                            x_val = new_value
                        else:
                            y_val = new_value
                            
                        updated_code = (
                            updated_code[:match.start()] +
                            f'.moveTo({x_val}, {y_val})' +
                            updated_code[match.end():]
                        )
                except (ValueError, IndexError):
                    continue
                    
            elif param_name.startswith('fillet_') and param_name.endswith('_radius'):
                idx = param_name.split('_')[1]
                pattern = r'(\.fillet\()[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?(\))'
                matches = list(re.finditer(pattern, updated_code))
                
                try:
                    fillet_idx = int(idx) - 1
                    if fillet_idx < len(matches):
                        match = matches[fillet_idx]
                        updated_code = (
                            updated_code[:match.start()] +
                            f'.fillet({new_value})' +
                            updated_code[match.end():]
                        )
                except (ValueError, IndexError):
                    continue
                    
        with open(py_path, 'w') as f:
            f.write(updated_code)
            
        return True
        
    def validate_parameter_value(self, param_name: str, value: float, min_val: Optional[float] = None, max_val: Optional[float] = None) -> Tuple[bool, Optional[str]]:
        
        if not isinstance(value, (int, float)):
            return False, "Value must be a number"
            
        if min_val is not None and value < min_val:
            return False, f"Value must be at least {min_val}"
            
        if max_val is not None and value > max_val:
            return False, f"Value must be at most {max_val}"
            
        if 'radius' in param_name or 'depth' in param_name or 'distance' in param_name:
            if value <= 0:
                return False, "Value must be positive"
                
        return True, None
