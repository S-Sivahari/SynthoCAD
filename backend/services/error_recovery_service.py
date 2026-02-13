"""
Error Recovery and Retry Service

Provides robust retry logic with exponential backoff for LLM calls and other operations.
Handles transient failures, rate limits, and provides fallback strategies.
"""

import time
import logging
from typing import Callable, Any, Optional, List, Dict, Tuple
from functools import wraps
from datetime import datetime
import traceback


class RetryConfig:
    """Configuration for retry behavior."""
    
    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        """
        Initialize retry configuration.
        
        Args:
            max_attempts: Maximum number of retry attempts
            initial_delay: Initial delay in seconds before first retry
            max_delay: Maximum delay in seconds between retries
            exponential_base: Base for exponential backoff (delay = initial * base^attempt)
            jitter: Add random jitter to prevent thundering herd
        """
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter


class RetryableError(Exception):
    """Base class for errors that should trigger a retry."""
    pass


class NonRetryableError(Exception):
    """Base class for errors that should NOT trigger a retry."""
    pass


class ErrorRecoveryService:
    """Service for handling errors and retries."""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize the error recovery service.
        
        Args:
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self.retry_history: List[Dict] = []
        
    def calculate_delay(
        self, 
        attempt: int, 
        config: RetryConfig
    ) -> float:
        """
        Calculate delay before next retry using exponential backoff.
        
        Args:
            attempt: Current attempt number (0-indexed)
            config: Retry configuration
            
        Returns:
            Delay in seconds
        """
        delay = config.initial_delay * (config.exponential_base ** attempt)
        delay = min(delay, config.max_delay)
        
        if config.jitter:
            import random
            delay = delay * (0.5 + random.random())  # Add ±50% jitter
            
        return delay
        
    def is_retryable_error(self, error: Exception) -> bool:
        """
        Determine if an error should trigger a retry.
        
        Args:
            error: The exception that occurred
            
        Returns:
            True if the error is retryable
        """
        # Explicit retry/non-retry errors
        if isinstance(error, NonRetryableError):
            return False
        if isinstance(error, RetryableError):
            return True
            
        # Check error message for common transient issues
        error_msg = str(error).lower()
        
        retryable_patterns = [
            'timeout',
            'connection',
            'temporary',
            'rate limit',
            'too many requests',
            'service unavailable',
            'internal server error',
            '500',
            '502',
            '503',
            '504',
            'quota exceeded',
            'resource exhausted'
        ]
        
        for pattern in retryable_patterns:
            if pattern in error_msg:
                return True
                
        # Specific error types that are retryable
        retryable_types = (
            ConnectionError,
            TimeoutError,
            OSError
        )
        
        return isinstance(error, retryable_types)
        
    def execute_with_retry(
        self,
        func: Callable,
        config: Optional[RetryConfig] = None,
        operation_name: str = "operation",
        *args,
        **kwargs
    ) -> Any:
        """
        Execute a function with retry logic.
        
        Args:
            func: Function to execute
            config: Retry configuration (uses defaults if None)
            operation_name: Name of operation for logging
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
            
        Returns:
            Result of successful function execution
            
        Raises:
            Exception: If all retry attempts fail
        """
        config = config or RetryConfig()
        last_error = None
        
        for attempt in range(config.max_attempts):
            try:
                start_time = time.time()
                result = func(*args, **kwargs)
                
                # Log success
                elapsed = time.time() - start_time
                self.logger.info(
                    f"{operation_name} succeeded on attempt {attempt + 1}/{config.max_attempts} "
                    f"({elapsed:.2f}s)"
                )
                
                # Record success in history
                self.retry_history.append({
                    'operation': operation_name,
                    'timestamp': datetime.now().isoformat(),
                    'attempt': attempt + 1,
                    'success': True,
                    'elapsed_seconds': elapsed
                })
                
                return result
                
            except Exception as e:
                last_error = e
                elapsed = time.time() - start_time if 'start_time' in locals() else 0
                
                # Record failure in history
                self.retry_history.append({
                    'operation': operation_name,
                    'timestamp': datetime.now().isoformat(),
                    'attempt': attempt + 1,
                    'success': False,
                    'error': str(e),
                    'error_type': type(e).__name__,
                    'elapsed_seconds': elapsed,
                    'retryable': self.is_retryable_error(e)
                })
                
                # Check if we should retry
                if not self.is_retryable_error(e):
                    self.logger.error(f"{operation_name} failed with non-retryable error: {str(e)}")
                    raise
                    
                # Check if we have attempts remaining
                if attempt < config.max_attempts - 1:
                    delay = self.calculate_delay(attempt, config)
                    self.logger.warning(
                        f"{operation_name} failed (attempt {attempt + 1}/{config.max_attempts}): {str(e)}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                else:
                    self.logger.error(
                        f"{operation_name} failed after {config.max_attempts} attempts: {str(e)}"
                    )
                    
        # All attempts failed
        raise last_error
        
    def execute_with_fallback(
        self,
        primary_func: Callable,
        fallback_func: Optional[Callable] = None,
        config: Optional[RetryConfig] = None,
        operation_name: str = "operation",
        *args,
        **kwargs
    ) -> Tuple[Any, bool]:
        """
        Execute a function with retry logic and fallback.
        
        Args:
            primary_func: Primary function to execute
            fallback_func: Fallback function if primary fails (optional)
            config: Retry configuration
            operation_name: Name of operation for logging
            *args: Positional arguments for functions
            **kwargs: Keyword arguments for functions
            
        Returns:
            Tuple of (result, used_fallback)
            
        Raises:
            Exception: If both primary and fallback fail
        """
        try:
            result = self.execute_with_retry(
                primary_func,
                config=config,
                operation_name=operation_name,
                *args,
                **kwargs
            )
            return result, False
            
        except Exception as primary_error:
            if fallback_func is not None:
                self.logger.warning(
                    f"{operation_name} primary failed, trying fallback: {str(primary_error)}"
                )
                try:
                    result = self.execute_with_retry(
                        fallback_func,
                        config=config,
                        operation_name=f"{operation_name} (fallback)",
                        *args,
                        **kwargs
                    )
                    return result, True
                    
                except Exception as fallback_error:
                    self.logger.error(
                        f"{operation_name} fallback also failed: {str(fallback_error)}"
                    )
                    raise fallback_error
            else:
                raise primary_error
                
    def get_retry_history(
        self, 
        limit: Optional[int] = None,
        operation_name: Optional[str] = None
    ) -> List[Dict]:
        """
        Get retry history.
        
        Args:
            limit: Maximum number of records to return
            operation_name: Filter by operation name
            
        Returns:
            List of retry history records
        """
        history = self.retry_history
        
        if operation_name:
            history = [h for h in history if h['operation'] == operation_name]
            
        if limit:
            history = history[-limit:]
            
        return history
        
    def get_retry_statistics(self, operation_name: Optional[str] = None) -> Dict:
        """
        Get statistics about retry operations.
        
        Args:
            operation_name: Filter by operation name
            
        Returns:
            Dictionary with statistics
        """
        history = self.get_retry_history(operation_name=operation_name)
        
        if not history:
            return {
                'total_operations': 0,
                'successful_operations': 0,
                'failed_operations': 0,
                'success_rate': 0.0,
                'average_attempts': 0.0,
                'retryable_failures': 0,
                'non_retryable_failures': 0
            }
            
        # Group by operation instance (same operation + timestamp prefix)
        operations = {}
        for record in history:
            op_key = f"{record['operation']}_{record['timestamp'][:19]}"  # Group by second
            if op_key not in operations:
                operations[op_key] = []
            operations[op_key].append(record)
            
        total_ops = len(operations)
        successful_ops = sum(1 for records in operations.values() if records[-1]['success'])
        failed_ops = total_ops - successful_ops
        
        total_attempts = sum(len(records) for records in operations.values())
        avg_attempts = total_attempts / total_ops if total_ops > 0 else 0
        
        retryable_failures = sum(1 for h in history if not h['success'] and h.get('retryable', False))
        non_retryable_failures = sum(1 for h in history if not h['success'] and not h.get('retryable', False))
        
        return {
            'total_operations': total_ops,
            'successful_operations': successful_ops,
            'failed_operations': failed_ops,
            'success_rate': round(successful_ops / total_ops * 100, 2) if total_ops > 0 else 0,
            'average_attempts': round(avg_attempts, 2),
            'retryable_failures': retryable_failures,
            'non_retryable_failures': non_retryable_failures,
            'total_records': len(history)
        }
        
    def clear_history(self):
        """Clear retry history."""
        self.retry_history.clear()
        self.logger.info("Retry history cleared")


def retry_on_error(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    operation_name: Optional[str] = None
):
    """
    Decorator for adding retry logic to a function.
    
    Args:
        max_attempts: Maximum retry attempts
        initial_delay: Initial delay before retry
        operation_name: Name for logging (uses function name if None)
        
    Example:
        @retry_on_error(max_attempts=3, initial_delay=2.0)
        def call_api():
            return requests.get('https://api.example.com')
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            service = ErrorRecoveryService()
            config = RetryConfig(max_attempts=max_attempts, initial_delay=initial_delay)
            op_name = operation_name or func.__name__
            
            return service.execute_with_retry(
                func, 
                config=config,
                operation_name=op_name,
                *args,
                **kwargs
            )
        return wrapper
    return decorator


if __name__ == "__main__":
    # Test the error recovery service
    service = ErrorRecoveryService()
    
    # Test function that fails a few times
    attempt_counter = {'count': 0}
    
    def flaky_function():
        attempt_counter['count'] += 1
        if attempt_counter['count'] < 3:
            raise RetryableError(f"Temporary failure (attempt {attempt_counter['count']})")
        return "Success!"
    
    print("=== Testing Retry Logic ===")
    try:
        result = service.execute_with_retry(
            flaky_function,
            config=RetryConfig(max_attempts=5, initial_delay=0.5),
            operation_name="test_operation"
        )
        print(f"Result: {result}")
    except Exception as e:
        print(f"Failed: {str(e)}")
        
    # Print statistics
    print("\n=== Retry Statistics ===")
    stats = service.get_retry_statistics()
    for key, value in stats.items():
        print(f"{key}: {value}")
