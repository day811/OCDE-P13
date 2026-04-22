#!/usr/bin/env python3
"""
Test script to validate RAG environment setup.
Checks compatibility of all required dependencies.

Usage:
    python tests/test_environment.py
"""

import sys
from typing import Dict, Tuple


def test_imports() -> Dict[str, Tuple[bool, str]]:
    """
    Test all required package imports.
    
    Returns:
        Dictionary with package names and test results (success, version/error message)
    """
    results = {}
    
    # Test 1: Python version
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    results["Python"] = (sys.version_info >= (3, 8), python_version)
    
    # Test 2: LangChain
    try:
        import langchain
        results["langchain"] = (True, langchain.__version__)
    except ImportError as e:
        results["langchain"] = (False, str(e))
    
    # Test 3: Faiss
    try:
        import faiss
        results["faiss-cpu"] = (True, "installed")
    except ImportError as e:
        results["faiss-cpu"] = (False, str(e))
    
    # Test 4: Mistral
    try:
        from mistralai import Mistral
        results["mistralai"] = (True, "installed")
    except ImportError as e:
        results["mistralai"] = (False, str(e))
    
    # Test 5: Pandas
    try:
        import pandas
        results["pandas"] = (True, pandas.__version__)
    except ImportError as e:
        results["pandas"] = (False, str(e))
    
    # Test 6: NumPy (dependency)
    try:
        import numpy
        results["numpy"] = (True, numpy.__version__)
    except ImportError as e:
        results["numpy"] = (False, str(e))
    
    # Test 7: Requests (for API calls)
    try:
        import requests
        results["requests"] = (True, requests.__version__)
    except ImportError as e:
        results["requests"] = (False, str(e))
    
    return results


def test_faiss_functionality() -> Tuple[bool, str]:
    """
    Test basic Faiss functionality (CPU backend).
    
    Returns:
        Tuple (success, message)
    """
    try:
        import faiss
        import numpy as np
        
        # Create simple index
        dimension = 384  # Mistral embedding dimension
        index = faiss.IndexFlatL2(dimension)
        
        # Add dummy vectors
        dummy_vectors = np.random.random((5, dimension)).astype('float32')
        index.add(dummy_vectors)
        
        # Test search
        query_vector = np.random.random((1, dimension)).astype('float32')
        distances, indices = index.search(query_vector, k=3)
        
        if indices.shape == (1, 3):
            return (True, f"Faiss working (tested with {dimension}D vectors)")
        else:
            return (False, "Faiss search returned unexpected shape")
            
    except Exception as e:
        return (False, f"Faiss error: {str(e)}")


def print_results(imports: Dict[str, Tuple[bool, str]], faiss_test: Tuple[bool, str]) -> bool:
    """
    Print test results in formatted table.
    
    Args:
        imports: Dictionary of import test results
        faiss_test: Faiss functionality test result
        
    Returns:
        True if all tests passed, False otherwise
    """
    print("\n" + "="*60)
    print("RAG ENVIRONMENT COMPATIBILITY TEST")
    print("="*60 + "\n")
    
    all_passed = True
    
    # Print imports
    print(f"{'Package':<20} {'Status':<10} {'Version/Info':<25}")
    print("-"*60)
    
    for package, (success, info) in imports.items():
        status = "✅ PASS" if success else "❌ FAIL"
        if not success:
            all_passed = False
        print(f"{package:<20} {status:<10} {info:<25}")
    
    # Print Faiss functionality
    print("-"*60)
    faiss_success, faiss_info = faiss_test
    faiss_status = "✅ PASS" if faiss_success else "❌ FAIL"
    if not faiss_success:
        all_passed = False
    print(f"{'Faiss (functional)':<20} {faiss_status:<10} {faiss_info:<25}")
    
    print("\n" + "="*60)
    if all_passed:
        print("✅ ALL TESTS PASSED - Environment is ready for Phase 2!")
    else:
        print("❌ SOME TESTS FAILED - See above for details")
    print("="*60 + "\n")
    
    return all_passed


def main():
    """Run all environment tests."""
    print("\nRunning environment compatibility tests...\n")
    
    imports = test_imports()
    faiss_test = test_faiss_functionality()
    
    all_passed = print_results(imports, faiss_test)
    
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
