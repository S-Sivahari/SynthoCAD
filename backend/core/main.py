import json
import sys
import subprocess
from pathlib import Path
from typing import Dict, Any, Tuple
import logging

sys.path.append(str(Path(__file__).parent.parent))

from validators.prompt_validator import PromptValidator
from validators.json_validator import validate_json
from core.cadquery_generator import CadQueryGenerator
from services.parameter_extractor import ParameterExtractor
from services.parameter_updater import ParameterUpdater
from services.freecad_instance_generator import FreeCADInstanceGenerator
from utils.errors import *
from utils.logger import pipeline_logger
from core import config


class SynthoCadPipeline:
    
    def __init__(self):
        self.prompt_validator = PromptValidator()
        self.generator = CadQueryGenerator
        self.param_extractor = ParameterExtractor()
        self.param_updater = ParameterUpdater()
        self.freecad = FreeCADInstanceGenerator()
        self.logger = pipeline_logger
        
    def validate_prompt(self, prompt: str) -> Dict[str, Any]:
        self.logger.info(f"Step 1: Validating prompt")
        is_valid, error_msg, metadata = self.prompt_validator.validate(prompt)
        
        if not is_valid:
            self.logger.error(f"Prompt validation failed: {error_msg}")
            raise PromptValidationError(error_msg or "Validation failed", metadata)
            
        self.logger.info(f"Prompt validated successfully")
        
        # Calculate confidence based on prompt quality
        prompt_lower = prompt.lower()
        cad_keyword_matches = sum(1 for kw in self.prompt_validator.cad_keywords if kw in prompt_lower)
        confidence = min(0.95, 0.5 + (cad_keyword_matches * 0.1))
        
        # Check for template suggestions
        suggestions = self.prompt_validator.suggest_templates(prompt)
        
        return {
            'valid': True,
            'confidence': round(confidence, 2),
            'suggestions': suggestions,
            'metadata': metadata or {}
        }
        
    def generate_json_from_prompt(self, prompt: str) -> Dict[str, Any]:
        self.logger.info("Step 2: Generating JSON from prompt (LLM integration placeholder)")
        
        raise NotImplementedError(
            "LLM integration not yet implemented. "
            "Please use templates or provide JSON directly."
        )
        
    def validate_json(self, json_data: Dict) -> bool:
        self.logger.info("Step 3: Validating JSON against SCL schema")
        
        if not validate_json(json_data):
            self.logger.error("JSON validation failed")
            raise JSONValidationError("JSON does not conform to SCL schema")
            
        self.logger.info("JSON validated successfully")
        return True
        
    def generate_cadquery_code(self, json_data: Dict, output_name: str) -> str:
        self.logger.info("Step 4: Generating CadQuery Python code")
        
        try:
            generator = self.generator(json_data, output_name)
            code = generator.generate()
            
            py_file = config.PY_OUTPUT_DIR / f"{output_name}_generated.py"
            with open(py_file, 'w') as f:
                f.write(code)
                
            self.logger.info(f"Generated Python code: {py_file}")
            return str(py_file)
            
        except Exception as e:
            self.logger.error(f"Code generation failed: {str(e)}")
            raise CodeGenerationError(f"Failed to generate CadQuery code: {str(e)}")
            
    def execute_cadquery_code(self, py_file: str, output_name: str) -> str:
        self.logger.info("Step 5: Executing CadQuery code to generate STEP")
        
        py_path = Path(py_file)
        if not py_path.is_absolute():
            py_path = config.BASE_DIR / py_path
            
        if not py_path.exists():
            raise ExecutionError(f"Python file not found: {py_file}")
            
        step_file = config.STEP_OUTPUT_DIR / f"{output_name}.step"
        
        try:
            result = subprocess.run(
                [sys.executable, str(py_path)],
                capture_output=True,
                text=True,
                timeout=config.EXECUTION_TIMEOUT,
                cwd=config.STEP_OUTPUT_DIR
            )
            
            if result.returncode != 0:
                self.logger.error(f"Execution failed: {result.stderr}")
                raise ExecutionError(f"Python execution failed: {result.stderr}")
                
            if not step_file.exists():
                raise ExecutionError("STEP file was not created")
                
            self.logger.info(f"STEP file generated: {step_file}")
            return str(step_file)
            
        except subprocess.TimeoutExpired:
            raise ExecutionError(f"Execution timeout ({config.EXECUTION_TIMEOUT}s)")
        except Exception as e:
            raise ExecutionError(f"Execution error: {str(e)}")
            
    def extract_parameters(self, py_file: str) -> Dict[str, Any]:
        self.logger.info("Step 6: Extracting editable parameters")
        
        try:
            params_data = self.param_extractor.extract_from_python(py_file)
            markdown = self.param_extractor.generate_markdown(params_data)
            
            self.logger.info(f"Extracted {params_data['total_count']} parameters")
            
            return {
                'parameters': params_data['parameters'],
                'markdown': markdown,
                'total_count': params_data['total_count']
            }
            
        except Exception as e:
            self.logger.error(f"Parameter extraction failed: {str(e)}")
            return {
                'parameters': [],
                'markdown': '# No parameters found',
                'total_count': 0
            }
            
    def open_in_freecad(self, step_file: str) -> bool:
        self.logger.info("Step 7: Opening STEP file in FreeCAD")
        
        try:
            self.freecad.open_step_file(step_file, async_mode=True)
            self.logger.info("FreeCAD opened successfully")
            return True
            
        except Exception as e:
            self.logger.warning(f"FreeCAD open failed: {str(e)}")
            return False
            
    def update_parameters(self, py_file: str, parameters: Dict[str, float]) -> str:
        self.logger.info(f"Step 8: Updating {len(parameters)} parameters")
        
        try:
            for param_name, value in parameters.items():
                is_valid, error_msg = self.param_updater.validate_parameter_value(param_name, value)
                if not is_valid:
                    raise ParameterUpdateError(f"Invalid value for {param_name}: {error_msg or 'Invalid value'}")
                    
            self.param_updater.update_python_file(py_file, parameters)
            self.logger.info("Parameters updated successfully")
            return py_file  # Return the path to the updated file
            
        except Exception as e:
            self.logger.error(f"Parameter update failed: {str(e)}")
            raise ParameterUpdateError(f"Failed to update parameters: {str(e)}")
            
    def regenerate_from_updated_python(self, py_file: str, output_name: str, open_freecad: bool = True) -> str:
        self.logger.info("Step 9: Regenerating STEP from updated Python")
        
        # Update the export filename in the Python file to match output_name
        py_path = Path(py_file)
        if not py_path.is_absolute():
            py_path = config.BASE_DIR / py_path
            
        content = py_path.read_text()
        # Replace the export line with the correct output name
        import re
        content = re.sub(
            r"cq\.exporters\.export\(result,\s*['\"][\w.-]+\.step['\"]\)",
            f"cq.exporters.export(result, '{output_name}.step')",
            content
        )
        py_path.write_text(content)
        
        step_file = self.execute_cadquery_code(str(py_path), output_name)
        
        if open_freecad:
            self.freecad.reload_step_file(step_file)
            
        return step_file
        
    def process_from_json(self, json_data: Dict, output_name: Optional[str] = None, open_freecad: bool = True) -> Dict[str, Any]:
        
        try:
            self.validate_json(json_data)
            
            if not output_name:
                output_name = json_data.get('final_name', 'output')
                if not output_name or output_name.strip() == "":
                    output_name = 'output'
            
            output_name = output_name.replace(' ', '_').replace('/', '_')
            
            json_file = config.JSON_OUTPUT_DIR / f"{output_name}.json"
            with open(json_file, 'w') as f:
                json.dump(json_data, f, indent=2)
            self.logger.info(f"Saved JSON: {json_file}")
            
            py_file = self.generate_cadquery_code(json_data, output_name)
            
            step_file = self.execute_cadquery_code(py_file, output_name)
            
            params_result = self.extract_parameters(py_file)
            
            if open_freecad:
                freecad_opened = self.open_in_freecad(step_file)
            else:
                freecad_opened = False
                
            return {
                'status': 'success',
                'json_file': str(json_file),
                'py_file': py_file,
                'step_file': step_file,
                'parameters': params_result,
                'freecad_opened': freecad_opened
            }
            
        except SynthoCadError as e:
            self.logger.error(f"Pipeline failed: {e.message}")
            return {
                'status': 'error',
                'error': e.to_dict()
            }
        except Exception as e:
            self.logger.error(f"Unexpected error: {str(e)}")
            return {
                'status': 'error',
                'error': {
                    'code': 'UNKNOWN_ERROR',
                    'message': str(e)
                }
            }
            
    def process_from_prompt(self, prompt: str, open_freecad: bool = True) -> Dict[str, Any]:
        
        try:
            self.validate_prompt(prompt)
            
            json_data = self.generate_json_from_prompt(prompt)
            
            return self.process_from_json(json_data, open_freecad=open_freecad)
            
        except NotImplementedError as e:
            return {
                'status': 'error',
                'error': {
                    'code': 'NOT_IMPLEMENTED',
                    'message': str(e)
                }
            }
        except SynthoCadError as e:
            return {
                'status': 'error',
                'error': e.to_dict()
            }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python main.py <json_file>")
        sys.exit(1)
        
    json_file_path = sys.argv[1]
    
    with open(json_file_path, 'r') as f:
        json_data = json.load(f)
    
    pipeline = SynthoCadPipeline()
    result = pipeline.process_from_json(json_data, open_freecad=False)
    
    if result['status'] == 'success':
        print("[SUCCESS]")
        print(f"  JSON:       {result['json_file']}")
        print(f"  Python:     {result['py_file']}")
        print(f"  STEP:       {result['step_file']}")
        print(f"  Parameters: {result['parameters']['total_count']} found")
    else:
        print(f"[FAILED] {result['error']}")
        sys.exit(1)
        print(f"Failed: {result}")
        sys.exit(1)
