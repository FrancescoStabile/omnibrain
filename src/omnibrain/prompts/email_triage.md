Classify this email.

Respond in JSON:
{
  "urgency": "critical|high|medium|low",
  "category": "action_required|fyi|newsletter|spam|personal",
  "action": "respond|forward|archive|delete|schedule",
  "reasoning": "One sentence explaining your classification",
  "draft_needed": true/false
}

Classification rules:
- CRITICAL: From known VIP contacts about time-sensitive matters
- HIGH: Requires response within 24h
- MEDIUM: Can wait 2-3 days
- LOW: Newsletter, notifications, no response needed

VIP contacts are identified from the user's interaction history
(high frequency, fast response times from user).
