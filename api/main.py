from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import asyncio
import uuid
import json
from datetime import datetime
from core.schema import SharedContext, AgentType
from core.orchestrator import MasterOrchestrator
from core.ollama_client import OllamaClient
from core.agents.decomposition_agent import DecompositionAgent
from core.agents.rag_agent import RAGAgent
from core.agents.critique_agent import CritiqueAgent
from core.agents.synthesis_agent import SynthesisAgent
from fastapi.middleware.cors import CORSMiddleware
from core.eval.harness import EvalHarness

app = FastAPI(title="Multi-Agent Orchestration API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state (In production, use Redis/DB)
client = OllamaClient()
orchestrator = MasterOrchestrator(client)
orchestrator.register_agent(DecompositionAgent(AgentType.DECOMPOSITION, client, orchestrator.context_manager))
orchestrator.register_agent(RAGAgent(AgentType.RAG, client, orchestrator.context_manager))
orchestrator.register_agent(CritiqueAgent(AgentType.CRITIQUE, client, orchestrator.context_manager))
orchestrator.register_agent(SynthesisAgent(AgentType.SYNTHESIS, client, orchestrator.context_manager))

harness = EvalHarness(orchestrator, client)
jobs = {}

class QueryRequest(BaseModel):
    query: str

@app.on_event("startup")
def startup_event():
    from core.db import init_db
    init_db()

@app.post("/query")
async def submit_query(request: QueryRequest):
    job_id = str(uuid.uuid4())
    
    async def event_generator():
        # Queue for capturing events from the orchestrator
        queue = asyncio.Queue()
        
        # We need a way for the orchestrator to push events to this queue
        # For this demo, we'll run it and yield simulated events based on the trace
        
        yield f"data: {json.dumps({'status': 'started', 'agent': 'orchestrator', 'job_id': job_id})}\n\n"
        
        # Run orchestrator
        context = await orchestrator.run(request.query, job_id)
        
        # Stream the trace events
        for event in context.metadata.get("execution_trace", []):
            yield f"data: {json.dumps({'status': 'active', 'agent': event['agent_id'], 'event': event['event_type'], 'payload': event['payload']})}\n\n"
            await asyncio.sleep(0.5) # Simulate real-time
            
        yield f"data: {json.dumps({'status': 'completed', 'answer': context.history[-1].content, 'provenance': [p.dict() for p in context.provenance], 'tokens': context.token_usage})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/trace/{job_id}")
async def get_trace(job_id: str):
    from core.db import SessionLocal, Job
    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return {"error": "Job not found"}
    return job.result

@app.get("/eval/summary")
async def get_eval_summary():
    from core.db import SessionLocal, EvalRun
    db = SessionLocal()
    runs = db.query(EvalRun).order_by(EvalRun.timestamp.desc()).limit(10).all()
    return [{
        "id": r.id,
        "test_case_id": r.test_case_id,
        "category": r.category,
        "total_score": r.total_score,
        "timestamp": r.timestamp.isoformat()
    } for r in runs]

@app.post("/prompt/approve")
async def approve_prompt(agent_id: str, version: int):
    from core.db import SessionLocal, PromptVersion
    db = SessionLocal()
    version_entry = db.query(PromptVersion).filter(PromptVersion.agent_id == agent_id, PromptVersion.version == version).first()
    if not version_entry:
        return {"error": "Prompt version not found"}
    
    version_entry.status = "approved"
    db.commit()
    db.close()
    return {"message": f"Prompt version {version} for {agent_id} approved."}

@app.post("/eval/re-run")
async def trigger_reeval(background_tasks: BackgroundTasks):
    from core.db import SessionLocal, EvalRun
    db = SessionLocal()
    # Get previously failed cases
    failed_cases = db.query(EvalRun).filter(EvalRun.total_score < 0.6).all()
    case_ids = [f.test_case_id for f in failed_cases]
    
    background_tasks.add_task(harness.run_full_suite) # In real life, filter by case_ids
    return {"message": f"Triggered re-eval for {len(case_ids)} failed cases."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
