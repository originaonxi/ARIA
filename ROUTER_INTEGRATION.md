# Aonxi Router Integration for ARIA

Replace in investor_writer.py, researcher.py, aria.py:
```python
# BEFORE:
from anthropic import Anthropic
client = Anthropic()

# AFTER:
from router.client import RoutedClient
client = RoutedClient(agent="ARIA")
```

Key routing changes for ARIA:
- Investor scoring → Grok 4.1 Fast (43x cheaper, structured scoring)
- Capital research → Kimi K2.5 Thinking (300+ tool calls, FinGPT-level synthesis)
- PKM classification → Gemini Flash Lite (85% accuracy)
- Email generation → Claude Sonnet 4.6 (NEVER downgrade — ARIA's only weapon)
- Reply classification → Gemini Flash Lite

For deep investor research (researcher.py), use route_and_call directly:
```python
from router import route_and_call
result = route_and_call(
    f"Research {fund_name} thesis and India investments 2024-2026",
    agent="ARIA",
    context={"investor": True, "fund": fund_name}
)
```
