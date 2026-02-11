import subprocess
import sys
from pathlib import Path
from typing import Optional
import time
import os


class FreeCADInstanceGenerator:
    
    def __init__(self, freecad_path: Optional[str] = None):
        self.freecad_path = freecad_path or self.find_freecad()
        self.process = None
        
    def find_freecad(self) -> Optional[str]:
        common_paths = [
            r"C:\Program Files\FreeCAD 0.21\bin\FreeCAD.exe",
            r"C:\Program Files\FreeCAD 0.22\bin\FreeCAD.exe",
            r"C:\Program Files\FreeCAD\bin\FreeCAD.exe",
            r"C:\Program Files (x86)\FreeCAD\bin\FreeCAD.exe",
            "/usr/bin/freecad",
            "/usr/local/bin/freecad",
            "/Applications/FreeCAD.app/Contents/MacOS/FreeCAD"
        ]
        
        for path in common_paths:
            if Path(path).exists():
                return path
                
        return None
        
    def open_step_file(self, step_file_path: str, async_mode: bool = True) -> bool:
        
        step_path = Path(step_file_path)
        
        if not step_path.exists():
            raise FileNotFoundError(f"STEP file not found: {step_file_path}")
            
        if not self.freecad_path:
            raise RuntimeError(
                "FreeCAD executable not found. Please install FreeCAD or specify the path."
            )
            
        if not Path(self.freecad_path).exists():
            raise RuntimeError(f"FreeCAD executable not found at: {self.freecad_path}")
            
        try:
            if async_mode:
                self.process = subprocess.Popen(
                    [self.freecad_path, str(step_path)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
                )
                time.sleep(1)
                if self.process.poll() is not None:
                    stdout, stderr = self.process.communicate()
                    raise RuntimeError(f"FreeCAD failed to start: {stderr.decode()}")
                return True
            else:
                result = subprocess.run(
                    [self.freecad_path, str(step_path)],
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    raise RuntimeError(f"FreeCAD exited with error: {result.stderr}")
                return True
                
        except Exception as e:
            raise RuntimeError(f"Failed to open FreeCAD: {str(e)}")
            
    def reload_step_file(self, step_file_path: str) -> bool:
        
        if self.process and self.process.poll() is None:
            self.close()
            time.sleep(0.5)
            
        return self.open_step_file(step_file_path)
        
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None
        
    def close(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()


def open_in_freecad(step_file_path: str, freecad_path: Optional[str] = None) -> bool:
    
    instance = FreeCADInstanceGenerator(freecad_path)
    return instance.open_step_file(step_file_path, async_mode=True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python freecad_instance_generator.py <step_file_path> [freecad_exe_path]")
        sys.exit(1)
        
    step_file = sys.argv[1]
    freecad_exe = sys.argv[2] if len(sys.argv) > 2 else None
    
    try:
        instance = FreeCADInstanceGenerator(freecad_exe)
        print(f"Opening {step_file} in FreeCAD...")
        instance.open_step_file(step_file, async_mode=False)
        print("FreeCAD opened successfully")
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)
