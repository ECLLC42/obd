from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import openai
from openai import AsyncOpenAI
from typing import List, Dict, Any
import json
import asyncio
import serial
import serial.tools.list_ports
import threading
import time
from datetime import datetime
import pandas as pd
import plotly.graph_objects as go
import plotly.utils
import logging
from collections import deque
import aiofiles

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Async OpenAI client
openai.api_key = os.getenv("OPENAI_API_KEY")
client = AsyncOpenAI(api_key=openai.api_key) if openai.api_key else None

app = FastAPI(title="Advanced OBD Diagnostic System")

# Mount static assets and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Global data storage
serial_data_buffer = deque(maxlen=1000)  # Store last 1000 data points
data_log = []
serial_connection = None
serial_thread = None
is_reading_serial = False

class ConnectionManager:
    """Advanced connection manager for multiple WebSocket connections."""

    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []
        self.connection_ids: Dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket, client_id: str = "") -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        self.connection_ids[websocket] = client_id or f"client_{len(self.active_connections)}"
        logger.info(f"Client {self.connection_ids[websocket]} connected")

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            client_id = self.connection_ids.get(websocket, "unknown")
            self.active_connections.remove(websocket)
            if websocket in self.connection_ids:
                del self.connection_ids[websocket]
            logger.info(f"Client {client_id} disconnected")

    async def send_personal_message(self, message: str, websocket: WebSocket) -> None:
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            self.disconnect(websocket)

    async def broadcast(self, message: str) -> None:
        """Broadcast message to all connected clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Error broadcasting to client: {e}")
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection)

manager = ConnectionManager()

def get_available_ports():
    """Get list of available serial ports."""
    ports = serial.tools.list_ports.comports()
    return [{"device": port.device, "description": port.description} for port in ports]

def read_serial_data():
    """Read data from serial port in a separate thread."""
    global is_reading_serial, serial_connection, serial_data_buffer
    
    while is_reading_serial and serial_connection:
        try:
            if serial_connection.in_waiting > 0:
                line = serial_connection.readline().decode('utf-8').strip()
                if line:
                    timestamp = datetime.now().isoformat()
                    data_point = {
                        "timestamp": timestamp,
                        "data": line,
                        "raw": line
                    }
                    
                    # Add to buffer
                    serial_data_buffer.append(data_point)
                    
                    # Add to log
                    data_log.append(data_point)
                    
                    # Broadcast to all connected clients
                    asyncio.run_coroutine_threadsafe(
                        manager.broadcast(json.dumps({
                            "type": "serial_data",
                            "data": data_point
                        })),
                        asyncio.get_event_loop()
                    )
                    
        except Exception as e:
            logger.error(f"Error reading serial data: {e}")
            is_reading_serial = False
            break
            
        time.sleep(0.1)  # Small delay to prevent excessive CPU usage

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the main application page."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/ports")
async def get_ports():
    """Get available serial ports."""
    return {"ports": get_available_ports()}

@app.post("/api/serial/connect")
async def connect_serial(request: Request):
    """Connect to a serial port."""
    global serial_connection, serial_thread, is_reading_serial
    
    data = await request.json()
    port = data.get("port", "/dev/ttyUSB0")
    baud_rate = data.get("baud_rate", 9600)
    
    try:
        if serial_connection and serial_connection.is_open:
            serial_connection.close()
        
        serial_connection = serial.Serial(port, baud_rate, timeout=1)
        is_reading_serial = True
        
        # Start reading thread
        serial_thread = threading.Thread(target=read_serial_data)
        serial_thread.daemon = True
        serial_thread.start()
        
        return {"success": True, "message": f"Connected to {port} at {baud_rate} baud"}
        
    except Exception as e:
        logger.error(f"Error connecting to serial port: {e}")
        return {"success": False, "message": f"Error: {str(e)}"}

@app.post("/api/serial/disconnect")
async def disconnect_serial():
    """Disconnect from serial port."""
    global serial_connection, is_reading_serial
    
    is_reading_serial = False
    
    if serial_connection and serial_connection.is_open:
        serial_connection.close()
        serial_connection = None
        
    return {"success": True, "message": "Disconnected from serial port"}

@app.get("/api/serial/status")
async def get_serial_status():
    """Get current serial connection status."""
    return {
        "connected": serial_connection is not None and serial_connection.is_open if serial_connection else False,
        "port": serial_connection.port if serial_connection else None,
        "reading": is_reading_serial,
        "buffer_size": len(serial_data_buffer)
    }

@app.get("/api/data/recent")
async def get_recent_data():
    """Get recent serial data."""
    return {"data": list(serial_data_buffer)[-50:]}  # Return last 50 data points

@app.get("/api/data/export")
async def export_data():
    """Export all collected data as JSON."""
    return {"data": data_log, "count": len(data_log)}

@app.post("/api/data/clear")
async def clear_data():
    """Clear all collected data."""
    global data_log
    data_log.clear()
    serial_data_buffer.clear()
    return {"success": True, "message": "Data cleared"}

@app.get("/api/data/chart")
async def get_chart_data():
    """Generate chart data for visualization."""
    if not serial_data_buffer:
        return {"error": "No data available"}
    
    # Convert to DataFrame for easier manipulation
    df = pd.DataFrame(list(serial_data_buffer))
    
    # Create a simple line chart
    fig = go.Figure()
    
    # Add trace for data points (assuming numeric data)
    try:
        # Try to extract numeric values from the data
        numeric_data = []
        timestamps = []
        
        for item in serial_data_buffer:
            try:
                # Try to extract numbers from the data string
                import re
                numbers = re.findall(r'-?\d+\.?\d*', item['data'])
                if numbers:
                    numeric_data.append(float(numbers[0]))
                    timestamps.append(item['timestamp'])
            except:
                continue
        
        if numeric_data:
            fig.add_trace(go.Scatter(
                x=timestamps,
                y=numeric_data,
                mode='lines+markers',
                name='Serial Data',
                line=dict(color='#00ff88', width=2),
                marker=dict(size=4)
            ))
    except:
        pass
    
    # Update layout
    fig.update_layout(
        title="Real-time Serial Data",
        xaxis_title="Time",
        yaxis_title="Value",
        template="plotly_dark",
        height=400
    )
    
    return {"chart": json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Enhanced WebSocket endpoint for real-time communication."""
    await manager.connect(websocket)
    
    try:
        while True:
            message = await websocket.receive_text()
            
            try:
                data = json.loads(message)
                message_type = data.get("type", "chat")
                
                if message_type == "chat" and client:
                    # Handle chat messages with OpenAI
                    user_input = data.get("message", "")
                    
                    try:
                        response = await client.chat.completions.create(
                            model="gpt-3.5-turbo",
                            messages=[
                                {"role": "system", "content": "You are an expert OBD diagnostic assistant. Help users understand their vehicle diagnostics data."},
                                {"role": "user", "content": user_input}
                            ],
                            max_tokens=500
                        )
                        
                        assistant_reply = response.choices[0].message.content
                        
                        await manager.send_personal_message(
                            json.dumps({
                                "type": "chat_response",
                                "message": assistant_reply
                            }),
                            websocket
                        )
                        
                    except Exception as e:
                        await manager.send_personal_message(
                            json.dumps({
                                "type": "error",
                                "message": f"Error contacting AI: {str(e)}"
                            }),
                            websocket
                        )
                
                elif message_type == "serial_command":
                    # Handle serial commands
                    command = data.get("command", "")
                    
                    if serial_connection and serial_connection.is_open:
                        serial_connection.write(f"{command}\n".encode())
                        await manager.send_personal_message(
                            json.dumps({
                                "type": "serial_response",
                                "message": f"Command sent: {command}"
                            }),
                            websocket
                        )
                    else:
                        await manager.send_personal_message(
                            json.dumps({
                                "type": "error",
                                "message": "Serial port not connected"
                            }),
                            websocket
                        )
                
                elif message_type == "ping":
                    # Handle ping for connection testing
                    await manager.send_personal_message(
                        json.dumps({"type": "pong"}),
                        websocket
                    )
                
            except json.JSONDecodeError:
                # Handle plain text messages (backwards compatibility)
                if client:
                    try:
                        response = await client.chat.completions.create(
                            model="gpt-3.5-turbo",
                            messages=[
                                {"role": "system", "content": "You are an expert OBD diagnostic assistant. Help users understand their vehicle diagnostics data."},
                                {"role": "user", "content": message}
                            ],
                            max_tokens=500
                        )
                        
                        assistant_reply = response.choices[0].message.content
                        await manager.send_personal_message(assistant_reply, websocket)
                        
                    except Exception as e:
                        await manager.send_personal_message(f"Error: {str(e)}", websocket)
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

@app.on_event("startup")
async def startup_event():
    """Initialize the application."""
    logger.info("Advanced OBD Diagnostic System starting up...")
    
    # Create data directory if it doesn't exist
    os.makedirs("data", exist_ok=True)
    
    logger.info("System ready!")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    global is_reading_serial, serial_connection
    
    logger.info("Shutting down...")
    
    is_reading_serial = False
    
    if serial_connection and serial_connection.is_open:
        serial_connection.close()
    
    logger.info("Shutdown complete!")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)