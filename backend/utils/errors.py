from enum import Enum
from typing import Optional, Dict


class ErrorCode(Enum):
    PROMPT_VALIDATION_FAILED = "PROMPT_001"
    JSON_VALIDATION_FAILED = "JSON_001"
    JSON_GENERATION_FAILED = "JSON_002"
    CODEGEN_FAILED = "CODEGEN_001"
    EXECUTION_FAILED = "EXEC_001"
    EXECUTION_TIMEOUT = "EXEC_002"
    STEP_EXPORT_FAILED = "STEP_001"
    PARAMETER_UPDATE_FAILED = "PARAM_001"
    FILE_NOT_FOUND = "FILE_001"
    INVALID_INPUT = "INPUT_001"
    TEMPLATE_NOT_FOUND = "TEMPLATE_001"
    FREECAD_CONNECTION_FAILED = "FREECAD_001"


class SynthoCadError(Exception):
    
    def __init__(self, code: ErrorCode, message: str, details: Optional[Dict] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(self.message)
        
    def to_dict(self) -> Dict:
        return {
            'error': True,
            'code': self.code.value,
            'message': self.message,
            'details': self.details
        }


class PromptValidationError(SynthoCadError):
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(ErrorCode.PROMPT_VALIDATION_FAILED, message, details)


class JSONValidationError(SynthoCadError):
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(ErrorCode.JSON_VALIDATION_FAILED, message, details)


class CodeGenerationError(SynthoCadError):
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(ErrorCode.CODEGEN_FAILED, message, details)


class ExecutionError(SynthoCadError):
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(ErrorCode.EXECUTION_FAILED, message, details)


class ParameterUpdateError(SynthoCadError):
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(ErrorCode.PARAMETER_UPDATE_FAILED, message, details)
