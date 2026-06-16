__all__ = ["run_turn", "TurnResult"]


def __getattr__(name: str):
    if name == "run_turn":
        from one_person_dnd.engine.orchestrator import run_turn

        return run_turn
    if name == "TurnResult":
        from one_person_dnd.engine.orchestrator import TurnResult

        return TurnResult
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
