import os
import sys
import logging
from typing import TypedDict, Annotated, Sequence
import time

from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel

# Imports do LangGraph
from langgraph.graph import StateGraph, END
import operator

# Imports do Ecossistema Kelevra atual (Aproveitando a inteligncia)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kelevra as K
import research

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# 1. ESTADO DO GRAFO (LangGraph State)
# ---------------------------------------------------------
class LeadState(TypedDict):
    lead_id: str
    phone: str
    business_data: dict
    seo_dossier: str
    icp_score: int
    icp_reason: str
    generated_message: str
    status: str

# ---------------------------------------------------------
# 2. NÓS DO GRAFO (LangGraph Nodes)
# ---------------------------------------------------------
def node_research(state: LeadState) -> LeadState:
    """Nó 1: Pesquisa os dados do Lead usando SerpAPI (Sem bloquear outras execues)."""
    logger.info(f"[{state['lead_id']}] Iniciando Pesquisa de SEO...")
    # Chamada real para a function j existente em research.py
    dossier = research.search_business(state["business_data"])
    return {"seo_dossier": dossier}

def node_qualify(state: LeadState) -> LeadState:
    """Nó 2: Avalia a qualidade do lead usando DeepSeek."""
    logger.info(f"[{state['lead_id']}] Qualificando Lead...")
    # Aqui vamos invocar a LLM baseada nas funes atuais do K.score_lead
    # Para o Scaffold V4, mockamos o tempo e a resposta
    time.sleep(1) # Simula chamadas LLM async
    return {"icp_score": 10, "icp_reason": "Empresa validada"}

def node_generate_pitch(state: LeadState) -> LeadState:
    """Nó 3: Gera a mensagem personalizada."""
    logger.info(f"[{state['lead_id']}] Gerando Pitch com DeepSeek...")
    time.sleep(1) # Simula LLM
    msg = f"Opa, vi que vocs esto mandando bem no {state['business_data'].get('cidade')}. Como captam clientes?"
    return {"generated_message": msg}

def node_dispatch(state: LeadState) -> LeadState:
    """Nó 4: Despacha para a Fila de Envio (Evolution API)."""
    logger.info(f"[{state['lead_id']}] Despachando para WhatsApp: {state['phone']}")
    # Aqui o script apenas joga num banco local ou Redis para o Sender enviar com o time.sleep anti-ban!
    # Dessa forma, o motor multi-agente roda livre!
    return {"status": "dispatched"}

# ---------------------------------------------------------
# 3. ORQUESTRAÇÃO DO GRAFO
# ---------------------------------------------------------
workflow = StateGraph(LeadState)

workflow.add_node("research", node_research)
workflow.add_node("qualify", node_qualify)
workflow.add_node("generate", node_generate_pitch)
workflow.add_node("dispatch", node_dispatch)

workflow.set_entry_point("research")
workflow.add_edge("research", "qualify")
workflow.add_edge("qualify", "generate")
workflow.add_edge("generate", "dispatch")
workflow.add_edge("dispatch", END)

sdr_app = workflow.compile()

# ---------------------------------------------------------
# 4. SERVIDOR FASTAPI (Escutando Webhooks do Bolten CRM)
# ---------------------------------------------------------
app = FastAPI(title="Kelevra SDR Multi-Agent Engine", version="4.0")

class WebhookPayload(BaseModel):
    lead_id: str
    phone: str
    nome: str
    cidade: str
    category: str

def run_sdr_graph(payload: WebhookPayload):
    initial_state = {
        "lead_id": payload.lead_id,
        "phone": payload.phone,
        "business_data": {"nome": payload.nome, "cidade": payload.cidade, "category": payload.category},
        "seo_dossier": "",
        "icp_score": 0,
        "icp_reason": "",
        "generated_message": "",
        "status": "started"
    }
    # Executa o Grafo Assincronamente
    for output in sdr_app.stream(initial_state):
        for key, value in output.items():
            logger.info(f"Node '{key}' finalizado.")

@app.post("/webhook/bolten/new-lead")
async def receive_new_lead(payload: WebhookPayload, background_tasks: BackgroundTasks):
    """
    Quando o CRM Bolten envia um novo lead, soltamos os agentes no background.
    O endpoint responde em milissegundos.
    """
    background_tasks.add_task(run_sdr_graph, payload)
    return {"status": "SDR Agents Deployed", "lead": payload.lead_id}

if __name__ == "__main__":
    import uvicorn
    # Para rodar: uvicorn sdr_v4_fastapi:app --host 0.0.0.0 --port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)
