Coming soon...

## OBD Diagnostic Chat

A simple FastAPI application with a beautiful glass-morphism UI that lets you paste raw OBD data and chat with an OpenAI model (`o3`) for insights and troubleshooting.

### Prerequisites

1. Python 3.10+
2. An OpenAI API key with access to the `o3` model.

### Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Running the App

```bash
export OPENAI_API_KEY="YOUR_KEY_HERE"
uvicorn main:app --reload
```

The app will be available at http://localhost:8000

Paste any raw OBD data in the text area and start chatting!
