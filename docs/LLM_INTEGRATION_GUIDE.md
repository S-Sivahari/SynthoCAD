# LLM Integration Guide — SynthoCAD Pipeline

**Purpose:** Universal instructions for any LLM (OpenAI, Anthropic, Gemini, Llama, etc.) to integrate with the SynthoCAD pipeline for converting natural language prompts into parametric CAD models.

---

## Integration Overview

The SynthoCAD pipeline provides a complete workflow from natural language → SCL JSON → CadQuery Python → STEP file with parametric editing capabilities. Your LLM integration should focus **only** on Step 2 (prompt → JSON generation).

### Pipeline Architecture

```
User Prompt → [Step 1: Validation] → [Step 2: LLM → JSON] → [Step 3: JSON Validation] 
→ [Step 4: CadQuery Generation] → [Step 5: STEP Export] → [Step 6: Parameter Extraction]
→ [Step 7-9: Parametric Editing Workflow]
```

**Your LLM's Role:** Implement `generate_json_from_prompt()` in `backend/core/main.py` (currently NotImplementedError)

---

## API Integration Point

### Location
File: `backend/core/main.py`  
Class: `SynthoCadPipeline`  
Method: `generate_json_from_prompt(prompt: str) -> Dict[str, Any]`

### Input
- **prompt** (str): Validated user prompt (already passed Step 1 validation)
  - Contains CAD keywords (cylinder, box, hole, etc.)
  - Includes dimensional information
  - Sanitized for security

### Output
Return a complete SCL JSON dictionary conforming to the schema in `core/scl_schema.json`

### Error Handling
- Raise `JSONGenerationError` (from `backend.utils.errors`) if generation fails
- Include error details and suggestions for user correction
- Implement retry logic with error feedback

---

## LLM System Prompt Template

Use this as your system prompt for any LLM:

```
You are a CAD design assistant that converts natural language descriptions into SCL JSON format.

TASK: Generate valid SCL JSON (Schema v3.0) from user CAD design prompts.

RULES:
1. Output ONLY valid JSON - no markdown code blocks, no explanations
2. Always set "units" field (default: "mm" if unspecified)
3. First operation must use "NewBodyFeatureOperation"
4. Use appropriate feature types:
   - "extrude" for prismatic shapes (boxes, cylinders via circle+extrude)
   - "revolve" for rotational symmetry (tubes, shafts)
   - "hole" for fastener holes (not generic cuts)
5. Close all sketch loops properly
6. Add "_comment" fields to document design intent
7. Include "_editable_parameters" list for parametric editing

SCHEMA STRUCTURE:
{
  "final_name": "PartName",
  "units": "mm",
  "coordinate_system": {...},
  "parts": {
    "Body1": {
      "profiles": {...},
      "operations": [...],
      "features": [...]
    }
  },
  "_editable_parameters": ["param1", "param2"]
}

EXAMPLES: Consult templates in templates/ folder for reference patterns:
- templates/basic/cylinder.json, box.json, tube.json
- templates/mechanical/l_bracket.json, flange.json
- templates/patterns/bolt_circle.json, linear_array.json

VALIDATION: Your JSON will be validated against the schema. Ensure:
- All required fields present
- Valid operation types
- Proper coordinate systems
- Closed sketch loops
```

---

## Implementation Examples

### OpenAI (GPT-4)

```python
import openai
from backend.utils.errors import JSONGenerationError

def generate_json_from_prompt(self, prompt: str) -> Dict[str, Any]:
    """Generate SCL JSON using OpenAI GPT-4"""
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},  # Use template above
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,  # Low temperature for consistency
            max_tokens=2000
        )
        
        json_text = response.choices[0].message.content
        json_data = json.loads(json_text)
        
        return json_data
        
    except json.JSONDecodeError as e:
        raise JSONGenerationError(f"LLM returned invalid JSON: {str(e)}")
    except Exception as e:
        raise JSONGenerationError(f"LLM generation failed: {str(e)}")
```

### Anthropic (Claude)

```python
import anthropic
from backend.utils.errors import JSONGenerationError

def generate_json_from_prompt(self, prompt: str) -> Dict[str, Any]:
    """Generate SCL JSON using Anthropic Claude"""
    
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    
    try:
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=2000,
            temperature=0.2,
            system=SYSTEM_PROMPT,  # Use template above
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        json_text = message.content[0].text
        json_data = json.loads(json_text)
        
        return json_data
        
    except json.JSONDecodeError as e:
        raise JSONGenerationError(f"LLM returned invalid JSON: {str(e)}")
    except Exception as e:
        raise JSONGenerationError(f"LLM generation failed: {str(e)}")
```

### Local Llama (via Ollama)

```python
import requests
from backend.utils.errors import JSONGenerationError

def generate_json_from_prompt(self, prompt: str) -> Dict[str, Any]:
    """Generate SCL JSON using local Llama via Ollama"""
    
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3.2",
                "prompt": f"{SYSTEM_PROMPT}\n\nUser prompt: {prompt}",
                "stream": False,
                "temperature": 0.2
            }
        )
        
        json_text = response.json()["response"]
        json_data = json.loads(json_text)
        
        return json_data
        
    except json.JSONDecodeError as e:
        raise JSONGenerationError(f"LLM returned invalid JSON: {str(e)}")
    except Exception as e:
        raise JSONGenerationError(f"LLM generation failed: {str(e)}")
```

---

## Retry Logic with Error Feedback

Implement retry mechanism when JSON validation fails:

```python
def generate_json_from_prompt(self, prompt: str, max_retries: int = 3) -> Dict[str, Any]:
    """Generate SCL JSON with retry on validation errors"""
    
    for attempt in range(max_retries):
        try:
            # Call LLM
            json_data = self._call_llm(prompt, previous_error=None)
            
            # Validate (Step 3 will validate, but we can pre-check)
            self.validate_json(json_data)
            
            return json_data
            
        except JSONValidationError as e:
            if attempt < max_retries - 1:
                # Retry with error feedback
                error_prompt = f"{prompt}\n\nPrevious attempt failed validation: {e.message}\nPlease correct and regenerate."
                json_data = self._call_llm(error_prompt, previous_error=str(e))
            else:
                raise JSONGenerationError(f"Failed after {max_retries} attempts: {str(e)}")
```

---

## Template-Assisted Generation

Load templates to help LLM understand patterns:

```python
def generate_json_from_prompt(self, prompt: str) -> Dict[str, Any]:
    """Generate SCL JSON using template examples"""
    
    # Load relevant template examples
    templates = self._find_relevant_templates(prompt)
    
    # Build enhanced system prompt
    enhanced_prompt = f"""
    {SYSTEM_PROMPT}
    
    RELEVANT EXAMPLES:
    {json.dumps(templates, indent=2)}
    
    USER REQUEST: {prompt}
    
    Generate SCL JSON similar to the examples above, adapted for the user's request.
    """
    
    # Call LLM with examples
    json_data = self._call_llm(enhanced_prompt)
    
    return json_data

def _find_relevant_templates(self, prompt: str) -> List[Dict]:
    """Find templates matching prompt keywords"""
    
    templates = []
    prompt_lower = prompt.lower()
    
    if 'cylinder' in prompt_lower or 'tube' in prompt_lower or 'pipe' in prompt_lower:
        with open('templates/basic/cylinder.json') as f:
            templates.append(json.load(f))
    
    if 'box' in prompt_lower or 'block' in prompt_lower or 'plate' in prompt_lower:
        with open('templates/basic/box.json') as f:
            templates.append(json.load(f))
    
    if 'bracket' in prompt_lower:
        with open('templates/mechanical/l_bracket.json') as f:
            templates.append(json.load(f))
    
    if 'flange' in prompt_lower or 'bolt circle' in prompt_lower:
        with open('templates/mechanical/flange.json') as f:
            templates.append(json.load(f))
    
    return templates
```

---

## Configuration

Add LLM configuration to `backend/core/config.py`:

```python
# LLM Configuration
LLM_PROVIDER = os.getenv('LLM_PROVIDER', 'openai')  # openai, anthropic, ollama, gemini
LLM_MODEL = os.getenv('LLM_MODEL', 'gpt-4')
LLM_API_KEY = os.getenv('LLM_API_KEY', '')
LLM_TEMPERATURE = float(os.getenv('LLM_TEMPERATURE', '0.2'))
LLM_MAX_TOKENS = int(os.getenv('LLM_MAX_TOKENS', '2000'))
LLM_MAX_RETRIES = int(os.getenv('LLM_MAX_RETRIES', '3'))
```

Create `.env` file:
```bash
LLM_PROVIDER=openai
LLM_MODEL=gpt-4
LLM_API_KEY=sk-...
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=2000
```

---

## Testing Your Integration

Test the complete pipeline with your LLM:

```python
from backend.core.main import SynthoCadPipeline

pipeline = SynthoCadPipeline()

# Test prompt → JSON generation
prompt = "Create a cylinder with 10mm radius and 20mm height"
json_data = pipeline.generate_json_from_prompt(prompt)

# Test complete workflow
result = pipeline.process_from_prompt(
    prompt=prompt,
    output_name="test_cylinder",
    open_freecad=False
)

print(f"Generated: {result['step_file']}")
print(f"Parameters: {result['parameters']['total_count']}")
```

---

## Best Practices

1. **Low Temperature:** Use 0.1-0.3 for consistency in JSON generation
2. **Token Limits:** 1500-2000 tokens usually sufficient for most CAD models
3. **Prompt Engineering:** Include dimensional units in system prompt
4. **Template Context:** Provide 1-3 relevant template examples
5. **Error Recovery:** Implement retry logic with specific error feedback
6. **Validation:** Always validate LLM output before returning
7. **Logging:** Log all LLM calls for debugging and cost tracking
8. **Streaming:** Disable streaming for JSON generation (need complete response)
9. **Safety:** Sanitize LLM output before JSON parsing
10. **Fallbacks:** Have default templates for common shapes if LLM fails

---

## Common Issues & Solutions

### Issue: LLM returns markdown code blocks
```python
# Solution: Strip markdown
json_text = response.strip()
if json_text.startswith('```'):
    json_text = json_text.split('```')[1]
    if json_text.startswith('json'):
        json_text = json_text[4:]
json_data = json.loads(json_text.strip())
```

### Issue: LLM includes explanatory text
```python
# Solution: Extract JSON block
import re
json_match = re.search(r'\{.*\}', response, re.DOTALL)
if json_match:
    json_data = json.loads(json_match.group())
```

### Issue: Schema validation failures
```python
# Solution: Add schema examples to system prompt
# Provide templates/basic/cylinder.json as reference
# Use retry with specific validation error feedback
```

---

## Support & Documentation

- **SCL Schema:** `core/scl_schema.json`
- **Templates:** `templates/` folder (basic, mechanical, patterns)
- **Error Classes:** `backend/utils/errors.py`
- **Pipeline Code:** `backend/core/main.py`
- **API Routes:** `backend/api/routes/generation_routes.py`

---

## Quick Start Checklist

- [ ] Choose LLM provider (OpenAI, Anthropic, Ollama, etc.)
- [ ] Install provider SDK (`pip install openai` or `anthropic`)
- [ ] Set API key in environment variable
- [ ] Copy system prompt template from this guide
- [ ] Implement `generate_json_from_prompt()` method
- [ ] Add retry logic with error feedback
- [ ] Load relevant templates for context
- [ ] Test with simple prompts (cylinder, box)
- [ ] Test with complex prompts ( brackets, flanges)
- [ ] Validate error handling and edge cases
