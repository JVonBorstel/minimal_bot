# File: bot_core/adapter_with_error_handler.py
import sys
import traceback
from datetime import datetime
from typing import Optional, Any  # Import Optional and Any


from botbuilder.core import (
    BotFrameworkAdapter,
    BotFrameworkAdapterSettings,
    TurnContext,
)  # type: ignore
from botbuilder.schema import ActivityTypes, Activity  # type: ignore


class AdapterWithErrorHandler(BotFrameworkAdapter):
    def __init__(
        self,
        settings: BotFrameworkAdapterSettings,
        config: Optional[Any] = None,
    ):  # Add config parameter
        super().__init__(settings)
        self.config = config  # Store config

        # Define the on_error event handler
        # It can now access self.config if needed, for example:
        # if self.config and self.config.DEBUG_MODE:
        #     await context.send_activity(f"Detailed error: {error}")

        async def on_error(context: TurnContext, error: Exception):
            # Log the error to stderr.
            # Consider using a logger from self.config if available
            # and configured
            print(
                f"\n[on_turn_error] unhandled error: {error}", file=sys.stderr
            )
            traceback.print_exc()

            # Send a message to the user
            await context.send_activity("The bot encountered an error or bug.")
            await context.send_activity(
                "To continue to run this bot, please fix the bot source code."
            )
            # Send a trace activity if connected to the Bot Framework Emulator
            if context.activity.channel_id == "emulator":
                # Create a trace activity
                trace_activity = Activity(
                    label="TurnError",
                    name="on_turn_error Trace",
                    timestamp=datetime.utcnow(),
                    type=ActivityTypes.trace,
                    value=f"{error}",
                    value_type="https.www.botframework.com/schemas/error",
                )
                # Send a trace activity, which will be displayed in
                # Bot Framework Emulator
                await context.send_activity(trace_activity)

        self.on_turn_error = on_error
