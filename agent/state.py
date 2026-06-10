import datetime
import json
import math
from dataclasses import dataclass, field


_DEFAULT_WORKING_MEMORY = {
    "current_hypothesis": None,
    "focus_dimension": None,
    "analysis_stage": "init",
}


def _to_json_safe(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if math.isinf(value):
            return str(value)
        return value

    if isinstance(value, dict):
        return {k: _to_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json_safe(v) for v in value]

    try:
        import pandas as pd
        if isinstance(value, pd.DataFrame):
            data_records = _to_json_safe(value.to_dict(orient="records"))
            return {
                "__snapshot_type__": "pandas_dataframe",
                "columns": list(value.columns),
                "data": data_records,
                "dtypes": {str(k): str(v) for k, v in value.dtypes.items()},
                "row_count": len(value),
            }
        if isinstance(value, pd.Series):
            return _to_json_safe(value.tolist())
        if isinstance(value, pd.Timestamp):
            return str(value)
    except ImportError:
        pass

    try:
        import numpy as np
        if isinstance(value, np.integer):
            return int(value)
        if isinstance(value, np.floating):
            v2 = float(value)
            if math.isnan(v2):
                return None
            if math.isinf(v2):
                return str(v2)
            return v2
        if isinstance(value, np.bool_):
            return bool(value)
        if isinstance(value, np.ndarray):
            return _to_json_safe(value.tolist())
    except ImportError:
        pass

    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, datetime.timedelta):
        return value.total_seconds()

    try:
        from decimal import Decimal
        if isinstance(value, Decimal):
            return float(value)
    except ImportError:
        pass

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, set):
        return _to_json_safe(list(value))

    return str(value)


def _from_snapshot_value(value: object) -> object:
    if isinstance(value, dict):
        marker = value.get("__snapshot_type__")
        if marker == "pandas_dataframe":
            data = value.get("data")
            columns = value.get("columns")
            if isinstance(data, list) and isinstance(columns, list):
                try:
                    import pandas as pd
                    df = pd.DataFrame(data)
                    if len(df.columns) == len(columns):
                        df.columns = columns
                    raw_dtypes = value.get("dtypes")
                    if isinstance(raw_dtypes, dict):
                        for col, dt_str in raw_dtypes.items():
                            if col in df.columns and "datetime" in dt_str.lower():
                                try:
                                    df[col] = pd.to_datetime(df[col])
                                except Exception:
                                    pass
                    return df
                except ImportError:
                    pass
            return value

        if value.get("__type__") == "dataframe":
            data = value.get("data")
            columns = value.get("columns")
            if isinstance(data, list) and isinstance(columns, list):
                try:
                    import pandas as pd
                    df = pd.DataFrame(data)
                    if len(df.columns) == len(columns):
                        df.columns = columns
                    return df
                except ImportError:
                    pass
            return value

        return {k: _from_snapshot_value(v) for k, v in value.items()}

    if isinstance(value, list):
        return [_from_snapshot_value(v) for v in value]

    return value


@dataclass
class LoopState:
    iteration: int = 0
    max_steps: int = 5
    done: bool = False
    history: list[dict] = field(default_factory=list)


@dataclass
class PlanningState:
    plans: list[dict] = field(default_factory=list)
    clarifications: list[dict] = field(default_factory=list)


@dataclass
class ResultBlock:
    block_id: str
    step: int
    block_type: str
    status: str
    question: str
    plan: dict
    dsl: dict
    result: object
    statistics: dict | None = None
    execution_meta: dict = field(default_factory=dict)
    error: object = None
    block: str = ""


@dataclass
class ResultsState:
    blocks: list[str] = field(default_factory=list)
    structured_blocks: list[ResultBlock] = field(default_factory=list)
    entries: list[dict] = field(default_factory=list)


@dataclass
class MemoryState:
    facts: list[dict] = field(default_factory=list)
    working_memory: dict = field(
        default_factory=lambda: {
            "current_hypothesis": None,
            "focus_dimension": None,
            "analysis_stage": "init",
        }
    )
    missing_info: dict = field(default_factory=dict)


@dataclass
class FinalState:
    answer: str = ""
    grounded_answer: str = ""
    status: str = ""
    execution_success: bool = False
    error: str = ""


