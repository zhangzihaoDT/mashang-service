import json
from dataclasses import dataclass, field


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


AgentRuntimeState = AgentState
