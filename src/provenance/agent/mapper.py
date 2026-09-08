"""The Control Mapper: for one control on one system, draft the implementation
statement from the evidence and the control text, citing every row and the control id
it read. It never asserts coverage it did not read; a control with no evidence gets a
statement that says so.

    python -m provenance.agent.mapper sys-windrow-prod 3.3.1

Same runner, same rails, same door as the Evidence Collector; a different prompt and
its own identity, `control-mapper`, with its own policy grant. Serves: BR-2, BR-3.
"""

from __future__ import annotations

import asyncio
import json
import sys

from provenance.agent.run import main as run_agent


def question_for(system_id: str, control_id: str) -> str:
    return (
        f"Draft the implementation statement for control {control_id} on system {system_id}. "
        f"First read the control's requirement with get_control (framework \"800-171\"), then read the "
        f"evidence with get_evidence. Write two to four sentences stating how the requirement is met, "
        f"citing the row_id of every piece of evidence you rely on and the control id you read. "
        f"If get_evidence returns no rows, state plainly that no evidence is held for this control "
        f"and cite no rows."
    )


async def main(system_id: str, control_id: str, token: str | None = None) -> dict:
    result = await run_agent(question_for(system_id, control_id), agent="control-mapper", token=token)
    result.update(system_id=system_id, control_id=control_id)
    return result


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    print("\n=== RESULT ===")
    print(json.dumps(asyncio.run(main(sys.argv[1], sys.argv[2])), indent=2))
