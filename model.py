from smolagents import OpenAIServerModel
import shutil


class ThinkingModel(OpenAIServerModel):
    def generate_stream(self, messages, stop_sequences=None, response_format=None, tools_to_call_from=None, **kwargs):
        from smolagents.models import ChatMessageStreamDelta, ChatMessageToolCallStreamDelta, TokenUsage
        completion_kwargs = self._prepare_completion_kwargs(
            messages=messages,
            stop_sequences=stop_sequences,
            response_format=response_format,
            tools_to_call_from=tools_to_call_from,
            model=self.model_id,
            custom_role_conversions=self.custom_role_conversions,
            convert_images_to_image_urls=True,
            **kwargs,
        )
        self._apply_rate_limit()
        thinking = False
        for event in self.retryer(
            self.client.chat.completions.create,
            **completion_kwargs,
            stream=True,
            stream_options={"include_usage": True},
        ):
            if event.usage:
                yield ChatMessageStreamDelta(
                    content="",
                    token_usage=TokenUsage(
                        input_tokens=event.usage.prompt_tokens,
                        output_tokens=event.usage.completion_tokens,
                    ),
                )
            if event.choices:
                choice = event.choices[0]
                if choice.delta:
                    raw = choice.delta.model_extra or {}
                    reasoning = raw.get("reasoning") or getattr(choice.delta, "reasoning_content", None)
                    if reasoning:
                        if not thinking:
                            print("\n💭 Thinking: ", end="")
                            thinking = True
                        print(f"{reasoning}", end="")
                    elif thinking and choice.delta.content:
                        thinking = False
                        print()
                        print('\033[90m' + '_' * shutil.get_terminal_size().columns + '\033[0m')
                        print()
                    yield ChatMessageStreamDelta(
                        content=choice.delta.content,
                        tool_calls=[
                            ChatMessageToolCallStreamDelta(
                                index=d.index, id=d.id, type=d.type, function=d.function,
                            )
                            for d in choice.delta.tool_calls
                        ] if choice.delta.tool_calls else None,
                    )
                elif not getattr(choice, "finish_reason", None):
                    raise ValueError(f"No content or tool calls in event: {event}")