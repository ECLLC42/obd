from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import openai
from typing import List

# Configure your OpenAI API key via environment variable for security
openai.api_key = os.getenv("OPENAI_API_KEY")

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
    conversation: List[dict] = []
    try:
        while True:
            user_input = await websocket.receive_text()
            # Append user message to history
            conversation.append({"role": "user", "content": user_input})

            # Call OpenAI chat completion
            try:
                response = await openai.ChatCompletion.acreate(
                    model="o3",
                    messages=conversation,
                )
                assistant_reply = response.choices[0].message.content
            except Exception as e:
                assistant_reply = f"Error contacting model: {e}"

            # Append assistant message to history and send back to client
            conversation.append({"role": "assistant", "content": assistant_reply})
            await manager.send_personal_message(assistant_reply, websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket)