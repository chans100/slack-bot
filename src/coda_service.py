"""
Coda service for the Python Slack Health Check Bot.
Handles Coda API operations for storing and retrieving bot data.
"""

import os
import requests
from datetime import datetime
from dotenv import load_dotenv
from difflib import SequenceMatcher
from .config import BotConfig
import json

# Load environment variables
load_dotenv('.env')

class CodaService:
    """Service class for Coda API operations."""
    
    def __init__(self):
        """Initialize Coda service with API token and table IDs."""
        self.api_token = os.environ.get("CODA_API_TOKEN")
        self.doc_id = os.environ.get("CODA_DOC_ID")
        self.health_check_table_id = BotConfig.HEALTH_CHECK_TABLE  # Single health check table
        self.blocker_table_id = BotConfig.BLOCKER_TABLE
        self.standup_table_id = BotConfig.STANDUP_TABLE
        self.blocker_res_table_id = BotConfig.BLOCKER_RESOLUTION_TABLE
        self.kr_table_id = BotConfig.KR_TABLE
        self.after_health_check_table_id = BotConfig.AFTER_HEALTH_CHECK_TABLE
        self.response_table_id = BotConfig.RESPONSE_TABLE
        self.error_table_id = BotConfig.ERROR_TABLE
        
        if not self.api_token:
            print("❌ CODA_API_TOKEN not found in environment variables")
            return
            
        if not self.doc_id:
            print("❌ CODA_DOC_ID not found in environment variables")
            return
            
        if not self.health_check_table_id:
            print("❌ Health_Check table ID not found in environment variables")
            return
            
        print("✅ Coda service initialized")
        print(f"   Doc ID: {self.doc_id}")
        print(f"   Health Check Table ID: {self.health_check_table_id}")
        print(f"   Blocker Table ID: {self.blocker_table_id}")
        print(f"   Standup Table ID: {self.standup_table_id}")
        print(f"   Blocker Resolution Table ID: {self.blocker_res_table_id}")
        print(f"   After Health Check Table ID: {self.after_health_check_table_id}")
        print(f"   Response Table ID: {self.response_table_id}")
        print(f"   KR Table ID: {self.kr_table_id}")
        print(f"   Error Table ID: {self.error_table_id}")
        
        # Debug: Check if environment variables are loaded
        print("🔍 DEBUG: Environment variable check:")
        print(f"   Health_Check env var: {os.environ.get('Health_Check', 'NOT SET')}")
        print(f"   KR_Table env var: {os.environ.get('KR_Table', 'NOT SET')}")
        print(f"   Stand_Up env var: {os.environ.get('Stand_Up', 'NOT SET')}")
        print(f"   Blocker env var: {os.environ.get('Blocker', 'NOT SET')}")
        print(f"   After_Health_Check env var: {os.environ.get('After_Health_Check', 'NOT SET')}")
        print(f"   SLACK_ESCALATION_CHANNEL: {os.environ.get('SLACK_ESCALATION_CHANNEL', 'NOT SET')}")
    
    def _make_request(self, method, endpoint, data=None):
        """Make a request to the Coda API."""
        print(f"🔍 DEBUG: _make_request called:")
        print(f"   - method: {method}")
        print(f"   - endpoint: {endpoint}")
        print(f"   - data: {data}")
        
        if not self.api_token:
            print("❌ No API token available")
            return None
            
        url = f"https://coda.io/apis/v1{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        
        print(f"🔍 DEBUG: Making request to: {url}")
        
        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers)
            elif method.upper() == "POST":
                response = requests.post(url, headers=headers, json=data)
            elif method.upper() == "PUT":
                response = requests.put(url, headers=headers, json=data)
            elif method.upper() == "DELETE":
                response = requests.delete(url, headers=headers)
            else:
                print(f"❌ Unsupported HTTP method: {method}")
                return None
            
            print(f"🔍 DEBUG: Response status: {response.status_code}")
            print(f"🔍 DEBUG: Response text: {response.text}")
                
            if response.status_code in [200, 201, 202]:
                return response.json()
            else:
                print(f"❌ Coda API error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ Error making Coda API request: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def add_response(self, user_id, response, timestamp=None, username=None):
        """Add a response to the health check table."""
        if not self.health_check_table_id:
            print("❌ Health check table ID not configured")
            return False
            
        if timestamp is None:
            timestamp = datetime.now().isoformat()
            
        if username is None:
            username = user_id
            
        data = {
            "rows": [{
                "cells": [
                    {"column": "User ID", "value": user_id},
                    {"column": "Name", "value": username},
                    {"column": "Response", "value": response},
                    {"column": "Timestamp", "value": timestamp}
                ]
            }]
        }
        
        endpoint = f"/docs/{self.doc_id}/tables/{self.health_check_table_id}/rows"
        result = self._make_request("POST", endpoint, data)
        
        if result:
            print(f"✅ Response stored in Coda: {result.get('id', 'unknown')}")
            return True
        else:
            print("❌ Failed to store response in Coda")
            return False
    
    def add_blocker(self, user_id, blocker_description, kr_name, urgency, notes=None, username=None, sprint_number=None):
        """Add a blocker to the blocker table."""
        print(f"🔍 DEBUG: add_blocker called with:")
        print(f"   - user_id: {user_id}")
        print(f"   - blocker_description: {blocker_description}")
        print(f"   - kr_name: {kr_name}")
        print(f"   - urgency: {urgency}")
        print(f"   - notes: {notes}")
        print(f"   - username: {username}")
        print(f"   - sprint_number: {sprint_number}")
        print(f"   - blocker_table_id: {self.blocker_table_id}")
        
        if not self.blocker_table_id:
            print("❌ Blocker table ID not configured")
            return False
            
        if username is None:
            username = user_id
            
        # Prepare cells for the blocker table
        cells = [
            {"column": "User ID", "value": user_id},
            {"column": "Name", "value": username},
            {"column": "Blocker Description", "value": blocker_description},
            {"column": "KR Name", "value": kr_name},
            {"column": "Urgency", "value": urgency},
            {"column": "Notes", "value": notes or ""}
        ]
        
        # Add sprint number if provided
        if sprint_number:
            cells.append({"column": "Sprint", "value": str(sprint_number)})
            
        data = {
            "rows": [{
                "cells": cells
            }]
        }
        
        print(f"🔍 DEBUG: Sending data to Coda: {data}")
        
        endpoint = f"/docs/{self.doc_id}/tables/{self.blocker_table_id}/rows"
        print(f"🔍 DEBUG: Endpoint: {endpoint}")
        
        result = self._make_request("POST", endpoint, data)
        
        print(f"🔍 DEBUG: Coda response: {result}")
        
        if result:
            print(f"✅ Blocker stored in Coda: {result.get('id', 'unknown')}")
            return True
        else:
            print("❌ Failed to store blocker in Coda")
            return False

    def get_column_id_map(self, table_id):
        """Fetch and return a mapping from display name to column ID for a table."""
        endpoint = f"/docs/{self.doc_id}/tables/{table_id}/columns"
        result = self._make_request("GET", endpoint)
        if not result or not result.get("items"):
            print("❌ Could not fetch columns for mapping.")
            return {}
        return {col["name"]: col["id"] for col in result["items"]}

    def resolve_blocker(self, user_id, kr_name, blocker_description, resolved_by, resolution_notes=None, slack_client=None, user_name=None):
        """Update the Resolution column for a blocker in the main blocker table, using column ID mapping. Tries both user_id and user_name for matching."""
        print(f"🔍 DEBUG: resolve_blocker called with:")
        print(f"   - user_id: {user_id}")
        print(f"   - user_name: {user_name}")
        print(f"   - kr_name: {kr_name}")
        print(f"   - blocker_description: {blocker_description}")
        print(f"   - resolved_by: {resolved_by}")
        print(f"   - resolution_notes: {resolution_notes}")
        
        if not self.blocker_table_id:
            print("❌ Blocker table ID not configured")
            return False
        
        # Get column ID mapping
        col_map = self.get_column_id_map(self.blocker_table_id)
        required = ["Blocker Description", "KR Name", "Resolution"]
        # Check for either User ID (new) or Name (old) column
        if "User ID" not in col_map and "Name" not in col_map:
            print(f"❌ Neither 'User ID' nor 'Name' column found in table.")
            return False
        for col in required:
            if col not in col_map:
                print(f"❌ Required column '{col}' not found in table.")
                return False
        
        # Find the correct row
        endpoint = f"/docs/{self.doc_id}/tables/{self.blocker_table_id}/rows"
        result = self._make_request("GET", endpoint)
        if not result:
            print("❌ Could not fetch blocker rows")
            return False
        
        row_id = None
        # Try all possible user identifiers for matching
        user_identifiers = [user_id]
        if user_name and user_name != user_id:
            user_identifiers.append(user_name)
        
        print(f"🔍 DEBUG: Looking for user identifiers: {user_identifiers}")
        print(f"🔍 DEBUG: Looking for KR: '{kr_name}'")
        print(f"🔍 DEBUG: Looking for description: '{blocker_description}'")
        
        # First pass: exact matching
        for row in result.get("items", []):
            cells = row.get("values", {})
            # Try User ID first (new format), then fall back to Name (old format)
            row_user_id = cells.get(col_map.get("User ID", ""), "")
            row_user_name = cells.get(col_map.get("Name", ""), "")
            row_kr = cells.get(col_map["KR Name"], "")
            row_description = cells.get(col_map["Blocker Description"], "")
            row_resolution = cells.get(col_map["Resolution"], "")
            
            print(f"🔍 DEBUG: Checking row - User ID: '{row_user_id}', Name: '{row_user_name}', KR: '{row_kr}', Desc: '{row_description}', Resolution: '{row_resolution}'")
            
            # Check if this row matches any identifier
            user_matches = any(
                ident == row_user_id or ident == row_user_name for ident in user_identifiers
            )
            
            # Check for exact matches first
            if (user_matches and 
                row_kr == kr_name and 
                row_description == blocker_description and
                not row_resolution):  # Only match unresolved blockers
                row_id = row.get('id')
                print(f"✅ Found exact matching row: {row_id}")
                break
        
        # Second pass: if no exact match, try partial matching for description
        if not row_id:
            print("🔍 DEBUG: No exact match found, trying partial description matching...")
            for row in result.get("items", []):
                cells = row.get("values", {})
                row_user_id = cells.get(col_map.get("User ID", ""), "")
                row_user_name = cells.get(col_map.get("Name", ""), "")
                row_kr = cells.get(col_map["KR Name"], "")
                row_description = cells.get(col_map["Blocker Description"], "")
                row_resolution = cells.get(col_map["Resolution"], "")
                
                # Check if this row matches any identifier
                user_matches = any(
                    ident == row_user_id or ident == row_user_name for ident in user_identifiers
                )
                
                # More flexible matching - check if descriptions are similar
                description_matches = False
                if row_description == blocker_description:
                    description_matches = True
                else:
                    # Try partial matching for truncated descriptions
                    if (blocker_description in row_description or 
                        row_description in blocker_description or
                        (len(blocker_description) > 20 and len(row_description) > 20 and
                         blocker_description[:20] == row_description[:20])):
                        description_matches = True
                        print(f"🔍 DEBUG: Partial description match - '{blocker_description}' vs '{row_description}'")
                
                if (user_matches and row_kr == kr_name and description_matches and not row_resolution):
                    row_id = row.get('id')
                    print(f"✅ Found partial matching row: {row_id}")
                    break
        
        # Third pass: fallback - find the most recent unresolved blocker for this user and KR
        if not row_id:
            print("🔍 DEBUG: No partial match found, trying fallback...")
            for row in result.get("items", []):
                cells = row.get("values", {})
                row_user_id = cells.get(col_map.get("User ID", ""), "")
                row_user_name = cells.get(col_map.get("Name", ""), "")
                row_kr = cells.get(col_map["KR Name"], "")
                row_resolution = cells.get(col_map["Resolution"], "")
                
                if (any(ident == row_user_id or ident == row_user_name for ident in user_identifiers)
                    and row_kr == kr_name and not row_resolution):
                    row_id = row.get('id')
                    print(f"✅ Found fallback unresolved blocker row: {row_id}")
                    break
        
        if not row_id:
            print("❌ No matching blocker row found to resolve")
            return False
        
        # Prepare update data
        update_data = {
            "row": {
                "cells": [
                    {"column": col_map["Resolution"], "value": resolution_notes or "Resolved"}
                ]
            }
        }
        print(f"🔍 DEBUG: Sending update data to Coda: {update_data}")
        endpoint = f"/docs/{self.doc_id}/tables/{self.blocker_table_id}/rows/{row_id}"
        print(f"🔍 DEBUG: Endpoint: {endpoint}")
        result = self._make_request("PUT", endpoint, update_data)
        print(f"🔍 DEBUG: Coda response: {result}")
        if result:
            print(f"✅ Blocker marked as resolved in Coda: {row_id}")
            return True
        else:
            print("❌ Failed to update blocker as resolved in Coda")
            return False


    
    def get_responses_by_date(self, date):
        """Get all responses for a specific date."""
        if not self.health_check_table_id:
            print("❌ Health check table ID not configured")
            return []
            
        endpoint = f"/docs/{self.doc_id}/tables/{self.health_check_table_id}/rows"
        result = self._make_request("GET", endpoint)
        
        if not result:
            return []
            
        responses = []
        for row in result.get("items", []):
            cells = row.get("values", {})
            responses.append({
                "user_id": cells.get("Name", ""),
                "response": cells.get("Response", ""),
                "timestamp": cells.get("Timestamp", "")
            })
        
        return responses
    
    def get_user_responses(self, user_id, limit=10):
        """Get recent responses for a specific user."""
        if not self.health_check_table_id:
            print("❌ Health check table ID not configured")
            return []
            
        endpoint = f"/docs/{self.doc_id}/tables/{self.health_check_table_id}/rows"
        result = self._make_request("GET", endpoint)
        
        if not result:
            return []
            
        responses = []
        for row in result.get("items", []):
            cells = row.get("values", {})
            if cells.get("Name", "") == user_id:
                responses.append({
                    "user_id": cells.get("Name", ""),
                    "response": cells.get("Response", ""),
                    "timestamp": cells.get("Timestamp", "")
                })
        
        # Sort by timestamp (newest first) and limit
        responses.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return responses[:limit]
    
    def get_blockers_by_date(self, date):
        """Get all blockers for a specific date."""
        if not self.blocker_table_id:
            print("❌ Blocker table ID not configured")
            return []
            
        endpoint = f"/docs/{self.doc_id}/tables/{self.blocker_table_id}/rows"
        result = self._make_request("GET", endpoint)
        
        if not result:
            return []
            
        blockers = []
        for row in result.get("items", []):
            cells = row.get("values", {})
            blockers.append({
                "user_id": cells.get("Name", ""),
                "blocker_description": cells.get("Blocker Description", ""),
                "kr_name": cells.get("KR Name", ""),
                "urgency": cells.get("Urgency", ""),
                "notes": cells.get("Notes", "")
            })
        
        return blockers
    
    def test_connection(self):
        """Test the Coda connection and table access."""
        print("🔍 Testing Coda connection...")
        
        if not self.api_token:
            print("❌ No API token configured")
            return False
            
        if not self.doc_id:
            print("❌ No Doc ID configured")
            return False
            
        # Test health check table access
        if self.health_check_table_id:
            endpoint = f"/docs/{self.doc_id}/tables/{self.health_check_table_id}/rows"
            result = self._make_request("GET", endpoint)
            if result:
                print(f"✅ Health check table accessible - {len(result.get('items', []))} rows")
            else:
                print("❌ Health check table not accessible")
                return False
        
        # Test blocker table access
        if self.blocker_table_id:
            endpoint = f"/docs/{self.doc_id}/tables/{self.blocker_table_id}/rows"
            result = self._make_request("GET", endpoint)
            if result:
                print(f"✅ Blocker table accessible - {len(result.get('items', []))} rows")
            else:
                print("❌ Blocker table not accessible")
                return False
        
        print("✅ Coda connection test successful")
        return True
    
    def add_standup_response(self, user_id, response_text, timestamp=None, username=None, is_late=False):
        """Add a standup response to the standup table."""
        if not self.standup_table_id:
            print("❌ Standup table ID not configured")
            return False
            
        if timestamp is None:
            timestamp = datetime.now().isoformat()
            
        if username is None:
            username = user_id
            
        # Prepare cells for the row
        cells = [
            {"column": "User ID", "value": user_id},
            {"column": "Name", "value": username},
            {"column": "Response", "value": response_text},
            {"column": "Timestamp", "value": timestamp}
        ]
        
        # Add late tag if check-in is late
        if is_late:
            cells.append({"column": "Status", "value": "Late"})
        
        data = {
            "rows": [{
                "cells": cells
            }]
        }
        
        endpoint = f"/docs/{self.doc_id}/tables/{self.standup_table_id}/rows"
        result = self._make_request("POST", endpoint, data)
        
        if result:
            print(f"✅ Standup response stored in Coda: {result.get('id', 'unknown')}")
            return True
        else:
            print("❌ Failed to store standup response in Coda")
            return False
    
    def search_kr_table(self, search_term):
        """Search all 16 KR tables for a KR/assignment name."""
        # Strip asterisk prefix if present
        original_search_term = search_term
        if search_term.startswith('* '):
            search_term = search_term[2:]  # Remove "* " prefix
            print(f"🔍 DEBUG: search_kr_table - Stripped asterisk prefix, now searching for: '{search_term}'")

        # Table IDs for all 16 KR tables
        kr_table_ids = []
        for i in range(1, 17):  # 1 to 16
            if i == 1:
                env_var = "KR_Table"  # First table is just "KR_Table"
            else:
                env_var = f"KR_Table{i}"  # Tables 2-16 are "KR_Table2", "KR_Table3", etc.
            
            table_id = os.environ.get(env_var)
            if table_id:
                kr_table_ids.append(table_id)
                print(f"🔍 DEBUG: Added KR table {env_var}: {table_id}")
            else:
                print(f"🔍 DEBUG: KR table {env_var} not found in environment variables")
        
        doc_id = self.doc_id
        all_matches = []

        # Helper to search a table for KR name
        def search_table(table_id):
            if not table_id:
                return []
            
            # First, get the table schema to find the KR name column
            schema_endpoint = f"/docs/{doc_id}/tables/{table_id}"
            schema_result = self._make_request("GET", schema_endpoint)
            if not schema_result:
                print(f"❌ Could not get schema for table {table_id}")
                return []
            
            # Get the columns from the table
            columns_endpoint = f"/docs/{doc_id}/tables/{table_id}/columns"
            columns_result = self._make_request("GET", columns_endpoint)
            if not columns_result:
                print(f"❌ Could not get columns for table {table_id}")
                return []
            
            # Find the KR name column (usually the first column or one with a descriptive name)
            kr_name_column = None
            columns = columns_result.get("items", [])
            
            # Look for common KR name column patterns
            for col in columns:
                col_name = col.get("name", "").lower()
                if any(keyword in col_name for keyword in ["key result", "kr", "name", "title", "description"]):
                    kr_name_column = col.get("id")
                    print(f"🔍 DEBUG: Found KR name column '{col.get('name')}' with ID '{kr_name_column}' in table {table_id}")
                    break
            
            # If no specific column found, use the display column (usually the main name column)
            if not kr_name_column:
                display_column = schema_result.get("displayColumn", {})
                if display_column:
                    kr_name_column = display_column.get("id")
                    print(f"🔍 DEBUG: Using display column '{display_column.get('name', 'Unknown')}' with ID '{kr_name_column}' in table {table_id}")
            
            # If still no column found, use the first column
            if not kr_name_column and columns:
                kr_name_column = columns[0].get("id")
                print(f"🔍 DEBUG: Using first column '{columns[0].get('name')}' with ID '{kr_name_column}' in table {table_id}")
            
            if not kr_name_column:
                print(f"❌ Could not find KR name column in table {table_id}")
                return []
            
            # Now search the table
            endpoint = f"/docs/{doc_id}/tables/{table_id}/rows"
            result = self._make_request("GET", endpoint)
            if not result:
                return []
            
            matches = []
            for row in result.get("items", []):
                cells = row.get("values", {})
                kr_name = cells.get(kr_name_column, "")
                if search_term.lower().strip() == kr_name.lower().strip():
                    # Return the full row with ID and cells
                    match_data = {
                        "id": row.get("id"),  # Include the row ID
                        "table_id": table_id,  # Include the table ID
                        **cells  # Include all the cell values
                    }
                    matches.append(match_data)
                    print(f"🔍 DEBUG: Found match in table {table_id}: '{kr_name}' (row ID: {row.get('id')})")
            
            return matches

        # Search all 16 KR tables
        for table_id in kr_table_ids:
            all_matches.extend(search_table(table_id))

        print(f"🔍 DEBUG: search_kr_table found {len(all_matches)} total matches for '{search_term}'")
        return all_matches

    def add_health_check_explanation(self, user_id, username, health_check_response, explanation):
        """Add health check explanation to After_Health_Check table."""
        after_health_check_table_id = os.environ.get("CODA_TABLE_ID5", "grid-akF8i4kCU3")  # After_Health_Check table
        if not after_health_check_table_id:
            print("❌ After Health Check table ID (CODA_TABLE_ID5) not configured")
            return False
        
        endpoint = f"/docs/{self.doc_id}/tables/{after_health_check_table_id}/rows"
        
        # Prepare the row data for After_Health_Check table
        # Table has columns: Name, Response, Timestamp
        # Using username instead of user_id for better readability
        row_data = {
            "rows": [{
                "cells": [
                    {"column": "Name", "value": username},
                    {"column": "Response", "value": explanation},
                    {"column": "Timestamp", "value": datetime.now().isoformat()}
                ]
            }]
        }
        
        try:
            result = self._make_request("POST", endpoint, data=row_data)
            if result:
                print(f"✅ Health check explanation added to Coda for {username}")
                return True
            else:
                print(f"❌ Failed to add health check explanation to Coda for {username}")
                return False
        except Exception as e:
            print(f"❌ Error adding health check explanation to Coda: {e}")
            return False
    
    def find_kr_row(self, kr_name):
        """Find a specific KR row in the KR table by name using fuzzy matching."""
        print(f"🔍 DEBUG: find_kr_row called with kr_name: '{kr_name}'")
        
        # Strip asterisk prefix if present
        original_kr_name = kr_name
        if kr_name.startswith('* '):
            kr_name = kr_name[2:]  # Remove "* " prefix
            print(f"🔍 DEBUG: Stripped asterisk prefix, now searching for: '{kr_name}'")
        
        kr_table_id = os.environ.get("KR_Table")
        if not kr_table_id:
            print("❌ KR table ID (KR_Table) not configured")
            return None
        
        endpoint = f"/docs/{self.doc_id}/tables/{kr_table_id}/rows"
        result = self._make_request("GET", endpoint)
        
        if not result:
            print("❌ No result from Coda API")
            return None
        
        print(f"🔍 DEBUG: Found {len(result.get('items', []))} rows in KR table")
        
        # Search for the KR by name with fuzzy matching
        best_match = None
        best_ratio = 0
        search_name_lower = kr_name.lower().strip()
        
        for row in result.get("items", []):
            cells = row.get("values", {})
            current_kr_name = cells.get("c-yQ1M6UqTSj", "")  # Coda column ID for 'Key Result'
            current_name_lower = current_kr_name.lower().strip()
            
            print(f"🔍 DEBUG: Checking row with KR name: '{current_kr_name}' against search: '{kr_name}'")
            
            # Exact match (highest priority)
            if kr_name.lower() == current_kr_name.lower():
                print(f"🔍 DEBUG: Exact match found!")
                return row
            
            # Fuzzy match using similarity calculation
            if current_name_lower and search_name_lower:
                # Calculate similarity ratio
                similarity = self._calculate_similarity(search_name_lower, current_name_lower)
                
                if similarity > best_ratio:
                    best_ratio = similarity
                    best_match = row
                    print(f"🔍 DEBUG: New best match found with {similarity:.2%} similarity")
        
        # Return best match if it meets the 100% threshold (perfect match)
        if best_match and best_ratio >= 1.0:
            print(f"🔍 DEBUG: Perfect match found with {best_ratio:.2%} similarity!")
            return best_match
        
        print(f"🔍 DEBUG: No matches found for '{kr_name}' (best match was {best_ratio:.2%})")
        return None
    
    def _calculate_similarity(self, str1, str2):
        """Calculate similarity between two strings using a comprehensive algorithm."""
        if not str1 or not str2:
            return 0.0
        
        # Simple similarity calculation
        # Count common words and character sequences
        words1 = set(str1.split())
        words2 = set(str2.split())
        
        if not words1 and not words2:
            return 1.0  # Both empty
        if not words1 or not words2:
            return 0.0  # One empty
        
        # Word overlap
        common_words = words1.intersection(words2)
        word_similarity = len(common_words) / max(len(words1), len(words2))
        
        # Character sequence similarity (for partial matches)
        char_similarity = 0.0
        if len(str1) > 3 and len(str2) > 3:
            # Check for substring matches
            if str1 in str2 or str2 in str1:
                char_similarity = min(len(str1), len(str2)) / max(len(str1), len(str2))
            else:
                # Check for common character sequences
                common_chars = 0
                for i in range(min(len(str1), len(str2))):
                    if str1[i] == str2[i]:
                        common_chars += 1
                char_similarity = common_chars / max(len(str1), len(str2))
        
        # Combine word and character similarity
        total_similarity = (word_similarity * 0.7) + (char_similarity * 0.3)
        
        return total_similarity
    
    def get_kr_display_info(self, kr_name):
        """Get KR information for display without updating anything."""
        kr_table_id = os.environ.get("KR_Table")
        if not kr_table_id:
            print("❌ KR table ID (KR_Table) not configured")
            return None
        
        # Find the KR row
        kr_row = self.find_kr_row(kr_name)
        if not kr_row:
            print(f"❌ KR '{kr_name}' not found in table")
            return None
        
        cells = kr_row.get("values", {})
        
        # Get the relevant information for display
        display_info = {
            "kr_name": cells.get("c-yQ1M6UqTSj", ""),  # Key Result column
            "owner": cells.get("c-efR-vVo_3w", ""),  # Owner column ID from logs
            "status": cells.get("c-cC29Yow8Gr", ""),  # Status column ID from logs
            "progress": cells.get("c--I8Kuqx_r3", ""),  # Progress column
            "notes": cells.get("c-whRefnNl8_", ""),  # Notes column
            "objective": cells.get("c-xKQ-IBpkKj", ""),  # Objective column
            "sprint": cells.get("c-AoFx_T0QNk", ""),  # Sprint column
            "predicted_hours": cells.get("c--d7eE74QvA", ""),  # Predicted Hours column
            "urgency": cells.get("c-4hZOppJ3oL", ""),  # TAGS column (urgency)
            "people": cells.get("c-HUmYflQiu4", ""),  # People column
            "definition_of_done": cells.get("c-P_mQJLObL0", ""),  # Definition of Done column
        }
        
        print(f"✅ Found KR '{kr_name}' for display")
        return display_info
    
    def get_kr_details(self, kr_name):
        """Get detailed information about a specific KR."""
        try:
            if not self.kr_table_id:
                print("❌ KR table ID not configured")
                return None
            
            # Get column mapping
            column_map = self.get_column_id_map(self.kr_table_id)
            if not column_map:
                print("❌ Could not get column mapping for KR table")
                return None
            
            kr_row = self.find_kr_row(kr_name)
            if not kr_row:
                print(f"❌ KR row not found for '{kr_name}'")
                return None
            
            cells = kr_row.get("values", {})
            
            result = {
                "row_id": kr_row.get("id"),
                "kr_name": cells.get(column_map.get("Key Result", ""), ""),
                "owner": cells.get(column_map.get("Owner", ""), ""),
                "status": cells.get(column_map.get("Status", ""), ""),
                "definition_of_done": cells.get(column_map.get("Definition of Done", ""), ""),
                "target_date": cells.get(column_map.get("Target Date", ""), ""),
                "progress": cells.get(column_map.get("Progress", ""), ""),
                "notes": cells.get(column_map.get("Notes", ""), "")
            }
            
            return result
            
        except Exception as e:
            print(f"❌ Error getting KR details: {e}")
            return None
    
    def list_kr_table_columns(self):
        """List all columns in the KR table for debugging."""
        kr_table_id = os.environ.get("KR_Table")
        if not kr_table_id:
            print("❌ KR table ID (KR_Table) not configured")
            return None
        
        endpoint = f"/docs/{self.doc_id}/tables/{kr_table_id}"
        result = self._make_request("GET", endpoint)
        
        if result:
            print("🔍 DEBUG: KR Table Structure:")
            # The response structure is different - let's check what we actually get
            print(f"🔍 DEBUG: Full table response: {result}")
            
            # Try to get columns from the response
            if isinstance(result, dict):
                # Look for columns in the response
                if "displayColumn" in result:
                    display_col = result["displayColumn"]
                    if isinstance(display_col, dict):
                        print(f"   Display Column: {display_col.get('name', 'Unknown')} - ID: {display_col.get('id', 'Unknown')}")
                    elif isinstance(display_col, list):
                        for column in display_col:
                            if isinstance(column, dict):
                                print(f"   Column: {column.get('name', 'Unknown')} - ID: {column.get('id', 'Unknown')}")
                else:
                    print("   No displayColumn found in response")
            return result
        else:
            print("❌ Failed to get KR table structure")
            return None 

    def _get_display_name(self, slack_client, user_id):
        """Helper method to get display name from Slack user ID."""
        try:
            user_info = slack_client.users_info(user=user_id)
            if user_info.get("ok"):
                return user_info["user"].get("real_name", "")
        except Exception as e:
            print(f"🔍 DEBUG: Error getting display name for {user_id}: {e}")
        return "" 

    def get_user_blockers(self, user_id):
        """Get active blockers for a specific user (excluding resolved ones)."""
        if not self.blocker_table_id:
            print("❌ Blocker table ID not configured")
            return []
        
        # First get the column mapping
        column_map = self.get_column_id_map(self.blocker_table_id)
        if not column_map:
            print("❌ Could not get column mapping for blocker table")
            return []
        
        endpoint = f"/docs/{self.doc_id}/tables/{self.blocker_table_id}/rows"
        result = self._make_request("GET", endpoint)
        if not result:
            return []
        
        blockers = []
        for row in result.get("items", []):
            cells = row.get("values", {})
            
            # Get user ID from the correct column
            user_id_col = column_map.get("User ID") or column_map.get("Name")
            if not user_id_col:
                print("❌ Could not find User ID or Name column in blocker table")
                continue
                
            # Check if this row belongs to the user
            if cells.get(user_id_col, "") == user_id:
                # Check if this blocker is resolved (has resolution notes)
                resolution_col = column_map.get("Resolution", "")
                resolution_notes = cells.get(resolution_col, "")
                
                # Check resolution timestamp for 24-hour grace period
                resolution_timestamp_col = column_map.get("Resolution Timestamp", "")
                resolution_timestamp = cells.get(resolution_timestamp_col, "")
                
                # Only include blockers that:
                # 1. Don't have resolution notes (unresolved), OR
                # 2. Have resolution notes but were resolved less than 24 hours ago
                should_include = False
                
                if not resolution_notes:
                    # Unresolved blocker - always include
                    should_include = True
                elif resolution_timestamp:
                    # Resolved blocker - check if within 24-hour grace period
                    from datetime import datetime, timedelta
                    try:
                        resolved_time = datetime.fromisoformat(resolution_timestamp.replace('Z', '+00:00'))
                        current_time = datetime.now(resolved_time.tzinfo)
                        time_diff = current_time - resolved_time
                        
                        # Include if resolved less than 24 hours ago
                        if time_diff < timedelta(hours=24):
                            should_include = True
                            print(f"🔍 Including recently resolved blocker (resolved {time_diff.total_seconds()/3600:.1f} hours ago)")
                    except Exception as e:
                        print(f"❌ Error parsing resolution timestamp: {e}")
                        # If timestamp parsing fails, include the blocker to be safe
                        should_include = True
                
                if should_include:
                    blockers.append({
                        "user_id": cells.get(user_id_col, ""),
                        "blocker_description": cells.get(column_map.get("Blocker Description", ""), ""),
                        "kr_name": cells.get(column_map.get("KR Name", ""), ""),
                        "urgency": cells.get(column_map.get("Urgency", ""), ""),
                        "notes": cells.get(column_map.get("Notes", ""), ""),
                        "row_id": row.get("id", "")
                    })
        
        print(f"🔍 DEBUG: Found {len(blockers)} active blockers for user {user_id}")
        return blockers

    def get_user_blockers_by_sprint(self, user_id, sprint_number=None):
        """Get active blockers for a specific user, optionally filtered by sprint number."""
        if not self.blocker_table_id:
            print("❌ Blocker table ID not configured")
            return []
        
        # First get the column mapping
        column_map = self.get_column_id_map(self.blocker_table_id)
        if not column_map:
            print("❌ Could not get column mapping for blocker table")
            return []
        
        endpoint = f"/docs/{self.doc_id}/tables/{self.blocker_table_id}/rows"
        result = self._make_request("GET", endpoint)
        if not result:
            return []
        
        blockers = []
        for row in result.get("items", []):
            cells = row.get("values", {})
            
            # Get user ID from the correct column
            user_id_col = column_map.get("User ID") or column_map.get("Name")
            if not user_id_col:
                print("❌ Could not find User ID or Name column in blocker table")
                continue
                
            # Check if this row belongs to the user
            if cells.get(user_id_col, "") == user_id:
                # Check if this blocker is resolved (has resolution notes)
                resolution_col = column_map.get("Resolution", "")
                resolution_notes = cells.get(resolution_col, "")
                
                # Check resolution timestamp for 24-hour grace period
                resolution_timestamp_col = column_map.get("Resolution Timestamp", "")
                resolution_timestamp = cells.get(resolution_timestamp_col, "")
                
                # Only include blockers that:
                # 1. Don't have resolution notes (unresolved), OR
                # 2. Have resolution notes but were resolved less than 24 hours ago
                should_include = False
                
                if not resolution_notes:
                    # Unresolved blocker - always include
                    should_include = True
                elif resolution_timestamp:
                    # Resolved blocker - check if within 24-hour grace period
                    from datetime import datetime, timedelta
                    try:
                        resolved_time = datetime.fromisoformat(resolution_timestamp.replace('Z', '+00:00'))
                        current_time = datetime.now(resolved_time.tzinfo)
                        time_diff = current_time - resolved_time
                        
                        # Include if resolved less than 24 hours ago
                        if time_diff < timedelta(hours=24):
                            should_include = True
                            print(f"🔍 Including recently resolved blocker (resolved {time_diff.total_seconds()/3600:.1f} hours ago)")
                    except Exception as e:
                        print(f"❌ Error parsing resolution timestamp: {e}")
                        # If timestamp parsing fails, include the blocker to be safe
                        should_include = True
                
                if should_include:
                    kr_name = cells.get(column_map.get("KR Name", ""), "")
                    
                    # If sprint number is provided, filter by it
                    if sprint_number and kr_name:
                        # Check if sprint number appears in the KR name
                        sprint_in_kr = f"Sprint {sprint_number}" in kr_name or f"Sprint {sprint_number} " in kr_name
                        if not sprint_in_kr:
                            continue
                    
                    blockers.append({
                        "user_id": cells.get(user_id_col, ""),
                        "blocker_description": cells.get(column_map.get("Blocker Description", ""), ""),
                        "kr_name": kr_name,
                        "urgency": cells.get(column_map.get("Urgency", ""), ""),
                        "notes": cells.get(column_map.get("Notes", ""), ""),
                        "row_id": row.get("id", ""),
                        "sprint_number": sprint_number
                    })
        
        print(f"🔍 DEBUG: Found {len(blockers)} active blockers for user {user_id}" + (f" in Sprint {sprint_number}" if sprint_number else ""))
        return blockers 

    def update_blocker_note(self, row_id, new_note):
        """Update the Notes field for a blocker."""
        if not self.blocker_table_id:
            print("❌ Blocker table ID not configured")
            return False
        endpoint = f"/docs/{self.doc_id}/tables/{self.blocker_table_id}/rows/{row_id}"
        data = {
            "row": {
                "cells": [
                    {"column": "Notes", "value": new_note}
                ]
            }
        }
        result = self._make_request("PUT", endpoint, data)
        return result is not None

    def mark_blocker_complete(self, row_id, resolution_notes=None):
        """Mark a blocker as complete by adding resolution notes and timestamp."""
        if not self.blocker_table_id:
            print("❌ Blocker table ID not configured")
            return False
        
        from datetime import datetime
        
        # Prepare cells to update
        cells = []
        
        # Add resolution notes if provided
        if resolution_notes:
            cells.append({"column": "Resolution", "value": resolution_notes})
        
        # Add resolution timestamp
        resolution_timestamp = datetime.now().isoformat()
        cells.append({"column": "Resolution Timestamp", "value": resolution_timestamp})
        
        # If no resolution notes, there's nothing to update
        if not cells:
            print("⚠️ No resolution notes provided - nothing to update")
            return True
        
        endpoint = f"/docs/{self.doc_id}/tables/{self.blocker_table_id}/rows/{row_id}"
        data = {
            "row": {
                "cells": cells
            }
        }
        result = self._make_request("PUT", endpoint, data)
        return result is not None

    def save_health_check(self, user_id, username, mood, share_text, is_public=True):
        """Save a health check to Coda."""
        if not self.health_check_table_id:
            print("❌ Health check table ID not configured")
            return False
            
        timestamp = datetime.now().isoformat()
            
        # Combine mood and share text into a single response
        response_text = f"{mood}"
        if share_text:
            response_text += f" - {share_text}"
        
        # Use the same structure as add_response
        data = {
            "rows": [{
                "cells": [
                    {"column": "User ID", "value": user_id},
                    {"column": "Name", "value": username},
                    {"column": "Response", "value": response_text},
                    {"column": "Timestamp", "value": timestamp}
                ]
            }]
        }
        
        endpoint = f"/docs/{self.doc_id}/tables/{self.health_check_table_id}/rows"
        result = self._make_request("POST", endpoint, data)
        if result:
            print(f"✅ Health check saved to Coda for {username}")
            return True
        else:
            print(f"❌ Failed to save health check to Coda for {username}")
            return False

    def save_health_check_sharing(self, user_id, username, mood, share_text, is_public=True):
        """Save health check sharing to the After_Health_Check table."""
        if not self.after_health_check_table_id:
            print("❌ After Health Check table ID not configured")
            return False
            
        timestamp = datetime.now().isoformat()
        
        # Combine mood and share text into a single response field
        combined_response = f"{mood}"
        if share_text:
            combined_response += f" - {share_text}"
        
        data = {
            "rows": [{
                "cells": [
                    {"column": "User ID", "value": user_id},
                    {"column": "Name", "value": username},
                    {"column": "Response", "value": combined_response},
                    {"column": "Timestamp", "value": timestamp}
                ]
            }]
        }
        
        endpoint = f"/docs/{self.doc_id}/tables/{self.after_health_check_table_id}/rows"
        result = self._make_request("POST", endpoint, data)
        if result:
            print(f"✅ Health check sharing saved to After_Health_Check table for {username}")
            return True
        else:
            print(f"❌ Failed to save health check sharing to After_Health_Check table for {username}")
            return False
    
    def log_error(self, error_data):
        """Log error to Coda error table."""
        try:
            # Check if error table ID is configured
            if not self.error_table_id or self.error_table_id == "error_logs":
                print("❌ Error table ID not configured - skipping Coda error logging")
                return False
            
            timestamp = datetime.now().isoformat()
            
            # Prepare error data for Coda
            data = {
                "rows": [{
                    "cells": [
                        {"column": "Timestamp", "value": timestamp},
                        {"column": "Error Type", "value": error_data.get('error_type', 'unknown')},
                        {"column": "Context", "value": error_data.get('context', 'unknown')},
                        {"column": "User ID", "value": error_data.get('user_id', 'unknown')},
                        {"column": "Error Message", "value": error_data.get('error_message', 'unknown')},
                        {"column": "Traceback", "value": error_data.get('traceback', '')},
                        {"column": "Additional Data", "value": json.dumps(error_data.get('additional_data', {}))}
                    ]
                }]
            }
            
            endpoint = f"/docs/{self.doc_id}/tables/{self.error_table_id}/rows"
            result = self._make_request("POST", endpoint, data)
            
            if result:
                print(f"✅ Error logged to Coda: {error_data.get('error_type', 'unknown')}")
                return True
            else:
                print(f"❌ Failed to log error to Coda: {error_data.get('error_type', 'unknown')}")
                return False
        
        except Exception as e:
            print(f"❌ Error logging to Coda failed: {e}")
            return False
    
    def update_kr_blocked_status(self, kr_name, is_blocked=True, blocker_context="", reported_by="", reported_by_id=""):
        """Update KR status to 'Blocked' or 'Unblocked' with blocker context and reporter info."""
        try:
            # Search across all KR tables using the same logic as /kr command
            kr_matches = self.search_kr_table(kr_name)
            if not kr_matches:
                print(f"❌ KR '{kr_name}' not found in any KR table")
                return False
            
            # Use the first match found (same logic as /kr command)
            kr_match = kr_matches[0]
            row_id = kr_match.get("id")
            table_id = kr_match.get("table_id")
            
            if not row_id:
                print(f"❌ No row ID found for KR '{kr_name}'")
                return False
            
            if not table_id:
                print(f"❌ No table ID found for KR '{kr_name}'")
                return False
            
            # Get column mapping for the table
            column_map = self.get_column_id_map(table_id)
            if not column_map:
                print(f"❌ Could not get column mapping for table {table_id}")
                return False
            
            # Get current timestamp
            timestamp = datetime.now().isoformat()
            
            # Prepare update data
            update_data = {
                "row": {
                    "cells": []
                }
            }
            
            # Update status
            if is_blocked:
                status_value = "Blocked"
                # Add blocker context and reporter info
                blocker_info = f"Blocked at {timestamp}"
                if reported_by:
                    blocker_info += f" by {reported_by}"
                if blocker_context:
                    blocker_info += f" - Context: {blocker_context}"
                
                # Use column IDs instead of column names
                cells_to_update = []
                
                # Status column
                status_col_id = column_map.get("Status")
                if status_col_id:
                    cells_to_update.append({"column": status_col_id, "value": status_value})
                
                # Blocked At column
                blocked_at_col_id = column_map.get("Blocked At")
                if blocked_at_col_id:
                    cells_to_update.append({"column": blocked_at_col_id, "value": timestamp})
                
                # Blocked By column
                blocked_by_col_id = column_map.get("Blocked By")
                if blocked_by_col_id:
                    cells_to_update.append({"column": blocked_by_col_id, "value": reported_by})
                
                # Blocked By ID column
                blocked_by_id_col_id = column_map.get("Blocked By ID")
                if blocked_by_id_col_id:
                    cells_to_update.append({"column": blocked_by_id_col_id, "value": reported_by_id})
                
                # Blocker Context column
                blocker_context_col_id = column_map.get("Blocker Context")
                if blocker_context_col_id:
                    cells_to_update.append({"column": blocker_context_col_id, "value": blocker_context})
                
                update_data["row"]["cells"] = cells_to_update
            else:
                status_value = "In Progress"  # or whatever the default status should be
                
                # Use column IDs instead of column names
                cells_to_update = []
                
                # Status column
                status_col_id = column_map.get("Status")
                if status_col_id:
                    cells_to_update.append({"column": status_col_id, "value": status_value})
                
                # Unblocked At column
                unblocked_at_col_id = column_map.get("Unblocked At")
                if unblocked_at_col_id:
                    cells_to_update.append({"column": unblocked_at_col_id, "value": timestamp})
                
                # Clear blocked fields
                blocked_at_col_id = column_map.get("Blocked At")
                if blocked_at_col_id:
                    cells_to_update.append({"column": blocked_at_col_id, "value": ""})
                
                blocked_by_col_id = column_map.get("Blocked By")
                if blocked_by_col_id:
                    cells_to_update.append({"column": blocked_by_col_id, "value": ""})
                
                blocked_by_id_col_id = column_map.get("Blocked By ID")
                if blocked_by_id_col_id:
                    cells_to_update.append({"column": blocked_by_id_col_id, "value": ""})
                
                blocker_context_col_id = column_map.get("Blocker Context")
                if blocker_context_col_id:
                    cells_to_update.append({"column": blocker_context_col_id, "value": ""})
                
                update_data["row"]["cells"] = cells_to_update
            
            # Update the row using the correct table ID
            endpoint = f"/docs/{self.doc_id}/tables/{table_id}/rows/{row_id}"
            result = self._make_request("PUT", endpoint, update_data)
            
            if result:
                action = "blocked" if is_blocked else "unblocked"
                print(f"✅ KR '{kr_name}' {action} successfully")
                return True
            else:
                print(f"❌ Failed to update KR '{kr_name}' status")
                return False
                
        except Exception as e:
            print(f"❌ Error updating KR blocked status: {e}")
            return False
    
    def get_kr_blocked_info(self, kr_name):
        """Get blocked information for a specific KR."""
        try:
            # Search across all KR tables using the same logic as /kr command
            kr_matches = self.search_kr_table(kr_name)
            if not kr_matches:
                print(f"❌ KR '{kr_name}' not found in any KR table")
                return None
            
            # Use the first match found (same logic as /kr command)
            kr_match = kr_matches[0]
            cells = kr_match
            
            # Extract blocked information
            blocked_info = {
                "kr_name": kr_name,
                "status": cells.get("Status", ""),
                "blocked_at": cells.get("Blocked At", ""),
                "blocked_by": cells.get("Blocked By", ""),
                "blocked_by_id": cells.get("Blocked By ID", ""),
                "blocker_context": cells.get("Blocker Context", ""),
                "unblocked_at": cells.get("Unblocked At", ""),
                "is_blocked": cells.get("Status", "") == "Blocked"
            }
            
            return blocked_info
            
        except Exception as e:
            print(f"❌ Error getting KR blocked info: {e}")
            return None
    
    def add_blocker_to_kr(self, kr_name, blocker_description, reported_by, reported_by_id, urgency="medium", notes="", sprint_number=None):
        """Add a blocker to a KR and update the KR status to 'Blocked'."""
        try:
            # First, add the blocker to the blocker table
            blocker_success = self.add_blocker(reported_by_id, blocker_description, kr_name, urgency, notes, reported_by, sprint_number)
            
            if not blocker_success:
                print(f"❌ Failed to add blocker to blocker table for KR '{kr_name}'")
                return False
            
            # Then, update the KR status to 'Blocked'
            kr_success = self.update_kr_blocked_status(
                kr_name, 
                is_blocked=True, 
                blocker_context=blocker_description, 
                reported_by=reported_by, 
                reported_by_id=reported_by_id
            )
            
            if not kr_success:
                print(f"❌ Failed to update KR status to 'Blocked' for KR '{kr_name}'")
                return False
            
            print(f"✅ Successfully added blocker to KR '{kr_name}' and updated status")
            return True
            
        except Exception as e:
            print(f"❌ Error adding blocker to KR: {e}")
            return False
    
    def resolve_blocker_from_kr(self, kr_name, resolution_notes="", resolved_by=None, resolved_by_id=None):
        """Resolve a blocker for a KR and update the KR status to 'Unblocked'."""
        try:
            # First, update the KR status to 'Unblocked'
            kr_success = self.update_kr_blocked_status(
                kr_name, 
                is_blocked=False, 
                blocker_context="", 
                reported_by="", 
                reported_by_id=""
            )
            
            if not kr_success:
                print(f"❌ Failed to update KR status to 'Unblocked' for KR '{kr_name}'")
                return False
            
            # Get blocked info to find the original blocker
            blocked_info = self.get_kr_blocked_info(kr_name)
            if blocked_info and blocked_info.get("blocked_by_id"):
                # Try to resolve the original blocker
                blocker_success = self.resolve_blocker(
                    blocked_info["blocked_by_id"], 
                    kr_name, 
                    blocked_info.get("blocker_context", ""), 
                    resolved_by, 
                    resolution_notes, 
                    None, 
                    resolved_by_id
                )
                
                if not blocker_success:
                    print(f"⚠️ KR status updated but failed to resolve original blocker for KR '{kr_name}'")
                    # Still return True since KR status was updated
                    return True
            
            print(f"✅ Successfully resolved blocker for KR '{kr_name}' and updated status")
            return True
            
        except Exception as e:
            print(f"❌ Error resolving blocker from KR: {e}")
            return False 

    def get_blocker_by_id(self, blocker_id):
        """Get blocker details by row ID."""
        try:
            if not self.blocker_table_id:
                print("❌ Blocker table ID not configured")
                return None
            
            endpoint = f"/docs/{self.doc_id}/tables/{self.blocker_table_id}/rows/{blocker_id}"
            result = self._make_request("GET", endpoint)
            
            if result:
                cells = result.get("values", {})
                return {
                    "row_id": blocker_id,
                "user_id": cells.get("User ID", ""),
                "username": cells.get("Name", ""),
                    "blocker_description": cells.get("Blocker Description", ""),
                    "kr_name": cells.get("KR Name", ""),
                    "urgency": cells.get("Urgency", ""),
                    "notes": cells.get("Notes", ""),
                    "status": cells.get("Status", "")
                }
            else:
                print(f"❌ Blocker with ID {blocker_id} not found")
                return None
                
        except Exception as e:
            print(f"❌ Error getting blocker by ID: {e}")
            return None

    def update_blocker_progress(self, blocker_row_id, progress_update, updated_by):
        """Update blocker with progress information."""
        try:
            if not self.blocker_table_id:
                print("❌ Blocker table ID not configured")
                return False
            
            # Get current blocker data
            current_data = self.get_blocker_by_id(blocker_row_id)
            if not current_data:
                print(f"❌ Blocker with ID {blocker_row_id} not found")
                return False
            
            # Prepare update data
            timestamp = datetime.now().isoformat()
            update_data = {
                "row": {
                    "cells": [
                        {
                            "column": "Progress Updates",
                            "value": f"{timestamp} - {updated_by}: {progress_update}"
                        }
                    ]
                }
            }
            
            # Update the blocker row
            endpoint = f"/docs/{self.doc_id}/tables/{self.blocker_table_id}/rows/{blocker_row_id}"
            result = self._make_request("PUT", endpoint, update_data)
            
            if result:
                print(f"✅ Progress update saved for blocker {blocker_row_id}")
                return True
            else:
                print(f"❌ Failed to save progress update for blocker {blocker_row_id}")
                return False
                
        except Exception as e:
            print(f"❌ Error updating blocker progress: {e}")
            return False 

    def get_unresolved_blockers(self):
        """Get all unresolved blockers from the blocker table."""
        try:
            if not self.blocker_table_id:
                print("❌ Blocker table ID not configured")
                return []
            
            # Get all rows from the blocker table
            endpoint = f"/docs/{self.doc_id}/tables/{self.blocker_table_id}/rows"
            response = self._make_request("GET", endpoint)
            
            if not response:
                print("❌ Failed to get blockers from Coda")
                return []
            
            unresolved_blockers = []
            for row in response.get('items', []):
                values = row.get('values', {})
                
                # Check if this blocker is unresolved (no resolution date/status)
                # Assuming there's a "Status" or "Resolved" column
                status = values.get('Status', '').lower() if 'Status' in values else ''
                resolved_date = values.get('Resolved Date', '') if 'Resolved Date' in values else ''
                
                # Consider unresolved if status is not "resolved" and no resolved date
                if 'resolved' not in status and not resolved_date:
                    blocker_data = {
                        'user_id': values.get('c-lGMsICF2m5', ''),  # Slack User ID column
                        'name': values.get('c-p08eiwzXzi', ''),  # Name column
                        'blocker_description': values.get('c-5kx3DHy-cr', ''),  # Blocker Description column
                        'kr_name': values.get('c-QPxAzx5UW1', ''),  # KR Name column
                        'urgency': values.get('c-oMV3tnVN6q', 'medium'),  # Urgency column
                        'notes': values.get('c-KHoCKe5qjS', ''),  # Notes column
                        'created_at': row.get('createdAt', ''),
                        'row_id': row.get('id', '')
                    }
                    unresolved_blockers.append(blocker_data)
            
            print(f"✅ Found {len(unresolved_blockers)} unresolved blockers in Coda")
            return unresolved_blockers
            
        except Exception as e:
            print(f"❌ Error getting unresolved blockers: {e}")
            return [] 

