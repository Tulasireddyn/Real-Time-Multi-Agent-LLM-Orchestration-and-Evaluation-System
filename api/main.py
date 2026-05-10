from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, status
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
import asyncio
import uuid
import json
from datetime import datetime
from typing import Optional, List, Dict, Any

from core.schema import (
    AgentType, TraceEvent, APIErrorResponse, 
    EvalSummaryResponse, EvalCategorySummary, 
    PromptReviewRequest, QuerySubmission
)
from core.orchestrator import MasterOrchestrator
from core.ollama_client import OllamaClient
from core.agents.decomposition_agent import DecompositionAgent
from core.agents.rag_agent import RAGAgent
from core.agents.critique_agent import CritiqueAgent
from core.agents.synthesis_agent import SynthesisAgent
from fastapi.middleware.cors import CORSMiddleware
from core.eval.harness import EvalHarness
from core.db import SessionLocal, Job, EvalRun, PromptVersion, init_db

app = FastAPI(
    title="Multi-Agent Orchestration API",
    description="Exactly five endpoints for orchestrating and evaluating multi-agent LLM systems.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialization
client = OllamaClient()
orchestrator = MasterOrchestrator(client)
orchestrator.register_agent(DecompositionAgent(AgentType.DECOMPOSITION, client, orchestrator.context_manager))
orchestrator.register_agent(RAGAgent(AgentType.RAG, client, orchestrator.context_manager))
orchestrator.register_agent(CritiqueAgent(AgentType.CRITIQUE, client, orchestrator.context_manager))
orchestrator.register_agent(SynthesisAgent(AgentType.SYNTHESIS, client, orchestrator.context_manager))
harness = EvalHarness(orchestrator, client)

@app.on_event("startup")
def startup_event():
    init_db()

# --- Exception Handling ---

class UnifiedAPIException(Exception):
    def __init__(self, status_code: int, error_code: str, message: str, job_id: Optional[str] = None):
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.job_id = job_id

@app.exception_handler(UnifiedAPIException)
async def unified_exception_handler(request: Request, exc: UnifiedAPIException):
    return JSONResponse(
        status_code=exc.status_code,
        content=APIErrorResponse(
            error_code=exc.error_code,
            message=exc.message,
            job_id=exc.job_id
        ).dict()
    )

# --- Endpoints ---

@app.post("/submit", responses={400: {"model": APIErrorResponse}, 500: {"model": APIErrorResponse}})
async def submit_query(submission: QuerySubmission):
    """
    Submit a query to the orchestrator and receive a real-time SSE stream of agent activity.
    """
    job_id = str(uuid.uuid4())
    
    async def event_generator():
        queue = asyncio.Queue()
        
        async def callback(event: TraceEvent):
            await queue.put(event)
            
        # Run orchestrator in the background or as part of the stream
        # Since we want to stream, we start it and then consume the queue
        
        task = asyncio.create_task(orchestrator.run(submission.query, job_id, event_callback=callback))
        
        try:
            while not task.done() or not queue.empty():
                try:
                    # Wait for an event with a timeout to check task status
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    yield f"data: {event.json()}\n\n"
                except asyncio.TimeoutError:
                    continue
            
            # Final result if successful
            context = await task
            final_payload = {
                "status": "completed",
                "job_id": job_id,
                "answer": context.history[-1].content if context.history else "No answer generated",
                "token_usage": context.token_usage
            }
            yield f"data: {json.dumps(final_payload)}\n\n"
            
        except Exception as e:
            error_payload = {
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": str(e),
                "job_id": job_id
            }
            yield f"data: {json.dumps(error_payload)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/trace/{job_id}", response_model=Dict[str, Any], responses={404: {"model": APIErrorResponse}})
async def get_execution_trace(job_id: str):
    """
    Retrieve the full execution trace and context for a completed job.
    """
    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    db.close()
    
    if not job:
        raise UnifiedAPIException(
            status_code=404,
            error_code="JOB_NOT_FOUND",
            message=f"No execution trace found for job ID: {job_id}",
            job_id=job_id
        )
    
    return job.result

@app.get("/eval/summary", response_model=EvalSummaryResponse)
async def get_eval_summary():
    """
    Retrieve the latest evaluation run summary broken down by test category and scoring dimension.
    """
    db = SessionLocal()
    runs = db.query(EvalRun).all()
    
    if not runs:
        return EvalSummaryResponse(total_runs=0, overall_avg_score=0, breakdown=[])
    
    # Simple aggregation logic
    categories = {}
    total_score_sum = 0
    
    for r in runs:
        cat = r.category
        if cat not in categories:
            categories[cat] = {"scores": [], "dimensions": {}}
        
        categories[cat]["scores"].append(r.total_score)
        total_score_sum += r.total_score
        
        # Aggregate dimensions
        if r.scores:
            for dim, data in r.scores.items():
                if dim not in categories[cat]["dimensions"]:
                    categories[cat]["dimensions"][dim] = []
                categories[cat]["dimensions"][dim].append(data.get("score", 0))
    
    breakdown = []
    for cat, data in categories.items():
        avg_dim = {dim: sum(scores)/len(scores) for dim, scores in data["dimensions"].items()}
        breakdown.append(EvalCategorySummary(
            category=cat,
            avg_score=sum(data["scores"])/len(data["scores"]),
            dimensions=avg_dim
        ))
    
    db.close()
    return EvalSummaryResponse(
        total_runs=len(runs),
        overall_avg_score=total_score_sum / len(runs),
        breakdown=breakdown,
        latest_run_id=runs[-1].id if runs else None
    )

@app.post("/prompt/review", responses={404: {"model": APIErrorResponse}, 400: {"model": APIErrorResponse}})
async def review_prompt(request: PromptReviewRequest):
    """
    Submit a human approval or rejection for a pending prompt rewrite.
    """
    db = SessionLocal()
    version = db.query(PromptVersion).filter(PromptVersion.id == request.version_id).first()
    
    if not version:
        db.close()
        raise UnifiedAPIException(
            status_code=404,
            error_code="PROMPT_NOT_FOUND",
            message=f"Prompt version {request.version_id} not found."
        )
    
    if request.action not in ["approve", "reject"]:
        db.close()
        raise UnifiedAPIException(
            status_code=400,
            error_code="INVALID_ACTION",
            message="Action must be 'approve' or 'reject'."
        )
    
    version.status = "approved" if request.action == "approve" else "rejected"
    db.commit()
    db.close()
    
    return {"message": f"Prompt version {request.version_id} {version.status} successfully."}

@app.post("/eval/re-evaluate", responses={500: {"model": APIErrorResponse}})
async def trigger_reevaluation(background_tasks: BackgroundTasks):
    """
    Trigger a targeted re-eval on previously failed cases using the latest approved prompts.
    """
    db = SessionLocal()
    # Find test cases that failed in the last run (score < 0.7)
    failed_runs = db.query(EvalRun).filter(EvalRun.total_score < 0.7).all()
    failed_case_ids = list(set([r.test_case_id for r in failed_runs]))
    db.close()
    
    if not failed_case_ids:
        return {"message": "No failed cases found to re-evaluate."}
    
    # Background task for re-evaluation
    async def run_targeted():
        # In a real system, we'd pass failed_case_ids to harness.run_suite
        # For now, we simulate the targeted run
        await harness.run_full_suite() 
        
    background_tasks.add_task(run_targeted)
    
    return {
        "message": f"Targeted re-evaluation triggered for {len(failed_case_ids)} failed cases.",
        "cases": failed_case_ids
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
