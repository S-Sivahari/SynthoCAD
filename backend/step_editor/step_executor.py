import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, List

import cadquery as cq
from OCP.BRepAlgoAPI import BRepAlgoAPI_Defeaturing
from OCP.TopTools import TopTools_ListOfShape
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.gp import gp_Vec

from step_editor import step_analyzer
from core import config

logger = logging.getLogger(__name__)


def _get_action_from_llm(prompt: str, features: dict) -> list:
    import sys
    sys.path.append(str(Path(__file__).parent.parent))
    from services.gemini_service import call_gemini

    context_str = json.dumps(features, indent=2)

    system_prompt = f"""
    You are a CAD editing assistant mapping user text directly to a geometric operation.
    Given this dictionary of existing geometric features in the model:
    {context_str}
    
    And the user's edit prompt:
    "{prompt}"
    
    Return a strictly formatted JSON array of action objects. Support multiple faces if asked!
    Supported actions:
    
    1. Resize a Hole/Cylinder:
    {{"action": "resize_hole", "face_id": "f5", "new_radius": 15.0}}
    
    2. Defeature (Delete a feature entirely):
    {{"action": "defeature", "face_id": "f12"}}
    
    3. Extrude / Move a Planar Face (to change block dimensions, etc.):
    {{"action": "extrude_face", "face_id": "f4", "distance": 5.0}}
    (Positive distance pushes outward adding volume. Negative distance pushes inward cutting volume.)
    
    If the user mentions multiple faces, return a list of JSON objects! 
    Output exactly the raw JSON array (or object). Do not output markdown, no conversational text.
    """
    
    try:
        response_text = call_gemini(system_prompt)
        
        json_str = response_text
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]
            
        json_str = json_str.strip()
        
        try:
            parsed = json.loads(json_str)
            return parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError:
            # Fallback search for list or dict
            start = response_text.find('[')
            end = response_text.rfind(']')
            if start != -1 and end != -1:
                return json.loads(response_text[start:end+1])
            start = response_text.find('{')
            end = response_text.rfind('}')
            if start != -1 and end != -1:
                return [json.loads(response_text[start:end+1])]
            raise ValueError("No JSON array/object found.")
            
    except Exception as e:
        logger.error(f"Failed to get action from LLM: {e}")
        raise ValueError(f"Failed to interpret edit prompt using LLM: {e}")


def execute_edit_from_prompt(step_path: str, prompt: str) -> Dict[str, Any]:
    features = step_analyzer.analyze(step_path)
    
    # Prune features slightly to save tokens, but add bounding_box!
    simplified_features = {
        "bounding_box": features.get("bounding_box", {}),
        "cylinders": features.get("cylinders", []),
        "planes": features.get("planes", []),
        "summary": features.get("summary", "")
    }
    
    commands = _get_action_from_llm(prompt, simplified_features)
    logger.info(f"LLM determined actions: {commands}")
    
    return execute_action(step_path, commands, features)


def execute_action(step_path: str, commands: List[dict], original_features: dict) -> Dict[str, Any]:
    try:
        model = cq.importers.importStep(step_path)
    except Exception as e:
        raise ValueError(f"Failed to load STEP for editing: {e}")
    
    # We must fetch the original faces before modifying the topology!
    faces = model.faces().vals()
    
    base_solid = cq.Workplane(cq.Solid(model.val().wrapped))
    
    # Keep track of what we are operating on 
    # (If we defeature, we mutate base_solid and must rely on the returned shape)
    current_model = base_solid
    
    for command in commands:
        action = command.get("action")
        face_id = command.get("face_id", "")
        
        try:
            idx = int(face_id.replace("f", ""))
        except ValueError:
            raise ValueError(f"Invalid face_id format: {face_id}")
        
        if idx < 0 or idx >= len(faces):
            raise ValueError(f"Face ID {idx} out of bounds.")
        
        # Original face geometry (valid for extrusion direction/profile)
        target_face = faces[idx]
        
        # Handle Extrude directly (no defeaturing needed)
        if action == "extrude_face":
            distance = float(command.get("distance", 0))
            if distance == 0:
                continue
                
            try:
                cq_face = cq.Face(target_face.wrapped)
                norm = cq_face.normalAt()
                vec = gp_Vec(norm.x * distance, norm.y * distance, norm.z * distance)
                
                prism_api = BRepPrimAPI_MakePrism(cq_face.wrapped, vec)
                if not prism_api.IsDone():
                    raise ValueError("Failed to construct prism from face.")
                    
                extruded_solid = cq.Solid(prism_api.Shape())
                wp_tool = cq.Workplane(extruded_solid)
                
                if distance > 0:
                    current_model = current_model.union(wp_tool)
                else:
                    current_model = current_model.cut(wp_tool)
                    
            except Exception as e:
                logger.error(f"Face extrude failed: {e}")
                raise ValueError(f"Failed to extrude face {face_id}. Overlapping topology issues?")
                
        else:
            # Defeature based actions
            try:
                # Warning: Defeaturing sequential faces requires them to exist in current_model.
                # If topology changed extensively, target_face might not map anymore. 
                # (For completely isolated holes, it usually handles fine).
                shape_to_remove = target_face.wrapped
                remove_list = TopTools_ListOfShape()
                remove_list.Append(shape_to_remove)
                
                solid = current_model.val().wrapped
                
                api = BRepAlgoAPI_Defeaturing()
                api.SetShape(solid)
                api.AddFacesToRemove(remove_list)
                api.SetRunParallel(True)
                api.Build()
                
                if not api.IsDone():
                    raise ValueError("OpenCASCADE Defeaturing API failed. Geometry might be too complex.")
                
                healed_solid = api.Shape()
            except Exception as e:
                logger.error(f"Defeaturing failed on face {face_id}: {e}")
                raise ValueError(f"Could not remove face {face_id}. It may be modified or intersecting.")
            
            healed_model = cq.Workplane(cq.Solid(healed_solid))
            current_model = healed_model
            
            if action == "defeature":
                pass
                
            elif action == "resize_hole":
                new_radius = float(command.get("new_radius", 0))
                if new_radius <= 0:
                    raise ValueError("Invalid new_radius for resize_hole.")
                
                cyl_data = next((c for c in original_features.get("cylinders", []) if c["id"] == face_id), None)
                if not cyl_data:
                    raise ValueError(f"Could not find face {face_id} in cylinder features.")
                
                loc = cyl_data["location"]
                axis = cyl_data["axis"]
                
                vec_axis = cq.Vector(*axis)
                pnt_loc = cq.Vector(*loc)
                
                cut_tool = cq.Workplane(cq.Plane(origin=pnt_loc, normal=vec_axis)).circle(new_radius).extrude(1000, both=True)
                
                try:
                    current_model = current_model.cut(cut_tool)
                except Exception as e:
                    raise ValueError(f"Failed to cut new hole: {e}")
                    
            else:
                raise ValueError(f"Unsupported action: {action}")
    
    import uuid
    out_filename = f"edited_{uuid.uuid4().hex[:8]}.step"
    out_path = config.STEP_OUTPUT_DIR / out_filename
    config.STEP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # We export the accumulated multi-edit model
    cq.exporters.export(current_model, str(out_path))
    logger.info(f"Successfully edited model and saved to {out_path}")
    
    return {
        "status": "success",
        "step_file": str(out_path)
    }

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python step_executor.py <file.step> <prompt>")
        sys.exit(1)
    res = execute_edit_from_prompt(sys.argv[1], sys.argv[2])
    print(res)
