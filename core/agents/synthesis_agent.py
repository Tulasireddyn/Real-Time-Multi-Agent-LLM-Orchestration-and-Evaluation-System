from core.orchestrator import BaseAgent
from core.schema import AgentType, SharedContext, ProvenanceMap
import json

class SynthesisAgent(BaseAgent):
    async def execute(self, context: SharedContext) -> str:
        all_outputs = [m.content for m in context.history if m.role == "assistant"]
        flags = [f.dict() for f in context.critique_flags]
        
        prompt = f"""
        Merge the following agent outputs into a final, coherent answer.
        Resolve any contradictions flagged by the critique agent.
        
        Outputs: {json.dumps(all_outputs)}
        Flags: {json.dumps(flags)}
        
        For each sentence in your final answer, identify the source agent and, if applicable, the source chunk ID.
        Return JSON:
        {{
          "final_answer": "...",
          "provenance": [
            {{"sentence": "...", "source_agent": "rag", "source_chunk_id": "chunk_1"}}
          ]
        }}
        """
        
        response_raw = await self.client.generate(prompt, format="json")
        try:
            data = json.loads(response_raw)
            context.provenance = [ProvenanceMap(**p) for p in data["provenance"]]
            
            final_answer = data["final_answer"]
            context.add_message("assistant", final_answer, self.agent_type)
            return final_answer
        except Exception as e:
            fallback = "Failed to synthesize final answer."
            context.add_message("assistant", fallback, self.agent_type)
            return fallback
