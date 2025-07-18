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

# Load environment variables
load_dotenv('.env')

class CodaService:
    """Service class for Coda API operations."""
    
    def __init__(self):
        """Initialize Coda service with API token and table IDs."""
        self.api_token = os.environ.get("CODA_API_TOKEN")
        self.doc_id = os.environ.get("CODA_DOC_ID")
        self.main_table_id = BotConfig.HEALTH_CHECK_TABLE  # Use Health_Check env var
        self.blocker_table_id = os.environ.get("Blocker")
        self.standup_table_id = os.environ.get("Stand_Up")
        self.mentor_table_id = os.environ.get("Mentor_Table")  # New mentor table
        self.blocker_res_table_id = "grid-Kt4x0G2iIM"  # Blocker Resolution table
        
        if not self.api_token:
            print("❌ CODA_API_TOKEN not found in environment variables")
            return
            
        if not self.doc_id:
            print("❌ CODA_DOC_ID not found in environment variables")
            return
            
        if not self.main_table_id:
            print("❌ Health_Check table ID not found in environment variables")
            return
            
        print("✅ Coda service initialized")
        print(f"   Doc ID: {self.doc_id}")
        print(f"   Main Health Check Table ID: {self.main_table_id}")
        print(f"   Blocker Table ID: {self.blocker_table_id}")
        print(f"   Standup Table ID: {self.standup_table_id}")
        print(f"   Mentor Table ID: {self.mentor_table_id}")
        print(f"   Blocker Resolution Table ID: {self.blocker_res_table_id}")
    
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
        """Add a response to the main table."""
        if not self.main_table_id:
            print("❌ Main table ID not configured")
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
        
        endpoint = f"/docs/{self.doc_id}/tables/{self.main_table_id}/rows"
        result = self._make_request("POST", endpoint, data)
        
        if result:
            print(f"✅ Response stored in Coda: {result.get('id', 'unknown')}")
            return True
        else:
            print("❌ Failed to store response in Coda")
            return False
    
    def add_blocker(self, user_id, blocker_description, kr_name, urgency, notes=None, username=None):
        """Add a blocker to the blocker table."""
        print(f"🔍 DEBUG: add_blocker called with:")
        print(f"   - user_id: {user_id}")
        print(f"   - blocker_description: {blocker_description}")
        print(f"   - kr_name: {kr_name}")
        print(f"   - urgency: {urgency}")
        print(f"   - notes: {notes}")
        print(f"   - username: {username}")
        print(f"   - blocker_table_id: {self.blocker_table_id}")
        
        if not self.blocker_table_id:
            print("❌ Blocker table ID not configured")
            return False
            
        if username is None:
            username = user_id
            
        data = {
            "rows": [{
                "cells": [
                    {"column": "User ID", "value": user_id},
                    {"column": "Name", "value": username},
                    {"column": "Blocker Description", "value": blocker_description},
                    {"column": "KR Name", "value": kr_name},
                    {"column": "Urgency", "value": urgency},
                    {"column": "Notes", "value": notes or ""}
                ]
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
        if not self.main_table_id:
            print("❌ Main table ID not configured")
            return []
            
        endpoint = f"/docs/{self.doc_id}/tables/{self.main_table_id}/rows"
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
        if not self.main_table_id:
            print("❌ Main table ID not configured")
            return []
            
        endpoint = f"/docs/{self.doc_id}/tables/{self.main_table_id}/rows"
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
            
        # Test main table access
        if self.main_table_id:
            endpoint = f"/docs/{self.doc_id}/tables/{self.main_table_id}/rows"
            result = self._make_request("GET", endpoint)
            if result:
                print(f"✅ Main table accessible - {len(result.get('items', []))} rows")
            else:
                print("❌ Main table not accessible")
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
    
    def add_standup_response(self, user_id, response_text, timestamp=None, username=None):
        """Add a standup response to the standup table."""
        if not self.standup_table_id:
            print("❌ Standup table ID not configured")
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
                    {"column": "Response", "value": response_text},
                    {"column": "Timestamp", "value": timestamp}
                ]
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
        """Search all four KR tables for a KR/assignment name."""
        # Strip asterisk prefix if present
        original_search_term = search_term
        if search_term.startswith('* '):
            search_term = search_term[2:]  # Remove "* " prefix
            print(f"🔍 DEBUG: search_kr_table - Stripped asterisk prefix, now searching for: '{search_term}'")

        # Table IDs for all four KR tables
        kr_table_ids = []
        for env_var in ["KR_Table", "KR_Table2", "KR_Table3", "KR_Table4"]:
            table_id = os.environ.get(env_var)
            if table_id:
                kr_table_ids.append(table_id)
        doc_id = self.doc_id
        all_matches = []

        # Helper to search a table for KR name
        def search_table(table_id, kr_column):
            if not table_id:
                return []
            endpoint = f"/docs/{doc_id}/tables/{table_id}/rows"
            result = self._make_request("GET", endpoint)
            if not result:
                return []
            matches = []
            for row in result.get("items", []):
                cells = row.get("values", {})
                kr_name = cells.get(kr_column, "")
                if search_term.lower().strip() == kr_name.lower().strip():
                    matches.append(cells)
            return matches

        # Search all four KR tables (assume same column id for now)
        for table_id in kr_table_ids:
            all_matches.extend(search_table(table_id, "c-yQ1M6UqTSj"))

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
        
        kr_table_id = os.environ.get("CODA_TABLE_ID4")
        if not kr_table_id:
            print("❌ KR table ID (CODA_TABLE_ID4) not configured")
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
        kr_table_id = os.environ.get("CODA_TABLE_ID4")
        if not kr_table_id:
            print("❌ KR table ID (CODA_TABLE_ID4) not configured")
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
        print(f"🔍 DEBUG: Getting KR details for '{kr_name}'")
        
        kr_row = self.find_kr_row(kr_name)
        print(f"🔍 DEBUG: find_kr_row returned: {kr_row is not None}")
        if not kr_row:
            print(f"❌ KR row not found for '{kr_name}'")
            return None
        
        cells = kr_row.get("values", {})
        print(f"🔍 DEBUG: Raw cells data: {cells}")
        
        # Use the actual column names from your table
        print(f"🔍 DEBUG: Looking for status in cells with key: Status")
        print(f"🔍 DEBUG: Status value found: {cells.get('Status', 'NOT_FOUND')}")
        
        result = {
            "row_id": kr_row.get("id"),
            "kr_name": cells.get("c-yQ1M6UqTSj", ""),  # Key Result column
            "owner": cells.get("c-efR-vVo_3w", ""),  # Owner column ID from logs
            "status": cells.get("c-cC29Yow8Gr", ""),  # Status column ID from logs
            "helper": "",  # No dedicated helper column, will be in Notes
            "all_cells": cells  # All available cell data
        }
        
        print(f"🔍 DEBUG: KR details result: {result}")
        return result
    
    def list_kr_table_columns(self):
        """List all columns in the KR table for debugging."""
        kr_table_id = os.environ.get("CODA_TABLE_ID4")
        if not kr_table_id:
            print("❌ KR table ID (CODA_TABLE_ID4) not configured")
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

    def add_mentor_check(self, user_id, mentor_response, request_type, timestamp=None, username=None):
        """Add a mentor check response to the mentor table."""
        if not self.mentor_table_id:
            print("❌ Mentor table ID not configured")
            return False
            
        if timestamp is None:
            timestamp = datetime.now().isoformat()
            
        if username is None:
            username = user_id
            
        data = {
            "rows": [{
                "cells": [
                    {"column": "Name", "value": username},
                    {"column": "User ID", "value": user_id},
                    {"column": "Mentor Response", "value": mentor_response},
                    {"column": "Request Type", "value": request_type},
                    {"column": "Timestamp", "value": timestamp}
                ]
            }]
        }
        
        endpoint = f"/docs/{self.doc_id}/tables/{self.mentor_table_id}/rows"
        result = self._make_request("POST", endpoint, data)
        
        if result:
            print(f"✅ Mentor check stored in Coda: {result.get('id', 'unknown')}")
            return True
        else:
            print("❌ Failed to store mentor check in Coda")
            return False
    
    def _get_display_name(self, slack_client, user_id):
        """Helper method to get display name from Slack user ID."""
        try:
            user_info = slack_client.users_info(user=user_id)
            if user_info.get("ok"):
                return user_info["user"].get("real_name", "")
        except Exception as e:
            print(f"🔍 DEBUG: Error getting display name for {user_id}: {e}")
        return ""
    
    def get_mentor_checks_by_date(self, date):
        """Get all mentor checks for a specific date."""
        if not self.mentor_table_id:
            print("❌ Mentor table ID not configured")
            return []
            
        endpoint = f"/docs/{self.doc_id}/tables/{self.mentor_table_id}/rows"
        result = self._make_request("GET", endpoint)
        
        if not result:
            return []
            
        mentor_checks = []
        for row in result.get("items", []):
            cells = row.get("values", {})
            mentor_checks.append({
                "user_id": cells.get("User ID", ""),
                "username": cells.get("Name", ""),
                "mentor_response": cells.get("Mentor Response", ""),
                "request_type": cells.get("Request Type", ""),
                "timestamp": cells.get("Timestamp", "")
            })
        
        return mentor_checks 