import os, httpx
from dotenv import load_dotenv
load_dotenv()

r = httpx.post(
    f"https://api.telegram.org/bot{os.getenv('TG_TOKEN')}/sendMessage",
    json={"chat_id": os.getenv("TG_CHAT_ID"), "text": "Prueba de alerta"},
)
print(r.status_code)