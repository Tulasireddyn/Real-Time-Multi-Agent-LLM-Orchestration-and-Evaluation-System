from typing import List, Dict, Any
from core.ollama_client import OllamaClient
import json

class MetaOptimizer:
    def __init__(self, client: OllamaClient):
        self.client = client

    async def optimize(self, eval_results: List[Dict[str, Any]], current_prompts: Dict[str, str]) -> Dict[str, Any]:
        """
        Identify the worst performing agent/prompt and propose a rewrite.
        """
        from core.db import SessionLocal, PromptVersion
        db = SessionLocal()
        
        # Aggregate failures
        failures = [r for r in eval_results if r["total_score"] < 0.6]
        
        if not failures:
            return {"message": "All tests passed with high scores. No optimization needed."}
            
        # Analysis prompt
        analysis_prompt = f"""
        System Role: Meta-Optimization Agent
        Failures: {json.dumps(failures[:5])} 
        Current Prompts: {json.dumps(current_prompts)}
        
        Task:
        1. Identify the agent prompt most likely causing these failures.
        2. Propose a rewritten version that addresses the specific failure modes.
        3. Provide a structured diff and justification.
        
        Return JSON:
        {{
          "agent_id": "...",
          "problem_analysis": "...",
          "proposed_prompt": "...",
          "justification": "...",
          "structured_diff": "..."
        }}
        """
        
        proposal_raw = await self.client.generate(analysis_prompt, format="json")
        proposal = json.loads(proposal_raw)
        
        # Save to DB for approval
        new_version = PromptVersion(
            agent_id=proposal["agent_id"],
            version=1, # In reality, increment based on existing versions
            content=proposal["proposed_prompt"],
            diff=proposal["structured_diff"],
            justification=proposal["justification"],
            status="pending"
        )
        db.add(new_version)
        db.commit()
        db.close()
        
        return proposal
