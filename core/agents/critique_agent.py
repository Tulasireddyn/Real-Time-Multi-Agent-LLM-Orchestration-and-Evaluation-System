from core.orchestrator import BaseAgent
from core.schema import AgentType, SharedContext, CritiqueFlag
import json

class CritiqueAgent(BaseAgent):
    async def execute(self, context: SharedContext) -> str:
        last_assistant_msg = next((m.content for m in reversed(context.history) if m.role == "assistant"), "")
        
        if not last_assistant_msg:
            return "No assistant message to critique."
            
        prompt = f"""
        Review the following response and flag specific spans of text that are incorrect, ambiguous, or lack citations.
        Assign a confidence score (0-1) for each claim.
        
        Response: "{last_assistant_msg}"
        
        Return JSON list of flags:
        [
          {{"span": "...", "reason": "...", "confidence": 0.8}}
        ]
        """
        
        response_raw = await self.client.generate(prompt, format="json")
        try:
            flags_data = json.loads(response_raw)
            for f in flags_data:
                flag = CritiqueFlag(**f)
                context.critique_flags.append(flag)
            
            summary = f"Critiqued response. Found {len(flags_data)} points of interest."
            context.add_message("assistant", summary, self.agent_type)
            return summary
        except Exception as e:
            return f"Critique failed: {str(e)}"
