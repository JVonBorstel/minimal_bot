class AgentResponse:
    """
    Minimal placeholder class for AgentResponse to resolve ImportError.
    """
    def __init__(self, content: str = "", tool_calls: list = None):
        self.content = content
        self.tool_calls = tool_calls if tool_calls is not None else []

    # Add any other minimal attributes needed for the test's mock setup if necessary later
    # For now, content and tool_calls seem sufficient based on the test context.