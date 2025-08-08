import os
import re
import json
import time
from typing import Dict, List, Optional, Tuple
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from .utils import logger, error_handler, input_validator, safe_executor

class OrgMetadataService:
    """
    Dynamic department/SME determination service using live org metadata with fallback rules.
    
    Features:
    - Extracts department/SME info from Slack user profiles and custom fields
    - Uses AI-powered topic analysis for intelligent routing
    - Implements fallback rules for when metadata is unavailable
    - Caches results to minimize API calls
    - Supports multiple determination strategies
    """
    
    def __init__(self, slack_client: WebClient):
        self.client = slack_client
        self.cache = {}
        self.cache_ttl = 3600  # 1 hour cache
        
        # Department/SME mapping patterns - Updated for actual org structure
        self.department_patterns = {
            'sales': ['sales', 'account', 'business development', 'bd', 'revenue', 'sales engineer', 'sales swe'],
            'engineering': ['engineer', 'developer', 'dev', 'software', 'backend', 'frontend', 'fullstack', 'swe', 'software engineer'],
            'scrum_master': ['scrum master', 'scrum', 'agile', 'sprint', 'task assignment', 'project management'],
            'operations': ['operations', 'ops', 'devops', 'infrastructure', 'platform', 'system admin'],
            'marketing': ['marketing', 'growth', 'seo', 'content', 'social media', 'brand', 'digital marketing'],
            'human_capital': ['hr', 'human resources', 'people', 'talent', 'recruiting', 'human capital', 'people ops'],
            'finance': ['finance', 'accounting', 'fp&a', 'controller', 'cfo', 'financial', 'bookkeeping'],
            'client_service': ['client service', 'customer service', 'support', 'customer success', 'cs', 'help desk', 'technical support', 'client delivery'],
            'executive': ['ceo', 'cto', 'cfo', 'coo', 'vp', 'director', 'head of', 'chief', 'executive']
        }
        
        # SME expertise patterns - Updated for actual org structure
        self.sme_patterns = {
            'sales_engineering': ['sales engineer', 'sales swe', 'technical sales', 'solution architect', 'pre-sales'],
            'software_engineering': ['software engineer', 'swe', 'developer', 'programming', 'coding', 'software development'],
            'agile_management': ['scrum master', 'agile', 'sprint planning', 'task assignment', 'project management'],
            'infrastructure': ['devops', 'aws', 'azure', 'gcp', 'kubernetes', 'docker', 'ci/cd', 'infrastructure', 'system admin'],
            'digital_marketing': ['seo', 'sem', 'social media', 'content marketing', 'email marketing', 'growth', 'digital marketing'],
            'people_operations': ['hr', 'human resources', 'talent acquisition', 'employee relations', 'people ops'],
            'financial_management': ['accounting', 'fp&a', 'financial planning', 'budgeting', 'financial analysis'],
            'client_support': ['customer service', 'technical support', 'client delivery', 'customer success', 'help desk'],
            'executive_leadership': ['executive', 'leadership', 'strategy', 'management', 'decision making']
        }
        
        # Fallback rules for when metadata is unavailable
        self.fallback_rules = {
            'default_department': 'engineering',
            'default_sme': 'engineering',
            'escalation_hierarchy': ['lead', 'manager', 'director', 'vp', 'executive'],
            'channel_mappings': {
                'sales': 'sales-team',
                'engineering': 'engineering-team',
                'scrum_master': 'scrum-team',
                'operations': 'operations-team',
                'marketing': 'marketing-team',
                'human_capital': 'hr-team',
                'finance': 'finance-team',
                'client_service': 'client-service-team',
                'executive': 'general'
            }
        }
        
        # Cache for user metadata
        self._user_metadata_cache = {}
        self._user_metadata_cache_time = {}
        
    def get_user_department_and_sme(self, user_id: str, topic: str = None) -> Dict[str, str]:
        """
        Determine user's department and SME expertise using live metadata.
        
        Args:
            user_id: Slack user ID
            topic: Optional topic for context-aware SME determination
            
        Returns:
            Dict with 'department', 'sme', 'confidence', and 'source' keys
        """
        try:
            # Check cache first
            cache_key = f"{user_id}_{topic or 'general'}"
            if self._is_cache_valid(cache_key):
                return self._user_metadata_cache[cache_key]
            
            # Get user info from Slack
            user_info = self._get_user_info_with_metadata(user_id)
            if not user_info:
                return self._get_fallback_department_sme(user_id, topic)
            
            # Extract department from profile fields
            department = self._extract_department_from_profile(user_info)
            
            # Extract SME expertise from profile and topic analysis
            sme = self._extract_sme_from_profile_and_topic(user_info, topic)
            
            # Determine confidence level
            confidence = self._calculate_confidence(user_info, department, sme)
            
            result = {
                'department': department,
                'sme': sme,
                'confidence': confidence,
                'source': 'metadata',
                'user_info': {
                    'name': user_info.get('real_name', 'Unknown'),
                    'title': user_info.get('profile', {}).get('title', ''),
                    'team': user_info.get('profile', {}).get('team', '')
                }
            }
            
            # Cache the result
            self._cache_result(cache_key, result)
            
            return result
            
        except Exception as e:
            error_handler.handle_unexpected_error(
                e, "get_user_department_and_sme", user_id,
                additional_data={'topic': topic}
            )
            return self._get_fallback_department_sme(user_id, topic)
    
    def get_department_sme_for_topic(self, topic: str, user_id: str = None) -> Dict[str, str]:
        """
        Find the best department/SME for a specific topic.
        
        Args:
            topic: The topic or issue description
            user_id: Optional user ID for context
            
        Returns:
            Dict with recommended department, SME, and rationale
        """
        try:
            # Analyze topic to determine relevant department and SME
            topic_analysis = self._analyze_topic(topic)
            
            # If user_id provided, get their context
            user_context = None
            if user_id:
                user_context = self.get_user_department_and_sme(user_id, topic)
            
            # Find best matching department and SME
            department = self._find_best_department_match(topic_analysis, user_context)
            sme = self._find_best_sme_match(topic_analysis, department, user_context)
            
            # Get users for this department/SME combination
            users = self._find_users_by_department_sme(department, sme)
            
            return {
                'department': department,
                'sme': sme,
                'recommended_users': users,
                'rationale': topic_analysis.get('rationale', ''),
                'confidence': topic_analysis.get('confidence', 'medium'),
                'topic_analysis': topic_analysis
            }
            
        except Exception as e:
            error_handler.handle_unexpected_error(
                e, "get_department_sme_for_topic", user_id,
                additional_data={'topic': topic}
            )
            return self._get_fallback_department_sme(user_id, topic)
    
    def get_escalation_path(self, issue_type: str, department: str, urgency: str = 'medium') -> List[str]:
        """
        Get escalation path based on issue type, department, and urgency.
        
        Args:
            issue_type: Type of issue (blocker, bug, feature, etc.)
            department: Department handling the issue
            urgency: Urgency level (low, medium, high, critical)
            
        Returns:
            List of user IDs in escalation order
        """
        try:
            escalation_path = []
            
            # Get department leads
            dept_leads = self._find_department_leads(department)
            escalation_path.extend(dept_leads)
            
            # Add cross-functional escalation based on issue type
            if issue_type in ['blocker', 'critical_bug']:
                cross_functional = self._get_cross_functional_escalation(issue_type, department)
                escalation_path.extend(cross_functional)
            
            # Add executive escalation for high urgency
            if urgency in ['high', 'critical']:
                executives = self._find_executives()
                escalation_path.extend(executives)
            
            # Remove duplicates while preserving order
            seen = set()
            unique_path = []
            for user_id in escalation_path:
                if user_id not in seen:
                    seen.add(user_id)
                    unique_path.append(user_id)
            
            return unique_path
            
        except Exception as e:
            error_handler.handle_unexpected_error(
                e, "get_escalation_path", additional_data={
                    'issue_type': issue_type,
                    'department': department,
                    'urgency': urgency
                }
            )
            return []
    
    def _get_user_info_with_metadata(self, user_id: str) -> Optional[Dict]:
        """Get user info including custom profile fields."""
        try:
            response = self.client.users_info(user=user_id)
            return response['user']
        except SlackApiError as e:
            logger.error(f"Error getting user info: {e}")
            return None
    
    def _extract_department_from_profile(self, user_info: Dict) -> str:
        """Extract department from user profile fields."""
        profile = user_info.get('profile', {})
        
        # Check custom profile fields first
        custom_fields = profile.get('fields', {})
        for field_id, field_data in custom_fields.items():
            field_value = field_data.get('value', '').lower()
            if 'department' in field_id.lower() or 'team' in field_id.lower():
                return self._normalize_department(field_value)
        
        # Check title and team fields
        title = profile.get('title', '').lower()
        team = profile.get('team', '').lower()
        
        # Analyze title for department indicators
        for dept, patterns in self.department_patterns.items():
            if any(pattern in title for pattern in patterns):
                return dept
        
        # Analyze team field
        if team:
            return self._normalize_department(team)
        
        # Default fallback
        return self.fallback_rules['default_department']
    
    def _extract_sme_from_profile_and_topic(self, user_info: Dict, topic: str = None) -> str:
        """Extract SME expertise from profile and topic analysis."""
        profile = user_info.get('profile', {})
        title = profile.get('title', '').lower()
        
        # Check custom fields for expertise
        custom_fields = profile.get('fields', {})
        for field_id, field_data in custom_fields.items():
            field_value = field_data.get('value', '').lower()
            if 'expertise' in field_id.lower() or 'skills' in field_id.lower():
                return self._normalize_sme(field_value)
        
        # Analyze title for SME indicators
        for sme, patterns in self.sme_patterns.items():
            if any(pattern in title for pattern in patterns):
                return sme
        
        # If topic provided, analyze for SME match
        if topic:
            topic_lower = topic.lower()
            for sme, patterns in self.sme_patterns.items():
                if any(pattern in topic_lower for pattern in patterns):
                    return sme
        
        return self.fallback_rules['default_sme']
    
    def _analyze_topic(self, topic: str) -> Dict:
        """Analyze topic to determine relevant department and SME."""
        topic_lower = topic.lower()
        
        # Simple keyword-based analysis (could be enhanced with AI)
        department_scores = {}
        sme_scores = {}
        
        # Score departments
        for dept, patterns in self.department_patterns.items():
            score = sum(1 for pattern in patterns if pattern in topic_lower)
            if score > 0:
                department_scores[dept] = score
        
        # Score SMEs
        for sme, patterns in self.sme_patterns.items():
            score = sum(1 for pattern in patterns if pattern in topic_lower)
            if score > 0:
                sme_scores[sme] = score
        
        # Determine best matches
        best_dept = max(department_scores.items(), key=lambda x: x[1])[0] if department_scores else None
        best_sme = max(sme_scores.items(), key=lambda x: x[1])[0] if sme_scores else None
        
        return {
            'department': best_dept,
            'sme': best_sme,
            'department_scores': department_scores,
            'sme_scores': sme_scores,
            'confidence': 'high' if department_scores or sme_scores else 'low',
            'rationale': f"Topic analysis matched {best_dept} department and {best_sme} expertise"
        }
    
    def _find_best_department_match(self, topic_analysis: Dict, user_context: Dict = None) -> str:
        """Find best department match considering topic and user context."""
        if user_context and user_context.get('department'):
            return user_context['department']
        
        return topic_analysis.get('department') or self.fallback_rules['default_department']
    
    def _find_best_sme_match(self, topic_analysis: Dict, department: str, user_context: Dict = None) -> str:
        """Find best SME match considering topic, department, and user context."""
        if user_context and user_context.get('sme'):
            return user_context['sme']
        
        return topic_analysis.get('sme') or self.fallback_rules['default_sme']
    
    def _find_users_by_department_sme(self, department: str, sme: str) -> List[str]:
        """Find users matching department and SME criteria."""
        try:
            # Get all users
            response = self.client.users_list()
            users = response['members']
            
            matching_users = []
            for user in users:
                if user.get('is_bot') or user.get('deleted'):
                    continue
                
                user_dept_sme = self.get_user_department_and_sme(user['id'])
                if (user_dept_sme['department'] == department and 
                    user_dept_sme['sme'] == sme):
                    matching_users.append(user['id'])
            
            return matching_users
            
        except SlackApiError as e:
            logger.error(f"Error finding users by department/SME: {e}")
            return []
    
    def _find_department_leads(self, department: str) -> List[str]:
        """Find department leads."""
        try:
            response = self.client.users_list()
            users = response['members']
            
            leads = []
            for user in users:
                if user.get('is_bot') or user.get('deleted'):
                    continue
                
                user_dept_sme = self.get_user_department_and_sme(user['id'])
                if (user_dept_sme['department'] == department and 
                    any(role in user_dept_sme.get('user_info', {}).get('title', '').lower() 
                        for role in ['lead', 'manager', 'director'])):
                    leads.append(user['id'])
            
            return leads
            
        except SlackApiError as e:
            logger.error(f"Error finding department leads: {e}")
            return []
    
    def _find_executives(self) -> List[str]:
        """Find executive users."""
        try:
            response = self.client.users_list()
            users = response['members']
            
            executives = []
            for user in users:
                if user.get('is_bot') or user.get('deleted'):
                    continue
                
                user_dept_sme = self.get_user_department_and_sme(user['id'])
                if user_dept_sme['department'] == 'executive':
                    executives.append(user['id'])
            
            return executives
            
        except SlackApiError as e:
            logger.error(f"Error finding executives: {e}")
            return []
    
    def _get_cross_functional_escalation(self, issue_type: str, department: str) -> List[str]:
        """Get cross-functional escalation based on issue type."""
        cross_functional_map = {
            'blocker': ['product', 'engineering'],
            'critical_bug': ['qa', 'engineering'],
            'security': ['security', 'legal'],
            'performance': ['operations', 'engineering'],
            'data': ['data', 'engineering']
        }
        
        target_departments = cross_functional_map.get(issue_type, [])
        users = []
        
        for dept in target_departments:
            if dept != department:
                dept_users = self._find_department_leads(dept)
                users.extend(dept_users)
        
        return users
    
    def _normalize_department(self, department: str) -> str:
        """Normalize department name to standard format."""
        dept_lower = department.lower()
        
        for dept, patterns in self.department_patterns.items():
            if any(pattern in dept_lower for pattern in patterns):
                return dept
        
        return self.fallback_rules['default_department']
    
    def _normalize_sme(self, sme: str) -> str:
        """Normalize SME expertise to standard format."""
        sme_lower = sme.lower()
        
        for sme_type, patterns in self.sme_patterns.items():
            if any(pattern in sme_lower for pattern in patterns):
                return sme_type
        
        return self.fallback_rules['default_sme']
    
    def _calculate_confidence(self, user_info: Dict, department: str, sme: str) -> str:
        """Calculate confidence level of department/SME determination."""
        profile = user_info.get('profile', {})
        
        # Check if we have rich profile data
        has_custom_fields = bool(profile.get('fields'))
        has_title = bool(profile.get('title'))
        has_team = bool(profile.get('team'))
        
        if has_custom_fields:
            return 'high'
        elif has_title and has_team:
            return 'medium'
        else:
            return 'low'
    
    def _get_fallback_department_sme(self, user_id: str, topic: str = None) -> Dict[str, str]:
        """Get fallback department/SME when metadata is unavailable."""
        return {
            'department': self.fallback_rules['default_department'],
            'sme': self.fallback_rules['default_sme'],
            'confidence': 'low',
            'source': 'fallback',
            'user_info': {
                'name': 'Unknown',
                'title': '',
                'team': ''
            }
        }
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached result is still valid."""
        if cache_key not in self._user_metadata_cache_time:
            return False
        
        cache_time = self._user_metadata_cache_time[cache_key]
        return (time.time() - cache_time) < self.cache_ttl
    
    def _cache_result(self, cache_key: str, result: Dict):
        """Cache a result with timestamp."""
        self._user_metadata_cache[cache_key] = result
        self._user_metadata_cache_time[cache_key] = time.time()
    
    def clear_cache(self):
        """Clear all cached data."""
        self._user_metadata_cache.clear()
        self._user_metadata_cache_time.clear()
    
    def get_channel_for_department(self, department: str) -> str:
        """Get the appropriate channel for a department."""
        return self.fallback_rules['channel_mappings'].get(
            department, 
            self.fallback_rules['channel_mappings']['engineering']
        ) 