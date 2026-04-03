import argparse
from smolagents.memory import ActionStep


MAX_AGENT_STEPS = 30


def remind_final_answer(step):
    """Callback to remind agent to call final_answer when running low on steps."""
    if not isinstance(step, ActionStep):
        return
    if step.step_number > MAX_AGENT_STEPS - 1:
        step.observations = (step.observations or "") + (
            "\n\n⚠️ You have no more steps! "
            "Call `final_answer` NOW with your best answer."
        )


def parse_arguments():
    parser = argparse.ArgumentParser(description="Sophy coding agent harness")
    parser.add_argument("--api_base", type=str, default=None, help="API base URL for the model")
    parser.add_argument("--api_key", type=str, default=None, help="API key for the model")
    parser.add_argument("--model", type=str, default=None, help="Model ID to use")
    return parser.parse_args()
