"""
Mistral AI Service for the Daily Standup Bot.
Handles AI-powered explanations and responses.
"""

import os
import requests
import json
from typing import Optional, Dict, Any
from src.config import BotConfig

class MistralService:
    """Service for interacting with Mistral AI API."""
    
    def __init__(self):
        """Initialize the Mistral service."""
        self.api_key = BotConfig.MISTRAL_API_KEY
        self.base_url = "https://api.mistral.ai/v1"
        self.model = "mistral-large-latest"  # You can change this to other models
        
        if not self.api_key:
            print("⚠️ Warning: Mistral API key not configured")
    
    def _make_request(self, endpoint: str, data: Dict[str, Any], max_retries: int = 3) -> Optional[Dict[str, Any]]:
        """Make a request to the Mistral API with retry logic."""
        if not self.api_key:
            return None
            
        url = f"{self.base_url}/{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        for attempt in range(max_retries):
            try:
                response = requests.post(url, headers=headers, json=data, timeout=30)
                
                # Handle rate limiting specifically
                if response.status_code == 429:
                    wait_time = (2 ** attempt) * 1  # Exponential backoff: 1s, 2s, 4s
                    print(f"⚠️ Rate limited (429). Waiting {wait_time}s before retry {attempt + 1}/{max_retries}")
                    import time
                    time.sleep(wait_time)
                    continue
                
                response.raise_for_status()
                return response.json()
                
            except requests.exceptions.RequestException as e:
                if attempt == max_retries - 1:  # Last attempt
                    print(f"❌ Error making Mistral API request after {max_retries} attempts: {e}")
                    return None
                else:
                    wait_time = (2 ** attempt) * 1
                    print(f"⚠️ Request failed, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    import time
                    time.sleep(wait_time)
        
        return None
    
    def generate_kr_explanation(self, kr_name: str, owner: str, status: str, 
                               progress: str = "", objective: str = "", definition_of_done: str = "") -> str:
        """Generate a contextual explanation for a KR using Mistral AI."""
        if not self.api_key:
            return f"This is a placeholder explanation for the KR '{kr_name}'. (AI integration needed)"
        
        prompt = f"""
You are an AI assistant helping a team understand their Key Results (KRs). 
Please provide a brief, helpful explanation for this KR:

KR Name: {kr_name}
Owner: {owner}
Status: {status}
Definition of Done: {definition_of_done if definition_of_done else 'Not specified'}
Progress: {progress if progress else "Not specified"}
Objective: {objective if objective else "Not specified"}

Please provide a 1-2 sentence explanation that:
1. Explains what this KR is about in simple terms
2. Provides context about why it's important
3. Suggests what might be needed if there are blockers
4. Refers to the definition of done if relevant

Keep it concise and actionable.
"""
        
        data = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": 200,
            "temperature": 0.7
        }
        
        result = self._make_request("chat/completions", data)
        
        if result and "choices" in result:
            return result["choices"][0]["message"]["content"].strip()
        else:
            # Provide a more helpful fallback based on available information
            if status.lower() in ['todo', 'not started']:
                return f"This KR '{kr_name}' is currently in planning phase. Consider breaking it down into smaller tasks and setting up initial milestones."
            elif status.lower() in ['in progress', 'working']:
                return f"This KR '{kr_name}' is actively being worked on. Regular check-ins and progress updates will help keep it on track."
            elif status.lower() in ['blocked', 'stuck']:
                return f"This KR '{kr_name}' appears to be blocked. Consider reaching out to your team lead or posting in the help channel for assistance."
            else:
                return f"This KR '{kr_name}' is in '{status}' status. Review the definition of done and ensure all requirements are being met."
    
    def generate_help_suggestion(self, blocker_description: str, kr_name: str = "") -> str:
        """Generate helpful suggestions for blockers using Mistral AI."""
        if not self.api_key:
            return "Consider reaching out to your team lead or posting in the help channel."
        
        prompt = f"""
You are an AI assistant helping team members who are blocked on their work.
Please provide helpful, actionable suggestions for this blocker:

Blocker Description: {blocker_description}
Related KR: {kr_name if kr_name else "Not specified"}

Please provide 2-3 specific, actionable suggestions that:
1. Are practical and immediately implementable
2. Consider different approaches to solving the problem
3. Include who they might reach out to for help
4. Are encouraging and supportive

Keep suggestions concise and specific.
"""
        
        data = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": 300,
            "temperature": 0.7
        }
        
        result = self._make_request("chat/completions", data)
        
        if result and "choices" in result:
            return result["choices"][0]["message"]["content"].strip()
        else:
            return "Consider reaching out to your team lead or posting in the help channel."
    
    def analyze_standup_response(self, response_text: str) -> Dict[str, Any]:
        """Analyze a standup response using Mistral AI to extract insights."""
        if not self.api_key:
            return {"sentiment": "neutral", "urgency": "medium", "suggestions": []}
        
        prompt = f"""
You are an AI assistant analyzing daily standup responses.
Please analyze this response and provide insights:

Response: {response_text}

Please provide a JSON response with:
1. "sentiment": positive, neutral, or negative
2. "urgency": low, medium, or high
3. "suggestions": array of 1-2 specific suggestions for follow-up
4. "key_points": array of main points mentioned

Focus on identifying if the person needs help or is doing well.
"""
        
        data = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": 400,
            "temperature": 0.3
        }
        
        result = self._make_request("chat/completions", data)
        
        if result and "choices" in result:
            try:
                content = result["choices"][0]["message"]["content"].strip()
                # Try to parse JSON from the response
                if "{" in content and "}" in content:
                    start = content.find("{")
                    end = content.rfind("}") + 1
                    json_str = content[start:end]
                    return json.loads(json_str)
                else:
                    return {"sentiment": "neutral", "urgency": "medium", "suggestions": [content]}
            except json.JSONDecodeError:
                return {"sentiment": "neutral", "urgency": "medium", "suggestions": [content]}
        else:
            return {"sentiment": "neutral", "urgency": "medium", "suggestions": []}
    
    def test_connection(self) -> bool:
        """Test the connection to Mistral AI."""
        if not self.api_key:
            print("❌ No Mistral API key configured")
            return False
        
        data = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": "Hello, this is a test message."
                }
            ],
            "max_tokens": 10
        }
        
        result = self._make_request("chat/completions", data)
        
        if result:
            print("✅ Mistral AI connection successful")
            return True
        else:
            print("❌ Mistral AI connection failed")
            return False 