import PIL.Image
from smolagents.agents import ToolCallingAgent, CodeAgent, ActionStep, PlanningStep, FinalAnswerStep, ChatMessageStreamDelta, AgentError, AgentGenerationError, ActionOutput, Timing, handle_agent_output_types
from typing import Generator
import time
from rich.text import Text
from smolagents import LogLevel
from smolagents.monitoring import YELLOW_HEX


class CustomToolCallingAgent(ToolCallingAgent):
   def _run_stream(
        self, task: str, max_steps: int, images: list["PIL.Image.Image"] | None = None
    ) -> Generator[ActionStep | PlanningStep | FinalAnswerStep | ChatMessageStreamDelta]:
        self.step_number = 1
        returned_final_answer = False
        while not returned_final_answer and self.step_number <= max_steps:
            if self.interrupt_switch:
                raise AgentError("Agent interrupted.", self.logger)

            # Run a planning step if scheduled
            if self.planning_interval is not None and (
                self.step_number == 1 or (self.step_number - 1) % self.planning_interval == 0
            ):
                planning_start_time = time.time()
                planning_step = None
                for element in self._generate_planning_step(
                    task, is_first_step=len(self.memory.steps) == 1, step=self.step_number
                ):  # Don't use the attribute step_number here, because there can be steps from previous runs
                    yield element
                    planning_step = element
                assert isinstance(planning_step, PlanningStep)  # Last yielded element should be a PlanningStep
                planning_end_time = time.time()
                planning_step.timing = Timing(
                    start_time=planning_start_time,
                    end_time=planning_end_time,
                )
                self._finalize_step(planning_step)
                self.memory.steps.append(planning_step)

            # Start action step!
            action_step_start_time = time.time()
            action_step = ActionStep(
                step_number=self.step_number,
                timing=Timing(start_time=action_step_start_time),
                observations_images=images,
            )
            # self.logger.log_rule(f"Step {self.step_number}", level=LogLevel.INFO)
            try:
                for output in self._step_stream(action_step):
                    # Yield all
                    yield output

                    if isinstance(output, ActionOutput) and output.is_final_answer:
                        final_answer = output.output
                        self.logger.log(
                            Text(f"Final answer: {final_answer}", style=f"bold {YELLOW_HEX}"),
                            level=LogLevel.INFO,
                        )

                        if self.final_answer_checks:
                            self._validate_final_answer(final_answer)
                        returned_final_answer = True
                        action_step.is_final_answer = True

            except AgentGenerationError as e:
                # Agent generation errors are not caused by a Model error but an implementation error: so we should raise them and exit.
                raise e
            except AgentError as e:
                # Other AgentError types are caused by the Model, so we should log them and iterate.
                action_step.error = e
            finally:
                self._finalize_step(action_step)
                self.memory.steps.append(action_step)
                yield action_step
                self.step_number += 1

        if not returned_final_answer and self.step_number == max_steps + 1:
            final_answer = self._handle_max_steps_reached(task)
            yield action_step
        final_answer_step = FinalAnswerStep(handle_agent_output_types(final_answer))
        self._finalize_step(final_answer_step)
        yield final_answer_step


class CustomCodeAgent(CodeAgent):
       def _run_stream(
        self, task: str, max_steps: int, images: list["PIL.Image.Image"] | None = None
    ) -> Generator[ActionStep | PlanningStep | FinalAnswerStep | ChatMessageStreamDelta]:
        self.step_number = 1
        returned_final_answer = False
        while not returned_final_answer and self.step_number <= max_steps:
            if self.interrupt_switch:
                raise AgentError("Agent interrupted.", self.logger)

            # Run a planning step if scheduled
            if self.planning_interval is not None and (
                self.step_number == 1 or (self.step_number - 1) % self.planning_interval == 0
            ):
                planning_start_time = time.time()
                planning_step = None
                for element in self._generate_planning_step(
                    task, is_first_step=len(self.memory.steps) == 1, step=self.step_number
                ):  # Don't use the attribute step_number here, because there can be steps from previous runs
                    yield element
                    planning_step = element
                assert isinstance(planning_step, PlanningStep)  # Last yielded element should be a PlanningStep
                planning_end_time = time.time()
                planning_step.timing = Timing(
                    start_time=planning_start_time,
                    end_time=planning_end_time,
                )
                self._finalize_step(planning_step)
                self.memory.steps.append(planning_step)

            # Start action step!
            action_step_start_time = time.time()
            action_step = ActionStep(
                step_number=self.step_number,
                timing=Timing(start_time=action_step_start_time),
                observations_images=images,
            )
            # self.logger.log_rule(f"Step {self.step_number}", level=LogLevel.INFO)
            try:
                for output in self._step_stream(action_step):
                    # Yield all
                    yield output

                    if isinstance(output, ActionOutput) and output.is_final_answer:
                        final_answer = output.output
                        self.logger.log(
                            Text(f"Final answer: {final_answer}", style=f"bold {YELLOW_HEX}"),
                            level=LogLevel.INFO,
                        )

                        if self.final_answer_checks:
                            self._validate_final_answer(final_answer)
                        returned_final_answer = True
                        action_step.is_final_answer = True

            except AgentGenerationError as e:
                # Agent generation errors are not caused by a Model error but an implementation error: so we should raise them and exit.
                raise e
            except AgentError as e:
                # Other AgentError types are caused by the Model, so we should log them and iterate.
                action_step.error = e
            finally:
                self._finalize_step(action_step)
                self.memory.steps.append(action_step)
                yield action_step
                self.step_number += 1

        if not returned_final_answer and self.step_number == max_steps + 1:
            final_answer = self._handle_max_steps_reached(task)
            yield action_step
        final_answer_step = FinalAnswerStep(handle_agent_output_types(final_answer))
        self._finalize_step(final_answer_step)
        yield final_answer_step
