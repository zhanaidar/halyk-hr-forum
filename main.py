from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import config

app = FastAPI(title="Halyk HR Forum")

@app.get("/", response_class=HTMLResponse)
async def home():
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{config.ORG_NAME} - HR Testing</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, {config.ORG_PRIMARY_COLOR}, #0a6b4f);
            }}
            .container {{
                text-align: center;
                background: white;
                padding: 50px;
                border-radius: 20px;
                box-shadow: 0 10px 50px rgba(0,0,0,0.2);
            }}
            h1 {{
                color: {config.ORG_PRIMARY_COLOR};
                margin-bottom: 20px;
            }}
            .status {{
                color: #28a745;
                font-size: 24px;
                margin: 20px 0;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>{config.ORG_NAME}</h1>
            <h2>Система HR тестирования</h2>
            <div class="status">✅ Сервер работает на Railway!</div>
            <p>Версия: 1.0.0 (базовая)</p>
        </div>
    </body>
    </html>
    """

@app.get("/health")
async def health():
    return {"status": "ok", "service": "halyk-hr-forum"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.APP_HOST, port=config.APP_PORT)