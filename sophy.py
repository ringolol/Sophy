#!/usr/bin/env python3

import argparse
import os
import traceback

from smolagents import ToolCallingAgent, LogLevel
from smolagents.memory import ActionStep

from monkey_patches import apply_monkey_patches, apply_explorer_monkey_patches
from utils import ToolDeniedException, SupportedModels, console, remind_final_answer, MAX_AGENT_STEPS
from context_compression import maybe_compress, compress
from model import ThinkingModel
from tools import TOOLS, EXPLORATION_TOOLS, set_history_provider
from session import Session, load_session, pick_session
from prompts import direct_solver_prompt, explorer_prompt


session_holder = [Session()]
set_history_provider(session_holder[0].get_summary)

parser = argparse.ArgumentParser(description="Sophy coding agent harness")
_gemini_key = os.environ.get("GEMINI_API_KEY")
_use_gemini = _gemini_key is not None

parser.add_argument(
        "--api_base", 
        type=str,
        default=os.environ.get(
            "SOPHY_MODEL_API", 
            "https://generativelanguage.googleapis.com/v1beta/openai/" 
                if _use_gemini else "http://localhost:11434/v1"
        ), 
        help="API base URL for the model"
)
parser.add_argument(
        "--api_key", 
        type=str, 
        default=_gemini_key or "ollama", 
        help="API key for the model"
)
parser.add_argument(
        "--model", 
        type=str, 
        default=SupportedModels.gemini_3_27b.value 
            if _use_gemini else SupportedModels.qwen_3_5_35b_a3b.value, 
        help="Model ID to use"
)
args = parser.parse_args()

model = ThinkingModel(
    model_id=args.model,
    api_base=args.api_base,
    api_key=args.api_key,
)

explorer = ToolCallingAgent(
    tools=EXPLORATION_TOOLS,
    add_base_tools=False,
    prompt_templates=explorer_prompt,
    model=model,
    max_steps=MAX_AGENT_STEPS,
    verbosity_level=LogLevel.INFO,
    stream_outputs=True,
    name="explorer",
    description="-",
    provide_run_summary=False,
    step_callbacks=[remind_final_answer],
)
apply_explorer_monkey_patches(explorer)

main_agent = ToolCallingAgent(
    tools=TOOLS,
    add_base_tools=False,
    prompt_templates=direct_solver_prompt,
    model=model,
    max_steps=MAX_AGENT_STEPS,
    verbosity_level=LogLevel.INFO,
    stream_outputs=True,
    managed_agents=[explorer],
    step_callbacks=[remind_final_answer],
)
apply_monkey_patches(main_agent)

def agent_loop():
    console.print(f'[dim]{main_agent.system_prompt}[/dim]')
    session_holder[0] = pick_session()
    console.print(f"[dim][bold]Session:[/bold] {session_holder[0].id}[/dim]")
    console.print("Type /quit to exit, /resume to switch sessions, /new to create a new session, /compress to compress context. Ctrl+C to stop execution\n")
    load_session(main_agent, session_holder[0])

    task_prefix = ""
    while True:
        session = session_holder[0]
        task = input("❯ ").strip()
        if not task:
            continue
        if task == "/quit":
            if session.entries:
                session.save_auto()
                console.print(f"[green]Session {session.id} saved.[/green]")
            break
        if task == "/new":
            task_prefix = ''
            if session.entries:
                session.save_auto()
            session_holder[0] = Session()
            main_agent.memory.reset()
            console.print(f"[dim][bold]Session:[/bold] {session_holder[0].id}[/dim]\n")
            continue
        if task == "/compress":
            compress(main_agent, session_holder)
            continue
        if task == "/resume":
            task_prefix = ''
            if session.entries:
                session.save_auto()
            session_holder[0] = pick_session()
            console.print(f"[dim][bold]Session:[/bold] {session_holder[0].id}[/dim]\n")
            load_session(main_agent, session_holder[0])
            continue

        try:
            maybe_compress(main_agent, session_holder)
            result = main_agent.run(task_prefix + task, reset=False)
            task_prefix = ""
            session = session_holder[0]

            tools_used = []
            for step in main_agent.memory.steps:
                if isinstance(step, ActionStep) and step.tool_calls:
                    for tc in step.tool_calls:
                        tools_used.append(tc.name)

            session.add_entry(
                task=task,
                result=str(result),
                steps=main_agent.memory.get_full_steps(),
                tools_used=tools_used,
            )
        except (KeyboardInterrupt, ToolDeniedException):
            console.print(f"\n[red]The execution was stopped manually[/red]\n")
            task_prefix = "[User stopped the last tool execution manually! Be attentive User could ask you to change something about the last task!]\n\n"
            session_holder[0].add_entry(
                task=task,
                result="[interrupted]",
                steps=main_agent.memory.get_full_steps(),
                tools_used=[tc.name for step in main_agent.memory.steps if isinstance(step, ActionStep) and step.tool_calls for tc in step.tool_calls],
            )
        except Exception:
            console.print(f'[red]{traceback.format_exc()}[/red]')
        finally:
            session_holder[0].save_auto()


def main():
    agent_loop()


if __name__ == "__main__":
    main()
