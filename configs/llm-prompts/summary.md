# Prospect Summary

For one scored company, produce a concise prospect brief.

## Inputs

- `company`: name, industry, size, revenue, technologies, description.
- `signals`: extracted business signals.
- `breakdown`: scoring rule hits and points.
- `contacts`: list of decision-maker contacts.

## Output (JSON, no prose)

```json
{
  "fit_reason": "Why this company matches our ICP (1-2 sentences).",
  "pain_points": ["Likely operational pain 1", "Pain 2"],
  "erp_relevance": "Why our agentic ERP is relevant (1-2 sentences).",
  "recommended_contacts": ["Name — Title", "Name — Title"],
  "confidence": "low" | "medium" | "high"
}
```

Be specific. Reference the actual signals/breakdown. Avoid generic claims.
