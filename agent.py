from smolagents import FinalAnswerPromptTemplate, ManagedAgentPromptTemplate, PlanningPromptTemplate, PromptTemplates, ToolCallingAgent, LogLevel
from smolagents.memory import ActionStep

from utils import ToolDeniedException, SupportedModels
from model import ThinkingModel
from tools import TOOLS, set_history_provider
from prompts import build_prompt
from session import Session, list_sessions, restore_memory


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
    print("Sessions:")
    print("  [0] New session")
    for i, s in enumerate(saved, 1):
        print(f"  [{i}] {s['id']} — {s['created_at'][:10]} — {s['entry_count']} entries — \"{s['preview']}\"")
    choice = input("Choose session [0]: ").strip()
    if not choice or choice == "0":
        return Session()
    try:
        idx = int(choice)
        if 1 <= idx <= len(saved):
            return Session.load(saved[idx - 1]["path"])
    except ValueError:
        pass
    print("Invalid choice, starting new session.")
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

print(agent.system_prompt)

def load_session(s: Session):
    """Print session history and restore agent memory."""
    if s.entries:
        print(f"\n--- Session history ({len(s.entries)} entries) ---")
        for i, entry in enumerate(s.entries, 1):
            print(f"  [{i}] User: {entry.task}")
            print(f"      Result: {entry.result}")
            if entry.tools_used:
                print(f"      Tools: {', '.join(entry.tools_used)}")
        print("---\n")
        restore_memory(agent, s)


if __name__ == "__main__":
    session = pick_session()
    print(f"Session: {session.id}\nType /quit to save & exit, /resume to switch sessions.\n")
    load_session(session)

    task_prefix = ""
    while True:
        task = input("❯ ").strip()
        if not task:
            continue
        if task == "/quit":
            if session.entries:
                session.save_auto()
                print(f"Session {session.id} saved.")
            break
        if task == "/new":
            if session.entries:
                session.save_auto()
            session = Session()
            agent.memory.reset()
            print(f"Session: {session.id}\n")
            continue
        if task == "/resume":
            if session.entries:
                session.save_auto()
            session = pick_session()
            print(f"Session: {session.id}\n")
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
            print(f"\n{e}\n")
            task_prefix = str(e) + '\n\n'
