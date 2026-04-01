from smolagents import FinalAnswerPromptTemplate, ManagedAgentPromptTemplate, PlanningPromptTemplate, PromptTemplates

from tools import TOOLS, EXPLORATION_TOOLS
from prompts_data import (
    DIRECT_PROMPT_TEMPLATE, ROLE_TASK_SOLVER,
    DIRECT_CODE_PROMPT_TEMPLATE, ROLE_CODE_TASK_SOLVER,
    EXPLORER_PROMPT_TEMPLATE, ROLE_EXPLORER, EXPLORER_TOOL_DESCRIPTION,
)


def format_tool_description(tool) -> str:
    """Format a single tool into a prompt-friendly string."""
    args = []
    for arg_name, arg_info in tool.inputs.items():
        arg_type = arg_info.get("type", "any")
        nullable = arg_info.get("nullable", False)
        suffix = "?" if nullable else ""
        args.append(f"{arg_name}{suffix}: {arg_type}")
    return f"- {tool.name}: {tool.description} Args: {{{', '.join(args)}}}"


def format_tool_as_function(tool) -> str:
    """Format a tool as a Python function signature with docstring."""
    args = []
    for arg_name, arg_info in tool.inputs.items():
        arg_type = arg_info.get("type", "any")
        nullable = arg_info.get("nullable", False)
        default = " = None" if nullable else ""
        args.append(f"{arg_name}: {arg_type}{default}")
    sig = f"def {tool.name}({', '.join(args)}) -> str:"
    doc = f'    """{tool.description}"""'
    return f"{sig}\n{doc}\n"


def build_solver_prompt(tools: list, project_description: str, agent_role: str = ROLE_TASK_SOLVER) -> str:
    """Build the system prompt with tool descriptions generated from the tool objects."""

    tool_sections = {
        "file_ops": ["read_file", "edit_file", "insert_text", "write_new_file", "delete_file", "move_file"],
        "search": ["search_files", "search_content"],
        "system": ["run_command", "execute_python"],
        "navigation": ["list_directory", "get_tree"],
        "web": ["web_search", "visit_webpage"],
        "communication": ["ask_user", "get_conversation_history"],
        "completion": ["final_answer"],
    }

    tool_by_name = {t.name: t for t in tools}

    def section_lines(section_name):
        names = tool_sections.get(section_name, set())
        return "\n".join(format_tool_description(tool_by_name[n]) for n in names if n in tool_by_name) or "(none)"

    return DIRECT_PROMPT_TEMPLATE.format(
        agent_role=agent_role,
        exploration_description=EXPLORER_TOOL_DESCRIPTION,
        file_ops_description=section_lines("file_ops"),
        search_description=section_lines("search"),
        system_description=section_lines("system"),
        navigation_description=section_lines("navigation"),
        web_description=section_lines("web"),
        communication_description=section_lines("communication"),
        completion_description=section_lines("completion"),
        project_description=project_description,
    )


def build_code_solver_prompt(tools: list, project_description: str, agent_role: str = ROLE_CODE_TASK_SOLVER) -> str:
    """Build the system prompt for code-based agents (no tool-calling support)."""

    tool_sections = {
        "file_ops": ["read_file", "edit_file", "insert_text", "write_new_file", "delete_file", "move_file"],
        "search": ["search_files", "search_content"],
        "system": ["run_command", "execute_python"],
        "navigation": ["list_directory", "get_tree"],
        "web": ["web_search", "visit_webpage"],
        "communication": ["ask_user", "get_conversation_history"],
        "completion": ["final_answer"],
    }

    tool_by_name = {t.name: t for t in tools}

    def section_lines(section_name):
        names = tool_sections.get(section_name, set())
        return "\n".join(format_tool_as_function(tool_by_name[n]) for n in names if n in tool_by_name) or "(none)"

    return DIRECT_CODE_PROMPT_TEMPLATE.format(
        agent_role=agent_role,
        exploration_description=EXPLORER_TOOL_DESCRIPTION,
        file_ops_description=section_lines("file_ops"),
        search_description=section_lines("search"),
        system_description=section_lines("system"),
        navigation_description=section_lines("navigation"),
        web_description=section_lines("web"),
        communication_description=section_lines("communication"),
        completion_description=section_lines("completion"),
        project_description=project_description,
    )


def build_explorer_prompt(tools: list) -> str:
    """Build the explorer sub-agent's system prompt (flat tool list, no sections)."""
    lines = [format_tool_description(t) for t in tools]
    return EXPLORER_PROMPT_TEMPLATE.format(
        agent_role=ROLE_EXPLORER,
        tools_description="\n".join(lines),
    )


project_description = ''
try:
    with open('CLAUDE.md', 'r') as f:
        claud_md = f.read().strip()
        project_description = f"\n\nCurrent Project:\n```\n{claud_md}\n```"
except FileNotFoundError:
    pass

explorer_prompt = PromptTemplates(
    system_prompt=build_explorer_prompt(EXPLORATION_TOOLS),
    planning=PlanningPromptTemplate(
        initial_plan="",
        update_plan_pre_messages="",
        update_plan_post_messages="",
    ),
    managed_agent=ManagedAgentPromptTemplate(
        task=(
            "Your exploration task:\n{{task}}\n\n"
        ),
        report="{{final_answer}}",
    ),
    final_answer=FinalAnswerPromptTemplate(pre_messages="", post_messages=""),
)

direct_solver_prompt = PromptTemplates(
    system_prompt=build_solver_prompt(TOOLS, project_description),
    planning=PlanningPromptTemplate(
        initial_plan="",
        update_plan_pre_messages="",
        update_plan_post_messages="",
    ),
    managed_agent=ManagedAgentPromptTemplate(task="", report=""),
    final_answer=FinalAnswerPromptTemplate(pre_messages="", post_messages=""),
)

direct_code_solver_prompt = PromptTemplates(
    system_prompt=build_code_solver_prompt(TOOLS, project_description),
    planning=PlanningPromptTemplate(
        initial_plan="",
        update_plan_pre_messages="",
        update_plan_post_messages="",
    ),
    managed_agent=ManagedAgentPromptTemplate(task="", report=""),
    final_answer=FinalAnswerPromptTemplate(pre_messages="", post_messages=""),
)
