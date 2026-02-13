"""
FreeCAD Viewer Service 

Provides a high-level interface for opening and managing STEP files in FreeCAD GUI.
This service wraps the FreeCADInstanceGenerator for easier use in the API and CLI.
"""

from pathlib import Path
from typing import Optional, Dict, Any
import logging

from services.freecad_instance_generator import FreeCADInstanceGenerator


class FreeCADViewerService:
    """Service for opening and viewing STEP files in FreeCAD."""
    
    def __init__(self, freecad_path: Optional[str] = None, logger: Optional[logging.Logger] = None):
        """
        Initialize the FreeCAD viewer service.
        
        Args:
            freecad_path: Optional custom path to FreeCAD executable
            logger: Optional logger instance
        """
        self.freecad_instance = FreeCADInstanceGenerator(freecad_path)
        self.logger = logger or logging.getLogger(__name__)
        
    def is_freecad_available(self) -> bool:
        """
        Check if FreeCAD is available on the system.
        
        Returns:
            True if FreeCAD is found, False otherwise
        """
        return self.freecad_instance.freecad_path is not None
        
    def get_freecad_path(self) -> Optional[str]:
        """
        Get the path to the FreeCAD executable.
        
        Returns:
            Path to FreeCAD executable, or None if not found
        """
        return self.freecad_instance.freecad_path
        
    def open_step_file(self, step_file_path: str, async_mode: bool = True) -> Dict[str, Any]:
        """
        Open a STEP file in FreeCAD GUI.
        
        Args:
            step_file_path: Path to the STEP file
            async_mode: If True, opens FreeCAD in background. If False, waits for FreeCAD to close.
            
        Returns:
            Dictionary with status and details
            
        Raises:
            FileNotFoundError: If STEP file doesn't exist
            RuntimeError: If FreeCAD is not installed or fails to start
        """
        step_path = Path(step_file_path)
        
        # Validate file exists
        if not step_path.exists():
            error_msg = f"STEP file not found: {step_file_path}"
            self.logger.error(error_msg)
            raise FileNotFoundError(error_msg)
            
        # Check FreeCAD availability
        if not self.is_freecad_available():
            error_msg = "FreeCAD executable not found. Please install FreeCAD or specify the path."
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)
            
        try:
            self.logger.info(f"Opening STEP file in FreeCAD: {step_file_path}")
            success = self.freecad_instance.open_step_file(str(step_path), async_mode=async_mode)
            
            if success:
                self.logger.info("FreeCAD opened successfully")
                return {
                    'success': True,
                    'message': 'STEP file opened in FreeCAD',
                    'step_file': str(step_path),
                    'freecad_path': self.freecad_instance.freecad_path,
                    'async_mode': async_mode
                }
            else:
                error_msg = "Failed to open FreeCAD (unknown error)"
                self.logger.error(error_msg)
                raise RuntimeError(error_msg)
                
        except Exception as e:
            self.logger.error(f"Error opening FreeCAD: {str(e)}")
            raise
            
    def reload_step_file(self, step_file_path: str) -> Dict[str, Any]:
        """
        Reload a STEP file in FreeCAD (closes existing instance and opens new one).
        
        Args:
            step_file_path: Path to the STEP file
            
        Returns:
            Dictionary with status and details
            
        Raises:
            FileNotFoundError: If STEP file doesn't exist
            RuntimeError: If FreeCAD is not installed or fails to start
        """
        step_path = Path(step_file_path)
        
        # Validate file exists
        if not step_path.exists():
            error_msg = f"STEP file not found: {step_file_path}"
            self.logger.error(error_msg)
            raise FileNotFoundError(error_msg)
            
        # Check FreeCAD availability
        if not self.is_freecad_available():
            error_msg = "FreeCAD executable not found. Please install FreeCAD or specify the path."
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)
            
        try:
            self.logger.info(f"Reloading STEP file in FreeCAD: {step_file_path}")
            success = self.freecad_instance.reload_step_file(str(step_path))
            
            if success:
                self.logger.info("FreeCAD reloaded successfully")
                return {
                    'success': True,
                    'message': 'STEP file reloaded in FreeCAD',
                    'step_file': str(step_path),
                    'freecad_path': self.freecad_instance.freecad_path
                }
            else:
                error_msg = "Failed to reload FreeCAD (unknown error)"
                self.logger.error(error_msg)
                raise RuntimeError(error_msg)
                
        except Exception as e:
            self.logger.error(f"Error reloading FreeCAD: {str(e)}")
            raise
            
    def is_running(self) -> bool:
        """
        Check if FreeCAD process is currently running.
        
        Returns:
            True if FreeCAD process is active, False otherwise
        """
        return self.freecad_instance.is_running()
        
    def close(self) -> None:
        """
        Close the FreeCAD instance if it's running.
        """
        if self.is_running():
            self.logger.info("Closing FreeCAD instance")
            self.freecad_instance.close()
        else:
            self.logger.debug("No FreeCAD instance to close")
            
    def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of the FreeCAD viewer service.
        
        Returns:
            Dictionary with service status information
        """
        return {
            'freecad_available': self.is_freecad_available(),
            'freecad_path': self.get_freecad_path(),
            'freecad_running': self.is_running(),
            'service': 'FreeCADViewerService'
        }


# Convenience function for quick use
def open_step_in_freecad(step_file_path: str, freecad_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Convenience function to quickly open a STEP file in FreeCAD.
    
    Args:
        step_file_path: Path to the STEP file
        freecad_path: Optional custom path to FreeCAD executable
        
    Returns:
        Dictionary with status and details
    """
    service = FreeCADViewerService(freecad_path)
    return service.open_step_file(step_file_path, async_mode=True)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python freecad_viewer_service.py <step_file_path> [freecad_exe_path]")
        sys.exit(1)
        
    step_file = sys.argv[1]
    freecad_exe = sys.argv[2] if len(sys.argv) > 2 else None
    
    try:
        service = FreeCADViewerService(freecad_exe)
        
        # Check status
        status = service.get_status()
        print(f"FreeCAD Available: {status['freecad_available']}")
        print(f"FreeCAD Path: {status['freecad_path']}")
        print()
        
        # Open file
        result = service.open_step_file(step_file, async_mode=False)
        print(f"Success: {result['success']}")
        print(f"Message: {result['message']}")
        
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)
