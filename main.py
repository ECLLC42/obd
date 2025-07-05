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

                assistant_reply = response.output_text
                last_response_id = response.id  # Track for conversation continuity
            except Exception as e:
                assistant_reply = f"Error contacting model: {e}"

            # Append assistant message to history and send back to client
            await manager.send_personal_message(assistant_reply, websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket)