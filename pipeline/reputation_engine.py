import os
import json
import logging
from fastapi import FastAPI, Request
# from googleapiclient.discovery import build # Descomentar aps pip install google-api-python-client

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Kelevra Reputation Engine", version="1.0.0")

def analyze_review_and_generate_response(review_text: str, rating: int, business_context: dict) -> dict:
    """
    Motor do Reputation Engine:
    L a avaliao, se for 4 ou 5 estrelas: injeta palavras chave de SEO Local via DeepSeek.
    Se for 1 a 3 estrelas: Retorna resposta de conteno e flag para alerta no WhatsApp.
    """
    if rating >= 4:
        # TODO: Conectar com DeepSeek Client
        # Exemplo simulado
        seo_keywords = business_context.get("seo_keywords", ["nossa loja", "nossa cidade"])
        return {
            "action": "reply",
            "reply_text": f"Ficamos felizes que voc gostou! Agradecemos por escolher a {seo_keywords[0]} no corao da cidade.",
            "alert_owner": False
        }
    else:
        # Conteno de Danos
        return {
            "action": "reply_and_alert",
            "reply_text": "Lamentamos muito que sua experincia no tenha sido ideal. Nossa gerncia j est analisando seu caso internamente para melhorarmos.",
            "alert_owner": True
        }

@app.post("/webhook/google-reviews")
async def handle_google_review(request: Request):
    """
    Endpoint para receber novos reviews do Google Business Profile via webhook
    """
    payload = await request.json()
    logger.info(f"Novo Review recebido: {payload}")
    
    # Extrair dados do Payload
    # comment = payload.get("comment", "")
    # rating = payload.get("starRating", 5)
    
    # action_plan = analyze_review_and_generate_response(...)
    
    # Se action_plan["action"] in ("reply", "reply_and_alert"):
    #    reply_to_google(review_id, action_plan["reply_text"])
    
    # Se action_plan["alert_owner"]:
    #    send_whatsapp_alert(owner_phone, comment)

    return {"status": "processed"}

if __name__ == "__main__":
    import uvicorn
    # Para rodar: uvicorn reputation_engine:app --host 0.0.0.0 --port 8001
    uvicorn.run(app, host="0.0.0.0", port=8001)