@dataclass
class AgentState:
    question: str
    normalized_question: str | None = None
    loop: LoopState = field(default_factory=LoopState)
    planning: PlanningState = field(default_factory=PlanningState)
    results: ResultsState = field(default_factory=ResultsState)
    memory: MemoryState = field(default_factory=MemoryState)
    final: FinalState = field(default_factory=FinalState)

    @property
    def goal(self) -> str:
        return self.question

    def add_step(self, action: dict, result: str) -> None:
        self.loop.history.append({"action": action, "result": result})
        self.loop.iteration += 1

    @staticmethod
    def _fact_key(fact: dict) -> tuple:
        def _hashable(v: object) -> object:
            if v is None or isinstance(v, (str, int, float, bool)):
                return v
            if isinstance(v, (dict, list, tuple, set)):
                try:
                    return json.dumps(v, ensure_ascii=False, sort_keys=True, default=str)
                except Exception:
                    return str(v)
            try:
                hash(v)
                return v
            except Exception:
                return str(v)

        fact_type = fact.get("fact_type")
        metric = fact.get("metric")
        dataset = fact.get("dataset")
        dimension = fact.get("dimension")
        time_range = fact.get("time_range") if isinstance(fact.get("time_range"), dict) else {}
        start = time_range.get("start")
        end = time_range.get("end")
        grain = time_range.get("grain")
        source = fact.get("source") if isinstance(fact.get("source"), dict) else {}
        block_id = source.get("block_id") or fact.get("source_block_id")
        return (
            _hashable(fact_type),
            _hashable(metric),
            _hashable(dataset),
            _hashable(dimension),
            _hashable(start),
            _hashable(end),
            _hashable(grain),
            _hashable(block_id),
        )

    def merge_facts(self, new_facts: object) -> None:
        if not isinstance(self.memory.facts, list):
            self.memory.facts = []

        facts_to_add: list[dict] = []
        if isinstance(new_facts, list):
            for f in new_facts:
                if isinstance(f, dict) and f:
                    facts_to_add.append(f)
        elif isinstance(new_facts, dict):
            for k, v in new_facts.items():
                if not (isinstance(k, str) and k.strip()):
                    continue
                facts_to_add.append({"fact_type": "legacy_kv", "key": k, "value": v})
        else:
            return

        existing = {AgentState._fact_key(f) for f in self.memory.facts if isinstance(f, dict)}
        for f in facts_to_add:
            key = AgentState._fact_key(f)
            if key in existing:
                continue
            self.memory.facts.append(f)
            existing.add(key)

    def update_working_memory(self, updates: object) -> None:
        if not isinstance(updates, dict):
            return
        if not isinstance(self.memory.working_memory, dict):
            self.memory.working_memory = {}
        for k, v in updates.items():
            if isinstance(k, str) and k.strip():
                self.memory.working_memory[k] = v

    def to_snapshot(self) -> dict:
        raw = {
            "question": self.question,
            "normalized_question": self.normalized_question,
            "loop": {
                "iteration": self.loop.iteration,
                "max_steps": self.loop.max_steps,
                "done": self.loop.done,
                "history": self.loop.history,
            },
            "planning": {
                "plans": self.planning.plans,
                "clarifications": self.planning.clarifications,
            },
            "results": {
                "blocks": self.results.blocks,
                "structured_blocks": [
                    {
                        "block_id": sb.block_id,
                        "step": sb.step,
                        "block_type": sb.block_type,
                        "status": sb.status,
                        "question": sb.question,
                        "plan": sb.plan,
                        "dsl": sb.dsl,
                        "result": sb.result,
                        "statistics": sb.statistics,
                        "execution_meta": sb.execution_meta,
                        "error": sb.error,
                        "block": sb.block,
                    }
                    for sb in (self.results.structured_blocks or [])
                ],
                "entries": self.results.entries,
            },
            "memory": {
                "facts": self.memory.facts,
                "working_memory": self.memory.working_memory,
                "missing_info": self.memory.missing_info,
            },
            "final": {
                "answer": self.final.answer,
                "grounded_answer": self.final.grounded_answer,
                "status": self.final.status,
                "execution_success": self.final.execution_success,
                "error": self.final.error,
            },
        }
        return _to_json_safe(raw)

    @staticmethod
    def from_snapshot(data: dict) -> "AgentState":
        data = _from_snapshot_value(data)

        loop_data = data.get("loop", {})
        loop = LoopState(
            iteration=loop_data.get("iteration", 0),
            max_steps=loop_data.get("max_steps", 5),
            done=loop_data.get("done", False),
            history=loop_data.get("history", []),
        )

        planning_data = data.get("planning", {})
        planning = PlanningState(
            plans=planning_data.get("plans", []),
            clarifications=planning_data.get("clarifications", []),
        )

        results_data = data.get("results", {})
        structured = []
        for sb in (results_data.get("structured_blocks") or []):
            if not isinstance(sb, dict):
                continue
            structured.append(ResultBlock(
                block_id=sb.get("block_id", ""),
                step=sb.get("step", 0),
                block_type=sb.get("block_type", "unknown"),
                status=sb.get("status", "success"),
                question=sb.get("question", ""),
                plan=sb.get("plan", {}),
                dsl=sb.get("dsl", {}),
                result=sb.get("result"),
                statistics=sb.get("statistics"),
                execution_meta=sb.get("execution_meta", {}),
                error=sb.get("error"),
                block=sb.get("block", ""),
            ))
        results = ResultsState(
            blocks=results_data.get("blocks", []),
            structured_blocks=structured,
            entries=results_data.get("entries", []),
        )

        memory_data = data.get("memory", {})
        restored_wm = dict(memory_data.get("working_memory", {}))
        merged_wm = dict(_DEFAULT_WORKING_MEMORY)
        merged_wm.update(restored_wm)
        memory = MemoryState(
            facts=memory_data.get("facts", []),
            working_memory=merged_wm,
            missing_info=dict(memory_data.get("missing_info", {})),
        )

        final_data = data.get("final", {})
        final = FinalState(
            answer=final_data.get("answer", ""),
            grounded_answer=final_data.get("grounded_answer", ""),
            status=final_data.get("status", ""),
            execution_success=final_data.get("execution_success", False),
            error=final_data.get("error", ""),
        )

        return AgentState(
            question=data.get("question", ""),
            normalized_question=data.get("normalized_question"),
            loop=loop,
            planning=planning,
            results=results,
            memory=memory,
            final=final,
        )


AgentRuntimeState = AgentState
