from core.orchestrator import BaseAgent
from core.schema import AgentType, SharedContext, SubTask
import json

class DecompositionAgent(BaseAgent):
    async def execute(self, context: SharedContext) -> str:
        prompt = f"""
        Break down the following query into explicit, typed sub-tasks with a dependency graph.
        Query: {context.original_query}
        
        Sub-tasks should be one of: [search, calculate, analyze, verify].
        Specify dependencies (ids of tasks that must finish first).
        
        Return JSON list of sub-tasks:
        [
          {{"id": "t1", "task_type": "search", "description": "...", "dependencies": []}},
          {{"id": "t2", "task_type": "analyze", "description": "...", "dependencies": ["t1"]}}
        ]
        """
        
        response_raw = await self.client.generate(prompt, format="json")
        try:
            tasks_data = json.loads(response_raw)
            for t in tasks_data:
                task = SubTask(**t)
                context.sub_tasks.append(task)
            
            summary = f"Decomposed query into {len(context.sub_tasks)} sub-tasks."
            context.add_message("assistant", summary, self.agent_type)
            return summary
        except Exception as e:
            error_msg = f"Failed to decompose query: {str(e)}"
            context.add_message("assistant", error_msg, self.agent_type)
            return error_msg
