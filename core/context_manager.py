import json
from typing import List, Dict, Any
from core.schema import SharedContext, AgentType, Message

class ContextBudgetManager:
    def __init__(self, default_budget: int = 4000):
        self.default_budget = default_budget

    def count_tokens(self, text: str) -> int:
        # Simplified token counting (approx 4 chars per token)
        # In production, use tiktoken or specific model tokenizer
        return len(text) // 4

    def get_current_usage(self, context: SharedContext, agent_type: AgentType) -> int:
        return context.token_usage.get(agent_type, 0)

    def check_budget(self, context: SharedContext, agent_type: AgentType, new_content: str) -> bool:
        current = self.get_current_usage(context, agent_type)
        addition = self.count_tokens(new_content)
        
        if current + addition > context.budget_limit:
            return False
        return True

    def track_usage(self, context: SharedContext, agent_type: AgentType, text: str):
        tokens = self.count_tokens(text)
        context.token_usage[agent_type] = context.token_usage.get(agent_type, 0) + tokens

    async def enforce_budget(self, context: SharedContext, agent_type: AgentType, llm_client: Any):
        """
        If budget is exceeded, call the compression agent.
        """
        current_tokens = sum(self.count_tokens(m.content) for m in context.history)
        
        if current_tokens > context.budget_limit:
            print(f"[Policy] Budget overflow by {agent_type}: {current_tokens}/{context.budget_limit}. Invoking compression.")
            context.policy_violations.append(f"Budget overflow by {agent_type}: {current_tokens} tokens")
            
            # Compression must be lossless for structured data
            # Lossy only for conversational filler
            compressed_history = await self.compress_history(context, llm_client)
            context.history = compressed_history
            
            # Recalculate usage
            new_total = sum(self.count_tokens(m.content) for m in context.history)
            context.token_usage[agent_type] = new_total
            print(f"Budget enforced: Compressed from {current_tokens} to {new_total} tokens.")

    async def compress_history(self, context: SharedContext, llm_client: Any) -> List[Message]:
        # Identify structured vs filler
        structured_info = {
            "sub_tasks": [t.dict() for t in context.sub_tasks],
            "tool_logs": [l.dict() for l in context.tool_logs],
            "provenance": [p.dict() for p in context.provenance]
        }
        
        filler_messages = [m for m in context.history if m.agent_id not in [AgentType.ORCHESTRATOR]]
        
        summary_prompt = f"""
        System Role: Compression Agent
        Task: Lossy summarization of conversational filler while preserving ALL facts and references to structured data.
        
        Conversational History:
        {[m.content for m in filler_messages]}
        
        Structured Data (DO NOT SUMMARIZE, KEEP REFERENCE):
        {json.dumps(structured_info)}
        
        Return a concise summary message.
        """
        
        summary_content = await llm_client.generate(summary_prompt)
        
        return [
            Message(role="system", content=f"Lossless data preserved. Previous summary: {summary_content}", agent_id=AgentType.COMPRESSION),
            context.history[-1] # Keep the very last message for immediate context
        ]
