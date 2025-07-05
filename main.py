from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import openai
from openai import AsyncOpenAI
from typing import List

# Initialize Async OpenAI client once
openai.api_key = os.getenv("OPENAI_API_KEY")  # still set for compatibility
client = AsyncOpenAI(api_key=openai.api_key)

app = FastAPI(title="OBD Diagnostic Chat")

# Mount static assets and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the main chat page."""
    return templates.TemplateResponse("index.html", {"request": request})


class ConnectionManager:
    """Simple connection manager for single-user websocket sessions."""

    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket) -> None:
        await websocket.send_text(message)


manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Websocket endpoint that streams a back-and-forth chat with OpenAI."""
    await manager.connect(websocket)
    last_response_id: str | None = None
    try:
        while True:
            user_input = await websocket.receive_text()
            # Call OpenAI Responses API
            try:
                if last_response_id is None:
                    response = await client.responses.create(
                        model="o3",
                        input=user_input,
                    )
                else:
                    response = await client.responses.create(
                        model="o3",
                        input=user_input,
                        previous_response_id=last_response_id,
                    )

                # Extract text from response according to Responses API documentation
                # response.output is an array of content items
                # Each message has content array with output_text objects
                assistant_reply = ""
                if response.output and len(response.output) > 0:
                    message_item = response.output[0]  # Get first output item
                    if hasattr(message_item, 'content') and len(message_item.content) > 0:
                        for content_item in message_item.content:
                            if hasattr(content_item, 'type') and content_item.type == 'output_text':
                                assistant_reply += content_item.text
                
                if not assistant_reply:
                    assistant_reply = "No response generated"
                
                last_response_id = response.id  # Track for conversation continuity
            except Exception as e:
                assistant_reply = f"Error contacting model: {e}"

            # Append assistant message to history and send back to client
            await manager.send_personal_message(assistant_reply, websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket)