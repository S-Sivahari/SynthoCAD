import os
import json
import uuid
import tempfile
import subprocess
import sys
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple

from core import config
from utils.logger import setup_logger

logger = setup_logger('synthocad.brep_engine', 'brep_engine.log')

# =============================================================================
# ISOLATED WORKERS (Prevent C-level OCC crashes from killing the backend)
# =============================================================================

_BREP_WORKER_SCRIPT = """
import sys, json, math, traceback
import cadquery as cq
from OCP.gp import gp_Pnt, gp_Dir, gp_Ax2
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder

def _apply_op(model, payload):
    op_type = payload['type']
    params = payload.get('params', {})

    def append_to_model(base_model, new_shape):
        if len(base_model.objects) == 0:
            return new_shape
        return base_model.union(new_shape)

    def make_tool(tool_type, tool_params):
        loc = tool_params.get('origin', [0.0, 0.0, 0.0])
        axis = tool_params.get('axis', [0.0, 1.0, 0.0])
        plane = cq.Plane(origin=cq.Vector(*loc), normal=cq.Vector(*axis))

        if tool_type == 'box':
            length = float(tool_params.get('length', 10.0))
            width = float(tool_params.get('width', 10.0))
            height = float(tool_params.get('height', 10.0))
            return cq.Workplane(plane).box(length, width, height, centered=(True, True, False))
        elif tool_type == 'cylinder':
            radius = float(tool_params.get('radius', 5.0))
            height = float(tool_params.get('height', 10.0))
            return cq.Workplane(plane).circle(radius).extrude(height)
        elif tool_type == 'cone':
            base_r = float(tool_params.get('base_radius', 5.0))
            top_r = float(tool_params.get('top_radius', 0.0))
            height = float(tool_params.get('height', 10.0))
            tip = max(top_r, 0.001)
            return cq.Workplane(plane).circle(base_r).workplane(offset=height).circle(tip).loft()
        elif tool_type == 'sphere':
            radius = float(tool_params.get('radius', 5.0))
            return cq.Workplane(plane).sphere(radius)
        else:
            raise ValueError(f"Unknown tool_type: {tool_type}")

    # Primitives
    if op_type == 'create_box':
        length = float(params.get('length', 10.0))
        width = float(params.get('width', 10.0))
        height = float(params.get('height', 10.0))
        loc = params.get('origin', [0.0, 0.0, 0.0])
        axis = params.get('axis', [0.0, 1.0, 0.0])
        plane = cq.Plane(origin=cq.Vector(*loc), normal=cq.Vector(*axis))
        primitive = cq.Workplane(plane).box(length, width, height, centered=(True, True, False))
        return append_to_model(model, primitive)

    elif op_type == 'create_cylinder':
        radius = float(params.get('radius', 5.0))
        height = float(params.get('height', 10.0))
        loc = params.get('origin', [0.0, 0.0, 0.0])
        axis = params.get('axis', [0.0, 1.0, 0.0])
        plane = cq.Plane(origin=cq.Vector(*loc), normal=cq.Vector(*axis))
        primitive = cq.Workplane(plane).circle(radius).extrude(height)
        return append_to_model(model, primitive)

    elif op_type == 'create_cone':
        base_r = float(params.get('base_radius', 5.0))
        top_r = float(params.get('top_radius', 0.0))
        height = float(params.get('height', 10.0))
        loc = params.get('origin', [0.0, 0.0, 0.0])
        axis = params.get('axis', [0.0, 1.0, 0.0])
        plane = cq.Plane(origin=cq.Vector(*loc), normal=cq.Vector(*axis))
        tip = max(top_r, 0.001)
        primitive = cq.Workplane(plane).circle(base_r).workplane(offset=height).circle(tip).loft()
        return append_to_model(model, primitive)

    elif op_type == 'create_sphere':
        radius = float(params.get('radius', 5.0))
        loc = params.get('origin', [0.0, 0.0, 0.0])
        axis = params.get('axis', [0.0, 1.0, 0.0])
        plane = cq.Plane(origin=cq.Vector(*loc), normal=cq.Vector(*axis))
        primitive = cq.Workplane(plane).sphere(radius)
        return append_to_model(model, primitive)

    # Booleans
    elif op_type in ('boolean_cut', 'boolean_union', 'boolean_intersect'):
        tool_data = payload.get('tool', {})
        tool_type = tool_data.get('type', 'cylinder')
        params = tool_data.get('params', {})
        tool = make_tool(tool_type, params)

        if op_type == 'boolean_cut':
            return model.cut(tool)
        elif op_type == 'boolean_union':
            if len(model.objects) == 0:
                return tool
            return model.union(tool)
        elif op_type == 'boolean_intersect':
            return model.intersect(tool)

    elif op_type == 'loop_pattern':
        pattern = str(payload.get('pattern', 'linear')).lower()
        action = str(payload.get('action', 'cut')).lower()
        count = int(payload.get('instances', payload.get('count', 1)))
        if count < 1:
            raise ValueError('loop_pattern.instances must be >= 1')

        tool_data = payload.get('tool', {})
        tool_type = tool_data.get('type', 'cylinder')
        tool_params = dict(tool_data.get('params', {}) or {})
        base_origin = tool_params.get('origin', [0.0, 0.0, 0.0])

        result = model
        for i in range(count):
            origin = list(base_origin)

            if pattern == 'linear':
                linear_cfg = payload.get('linear', {})
                if 'step' in linear_cfg:
                    step = linear_cfg.get('step', [0.0, 0.0, 0.0])
                else:
                    direction = linear_cfg.get('direction', [1.0, 0.0, 0.0])
                    spacing = float(linear_cfg.get('spacing', 0.0))
                    step = [direction[0] * spacing, direction[1] * spacing, direction[2] * spacing]
                origin = [
                    base_origin[0] + float(step[0]) * i,
                    base_origin[1] + float(step[1]) * i,
                    base_origin[2] + float(step[2]) * i,
                ]

            elif pattern == 'circular':
                circular_cfg = payload.get('circular', {})
                center = circular_cfg.get('center', [0.0, base_origin[1], 0.0])
                radius = float(circular_cfg.get('radius', 0.0))
                start_deg = float(circular_cfg.get('start_angle_deg', 0.0))
                if 'angle_step_deg' in circular_cfg:
                    step_deg = float(circular_cfg.get('angle_step_deg', 0.0))
                else:
                    sweep = float(circular_cfg.get('sweep_deg', 360.0))
                    step_deg = (sweep / count) if count > 0 else 0.0

                angle = math.radians(start_deg + i * step_deg)
                origin = [
                    float(center[0]) + radius * math.cos(angle),
                    float(center[1]) if len(center) > 1 else base_origin[1],
                    float(center[2]) + radius * math.sin(angle),
                ]

            elif pattern == 'parabolic':
                para_cfg = payload.get('parabolic', {})
                axis = str(para_cfg.get('axis', 'x')).lower()
                x_step = float(para_cfg.get('x_step', para_cfg.get('step', 1.0)))
                a = float(para_cfg.get('a', 0.0))
                b = float(para_cfg.get('b', 0.0))
                c = float(para_cfg.get('c', 0.0))
                t = i * x_step
                p = a * t * t + b * t + c

                if axis == 'y':
                    origin = [base_origin[0] + p, base_origin[1] + t, base_origin[2]]
                else:
                    origin = [base_origin[0] + t, base_origin[1] + p, base_origin[2]]
            else:
                raise ValueError(f"Unsupported loop pattern: {pattern}")

            inst_params = dict(tool_params)
            inst_params['origin'] = origin
            tool = make_tool(tool_type, inst_params)

            if action == 'cut':
                result = result.cut(tool)
            elif action == 'union':
                if len(result.objects) == 0:
                    result = tool
                else:
                    result = result.union(tool)
            elif action == 'intersect':
                result = result.intersect(tool)
            else:
                raise ValueError(f"Unsupported loop action: {action}")

        return result

    # Modifiers
    elif op_type == 'fillet_edges':
        radius = float(params.get('radius', 1.0))
        selector = params.get('selector', '')
        if selector:
            return model.edges(selector).fillet(radius)
        return model.edges().fillet(radius)

    elif op_type == 'chamfer_edges':
        length = float(params.get('length', 1.0))
        selector = params.get('selector', '')
        if selector:
            return model.edges(selector).chamfer(length)
        return model.edges().chamfer(length)

    raise ValueError(f"Unsupported op_type: {op_type}")

def main():
    try:
        p = json.loads(sys.argv[1])
        step_in = p.get('step_in')
        step_out = p['step_out']
        
        # Load existing model if provided (and file exists and size > 0)
        import os
        if step_in and os.path.exists(step_in) and os.path.getsize(step_in) > 0:
            model = cq.importers.importStep(step_in)
        else:
            model = cq.Workplane("XZ")
            
        sequence = p.get('sequence')
        if sequence is None:
            sequence = [{
                'type': p['type'],
                'params': p.get('params', {}),
                'tool': p.get('tool', {}),
            }]
        if not isinstance(sequence, list) or len(sequence) == 0:
            raise ValueError('Expected non-empty operation sequence.')

        result = model
        for op in sequence:
            result = _apply_op(result, op)
            
        # Export
        if len(result.objects) == 0:
            raise ValueError("Operation resulted in an empty shape.")
            
        cq.exporters.export(result, step_out)
        print("SUCCESS")
        
    except Exception as e:
        print(f"ERROR: {str(e)}\\n{traceback.format_exc()}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
"""

