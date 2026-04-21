"""
Pipeline — Level 2 Clean Architecture with Deep Logging.
Uses a State Machine to orchestrate Clarify → Plan → Execute → Review → Verify.
"""

from __future__ import annotations

import re
import time
import json
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any
from myagent.utils.logger import log

from myagent.agent.executor import ExecutionResult, parse_batch_and_execute
from myagent.agent.planner import plan
from myagent.agent.state import PipelineState, new_session_id, phase_done, save_state
from myagent.agent.worker import execute_all_steps, set_interface_contract
from myagent.config.settings import WORK_DIR

if TYPE_CHECKING:
    from myagent.ui import AgentUI, NullUI


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class StepRecord:
    index: int
    description: str
    worker_output: str
    result: ExecutionResult


@dataclass
class RunResult:
    task_original: str
    task_english: str
    steps: list[StepRecord] = field(default_factory=list)
    plan_steps: list[str] = field(default_factory=list)
    created_files: list[str] = field(default_factory=list)
    summary_en: str = ""
    success: bool = True
    review_approved: bool = False
    completion_verified: bool = False


# ---------------------------------------------------------------------------
# State Machine Infrastructure
# ---------------------------------------------------------------------------

class PipelineContext:
    """Shared state container for all phases of the pipeline."""
    def __init__(self, task: str, ui: AgentUI | NullUI, verbose: bool):
        self.task = task
        self.ui = ui
        self.verbose = verbose
        self.result = RunResult(task, task)
        self.session_id = new_session_id()
        self.state = PipelineState(
            session_id=self.session_id,
            task=task,
            work_dir=str(WORK_DIR),
            phase="started",
            started_at=time.time()
        )
        self.steps: list[str] = []
        self.interface_contract: str = ""
        log.info(f"Pipeline Context Initialized. Session: {self.session_id} | Task: {task[:100]}")


class PipelinePhase(ABC):
    """Abstract base for all pipeline execution stages."""
    @abstractmethod
    def run(self, ctx: PipelineContext) -> str | None:
        """Execute phase logic and return name of the next phase or None to stop."""
        pass


# ---------------------------------------------------------------------------
# Phase Implementations
# ---------------------------------------------------------------------------

class PlanningPhase(PipelinePhase):
    def run(self, ctx: PipelineContext) -> str | None:
        log.info("Entering PLANNING phase.")
        try:
            with ctx.ui.streaming("Claude is planning...", color="medium_purple1") as write:
                steps, interface = plan(ctx.task, verbose=ctx.verbose, stream_callback=write)
            
            if not steps:
                log.error("Planning failed: No steps generated.")
                ctx.result.success = False
                ctx.result.summary_en = "Failed to generate a plan."
                return None

            ctx.steps = steps
            ctx.interface_contract = interface
            ctx.result.plan_steps = steps
            set_interface_contract(interface)
            ctx.ui.plan_done(steps)
            log.info(f"Plan generated successfully: {len(steps)} steps.")
            
            # Human-in-the-loop
            log.debug("Awaiting user approval for plan...")
            if not ctx.ui.ask_approval():
                log.info("User rejected the plan.")
                ctx.result.summary_en = "Plan rejected by user."
                ctx.result.success = False
                return None

            log.info("User approved the plan. Moving to EXECUTION.")
            return "execution"

        except Exception as e:
            log.exception(f"Fatal error during Planning phase: {str(e)}")
            ctx.ui.raw("Planning Error", str(e), color="red1")
            ctx.result.success = False
            ctx.result.summary_en = f"Planning Error: {str(e)}"
            return None


class ExecutionPhase(PipelinePhase):
    def run(self, ctx: PipelineContext) -> str | None:
        log.info(f"Entering EXECUTION phase. Executing {len(ctx.steps)} steps.")
        try:
            with ctx.ui.streaming(f"Gemini is executing — {len(ctx.steps)} steps...", color="dodger_blue1") as write:
                worker_out = execute_all_steps(ctx.steps, ctx.task, verbose=ctx.verbose, stream_callback=write)
            
            log.debug(f"Worker Output Captured. Length: {len(worker_out)} chars.")
            
            # LEVEL 2: Structured JSON parsing
            exec_results = parse_batch_and_execute(worker_out, expected=len(ctx.steps))
            log.info(f"Execution finished. Parsed {len(exec_results)} results.")
            
            seen_files = set()
            for i, (step_desc, res) in enumerate(zip(ctx.steps, exec_results), 1):
                log.debug(f"Step {i} Result: {res.kind} | OK={res.ok} | Msg: {res.message[:50]}")
                ctx.result.steps.append(StepRecord(i, step_desc, worker_out, res))
                
                # Check for autonomous loop trigger (OBSERVATION)
                if res.kind == "observation":
                    log.info(f"Observation detected at Step {i}: {res.message}. Triggering RE-PLAN.")
                    ctx.task = f"Gözlem: {res.message}\nÖnceki plandan kalanlar: {ctx.steps[i-1:]}\nLütfen stratejiyi uyarla."
                    return "planning"

                if res.kind == "file" and "filename" in res.details:
                    seen_files.add(res.details["filename"])
                
                if not res.ok:
                    log.warning(f"Step {i} failed: {res.message}")
                    ctx.result.success = False

            ctx.result.created_files = list(seen_files)
            ctx.ui.exec_results(ctx.steps, exec_results)
            log.info(f"Execution cycle complete. Created {len(seen_files)} files.")
            
            return "summary"

        except Exception as e:
            log.exception(f"Fatal error during Execution phase: {str(e)}")
            ctx.result.success = False
            return None


class SummaryPhase(PipelinePhase):
    def run(self, ctx: PipelineContext) -> str | None:
        log.info("Entering SUMMARY phase.")
        ctx.ui.summary(
            success=ctx.result.success,
            review_approved=ctx.result.review_approved,
            n_review_rounds=0, 
            created_files=ctx.result.created_files
        )
        log.info(f"Task Finalized. Success: {ctx.result.success} | Files: {ctx.result.created_files}")
        return None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class PipelineOrchestrator:
    def __init__(self):
        self.phases: dict[str, PipelinePhase] = {
            "planning": PlanningPhase(),
            "execution": ExecutionPhase(),
            "summary": SummaryPhase(),
        }

    def run(self, task: str, verbose: bool = False) -> RunResult:
        from myagent.ui import make_ui
        ui = make_ui(verbose=verbose)
        
        ctx = PipelineContext(task, ui, verbose)
        current_phase_name = "planning"

        log.info("--- PIPELINE START ---")
        while current_phase_name:
            phase = self.phases.get(current_phase_name)
            if not phase:
                log.error(f"Invalid Phase transition: {current_phase_name}")
                break
            log.debug(f"Transitioning to Phase: {current_phase_name}")
            current_phase_name = phase.run(ctx)

        log.info("--- PIPELINE END ---")
        return ctx.result


def run(task: str, verbose: bool = False, **kwargs) -> RunResult:
    """Level 2 entry point compatibility wrapper."""
    orchestrator = PipelineOrchestrator()
    return orchestrator.run(task, verbose)
