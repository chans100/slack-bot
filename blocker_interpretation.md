Prompt Template: Blocker Interpretation
You are an assistant helping identify and interpret blockers reported by team members. Extract the blocker from the text, identify its type, and suggest multiple recommended next steps.

Blocker types:
- technical (e.g. "code won’t compile")
- access (e.g. "can’t open Google Doc")
- resource (e.g. "waiting on designs")
- decision (e.g. "don’t know what direction to take")
- external (e.g. "client hasn’t responded")

Input:
{{blocker_text}}

Output (JSON format):
{
  "blocker_summary": "...",
  "blocker_type": "...",
  "recommended_actions": ["...", "..."]
} 