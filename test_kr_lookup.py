#!/usr/bin/env python3
"""
Test script to check KR lookup behavior.
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from coda_service import CodaService

def test_kr_lookup():
    """Test KR lookup to see if it's requiring exact matches."""
    print("🔍 Testing KR Lookup Behavior...")
    
    # Initialize Coda service
    coda = CodaService()
    
    # Test 1: Search for a specific KR that should exist
    print("\n1️⃣ Testing exact KR search...")
    search_term = "Draft Slack Healthcheck Prompt Flow (v1)"
    print(f"Searching for: '{search_term}'")
    
    matches = coda.search_kr_table(search_term)
    print(f"Found {len(matches)} matches")
    
    for i, match in enumerate(matches, 1):
        kr_name = match.get('c-yQ1M6UqTSj', 'N/A')
        print(f"  {i}. {kr_name}")
    
    # Test 2: Search for partial match (should NOT work)
    print("\n2️⃣ Testing partial KR search...")
    search_term = "Draft Slack Healthcheck"
    print(f"Searching for: '{search_term}'")
    
    matches = coda.search_kr_table(search_term)
    print(f"Found {len(matches)} matches")
    
    for i, match in enumerate(matches, 1):
        kr_name = match.get('c-yQ1M6UqTSj', 'N/A')
        print(f"  {i}. {kr_name}")
    
    # Test 3: Search for similar but not exact match (should NOT work)
    print("\n3️⃣ Testing similar KR search...")
    search_term = "Draft Slack Healthcheck Prompt Flow"
    print(f"Searching for: '{search_term}'")
    
    matches = coda.search_kr_table(search_term)
    print(f"Found {len(matches)} matches")
    
    for i, match in enumerate(matches, 1):
        kr_name = match.get('c-yQ1M6UqTSj', 'N/A')
        print(f"  {i}. {kr_name}")
    
    # Test 4: Search for something that definitely doesn't exist
    print("\n4️⃣ Testing non-existent KR search...")
    search_term = "This KR Definitely Does Not Exist"
    print(f"Searching for: '{search_term}'")
    
    matches = coda.search_kr_table(search_term)
    print(f"Found {len(matches)} matches")
    
    for i, match in enumerate(matches, 1):
        kr_name = match.get('c-yQ1M6UqTSj', 'N/A')
        print(f"  {i}. {kr_name}")
    
    print("\n🎉 KR Lookup test completed!")

if __name__ == "__main__":
    test_kr_lookup() 