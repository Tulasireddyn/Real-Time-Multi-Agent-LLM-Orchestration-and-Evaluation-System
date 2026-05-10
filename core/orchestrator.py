from typing import List, Dict, Any, Optional
from core.schema import SharedContext, AgentType, TraceEvent, Message
from core.ollama_client import OllamaClient
from core.context_manager import ContextBudgetManager
import json
from datetime import datetime
from core.db import SessionLocal, Job

class BaseAgent:
    def __init__(self, agent_type: AgentType, client: OllamaClient, context_manager: ContextBudgetManager):
        self.agent_type = agent_type
        self.client = client
        self.context_manager = context_manager

    async def execute(self, context: SharedContext) -> str:
        raise NotImplementedError

class MasterOrchestrator:
    def __init__(self, client: OllamaClient):
        self.client = client
        self.context_manager = ContextBudgetManager()
        self.agents: Dict[AgentType, BaseAgent] = {}

    def register_agent(self, agent: BaseAgent):
        self.agents[agent.agent_type] = agent

    async def run(self, query: str, job_id: str):
        context = SharedContext(job_id=job_id, original_query=query)
        context.add_message("user", query, AgentType.ORCHESTRATOR)
        
        # 1. Routing Loop
        current_agent_type = None
        visited_count = {}
        trace = [TraceEvent(job_id=job_id, agent_id=AgentType.ORCHESTRATOR, event_type="start", payload={"query": query})]
        
        while current_agent_type != AgentType.SYNTHESIS:
            # Decision reasoning
            reasoning_prompt = f"""
            System Role: Master Orchestrator
            Query: '{query}'
            Current context: {len(context.history)} messages, {len(context.sub_tasks)} tasks.
            Sub-tasks status: {[{'id': t.id, 'status': t.status} for t in context.sub_tasks]}
            
            Decide the next best agent to invoke. 
            Options: decomposition, rag, critique, synthesis.
            Rule: Synthesis should only be called when all info is gathered.
            
            Return JSON format: {{"next_agent": "...", "reasoning": "...", "context_budget": 2000}}
            """
            
            decision_raw = await self.client.generate(reasoning_prompt, format="json")
            decision = json.loads(decision_raw)
            
            next_agent_type = AgentType(decision["next_agent"])
            reasoning = decision["reasoning"]
            budget = decision.get("context_budget", 2000)
            
            # Log decision trace
            trace.append(TraceEvent(
                job_id=job_id, 
                agent_id=AgentType.ORCHESTRATOR, 
                event_type="decision", 
                payload={"next_agent": next_agent_type, "reasoning": reasoning}
            ))
            
            print(f"[Orchestrator] Routing to {next_agent_type} because: {reasoning}")
            
            # Prevent infinite loops/over-execution
            visited_count[next_agent_type] = visited_count.get(next_agent_type, 0) + 1
            if visited_count[next_agent_type] > 5:
                print(f"Warning: Agent {next_agent_type} executed too many times. Forcing Synthesis.")
                next_agent_type = AgentType.SYNTHESIS
            
            # Set budget for this turn
            context.budget_limit = budget
            
            # Execute agent
            agent = self.agents.get(next_agent_type)
            if not agent:
                print(f"Error: Agent {next_agent_type} not registered.")
                break
                
            # Log handoff
            trace.append(TraceEvent(job_id=job_id, agent_id=next_agent_type, event_type="handoff", payload={}))
            
            await agent.execute(context)
            
            # Enforce budget after each turn
            await self.context_manager.enforce_budget(context, next_agent_type, self.client)
            
            current_agent_type = next_agent_type
            if current_agent_type == AgentType.SYNTHESIS:
                break

        # Record final trace
        trace.append(TraceEvent(job_id=job_id, agent_id=AgentType.ORCHESTRATOR, event_type="completed", payload={}))
        
        # Save trace to context metadata for retrieval
        context.metadata["execution_trace"] = [t.dict() for t in trace]
        
        # Save to DB
        db = SessionLocal()
        job = Job(
            id=job_id,
            query=query,
            status="completed",
            result=context.dict(),
            completed_at=datetime.utcnow()
        )
        db.merge(job) # Use merge to handle potential existing entries
        db.commit()
        db.close()
        
        return context
