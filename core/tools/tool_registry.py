import asyncio
import time
from typing import Dict, Any, Callable, Optional, List
from core.schema import ToolCall, ToolStatus, SharedContext
import json

class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, Callable] = {}

    def register(self, name: str, func: Callable):
        self.tools[name] = func

    async def call_tool(self, name: str, input_data: Dict[str, Any], context: SharedContext) -> ToolCall:
        if name not in self.tools:
            return ToolCall(
                tool_name=name,
                input_data=input_data,
                status=ToolStatus.FAILURE,
                latency_ms=0,
                output_data={"error": f"Tool {name} not found"}
            )

        start_time = time.time()
        
        try:
            # Execute tool with timeout
            output = await asyncio.wait_for(self.tools[name](**input_data), timeout=10.0)
            
            status = ToolStatus.SUCCESS
            if not output or (isinstance(output, list) and len(output) == 0):
                status = ToolStatus.EMPTY
            
            latency = (time.time() - start_time) * 1000
            
            tool_call = ToolCall(
                tool_name=name,
                input_data=input_data,
                output_data=output,
                status=status,
                latency_ms=latency
            )
            
            # Specific failure contracts
            if name == "python_sandbox" and output.get("exit_code") != 0:
                tool_call.status = ToolStatus.FAILURE
            
            if name == "sql_lookup" and status == ToolStatus.EMPTY:
                # Orchestrator might handle EMPTY differently
                pass

            context.tool_logs.append(tool_call)
            return tool_call

        except asyncio.TimeoutError:
            latency = (time.time() - start_time) * 1000
            call = ToolCall(tool_name=name, input_data=input_data, status=ToolStatus.TIMEOUT, latency_ms=latency)
            context.tool_logs.append(call)
            return call
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            call = ToolCall(tool_name=name, input_data=input_data, status=ToolStatus.MALFORMED, latency_ms=latency, output_data={"error": str(e)})
            context.tool_logs.append(call)
            return call

    async def execute_agent_tool_loop(self, agent_type: AgentType, tool_name: str, initial_input: Dict[str, Any], context: SharedContext):
        """
        Agent-driven tool loop: agent can re-call up to 2 times with modified input.
        """
        current_input = initial_input
        for attempt in range(3): # Initial + 2 retries
            tool_result = await self.call_tool(tool_name, current_input, context)
            
            # Fallback logic based on failure mode
            if tool_result.status == ToolStatus.TIMEOUT:
                # Explicit fallback: maybe try a simpler query?
                print(f"[Tool] {tool_name} timed out. Handoff to fallback logic.")
                break
            
            # Agent decides if result is sufficient
            decision_prompt = f"""
            Agent: {agent_type}
            Tool: {tool_name}
            Input: {json.dumps(current_input)}
            Output: {json.dumps(tool_result.output_data)}
            Status: {tool_result.status}
            
            Is this result sufficient? If not, provide modified input for retry.
            Return JSON: {{"sufficient": true, "modified_input": null}}
            """
            
            # This would call the LLM client
            # decision = await llm_client.generate(decision_prompt, format="json")
            # For simplicity in this demo, let's assume it's sufficient if SUCCESS
            if tool_result.status == ToolStatus.SUCCESS:
                tool_result.accepted = True
                break
            else:
                tool_result.accepted = False
                if attempt < 2:
                    print(f"[Tool] {tool_name} {tool_result.status}. Agent retrying...")
                    # In real life, we'd use the LLM to modify current_input
                    # Here we just tweak it for the demo
                    current_input["query"] = current_input.get("query", "") + " (retry)"
                else:
                    print(f"[Tool] {tool_name} failed after 2 retries.")
