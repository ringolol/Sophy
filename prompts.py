from enum import Enum
from smolagents import FinalAnswerPromptTemplate, ManagedAgentPromptTemplate, PlanningPromptTemplate, PromptTemplates

from tools import TOOLS, EXPLORATION_TOOLS, SUB_AGENTS
from prompts_data import (
    DIRECT_PROMPT_TEMPLATE, ROLE_TASK_SOLVER,
    DIRECT_CODE_PROMPT_TEMPLATE, ROLE_CODE_TASK_SOLVER,
    ROLE_EXPLORER, EXPLORER_PROMPT_TEMPLATE, ROLE_CODE_EXPLORER, EXPLORER_CODE_PROMPT_TEMPLATE
)


class AgentRole(Enum):
    SOLVER = "solver"
    EXPLORER = "explorer"


def format_tool_as_json(tool) -> str:
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


def build_system_prompt(
    tools: list,
    template: str,
    agent_role: str,
    use_code_format: bool,
    project_description: str = "",
) -> str:
    """Build the system prompt with tool descriptions generated from the tool objects."""

    tool_sections = {
        "file_ops": ["read_file", "edit_file", "insert_text", "write_new_file", "delete_file", "move_file"],
        "search": ["search_files", "search_content"],
        "system": ["run_command", "execute_python"],
        "navigation": ["list_directory", "get_tree"],
        "web": ["web_search", "visit_webpage"],
        "communication": ["ask_user", "get_conversation_history"],
        "completion": ["final_answer"],
        "exploration": ["explorer"],
    }

    tool_by_name = {t.name: t for t in tools}

    def section_lines(section_name):
        names = tool_sections.get(section_name, set())
        formatter = format_tool_as_function if use_code_format else format_tool_as_json
        return "\n".join(formatter(tool_by_name[n]) for n in names if n in tool_by_name) or "(none)"


    return template.format(
        agent_role=agent_role,
        exploration_description=section_lines("exploration"),
        file_ops_description=section_lines("file_ops"),
        search_description=section_lines("search"),
        system_description=section_lines("system"),
        navigation_description=section_lines("navigation"),
        web_description=section_lines("web"),
        communication_description=section_lines("communication"),
        completion_description=section_lines("completion"),
        project_description=project_description,
    )


def get_project_description() -> str:
    project_description = ''
    try:
        with open('CLAUDE.md', 'r') as f:
            claud_md = f.read().strip()
            project_description = f"\n\nCurrent Project:\n{claud_md}\n"
    except FileNotFoundError:
        pass
    return project_description


def build_prompt(
    role: AgentRole,
    use_code_format: bool = False
) -> PromptTemplates:
    """Build the system prompt and templates based on the agent role."""

    if role == AgentRole.SOLVER:
        template = DIRECT_CODE_PROMPT_TEMPLATE if use_code_format else DIRECT_PROMPT_TEMPLATE
        agent_role = ROLE_CODE_TASK_SOLVER if use_code_format else ROLE_TASK_SOLVER
        tools = TOOLS + SUB_AGENTS
        managed_agent = ManagedAgentPromptTemplate(task="", report="")
    elif role == AgentRole.EXPLORER:
        template = EXPLORER_CODE_PROMPT_TEMPLATE if use_code_format else EXPLORER_PROMPT_TEMPLATE
        agent_role = ROLE_CODE_EXPLORER if use_code_format else ROLE_EXPLORER
        tools = EXPLORATION_TOOLS
        managed_agent = ManagedAgentPromptTemplate(
            task="Your exploration task:\n{{task}}\n\n",
            report="{{final_answer}}",
        )
    else:
        raise ValueError(f"Unknown agent role: {role}")

    system_prompt = build_system_prompt(
        tools=tools,
        project_description="",
        agent_role=agent_role,
        use_code_format=use_code_format,
        template=template,
    )

    return PromptTemplates(
        system_prompt=system_prompt,
        planning=PlanningPromptTemplate(
            initial_plan="",
            update_plan_pre_messages="",
            update_plan_post_messages="",
        ),
        managed_agent=managed_agent,
        final_answer=FinalAnswerPromptTemplate(pre_messages="", post_messages=""),
    )

