# Dynamic Department/SME Determination System

## Overview

The Slack bot now uses **live org metadata** with **intelligent fallback rules** instead of hardcoded mappings to determine departments and Subject Matter Experts (SMEs). This provides a more flexible, maintainable, and accurate routing system.

## Key Features

### 🎯 **Live Org Metadata Extraction**
- Extracts department/SME info from Slack user profiles and custom fields
- Analyzes job titles, team assignments, and profile metadata
- Supports custom profile fields for department and expertise

### 🤖 **AI-Powered Topic Analysis**
- Analyzes blocker descriptions and KR names to determine relevant department/SME
- Uses keyword matching and pattern recognition
- Provides confidence levels and rationale for decisions

### 🔄 **Dynamic Escalation Paths**
- Generates escalation paths based on issue type, department, and urgency
- Supports cross-functional escalation for complex issues
- Includes executive escalation for high-priority items

### 📊 **Intelligent Channel Mapping**
- Maps departments to appropriate Slack channels
- Supports custom channel configurations
- Fallback to default channels when needed

### ⚡ **Performance Optimization**
- Caches results to minimize API calls
- Configurable cache TTL (default: 1 hour)
- Graceful degradation when services are unavailable

### 🛡️ **Robust Fallback Rules**
- Comprehensive fallback system when metadata is unavailable
- Default department/SME assignments
- Legacy role system compatibility

## Architecture

### Core Components

#### 1. **OrgMetadataService** (`src/org_metadata_service.py`)
The main service that handles all department/SME determination logic.

```python
class OrgMetadataService:
    def get_user_department_and_sme(self, user_id: str, topic: str = None) -> Dict
    def get_department_sme_for_topic(self, topic: str, user_id: str = None) -> Dict
    def get_escalation_path(self, issue_type: str, department: str, urgency: str) -> List[str]
    def get_channel_for_department(self, department: str) -> str
```

#### 2. **Integration with Bot** (`src/bot.py`)
Updated bot methods to use the new service:

```python
# Legacy methods now use org metadata service
def get_user_roles(self, user_id)
def get_users_by_role(self, role)
def has_role(self, user_id, role)
def escalate_by_hierarchy(self, issue_type, message, additional_context, topic, user_id)
def escalate_blocker_with_details(self, user_id, user_name, blocker_description, kr_name, urgency, notes)
```

## Configuration

### Department Patterns
The system recognizes departments based on these patterns:

```python
department_patterns = {
    'engineering': ['engineer', 'developer', 'dev', 'software', 'backend', 'frontend', 'fullstack', 'swe'],
    'design': ['designer', 'ux', 'ui', 'product design', 'visual', 'creative'],
    'product': ['product', 'pm', 'product manager', 'product owner', 'po'],
    'marketing': ['marketing', 'growth', 'seo', 'content', 'social media', 'brand'],
    'sales': ['sales', 'account', 'business development', 'bd', 'revenue'],
    'operations': ['operations', 'ops', 'devops', 'infrastructure', 'platform'],
    'data': ['data', 'analytics', 'bi', 'data science', 'ml', 'ai'],
    'qa': ['qa', 'quality', 'testing', 'test engineer', 'sdet'],
    'support': ['support', 'customer success', 'cs', 'help desk', 'technical support'],
    'finance': ['finance', 'accounting', 'fp&a', 'controller', 'cfo'],
    'hr': ['hr', 'human resources', 'people', 'talent', 'recruiting'],
    'legal': ['legal', 'compliance', 'counsel', 'lawyer'],
    'executive': ['ceo', 'cto', 'cfo', 'coo', 'vp', 'director', 'head of', 'chief']
}
```

### SME Expertise Patterns
SME areas are determined by these patterns:

```python
sme_patterns = {
    'frontend': ['react', 'vue', 'angular', 'javascript', 'typescript', 'css', 'html', 'frontend', 'ui'],
    'backend': ['python', 'java', 'node', 'api', 'database', 'sql', 'nosql', 'backend', 'server'],
    'mobile': ['ios', 'android', 'react native', 'flutter', 'mobile', 'app'],
    'devops': ['aws', 'azure', 'gcp', 'kubernetes', 'docker', 'ci/cd', 'infrastructure', 'devops'],
    'data': ['sql', 'python', 'r', 'tableau', 'powerbi', 'analytics', 'machine learning', 'ai'],
    'security': ['security', 'cybersecurity', 'penetration testing', 'compliance', 'gdpr', 'sox'],
    'design': ['figma', 'sketch', 'adobe', 'ux', 'ui', 'design system', 'prototyping'],
    'product': ['product strategy', 'roadmap', 'user research', 'a/b testing', 'analytics'],
    'marketing': ['seo', 'sem', 'social media', 'content marketing', 'email marketing', 'growth'],
    'sales': ['crm', 'salesforce', 'lead generation', 'account management', 'negotiation']
}
```

### Channel Mappings
Default channel mappings for departments:

```python
channel_mappings = {
    'engineering': 'dev-team',
    'design': 'design-team', 
    'product': 'product-team',
    'marketing': 'marketing-team',
    'sales': 'sales-team',
    'operations': 'ops-team',
    'data': 'data-team',
    'qa': 'qa-team',
    'support': 'support-team',
    'finance': 'finance-team',
    'hr': 'hr-team',
    'legal': 'legal-team',
    'executive': 'general'
}
```

## Usage Examples

### 1. Get User Department/SME
```python
# Get user's department and SME expertise
user_info = org_service.get_user_department_and_sme("U1234567890")
print(f"Department: {user_info['department']}")
print(f"SME: {user_info['sme']}")
print(f"Confidence: {user_info['confidence']}")
```

### 2. Topic-Based Analysis
```python
# Analyze a blocker topic to find appropriate department/SME
topic = "Database connection timeout in production"
analysis = org_service.get_department_sme_for_topic(topic)
print(f"Department: {analysis['department']}")  # 'operations'
print(f"SME: {analysis['sme']}")  # 'backend'
print(f"Rationale: {analysis['rationale']}")
```

### 3. Escalation Path Generation
```python
# Get escalation path for a blocker
escalation_path = org_service.get_escalation_path(
    issue_type="blocker",
    department="engineering", 
    urgency="high"
)
print(f"Escalation path: {escalation_path}")
```

### 4. Channel Mapping
```python
# Get appropriate channel for a department
channel = org_service.get_channel_for_department("engineering")
print(f"Channel: {channel}")  # 'dev-team'
```

## Integration with Existing Bot

### Updated Methods

#### `get_user_roles(user_id)`
Now uses org metadata service with fallback to legacy roles:
```python
def get_user_roles(self, user_id):
    if self.org_metadata:
        user_info = self.org_metadata.get_user_department_and_sme(user_id)
        roles = []
        if user_info.get('department'):
            roles.append(user_info['department'])
        if user_info.get('sme'):
            roles.append(user_info['sme'])
        # Add leadership roles based on title
        return roles
    # Fallback to legacy hardcoded roles
    return self.user_roles.get(user_id, [])
```

#### `escalate_blocker_with_details(...)`
Now includes department/SME analysis:
```python
# Use org metadata service to determine appropriate escalation
topic = f"{blocker_description} {kr_name}"
if self.org_metadata:
    topic_analysis = self.org_metadata.get_department_sme_for_topic(topic, user_id)
    department = topic_analysis.get('department', 'engineering')
    sme = topic_analysis.get('sme', 'backend')
```

### Enhanced Blocker Messages
Blocker escalation messages now include:
- **Department**: Determined from topic analysis
- **SME Area**: Specific expertise area
- **Dynamic routing**: Based on department/SME combination

## Testing

Run the test script to verify functionality:

```bash
cd slack-bot
python test_org_metadata.py
```

The test script demonstrates:
- User department/SME determination
- Topic-based analysis
- Escalation path generation
- Channel mapping
- Cache functionality
- Fallback rules

## Benefits

### 🎯 **Accuracy**
- Real-time org structure awareness
- Topic-based intelligent routing
- Context-aware escalation

### 🔧 **Maintainability**
- No more hardcoded user mappings
- Automatic updates when org structure changes
- Configurable patterns and rules

### ⚡ **Performance**
- Intelligent caching reduces API calls
- Fast fallback when services unavailable
- Optimized for high-volume usage

### 🛡️ **Reliability**
- Multiple fallback layers
- Graceful degradation
- Comprehensive error handling

### 🔄 **Flexibility**
- Easy to add new departments/SMEs
- Configurable patterns and rules
- Support for custom profile fields

## Migration from Legacy System

The new system is **backward compatible** with the existing hardcoded role system:

1. **Legacy roles** are used as fallback when org metadata service is unavailable
2. **Existing functionality** continues to work unchanged
3. **Gradual migration** - new features use org metadata, old features fall back gracefully

### Migration Steps

1. **Deploy the new service** alongside existing bot
2. **Test with a subset of users** to verify functionality
3. **Monitor performance** and adjust cache settings if needed
4. **Gradually enable** org metadata features
5. **Remove legacy mappings** once fully migrated

## Configuration Options

### Environment Variables
```bash
# Cache settings
ORG_METADATA_CACHE_TTL=3600  # Cache TTL in seconds

# Fallback settings
DEFAULT_DEPARTMENT=engineering
DEFAULT_SME=backend
```

### Custom Patterns
You can customize department and SME patterns by modifying the `department_patterns` and `sme_patterns` dictionaries in `OrgMetadataService`.

### Custom Channel Mappings
Update the `channel_mappings` dictionary to match your Slack workspace structure.

## Troubleshooting

### Common Issues

1. **API Rate Limits**
   - Solution: Increase cache TTL
   - Monitor API usage

2. **Missing Profile Data**
   - Solution: Check Slack profile completeness
   - Use fallback rules

3. **Incorrect Department Detection**
   - Solution: Update department patterns
   - Add custom profile fields

4. **Cache Issues**
   - Solution: Clear cache with `org_service.clear_cache()`
   - Check cache TTL settings

### Debug Mode
Enable debug logging to see detailed analysis:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Future Enhancements

### Planned Features
- **AI-powered analysis** using machine learning
- **Learning from escalations** to improve routing
- **Integration with HR systems** for org data
- **Advanced caching** with Redis
- **Analytics dashboard** for routing effectiveness

### Extensibility
The system is designed to be easily extensible:
- Add new departments/SMEs by updating patterns
- Custom analysis algorithms
- Integration with external org management systems
- Custom escalation rules

## Conclusion

The dynamic department/SME determination system provides a **modern, flexible, and intelligent** approach to routing issues and escalations. It eliminates the need for hardcoded mappings while providing better accuracy and maintainability.

The system is **production-ready** and **backward compatible**, making it easy to deploy and gradually migrate from the legacy system. 