from smolagents import FinalAnswerPromptTemplate, ManagedAgentPromptTemplate, PlanningPromptTemplate, PromptTemplates, ToolCallingAgent, LogLevel
from smolagents.memory import ActionStep
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from utils import ToolDeniedException, SupportedModels
from model import ThinkingModel
from tools import TOOLS, set_history_provider
from prompts import build_prompt
from session import Session, list_sessions, restore_memory

console = Console()


def remind_final_answer(step):
    if not isinstance(step, ActionStep):
        return
    if step.step_number >= agent.max_steps - 2:
        step.observations = (step.observations or "") + (
            "\n\n⚠️ You are running low on steps. "
            "Call `final_answer` NOW with your best answer."
        )


def pick_session() -> Session:
    saved = list_sessions()
    table = Table(title="Sessions", show_header=True, header_style="bold cyan")
    table.add_column("#", style="bold")
    table.add_column("ID")
    table.add_column("Date")
    table.add_column("Entries", justify="right")
    table.add_column("Preview")
    table.add_row("0", "[green]New session[/green]", "", "", "")
    for i, s in enumerate(saved, 1):
        table.add_row(str(i), s['id'], s['created_at'][:10], str(s['entry_count']), s['preview'])
    console.print(table)
    choice = input("Choose session [0]: ").strip()
    if not choice or choice == "0":
        return Session()
    try:
        idx = int(choice)
        if 1 <= idx <= len(saved):
            return Session.load(saved[idx - 1]["path"])
    except ValueError:
        pass
    console.print("[red]Invalid choice, starting new session.[/red]")
    return Session()


session = Session()
set_history_provider(session.get_summary)

model = ThinkingModel(
    model_id=SupportedModels.qwen_3_5_35b_a3b.value,
    api_base="http://localhost:11434/v1",
    api_key="ollama",
)


agent = ToolCallingAgent(
    tools=TOOLS,
    add_base_tools=False,
    prompt_templates=PromptTemplates(
        system_prompt=build_prompt(TOOLS),
        planning=PlanningPromptTemplate(
            initial_plan="",
            update_plan_pre_messages="",
            update_plan_post_messages="",
        ),
        managed_agent=ManagedAgentPromptTemplate(task="", report=""),
        final_answer=FinalAnswerPromptTemplate(pre_messages="", post_messages=""),
    ),
    model=model,
    max_steps=20,
    verbosity_level=LogLevel.INFO,
    stream_outputs=True,
    step_callbacks=[remind_final_answer],
)

# Hide observation logs — they're noisy and we show tool results via confirm()
_original_log = agent.logger.log
def _filtered_log(*args, **kwargs):
    if args and isinstance(args[0], str) and args[0].startswith("Observations:"):
        return
    _original_log(*args, **kwargs)
agent.logger.log = _filtered_log

# Hide raw tool call JSON from the streamed Live display
import re
from smolagents.models import ChatMessage
_TOOL_CALL_RE = re.compile(r"\{\"name\":\s*\".*$", re.DOTALL)
def _clean_render(self):
    text = str(self.content or "")
    text = _TOOL_CALL_RE.sub("", text)
    return text.strip()
ChatMessage.render_as_markdown = _clean_render

# console.print(agent.system_prompt)

def load_session(s: Session):
    """Print session history and restore agent memory."""
    if s.entries:
        console.rule(f"[bold cyan]Session History ({len(s.entries)} entries)[/bold cyan]")
        for entry in s.entries:
            console.print(Panel(entry.task, title="[bold green]You[/bold green]", title_align="left", border_style="green", padding=(0, 1)))
            console.print(Panel(entry.result, title="[bold blue]Agent[/bold blue]", title_align="left", border_style="blue", padding=(0, 1)))
        console.rule(style="dim")
        console.print()
        restore_memory(agent, s)


if __name__ == "__main__":
    session = pick_session()
    console.print(f"[dim][bold]Session:[/bold] {session.id}[/dim]")
    console.print("Type /quit to save & exit, /resume to switch sessions.\n")
    load_session(session)

    task_prefix = ""
    while True:
        task = input("❯ ").strip()
        # Clear the input line (move up one line, clear it)
        print("\033[A\033[2K", end="", flush=True)
        if not task:
            continue
        if task == "/quit":
            if session.entries:
                session.save_auto()
                console.print(f"[green]Session {session.id} saved.[/green]")
            break
        if task == "/new":
            if session.entries:
                session.save_auto()
            session = Session()
            agent.memory.reset()
            console.print(f"[bold]Session:[/bold] {session.id}\n")
            continue
        if task == "/resume":
            if session.entries:
                session.save_auto()
            session = pick_session()
            console.print(f"[bold]Session:[/bold] {session.id}\n")
            load_session(session)
            continue
        try:
            result = agent.run(task_prefix + task, reset=False)
            task_prefix = ""

            # Extract history from memory before next run resets it
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
            session.save_auto()
        except ToolDeniedException as e:
            console.print(f"\n[red]{e}[/red]\n")
            task_prefix = str(e) + '\n\n'