class BRepEngineError(Exception):
    pass

class BRepEngine:
    def __init__(self, timeout: int = 45):
        self.timeout = timeout
        config.STEP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.per_step_export = bool(getattr(config, 'BREP_PER_STEP_EXPORT', False))

    def execute_sequence(self, operations: List[Dict[str, Any]], start_step_path: str = None) -> List[Dict[str, Any]]:
        """
        Executes a sequence of B-Rep operations iteratively.
        Returns a list of outputs, tracking the step file for each state.
        Throws BRepEngineError if a step fails.
        """
        logger.info(f"Starting execution of {len(operations)} B-Rep operations.")

        if not self.per_step_export:
            return self._execute_sequence_batched(operations, start_step_path)
        
        current_step_path = start_step_path
        history = []
        
        for idx, op in enumerate(operations):
            op_id = op.get('step_id', idx + 1)
            op_type = op.get('type')
            logger.info(f"Executing step {op_id}: {op_type}")
            
            out_filename = f"brep_gen_{uuid.uuid4().hex[:8]}.step"
            out_path = config.STEP_OUTPUT_DIR / out_filename
            
            try:
                self._run_isolated_op(op, current_step_path, str(out_path))
                current_step_path = str(out_path)
                
                # Analyze Bounding Box as a quick sanity check
                bbox = self._get_bounding_box(current_step_path)
                
                history.append({
                    'step_id': op_id,
                    'status': 'success',
                    'step_file': current_step_path,
                    'step_url': f'/outputs/step/{out_filename}',
                    'bounding_box': bbox,
                    'operation': op
                })
            except Exception as e:
                logger.error(f"Step {op_id} failed: {str(e)}")
                history.append({
                    'step_id': op_id,
                    'status': 'error',
                    'error': str(e),
                    'operation': op
                })
                raise BRepEngineError(f"Step {op_id} failed: {str(e)}")
                
        return history

    def _execute_sequence_batched(self, operations: List[Dict[str, Any]], start_step_path: str = None) -> List[Dict[str, Any]]:
        """
        Fast path: run the full operation sequence inside a single isolated worker
        process and export STEP exactly once.
        """
        if not operations:
            return []

        out_filename = f"brep_gen_{uuid.uuid4().hex[:8]}.step"
        out_path = config.STEP_OUTPUT_DIR / out_filename

        logger.info(
            f"Executing batched sequence in one worker ({len(operations)} ops, single STEP export)."
        )
        self._run_isolated_batch(operations, start_step_path, str(out_path))

        bbox = self._get_bounding_box(str(out_path))
        final_step_path = str(out_path)
        final_step_url = f'/outputs/step/{out_filename}'

        history = []
        for idx, op in enumerate(operations):
            op_id = op.get('step_id', idx + 1)
            history.append({
                'step_id': op_id,
                'status': 'success',
                'step_file': final_step_path,
                'step_url': final_step_url,
                'bounding_box': bbox if idx == (len(operations) - 1) else {},
                'operation': op,
            })

        return history

    def _run_isolated_op(self, op: dict, step_in: str, step_out: str):
        params = {
            'type': op.get('type'),
            'params': op.get('params', {}),
            'tool': op.get('tool', {}),
            'step_in': step_in,
            'step_out': step_out
        }
        
        params_json = json.dumps(params)
        
        # Use python 3.12 global because CadQuery is there
        python_exe = "C:/Users/Ashfaq Ahamed A/AppData/Local/Programs/Python/Python312/python.exe"
        if not os.path.exists(python_exe):
            python_exe = sys.executable

        try:
            proc = subprocess.run(
                [python_exe, '-c', _BREP_WORKER_SCRIPT, params_json],
                timeout=self.timeout,
                capture_output=True,
                text=True
            )
        except subprocess.TimeoutExpired:
            raise BRepEngineError(f"Operation timed out after {self.timeout}s.")
            
        if proc.returncode != 0 and 'SUCCESS' not in proc.stdout:
            stderr = proc.stderr.strip()
            if not stderr:
                stderr = proc.stdout.strip()
            raise BRepEngineError(f"OCC Crash/Error: {stderr}")

        if not os.path.exists(step_out) or os.path.getsize(step_out) == 0:
            raise BRepEngineError("Subprocess succeeded but output STEP is missing or empty.")

    def _run_isolated_batch(self, operations: List[Dict[str, Any]], step_in: str, step_out: str):
        params = {
            'sequence': operations,
            'step_in': step_in,
            'step_out': step_out,
        }

        params_json = json.dumps(params)

        python_exe = "C:/Users/Ashfaq Ahamed A/AppData/Local/Programs/Python/Python312/python.exe"
        if not os.path.exists(python_exe):
            python_exe = sys.executable

        try:
            proc = subprocess.run(
                [python_exe, '-c', _BREP_WORKER_SCRIPT, params_json],
                timeout=self.timeout,
                capture_output=True,
                text=True
            )
        except subprocess.TimeoutExpired:
            raise BRepEngineError(f"Batched operation timed out after {self.timeout}s.")

        if proc.returncode != 0 and 'SUCCESS' not in proc.stdout:
            stderr = proc.stderr.strip() or proc.stdout.strip()
            raise BRepEngineError(f"OCC Crash/Error (batched): {stderr}")

        if not os.path.exists(step_out) or os.path.getsize(step_out) == 0:
            raise BRepEngineError("Batched subprocess succeeded but output STEP is missing or empty.")

    def _get_bounding_box(self, step_path: str) -> dict:
        import cadquery as cq
        try:
            model = cq.importers.importStep(step_path)
            bb = model.val().BoundingBox()
            return {
                'x_len': round(float(bb.xlen), 3),
                'y_len': round(float(bb.ylen), 3),
                'z_len': round(float(bb.zlen), 3)
            }
        except:
            return {}
