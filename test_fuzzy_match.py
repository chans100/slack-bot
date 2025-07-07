#!/usr/bin/env python3
"""
Test script to verify that fuzzy matching now requires perfect matches.
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from coda_service import CodaService

def test_fuzzy_matching():
    """Test that fuzzy matching now requires perfect matches."""
    print("🔍 Testing Fuzzy Matching (Perfect Match Only)...")
    
    # Initialize Coda service
    coda = CodaService()
    
    # Test 1: Perfect match should work
    print("\n1️⃣ Testing perfect match...")
    perfect_search = "KR1: Increase user engagement"
    matches = coda.search_kr_table(perfect_search)
    if matches:
        print(f"✅ Perfect match found: {len(matches)} results")
        for match in matches:
            kr_name = match.get('c-yQ1M6UqTSj', 'N/A')
            print(f"   - {kr_name}")
    else:
        print("❌ Perfect match not found")
    
    # Test 2: Partial match should NOT work
    print("\n2️⃣ Testing partial match (should fail)...")
    partial_search = "KR1: Increase"
    matches = coda.search_kr_table(partial_search)
    if matches:
        print(f"❌ Partial match found (should not happen): {len(matches)} results")
        for match in matches:
            kr_name = match.get('c-yQ1M6UqTSj', 'N/A')
            print(f"   - {kr_name}")
    else:
        print("✅ Partial match correctly rejected")
    
    # Test 3: Similar but not exact match should NOT work
    print("\n3️⃣ Testing similar match (should fail)...")
    similar_search = "KR1: Increase user engagement system"
    matches = coda.search_kr_table(similar_search)
    if matches:
        print(f"❌ Similar match found (should not happen): {len(matches)} results")
        for match in matches:
            kr_name = match.get('c-yQ1M6UqTSj', 'N/A')
            print(f"   - {kr_name}")
    else:
        print("✅ Similar match correctly rejected")
    
    # Test 4: Case insensitive perfect match should work
    print("\n4️⃣ Testing case insensitive perfect match...")
    case_search = "kr1: increase user engagement"
    matches = coda.search_kr_table(case_search)
    if matches:
        print(f"✅ Case insensitive perfect match found: {len(matches)} results")
        for match in matches:
            kr_name = match.get('c-yQ1M6UqTSj', 'N/A')
            print(f"   - {kr_name}")
    else:
        print("❌ Case insensitive perfect match not found")
    
    print("\n🎉 Fuzzy matching test completed!")
    return True

if __name__ == "__main__":
    success = test_fuzzy_matching()
    if success:
        print("\n✅ Fuzzy Matching Verification Complete - Perfect matches only!")
    else:
        print("\n❌ Fuzzy Matching Verification Failed!")
        sys.exit(1) 