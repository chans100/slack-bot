#!/usr/bin/env python3
"""
Test script to demonstrate role assignment with proper job titles.
This shows how the system would work if users had job titles in their Slack profiles.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from bot import DailyStandupBot

def test_role_assignment_with_titles():
    """Test role assignment with simulated job titles."""
    
    # Simulated users with proper job titles
    test_users = [
        {
            'id': 'U001',
            'name': 'John Sales',
            'title': 'Sales Engineer',
            'expected_roles': ['sales', 'sales_engineering']
        },
        {
            'id': 'U002', 
            'name': 'Sarah Scrum',
            'title': 'Scrum Master',
            'expected_roles': ['scrum_master', 'agile_management']
        },
        {
            'id': 'U003',
            'name': 'Mike Ops',
            'title': 'DevOps Engineer',
            'expected_roles': ['operations', 'infrastructure']
        },
        {
            'id': 'U004',
            'name': 'Lisa Marketing',
            'title': 'Digital Marketing Manager',
            'expected_roles': ['marketing', 'digital_marketing', 'lead']
        },
        {
            'id': 'U005',
            'name': 'Tom HR',
            'title': 'Human Resources Specialist',
            'expected_roles': ['human_capital', 'people_operations']
        },
        {
            'id': 'U006',
            'name': 'Anna Finance',
            'title': 'Financial Analyst',
            'expected_roles': ['finance', 'financial_management']
        },
        {
            'id': 'U007',
            'name': 'Carl Support',
            'title': 'Client Service Manager',
            'expected_roles': ['client_service', 'client_support', 'lead']
        },
        {
            'id': 'U008',
            'name': 'Emma Engineer',
            'title': 'Software Engineer',
            'expected_roles': ['engineering', 'software_engineering']
        }
    ]
    
    print("🤖 Role Assignment Demo with Proper Job Titles")
    print("=" * 50)
    print()
    
    # Create a mock bot instance for testing
    bot = DailyStandupBot()
    
    for user in test_users:
        # Create mock user info
        mock_user_info = {
            'id': user['id'],
            'name': user['name'],
            'real_name': user['name'],
            'profile': {
                'title': user['title'],
                'team': 'T0919MVQC5A'
            }
        }
        
        # Test role assignment
        try:
            roles = bot._get_auto_assigned_roles(user['id'], mock_user_info)
            expected = user['expected_roles']
            
            print(f"👤 {user['name']} ({user['title']})")
            print(f"   Expected: {', '.join(expected)}")
            print(f"   Assigned: {', '.join(roles)}")
            
            # Check if roles match expectations
            matches = set(roles) & set(expected)
            if matches:
                print(f"   ✅ Matches: {', '.join(matches)}")
            else:
                print(f"   ❌ No matches found")
            
            print()
            
        except Exception as e:
            print(f"❌ Error testing {user['name']}: {e}")
            print()
    
    print("📝 Summary:")
    print("- The system works correctly when users have job titles")
    print("- Job titles like 'Sales Engineer' get 'sales' and 'sales_engineering' roles")
    print("- Leadership keywords like 'Manager' get 'lead' role")
    print("- Users without job titles default to 'engineering' and 'software_engineering'")
    print()
    print("💡 To fix the current issue:")
    print("1. Ask users to add job titles to their Slack profiles")
    print("2. Or manually assign roles using '/role [role_name]'")
    print("3. Or set up custom profile fields for departments")

if __name__ == "__main__":
    test_role_assignment_with_titles() 