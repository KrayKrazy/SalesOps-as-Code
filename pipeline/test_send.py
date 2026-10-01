"""Teste E2E de envio WhatsApp para um número específico.

Uso:
  python test_send.py 5511999999999        # número no formato DDI+DDD+número
  python test_send.py 61981952874          # formatação BR (adiciona 55)

Sem argumento, usa a variável de ambiente TEST_SEND_NUMBER (ou aborta).
"""
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kelevra as K

K.setup_console_encoding()
cfg = K.get_config()
evo = K.Evolution(cfg)

target = (sys.argv[1] if len(sys.argv) > 1
          else (os.environ.get("TEST_SEND_NUMBER") or "").strip())
if not target:
    sys.exit("Informe o número: python test_send.py <DDI+DDD+número>")
phone = K.normalize_phone(target)
print("Destino normalizado:", phone)

# 1) listar instâncias + estado de conexão
print("\n--- Instâncias Evolution ---")
c = K.HttpClient(evo.base, {"apikey": evo.apikey}, timeout=20)
status, instances = c.request("GET", "/instance/fetchInstances")
print("fetchInstances HTTP", status)
names = []
connected = []
if isinstance(instances, list):
    for d in instances:
        name = d.get("instanceName") or d.get("name")
        names.append(name)
        st2, st = c.request("GET", "/instance/connectionState/" + urllib.parse.quote(str(name)))
        state = "?"
        if isinstance(st, dict):
            state = st.get("state") or st.get("status") or json.dumps(st, ensure_ascii=False)[:60]
        elif isinstance(st, list) and st:
            state = st[0].get("state") if isinstance(st[0], dict) else json.dumps(st, ensure_ascii=False)[:60]
        print("  %-18s HTTP=%s estado=%s" % (name, st2, state))
        if str(state).lower() in ("open", "connected"):
            connected.append(name)

# 2) escolher instância (preferir Número comercial, senão a 1a conectada)
use = "Número comercial" if "Número comercial" in names else (connected[0] if connected else evo.instance)
evo.instance = use
print("\nUsando instância:", use)

# 3) enviar mensagem de teste
msg = "Teste do sistema Kelevra SalesOps ✅ (mensagem de teste — pode ignorar)."
print("Enviando para", phone, "...")
st, resp = evo.send_text(phone, msg)
print("Envio HTTP", st)
print(json.dumps(resp, ensure_ascii=False)[:500])
