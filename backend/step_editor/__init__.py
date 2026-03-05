"""SynthoCAD STEP Editor Module.

Provides functionality to analyze, render, and edit existing STEP files
using Geometric Decompilation + LLM Synthesis.
"""

from . import step_analyzer
from . import step_renderer
from . import edit_pipeline
from . import geometric_interpreter
from . import shape_recognizer
from .shape_recognizer import ShapeRecognizer
