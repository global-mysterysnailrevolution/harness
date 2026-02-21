#!/usr/bin/env python3
"""
Weave Tracing Integration
Provides observability for broker operations with secret redaction
"""

import os
from typing import Any, Dict, Optional
import functools

_weave_initialized = False
_weave_available = False

def init_weave() -> bool:
    """
    Initialize Weave tracing (idempotent)
    
    Returns True if Weave is available and initialized
    """
    global _weave_initialized, _weave_available
    
    if _weave_initialized:
        return _weave_available
    
    _weave_initialized = True
    
    # Check for required env vars
    wandb_key = os.getenv("WANDB_API_KEY")
    weave_project = os.getenv("WEAVE_PROJECT", "globalmysterysnailrevolution/tool-broker")
    
    if not wandb_key:
        print("Warning: WANDB_API_KEY not set. Weave tracing disabled.")
        return False
    
    try:
        import weave
        import wandb
        
        # Initialize Weave
        weave.init(project_name=weave_project)
        _weave_available = True
        print(f"Weave tracing initialized for project: {weave_project}")
        return True
    except ImportError:
        print("Warning: weave or wandb not installed. Install with: pip install weave wandb")
        return False
    except Exception as e:
        print(f"Warning: Failed to initialize Weave: {e}")
        return False

def redact(obj: Any) -> Any:
    """
    Redact secrets from objects before logging
    
    Removes keys containing: key, token, secret, password, auth, bearer (case-insensitive)
    """
    if isinstance(obj, dict):
        redacted = {}
        for key, value in obj.items():
            key_lower = str(key).lower()
            # Check if key contains sensitive terms
            if any(term in key_lower for term in ['key', 'token', 'secret', 'password', 'auth', 'bearer', 'credential', 'api_key']):
                redacted[key] = "***REDACTED***"
            else:
                redacted[key] = redact(value)  # Recursively redact nested objects
        return redacted
    elif isinstance(obj, list):
        return [redact(item) for item in obj]
    elif isinstance(obj, str):
        # Check if string looks like a token/key
        if isinstance(obj, str) and len(obj) > 20 and any(c.isalnum() for c in obj):
            # Heuristic: long alphanumeric strings might be tokens
            if any(term in str(obj).lower()[:20] for term in ['sk-', 'x-', 'bearer', 'token']):
                return "***REDACTED***"
        return obj
    else:
        return obj

def weave_op(func):
    """
    Decorator to trace function calls with Weave
    
    Automatically redacts secrets from args and results
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        global _weave_available
        
        if not _weave_available:
            # Weave not available, just call function normally
            return func(*args, **kwargs)
        
        try:
            import weave
            
            # Redact args and kwargs
            redacted_args = [redact(arg) for arg in args]
            redacted_kwargs = redact(kwargs)
            
            # Create op
            op = weave.op()(func)
            
            # Call with redacted inputs
            result = op(*redacted_args, **redacted_kwargs)
            
            # Redact result before returning
            return redact(result)
        except Exception as e:
            # If Weave fails, fall back to normal execution
            print(f"Warning: Weave tracing failed for {func.__name__}: {e}")
            return func(*args, **kwargs)
    
    return wrapper

def trace_broker_operation(operation_name: str, **kwargs):
    """
    Manually trace a broker operation
    
    Use this for operations that can't be easily decorated
    """
    global _weave_available
    
    if not _weave_available:
        return
    
    try:
        import weave
        
        # Redact all kwargs
        redacted_kwargs = redact(kwargs)
        
        # Log operation
        with weave.op(name=operation_name) as op:
            op.log(**redacted_kwargs)
    except Exception as e:
        print(f"Warning: Failed to trace operation {operation_name}: {e}")
