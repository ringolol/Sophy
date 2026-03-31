from smolagents import FinalAnswerPromptTemplate, ManagedAgentPromptTemplate, PlanningPromptTemplate, PromptTemplates

from tools import TOOLS, EXPLORATION_TOOLS


DIRECT_PROMPT_TEMPLATE = """{agent_role}

# The Loop
1. **Action**: You output a JSON blob calling a tool.
2. **Observation**: You will receive the tool's output.
3. **Repeat**: Use the observation to inform your next Action.
4. **Finality**: To finish, you MUST call the `final_answer` tool. This is the ONLY way to end the task.

Action format:
{{"name": "tool_name", "arguments": {{"arg": "value"}}}}

Example:
Task: "What is 5 + 3 + 1294.678?"

Action:
{{"name": "python_interpreter", "arguments": {{"code": "print(5 + 3 + 1294.678)"}}}}
Observation: 1302.678

Action:
{{"name": "final_answer", "arguments": {{"answer": "1302.678"}}}}

AVAILABLE TOOLS:
{tools_description}

MANDATORY RULES — VIOLATION MEANS FAILURE:
1. NO PROSE: Do not explain your thought process unless the tool requires it. Output the JSON Action blob immediately.
2. JSON INTEGRITY: Every response MUST contain a valid JSON tool call. If you provide no JSON, you fail. If you see the error "does not contain any JSON blob" — you failed to include an Action. Fix it immediately.
3. LITERAL ARGS: Use literal values in arguments, NEVER variable names.
4. NO REDUNDANCY: Do NOT repeat a tool call with identical parameters.
5. FINAL ANSWER. When you have the answer, you MUST call final_answer. This is the ONLY way to complete the task. Anything else causes an infinite loop.

Now Begin!{project_description}"""


def format_tool_description(tool) -> str:
    """Format a single tool into a prompt-friendly string."""
    args = []
    for arg_name, arg_info in tool.inputs.items():
        arg_type = arg_info.get("type", "any")
        nullable = arg_info.get("nullable", False)
        suffix = "?" if nullable else ""
        args.append(f"{arg_name}{suffix}: {arg_type}")
    return f"- {tool.name}: {tool.description} Args: {{{', '.join(args)}}}"


ROLE_TASK_SOLVER = "You are a task-solving agent that operates strictly through a Tool-Call Loop. You MUST solve the user's task by emitting valid JSON tool calls."
ROLE_EXPLORER = "You are a filesystem explorer agent that operates strictly through a Tool-Call Loop. You MUST fulfill the user's request by emitting valid JSON tool calls."


def build_direct_prompt(tools: list, project_description: str, agent_role: str = ROLE_TASK_SOLVER) -> str:
    """Build the system prompt with tool descriptions generated from the tool objects."""
    lines = [format_tool_description(t) for t in tools]
    return DIRECT_PROMPT_TEMPLATE.format(
        agent_role=agent_role,
        tools_description="\n".join(lines),
        project_description=project_description
    )


found_claude_md = False
project_description = ''
try:
    with open('CLAUDE.md', 'r') as f:
        claud_md = f.read().strip()
        project_description = f"\n\nCurrent Project:\n```\n{claud_md}\n```"
        found_claude_md = True
except FileNotFoundError:
    claud_md = ''

explorer_prompt = PromptTemplates(
    system_prompt=build_direct_prompt(EXPLORATION_TOOLS, "", agent_role=ROLE_EXPLORER),
    planning=PlanningPromptTemplate(
        initial_plan="",
        update_plan_pre_messages="",
        update_plan_post_messages="",
    ),
    managed_agent=ManagedAgentPromptTemplate(task="", report=""),
    final_answer=FinalAnswerPromptTemplate(pre_messages="", post_messages=""),
)

direct_prompt = PromptTemplates(
    system_prompt=build_direct_prompt(TOOLS, project_description),
    planning=PlanningPromptTemplate(
        initial_plan="",
        update_plan_pre_messages="",
        update_plan_post_messages="",
    ),
    managed_agent=ManagedAgentPromptTemplate(
        task=(
            "You are a filesystem explorer agent named '{{name}}'.\n"
            "Your task:\n{{task}}\n\n"
            "Use your tools to explore the filesystem and gather the requested information.\n"
            "Be thorough but concise — include file paths, line numbers, and relevant code snippets.\n"
            "Put everything in your final_answer call. Anything not passed to final_answer is lost."
        ),
        report="Exploration result from '{{name}}':\n{{final_answer}}",
    ),
    final_answer=FinalAnswerPromptTemplate(pre_messages="", post_messages=""),
)