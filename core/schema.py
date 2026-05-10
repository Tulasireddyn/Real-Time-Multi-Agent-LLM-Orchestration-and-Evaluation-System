from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime

class AgentType(str, Enum):
    ORCHESTRATOR = "orchestrator"
    DECOMPOSITION = "decomposition"
    RAG = "rag"
    CRITIQUE = "critique"
    SYNTHESIS = "synthesis"
    COMPRESSION = "compression"
    META = "meta"

class ToolStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    MALFORMED = "malformed"
    EMPTY = "empty"

class ToolCall(BaseModel):
    tool_name: str
    input_data: Dict[str, Any]
    output_data: Optional[Any] = None
    status: ToolStatus
    latency_ms: float
    retries: int = 0
    accepted: bool = True  # Whether the agent liked the result

class Message(BaseModel):
    role: str # 'user', 'assistant', 'system'
    content: str
    agent_id: Optional[AgentType] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class SubTask(BaseModel):
    id: str
    task_type: str
    description: str
    dependencies: List[str] = []
    status: str = "pending" # pending, in_progress, completed, failed
    result: Optional[str] = None

class CritiqueFlag(BaseModel):
    span: str
    reason: str
    confidence: float

class ProvenanceMap(BaseModel):
    sentence: str
    source_agent: AgentType
    source_chunk_id: Optional[str] = None

class SharedContext(BaseModel):
    job_id: str
    original_query: str
    history: List[Message] = []
    sub_tasks: List[SubTask] = []
    tool_logs: List[ToolCall] = []
    critique_flags: List[CritiqueFlag] = []
    provenance: List[ProvenanceMap] = []
    metadata: Dict[str, Any] = {}
    token_usage: Dict[AgentType, int] = {}
    budget_limit: int = 10000 # Default limit
    policy_violations: List[str] = []
    
    def add_message(self, role: str, content: str, agent_id: AgentType):
        self.history.append(Message(role=role, content=content, agent_id=agent_id))

class TraceEvent(BaseModel):
    job_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    agent_id: AgentType
    event_type: str # 'decision', 'call', 'result', 'handoff'
    payload: Dict[str, Any]

# API Models
class APIErrorResponse(BaseModel):
    error_code: str
    message: str
    job_id: Optional[str] = None

class EvalDimension(BaseModel):
    score: float
    justification: str

class EvalCategorySummary(BaseModel):
    category: str
    avg_score: float
    dimensions: Dict[str, float]

class EvalSummaryResponse(BaseModel):
    total_runs: int
    overall_avg_score: float
    breakdown: List[EvalCategorySummary]
    latest_run_id: Optional[int] = None

class PromptReviewRequest(BaseModel):
    version_id: int
    action: str  # 'approve' or 'reject'

class QuerySubmission(BaseModel):
    query: str
