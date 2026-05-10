from core.orchestrator import BaseAgent
from core.schema import AgentType, SharedContext
import json

class RAGAgent(BaseAgent):
    async def execute(self, context: SharedContext) -> str:
        # Simulate retrieval of 2 chunks
        chunks = [
            {"id": "chunk_1", "content": "The capital of France is Paris. It is known for the Eiffel Tower."},
            {"id": "chunk_2", "content": "Paris hosted the Olympic Games in 1900, 1924, and will host in 2024."}
        ]
        
        prompt = f"""
        Answer the query using the provided chunks. You MUST perform multi-hop reasoning (combine info from both chunks).
        Cite which chunk contributed to which part of your answer.
        
        Query: {context.original_query}
        Chunks: {json.dumps(chunks)}
        
        Return JSON:
        {{
          "answer": "...",
          "citations": [
            {{"sentence": "...", "chunk_id": "..."}}
          ]
        }}
        """
        
        response_raw = await self.client.generate(prompt, format="json")
        data = json.loads(response_raw)
        answer = data["answer"]
        
        context.add_message("assistant", answer, self.agent_type)
        
        # Populate provenance
        from core.schema import ProvenanceMap
        for cit in data.get("citations", []):
            context.provenance.append(ProvenanceMap(
                sentence=cit["sentence"],
                source_agent=self.agent_type,
                source_chunk_id=cit["chunk_id"]
            ))
            
        return answer
