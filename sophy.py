from smolagents import AgentError, FinalAnswerPromptTemplate, ManagedAgentPromptTemplate, PlanningPromptTemplate, PromptTemplates, ToolCallingAgent, LogLevel
from smolagents.memory import ActionStep

from monkey_patches import apply_monkey_patches, apply_explorer_patches
from utils import ToolDeniedException, SupportedModels, console, remind_final_answer, MAX_AGENT_STEPS
from model import ThinkingModel
from tools import TOOLS, EXPLORATION_TOOLS, set_history_provider
from session import Session, load_session, pick_session
from prompts import direct_prompt, explorer_prompt


session = Session()
set_history_provider(session.get_summary)

model = ThinkingModel(
    model_id=SupportedModels.qwen_3_5_35b_a3b.value,
    api_base="http://localhost:11434/v1",
    api_key="ollama",
)

explorer = ToolCallingAgent(
    tools=EXPLORATION_TOOLS,
    add_base_tools=False,
    prompt_templates=explorer_prompt,
    model=model,
    max_steps=10,
    verbosity_level=LogLevel.INFO,
    stream_outputs=True,
    name="explorer",
    description=(
        "Explores the filesystem: reads files, searches for files and content, "
        "lists directories, and builds tree views. "
        "Use this for complex multi-step exploration tasks. "
        "For quick single-file reads, use your own read_file tool instead."
    ),
    provide_run_summary=False,
)
apply_explorer_patches(explorer)

agent = ToolCallingAgent(
    tools=TOOLS,
    add_base_tools=False,
    prompt_templates=direct_prompt,
    model=model,
    max_steps=MAX_AGENT_STEPS,
    verbosity_level=LogLevel.INFO,
    stream_outputs=True,
    managed_agents=[explorer],
    step_callbacks=[remind_final_answer],
)
apply_monkey_patches(agent)

console.print(f'[dim]{agent.system_prompt}[/dim]')


def agent_loop():
    session = pick_session()
    console.print(f"[dim][bold]Session:[/bold] {session.id}[/dim]")
    console.print("Type /quit to exit, /resume to switch sessions, /new to create a new session. Ctrl+C to stop execution\n")
    load_session(agent, session)

    task_prefix = ""
    while True:
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
            session = Session()
            agent.memory.reset()
            console.print(f"[dim][bold]Session:[/bold] {session.id}[/dim]\n")
            continue
        if task == "/resume":
            task_prefix = ''
            if session.entries:
                session.save_auto()
            session = pick_session()
            console.print(f"[dim][bold]Session:[/bold] {session.id}[/dim]\n")
            load_session(agent, session)
            continue

        try:
            result = agent.run(task_prefix + task, reset=False)
            task_prefix = ""

            tools_used = []
            for step in agent.memory.steps:
                if isinstance(step, ActionStep) and step.tool_calls:
                    for tc in step.tool_calls:
                        tools_used.append(tc.name)

            session.add_entry(
                task=task,
                result=str(result),
                steps=agent.memory.get_full_steps(),
                tools_used=tools_used,
            )
        except ToolDeniedException as e:
            console.print(f"\n[red]{e}[/red]\n")
            task_prefix = str(e) + '\n\n'
        except (AgentError, KeyboardInterrupt):
            console.print(f"\n[red]The execution was stopped manually[/red]\n")
            task_prefix = "User stopped the last tool execution manually. Be attentive User may ask you to explain or change something about the last task!\n\n"
            session.add_entry(
                task=task,
                result="[interrupted]",
                steps=agent.memory.get_full_steps(),
                tools_used=[tc.name for step in agent.memory.steps if isinstance(step, ActionStep) and step.tool_calls for tc in step.tool_calls],
            )
        finally:
            session.save_auto()


if __name__ == "__main__":
    agent_loop()
