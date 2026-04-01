from smolagents import OpenAIServerModel
from rich.console import Console
from rich.panel import Panel 

console = Console()


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
        thinking_text = [] 
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
                        thinking_text.append(reasoning)
                        thinking = True
                    elif thinking and choice.delta.content:
                        thinking = False
                        console.print(Panel(
                            ''.join(thinking_text).strip(),
                            title="💭 Thinking",
                            title_align="left", 
                            border_style="dim",   
                            style="gray70",
                            padding=(0, 1),
                        ))
                        thinking_text.clear()  
                        
                    yield ChatMessageStreamDelta(
                        content=choice.delta.content,
                        tool_calls=[
                            ChatMessageToolCallStreamDelta(
                                index=d.index if d.index is not None else i,
                                id=d.id, type=d.type, function=d.function,
                            )
                            for i, d in enumerate(choice.delta.tool_calls)
                        ] if choice.delta.tool_calls else None,
                    )
                elif not getattr(choice, "finish_reason", None):
                    raise ValueError(f"No content or tool calls in event: {event}")