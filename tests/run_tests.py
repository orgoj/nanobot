#!/usr/bin/env python3
"""
Simple test runner for nanobot router tests.

This script runs the router tests without requiring pytest.
It provides basic test discovery and execution.
"""

import sys
import os
import importlib.util
import traceback
from pathlib import Path
from typing import List, Tuple

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def load_test_module(module_path: Path):
    """Load a test module dynamically."""
    spec = importlib.util.spec_from_file_location(
        module_path.stem, 
        module_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_test_class(cls) -> Tuple[int, int, List[str]]:
    """Run all test methods in a class."""
    passed = 0
    failed = 0
    errors = []
    
    # Get all test methods
    test_methods = [
        getattr(cls, method_name) 
        for method_name in dir(cls) 
        if method_name.startswith('test_') and callable(getattr(cls, method_name))
    ]
    
    # Instantiate test class
    try:
        instance = cls()
        # Run setup if exists
        if hasattr(instance, 'setup_method'):
            instance.setup_method()
    except Exception as e:
        errors.append(f"  ✗ Setup failed: {e}")
        return 0, len(test_methods), errors
    
    for method in test_methods:
        method_name = method.__name__
        try:
            # Check if async
            import asyncio
            if asyncio.iscoroutinefunction(method):
                asyncio.run(method(instance))
            else:
                method(instance)
            passed += 1
            print(f"  ✓ {method_name}")
        except Exception as e:
            failed += 1
            error_msg = f"  ✗ {method_name}: {str(e)}"
            errors.append(error_msg)
            print(error_msg)
    
    return passed, failed, errors


def discover_tests(test_dir: Path) -> List[Path]:
    """Discover all test files."""
    test_files = []
    for file in test_dir.glob("test_*.py"):
        if file.name != "__init__.py":
            test_files.append(file)
    return sorted(test_files)


def run_all_tests(test_dir: Path) -> Tuple[int, int, List[str]]:
    """Run all tests in directory."""
    total_passed = 0
    total_failed = 0
    all_errors = []
    
    test_files = discover_tests(test_dir)
    
    print(f"\n{'='*70}")
    print(f"Running Router Tests")
    print(f"{'='*70}\n")
    
    for test_file in test_files:
        print(f"\n{test_file.name}:")
        print("-" * 70)
        
        try:
            module = load_test_module(test_file)
            
            # Find test classes
            test_classes = [
                getattr(module, name) 
                for name in dir(module) 
                if name.startswith('Test') and isinstance(getattr(module, name), type)
            ]
            
            for test_class in test_classes:
                print(f"\n  {test_class.__name__}:")
                passed, failed, errors = run_test_class(test_class)
                total_passed += passed
                total_failed += failed
                all_errors.extend(errors)
                
        except Exception as e:
            print(f"  ✗ Failed to load module: {e}")
            traceback.print_exc()
            total_failed += 1
    
    return total_passed, total_failed, all_errors


def main():
    """Main entry point."""
    test_dir = Path(__file__).parent / "router"
    
    if not test_dir.exists():
        print(f"Error: Test directory not found: {test_dir}")
        sys.exit(1)
    
    try:
        passed, failed, errors = run_all_tests(test_dir)
        
        # Summary
        print(f"\n{'='*70}")
        print(f"Test Summary")
        print(f"{'='*70}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Total:  {passed + failed}")
        
        if errors:
            print(f"\nErrors:")
            for error in errors:
                print(error)
        
        print()
        
        if failed > 0:
            sys.exit(1)
        else:
            print("✓ All tests passed!")
            sys.exit(0)
            
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\nError running tests: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
