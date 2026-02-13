"""
File Cleanup Service

Automatically manages and cleans up old generated files to prevent disk space issues.
Provides both automatic cleanup based on age/size and manual cleanup options.
"""

import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging


class FileCleanupService:
    """Service for cleaning up old generated files."""
    
    def __init__(
        self, 
        output_dirs: Dict[str, Path],
        max_age_days: int = 30,
        max_files_per_type: int = 100,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize the cleanup service.
        
        Args:
            output_dirs: Dictionary mapping file types to their output directories
                        e.g., {'py': Path, 'step': Path, 'json': Path}
            max_age_days: Maximum age of files in days before cleanup
            max_files_per_type: Maximum number of files to keep per type
            logger: Optional logger instance
        """
        self.output_dirs = output_dirs
        self.max_age_days = max_age_days
        self.max_files_per_type = max_files_per_type
        self.logger = logger or logging.getLogger(__name__)
        
    def get_file_age_days(self, file_path: Path) -> float:
        """
        Get the age of a file in days.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Age in days
        """
        file_age_seconds = time.time() - file_path.stat().st_mtime
        return file_age_seconds / 86400  # Convert to days
        
    def scan_directory(self, directory: Path, pattern: str = "*") -> List[Tuple[Path, float]]:
        """
        Scan directory and return files with their ages.
        
        Args:
            directory: Directory to scan
            pattern: Glob pattern for files (default: "*")
            
        Returns:
            List of (file_path, age_in_days) tuples, sorted by age (oldest first)
        """
        if not directory.exists():
            return []
            
        files_with_age = []
        for file_path in directory.glob(pattern):
            if file_path.is_file():
                age = self.get_file_age_days(file_path)
                files_with_age.append((file_path, age))
                
        # Sort by age, oldest first
        files_with_age.sort(key=lambda x: x[1], reverse=True)
        return files_with_age
        
    def cleanup_by_age(
        self, 
        directory: Path, 
        max_age_days: Optional[int] = None,
        pattern: str = "*",
        dry_run: bool = False
    ) -> Dict[str, any]:
        """
        Clean up files older than specified age.
        
        Args:
            directory: Directory to clean
            max_age_days: Maximum age in days (uses instance default if None)
            pattern: Glob pattern for files
            dry_run: If True, only report what would be deleted
            
        Returns:
            Dictionary with cleanup statistics
        """
        max_age = max_age_days or self.max_age_days
        files_with_age = self.scan_directory(directory, pattern)
        
        deleted_files = []
        deleted_size = 0
        
        for file_path, age in files_with_age:
            if age > max_age:
                file_size = file_path.stat().st_size
                
                if not dry_run:
                    try:
                        file_path.unlink()
                        self.logger.info(f"Deleted old file: {file_path.name} (age: {age:.1f} days)")
                        deleted_files.append(str(file_path))
                        deleted_size += file_size
                    except Exception as e:
                        self.logger.error(f"Failed to delete {file_path.name}: {str(e)}")
                else:
                    self.logger.info(f"Would delete: {file_path.name} (age: {age:.1f} days)")
                    deleted_files.append(str(file_path))
                    deleted_size += file_size
                    
        return {
            'deleted_count': len(deleted_files),
            'deleted_size_bytes': deleted_size,
            'deleted_size_mb': round(deleted_size / (1024 * 1024), 2),
            'deleted_files': deleted_files,
            'dry_run': dry_run
        }
        
    def cleanup_by_count(
        self, 
        directory: Path,
        max_files: Optional[int] = None,
        pattern: str = "*",
        dry_run: bool = False
    ) -> Dict[str, any]:
        """
        Clean up oldest files to keep only max_files most recent.
        
        Args:
            directory: Directory to clean
            max_files: Maximum number of files to keep (uses instance default if None)
            pattern: Glob pattern for files
            dry_run: If True, only report what would be deleted
            
        Returns:
            Dictionary with cleanup statistics
        """
        max_count = max_files or self.max_files_per_type
        files_with_age = self.scan_directory(directory, pattern)
        
        if len(files_with_age) <= max_count:
            return {
                'deleted_count': 0,
                'deleted_size_bytes': 0,
                'deleted_size_mb': 0,
                'deleted_files': [],
                'message': f'File count ({len(files_with_age)}) within limit ({max_count})',
                'dry_run': dry_run
            }
            
        # Delete oldest files beyond the limit
        files_to_delete = files_with_age[max_count:]
        deleted_files = []
        deleted_size = 0
        
        for file_path, age in files_to_delete:
            file_size = file_path.stat().st_size
            
            if not dry_run:
                try:
                    file_path.unlink()
                    self.logger.info(f"Deleted excess file: {file_path.name}")
                    deleted_files.append(str(file_path))
                    deleted_size += file_size
                except Exception as e:
                    self.logger.error(f"Failed to delete {file_path.name}: {str(e)}")
            else:
                self.logger.info(f"Would delete: {file_path.name}")
                deleted_files.append(str(file_path))
                deleted_size += file_size
                
        return {
            'deleted_count': len(deleted_files),
            'deleted_size_bytes': deleted_size,
            'deleted_size_mb': round(deleted_size / (1024 * 1024), 2),
            'deleted_files': deleted_files,
            'dry_run': dry_run
        }
        
    def cleanup_all(
        self, 
        max_age_days: Optional[int] = None,
        max_files_per_type: Optional[int] = None,
        dry_run: bool = False
    ) -> Dict[str, Dict]:
        """
        Clean up all configured directories.
        
        Args:
            max_age_days: Maximum age in days
            max_files_per_type: Maximum files per type
            dry_run: If True, only report what would be deleted
            
        Returns:
            Dictionary mapping file types to cleanup results
        """
        self.logger.info(f"Starting cleanup (dry_run={dry_run})")
        
        results = {}
        total_deleted = 0
        total_size = 0
        
        for file_type, directory in self.output_dirs.items():
            self.logger.info(f"Cleaning {file_type} directory: {directory}")
            
            # First cleanup by age
            age_result = self.cleanup_by_age(
                directory, 
                max_age_days=max_age_days,
                dry_run=dry_run
            )
            
            # Then cleanup by count (for remaining files)
            count_result = self.cleanup_by_count(
                directory,
                max_files=max_files_per_type,
                dry_run=dry_run
            )
            
            total_deleted += age_result['deleted_count'] + count_result['deleted_count']
            total_size += age_result['deleted_size_bytes'] + count_result['deleted_size_bytes']
            
            results[file_type] = {
                'by_age': age_result,
                'by_count': count_result,
                'total_deleted': age_result['deleted_count'] + count_result['deleted_count']
            }
            
        self.logger.info(f"Cleanup complete: {total_deleted} files, {round(total_size / (1024 * 1024), 2)} MB")
        
        return {
            'results_by_type': results,
            'total_deleted_files': total_deleted,
            'total_deleted_size_mb': round(total_size / (1024 * 1024), 2),
            'dry_run': dry_run
        }
        
    def cleanup_matching_set(
        self, 
        base_name: str,
        dry_run: bool = False
    ) -> Dict[str, any]:
        """
        Clean up a matching set of files (json, py, step) by base name.
        Useful for cleaning up a specific generated model across all file types.
        
        Args:
            base_name: Base name of the files (without extension)
            dry_run: If True, only report what would be deleted
            
        Returns:
            Dictionary with cleanup results
        """
        deleted_files = []
        deleted_size = 0
        
        patterns = {
            'json': f"{base_name}.json",
            'py': [f"{base_name}_generated.py", f"{base_name}.py"],
            'step': f"{base_name}.step"
        }
        
        for file_type, directory in self.output_dirs.items():
            if file_type in patterns:
                pattern_list = patterns[file_type] if isinstance(patterns[file_type], list) else [patterns[file_type]]
                
                for pattern in pattern_list:
                    file_path = directory / pattern
                    if file_path.exists():
                        file_size = file_path.stat().st_size
                        
                        if not dry_run:
                            try:
                                file_path.unlink()
                                self.logger.info(f"Deleted: {file_path}")
                                deleted_files.append(str(file_path))
                                deleted_size += file_size
                            except Exception as e:
                                self.logger.error(f"Failed to delete {file_path}: {str(e)}")
                        else:
                            self.logger.info(f"Would delete: {file_path}")
                            deleted_files.append(str(file_path))
                            deleted_size += file_size
                            
        return {
            'deleted_count': len(deleted_files),
            'deleted_size_bytes': deleted_size,
            'deleted_size_mb': round(deleted_size / (1024 * 1024), 2),
            'deleted_files': deleted_files,
            'dry_run': dry_run
        }
        
    def get_storage_stats(self) -> Dict[str, any]:
        """
        Get storage statistics for all output directories.
        
        Returns:
            Dictionary with storage statistics
        """
        stats = {}
        total_files = 0
        total_size = 0
        
        for file_type, directory in self.output_dirs.items():
            if not directory.exists():
                stats[file_type] = {'file_count': 0, 'total_size_mb': 0, 'directory': str(directory)}
                continue
                
            files = list(directory.glob("*"))
            file_count = len([f for f in files if f.is_file()])
            dir_size = sum(f.stat().st_size for f in files if f.is_file())
            
            stats[file_type] = {
                'file_count': file_count,
                'total_size_bytes': dir_size,
                'total_size_mb': round(dir_size / (1024 * 1024), 2),
                'directory': str(directory),
                'oldest_file_age_days': None,
                'newest_file_age_days': None
            }
            
            # Get age info
            files_with_age = self.scan_directory(directory)
            if files_with_age:
                stats[file_type]['oldest_file_age_days'] = round(files_with_age[0][1], 2)
                stats[file_type]['newest_file_age_days'] = round(files_with_age[-1][1], 2)
                
            total_files += file_count
            total_size += dir_size
            
        return {
            'by_type': stats,
            'total_files': total_files,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'timestamp': datetime.now().isoformat()
        }


if __name__ == "__main__":
    import sys
    sys.path.append(str(Path(__file__).parent.parent))
    from core import config
    
    # Test the cleanup service
    service = FileCleanupService(
        output_dirs={
            'json': config.JSON_OUTPUT_DIR,
            'py': config.PY_OUTPUT_DIR,
            'step': config.STEP_OUTPUT_DIR
        },
        max_age_days=30,
        max_files_per_type=100
    )
    
    # Get stats
    print("=== Storage Statistics ===")
    stats = service.get_storage_stats()
    print(f"Total files: {stats['total_files']}")
    print(f"Total size: {stats['total_size_mb']} MB")
    print()
    
    for file_type, type_stats in stats['by_type'].items():
        print(f"{file_type.upper()}: {type_stats['file_count']} files, {type_stats['total_size_mb']} MB")
        if type_stats['oldest_file_age_days']:
            print(f"  Oldest: {type_stats['oldest_file_age_days']} days")
    
    # Dry run cleanup
    print("\n=== Dry Run Cleanup ===")
    result = service.cleanup_all(dry_run=True)
    print(f"Would delete: {result['total_deleted_files']} files, {result['total_deleted_size_mb']} MB")
