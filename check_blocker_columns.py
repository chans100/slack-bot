#!/usr/bin/env python3
"""
Script to check the actual column names in the Coda blocker table.
"""

import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv('.env')

def check_blocker_table_columns():
    """Check the actual column names in the blocker table."""
    
    api_token = os.environ.get("CODA_API_TOKEN")
    doc_id = os.environ.get("CODA_DOC_ID")
    blocker_table_id = os.environ.get("CODA_TABLE_ID2")
    
    if not all([api_token, doc_id, blocker_table_id]):
        print("❌ Missing required environment variables")
        return
    
    print("🔍 Checking blocker table columns...")
    print(f"   Doc ID: {doc_id}")
    print(f"   Blocker Table ID: {blocker_table_id}")
    
    # Get table schema
    url = f"https://coda.io/apis/v1/docs/{doc_id}/tables/{blocker_table_id}"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            table_data = response.json()
            
            print("\n📋 Table information:")
            print(f"   Name: {table_data.get('name', 'Unknown')}")
            print(f"   Display Column: {table_data.get('displayColumn', 'Unknown')}")
            
            # Get columns
            columns_url = f"https://coda.io/apis/v1/docs/{doc_id}/tables/{blocker_table_id}/columns"
            columns_response = requests.get(columns_url, headers=headers)
            
            if columns_response.status_code == 200:
                columns_data = columns_response.json()
                print(f"\n📋 Actual column names in blocker table:")
                for i, col in enumerate(columns_data.get('items', []), 1):
                    col_id = col.get('id', 'Unknown')
                    col_name = col.get('name', 'Unknown')
                    col_type = col.get('format', {}).get('type', 'Unknown')
                    print(f"   {i}. ID: {col_id} | Name: '{col_name}' | Type: {col_type}")
            
            # Also get a sample row to see the actual column names
            print("\n📊 Getting sample data...")
            rows_url = f"https://coda.io/apis/v1/docs/{doc_id}/tables/{blocker_table_id}/rows"
            rows_response = requests.get(rows_url, headers=headers)
            
            if rows_response.status_code == 200:
                rows_data = rows_response.json()
                if rows_data.get('items'):
                    sample_row = rows_data['items'][0]
                    print(f"\n📝 Sample row values:")
                    for key, value in sample_row.get('values', {}).items():
                        print(f"   {key}: {value}")
                else:
                    print("   No rows found in table")
            else:
                print(f"❌ Error getting rows: {rows_response.status_code}")
                
        else:
            print(f"❌ Error getting table schema: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    check_blocker_table_columns() 