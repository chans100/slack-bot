from slack_sdk.errors import SlackApiError


class KRManager:
    """Manages Key Results (KR) functionality including search, tracking, and status updates."""
    
    def __init__(self, bot):
        self.bot = bot
        # Track KR name mappings for sanitized button values
        self.kr_name_mappings = {}  # Map sanitized names to original names
    
    def search_kr_table(self, search_term):
        """Search for KRs in the Coda table."""
        try:
            if not self.bot.coda:
                print("❌ Coda service not available")
                return []
            
            # Search in KR table
            matches = self.bot.coda.search_kr_table(search_term)
            if matches:
                print(f"✅ Found {len(matches)} matching KRs for '{search_term}'")
                return matches
            else:
                print(f"⚠️ No KRs found matching '{search_term}'")
                return []
                
        except Exception as e:
            print(f"❌ Error searching KR table: {e}")
            return []
    
    def get_kr_details(self, kr_name):
        """Get detailed information about a specific KR."""
        try:
            if not self.bot.coda:
                print("❌ Coda service not available")
                return None
            
            kr_details = self.bot.coda.get_kr_details(kr_name)
            if kr_details:
                print(f"✅ Retrieved KR details for '{kr_name}'")
                return kr_details
            else:
                print(f"⚠️ KR '{kr_name}' not found")
                return None
                
        except Exception as e:
            print(f"❌ Error getting KR details: {e}")
            return None
    
    def get_kr_display_info(self, kr_name):
        """Get KR information formatted for display."""
        try:
            if not self.bot.coda:
                print("❌ Coda service not available")
                return None
            
            kr_info = self.bot.coda.get_kr_display_info(kr_name)
            if kr_info:
                print(f"✅ Retrieved KR display info for '{kr_name}'")
                return kr_info
            else:
                print(f"⚠️ KR display info not found for '{kr_name}'")
                return None
                
        except Exception as e:
            print(f"❌ Error getting KR display info: {e}")
            return None
    
    def update_kr_status(self, kr_name, new_status, updated_by=None):
        """Update the status of a KR."""
        try:
            if not self.bot.coda:
                print("❌ Coda service not available")
                return False
            
            success = self.bot.coda.update_kr_status(kr_name, new_status, updated_by)
            if success:
                print(f"✅ Updated KR '{kr_name}' status to '{new_status}'")
                return True
            else:
                print(f"❌ Failed to update KR '{kr_name}' status")
                return False
                
        except Exception as e:
            print(f"❌ Error updating KR status: {e}")
            return False
    
    def assign_kr_helper(self, kr_name, helper_id, helper_name):
        """Assign a helper to a KR."""
        try:
            if not self.bot.coda:
                print("❌ Coda service not available")
                return False
            
            success = self.bot.coda.assign_kr_helper(kr_name, helper_id, helper_name)
            if success:
                print(f"✅ Assigned {helper_name} as helper for KR '{kr_name}'")
                return True
            else:
                print(f"❌ Failed to assign helper for KR '{kr_name}'")
                return False
                
        except Exception as e:
            print(f"❌ Error assigning KR helper: {e}")
            return False
    
    def get_kr_progress(self, kr_name):
        """Get progress information for a KR."""
        try:
            if not self.bot.coda:
                print("❌ Coda service not available")
                return None
            
            progress = self.bot.coda.get_kr_progress(kr_name)
            if progress is not None:
                print(f"✅ Retrieved progress for KR '{kr_name}': {progress}%")
                return progress
            else:
                print(f"⚠️ Progress not found for KR '{kr_name}'")
                return None
                
        except Exception as e:
            print(f"❌ Error getting KR progress: {e}")
            return None
    
    def update_kr_progress(self, kr_name, new_progress, updated_by=None):
        """Update the progress of a KR."""
        try:
            if not self.bot.coda:
                print("❌ Coda service not available")
                return False
            
            success = self.bot.coda.update_kr_progress(kr_name, new_progress, updated_by)
            if success:
                print(f"✅ Updated KR '{kr_name}' progress to {new_progress}%")
                return True
            else:
                print(f"❌ Failed to update KR '{kr_name}' progress")
                return False
                
        except Exception as e:
            print(f"❌ Error updating KR progress: {e}")
            return False
    
    def get_kr_assignees(self, kr_name):
        """Get users assigned to a specific KR."""
        try:
            if not self.bot.coda:
                print("❌ Coda service not available")
                return []
            
            assignees = self.bot.coda.get_kr_assignees(kr_name)
            if assignees:
                print(f"✅ Retrieved {len(assignees)} assignees for KR '{kr_name}'")
                return assignees
            else:
                print(f"⚠️ No assignees found for KR '{kr_name}'")
                return []
                
        except Exception as e:
            print(f"❌ Error getting KR assignees: {e}")
            return []
    
    def assign_kr_owner(self, kr_name, owner_id, owner_name):
        """Assign an owner to a KR."""
        try:
            if not self.bot.coda:
                print("❌ Coda service not available")
                return False
            
            success = self.bot.coda.assign_kr_owner(kr_name, owner_id, owner_name)
            if success:
                print(f"✅ Assigned {owner_name} as owner for KR '{kr_name}'")
                return True
            else:
                print(f"❌ Failed to assign owner for KR '{kr_name}'")
                return False
                
        except Exception as e:
            print(f"❌ Error assigning KR owner: {e}")
            return False
    
    def get_kr_notes(self, kr_name):
        """Get notes for a KR."""
        try:
            if not self.bot.coda:
                print("❌ Coda service not available")
                return None
            
            notes = self.bot.coda.get_kr_notes(kr_name)
            if notes:
                print(f"✅ Retrieved notes for KR '{kr_name}'")
                return notes
            else:
                print(f"⚠️ No notes found for KR '{kr_name}'")
                return None
                
        except Exception as e:
            print(f"❌ Error getting KR notes: {e}")
            return None
    
    def update_kr_notes(self, kr_name, new_notes, updated_by=None):
        """Update notes for a KR."""
        try:
            if not self.bot.coda:
                print("❌ Coda service not available")
                return False
            
            success = self.bot.coda.update_kr_notes(kr_name, new_notes, updated_by)
            if success:
                print(f"✅ Updated notes for KR '{kr_name}'")
                return True
            else:
                print(f"❌ Failed to update notes for KR '{kr_name}'")
                return False
                
        except Exception as e:
            print(f"❌ Error updating KR notes: {e}")
            return False
    
    def get_kr_urgency(self, kr_name):
        """Get urgency level for a KR."""
        try:
            if not self.bot.coda:
                print("❌ Coda service not available")
                return None
            
            urgency = self.bot.coda.get_kr_urgency(kr_name)
            if urgency:
                print(f"✅ Retrieved urgency for KR '{kr_name}': {urgency}")
                return urgency
            else:
                print(f"⚠️ Urgency not found for KR '{kr_name}'")
                return None
                
        except Exception as e:
            print(f"❌ Error getting KR urgency: {e}")
            return None
    
    def update_kr_urgency(self, kr_name, new_urgency, updated_by=None):
        """Update urgency level for a KR."""
        try:
            if not self.bot.coda:
                print("❌ Coda service not available")
                return False
            
            success = self.bot.coda.update_kr_urgency(kr_name, new_urgency, updated_by)
            if success:
                print(f"✅ Updated urgency for KR '{kr_name}' to '{new_urgency}'")
                return True
            else:
                print(f"❌ Failed to update urgency for KR '{kr_name}'")
                return False
                
        except Exception as e:
            print(f"❌ Error updating KR urgency: {e}")
            return False
    
    def get_kr_sprint(self, kr_name):
        """Get sprint information for a KR."""
        try:
            if not self.bot.coda:
                print("❌ Coda service not available")
                return None
            
            sprint = self.bot.coda.get_kr_sprint(kr_name)
            if sprint:
                print(f"✅ Retrieved sprint for KR '{kr_name}': {sprint}")
                return sprint
            else:
                print(f"⚠️ Sprint not found for KR '{kr_name}'")
                return None
                
        except Exception as e:
            print(f"❌ Error getting KR sprint: {e}")
            return None
    
    def assign_kr_sprint(self, kr_name, sprint_name, updated_by=None):
        """Assign a KR to a sprint."""
        try:
            if not self.bot.coda:
                print("❌ Coda service not available")
                return False
            
            success = self.bot.coda.assign_kr_sprint(kr_name, sprint_name, updated_by)
            if success:
                print(f"✅ Assigned KR '{kr_name}' to sprint '{sprint_name}'")
                return True
            else:
                print(f"❌ Failed to assign KR '{kr_name}' to sprint")
                return False
                
        except Exception as e:
            print(f"❌ Error assigning KR to sprint: {e}")
            return False
    
    def get_kr_predicted_hours(self, kr_name):
        """Get predicted hours for a KR."""
        try:
            if not self.bot.coda:
                print("❌ Coda service not available")
                return None
            
            hours = self.bot.coda.get_kr_predicted_hours(kr_name)
            if hours is not None:
                print(f"✅ Retrieved predicted hours for KR '{kr_name}': {hours}")
                return hours
            else:
                print(f"⚠️ Predicted hours not found for KR '{kr_name}'")
                return None
                
        except Exception as e:
            print(f"❌ Error getting KR predicted hours: {e}")
            return None
    
    def update_kr_predicted_hours(self, kr_name, new_hours, updated_by=None):
        """Update predicted hours for a KR."""
        try:
            if not self.bot.coda:
                print("❌ Coda service not available")
                return False
            
            success = self.bot.coda.update_kr_predicted_hours(kr_name, new_hours, updated_by)
            if success:
                print(f"✅ Updated predicted hours for KR '{kr_name}' to {new_hours}")
                return True
            else:
                print(f"❌ Failed to update predicted hours for KR '{kr_name}'")
                return False
                
        except Exception as e:
            print(f"❌ Error updating KR predicted hours: {e}")
            return False
    
    def get_kr_objective(self, kr_name):
        """Get objective information for a KR."""
        try:
            if not self.bot.coda:
                print("❌ Coda service not available")
                return None
            
            objective = self.bot.coda.get_kr_objective(kr_name)
            if objective:
                print(f"✅ Retrieved objective for KR '{kr_name}'")
                return objective
            else:
                print(f"⚠️ Objective not found for KR '{kr_name}'")
                return None
                
        except Exception as e:
            print(f"❌ Error getting KR objective: {e}")
            return None
    
    def get_kr_definition_of_done(self, kr_name):
        """Get definition of done for a KR."""
        try:
            if not self.bot.coda:
                print("❌ Coda service not available")
                return None
            
            dod = self.bot.coda.get_kr_definition_of_done(kr_name)
            if dod:
                print(f"✅ Retrieved definition of done for KR '{kr_name}'")
                return dod
            else:
                print(f"⚠️ Definition of done not found for KR '{kr_name}'")
                return None
                
        except Exception as e:
            print(f"❌ Error getting KR definition of done: {e}")
            return None
    
    def update_kr_definition_of_done(self, kr_name, new_dod, updated_by=None):
        """Update definition of done for a KR."""
        try:
            if not self.bot.coda:
                print("❌ Coda service not available")
                return False
            
            success = self.bot.coda.update_kr_definition_of_done(kr_name, new_dod, updated_by)
            if success:
                print(f"✅ Updated definition of done for KR '{kr_name}'")
                return True
            else:
                print(f"❌ Failed to update definition of done for KR '{kr_name}'")
                return False
                
        except Exception as e:
            print(f"❌ Error updating KR definition of done: {e}")
            return False
    
    def sanitize_kr_name_for_button(self, kr_name):
        """Sanitize KR name for use in button values."""
        try:
            # Remove special characters and spaces, limit length
            sanitized = kr_name.replace(' ', '_').replace('-', '_').replace(':', '_')
            sanitized = ''.join(c for c in sanitized if c.isalnum() or c == '_')
            sanitized = sanitized[:30]  # Limit length
            
            # Store mapping
            self.kr_name_mappings[sanitized] = kr_name
            
            return sanitized
            
        except Exception as e:
            print(f"❌ Error sanitizing KR name: {e}")
            return kr_name[:30] if kr_name else "unknown"
    
    def get_original_kr_name(self, sanitized_name):
        """Get original KR name from sanitized name."""
        return self.kr_name_mappings.get(sanitized_name, sanitized_name)
    
    def generate_kr_explanation(self, kr_name, owner, status, definition_of_done=None):
        """Generate AI explanation for a KR."""
        try:
            explanation = f"This KR is currently {status.lower()}"
            if owner and owner != "Unknown":
                explanation += f" and is owned by {owner}"
            
            if definition_of_done:
                explanation += f". The definition of done includes: {definition_of_done[:100]}..."
            else:
                explanation += "."
            
            return explanation
            
        except Exception as e:
            print(f"Error generating KR explanation: {e}")
            return "Unable to generate explanation."
    
    def format_kr_for_display(self, kr_info):
        """Format KR information for display in Slack."""
        try:
            if not kr_info:
                return "No KR information available."
            
            display_text = f"📊 *KR Information*\n\n"
            display_text += f"**{kr_info.get('name', 'Unknown KR')}**\n"
            display_text += f"• **Owner:** {kr_info.get('owner', 'Unknown')}\n"
            display_text += f"• **Status:** {kr_info.get('status', 'Unknown')}\n"
            display_text += f"• **Progress:** {kr_info.get('progress', 'Unknown')}%\n"
            
            if kr_info.get('objective'):
                display_text += f"• **Objective:** {kr_info.get('objective')}\n"
            
            if kr_info.get('sprint'):
                display_text += f"• **Sprint:** {kr_info.get('sprint')}\n"
            
            if kr_info.get('predicted_hours'):
                display_text += f"• **Predicted Hours:** {kr_info.get('predicted_hours')}\n"
            
            if kr_info.get('urgency'):
                display_text += f"• **Urgency:** {kr_info.get('urgency')}\n"
            
            if kr_info.get('helper'):
                display_text += f"• **Helper:** {kr_info.get('helper')}\n"
            
            if kr_info.get('notes'):
                display_text += f"• **Notes:** {kr_info.get('notes')[:100]}...\n"
            
            if kr_info.get('definition_of_done'):
                display_text += f"• **Definition of Done:** {kr_info.get('definition_of_done')[:100]}...\n"
            
            return display_text
            
        except Exception as e:
            print(f"❌ Error formatting KR for display: {e}")
            return "Error formatting KR information." 