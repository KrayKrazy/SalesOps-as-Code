import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kelevra as K

def delete_lead():
    cfg = K.get_config()
    supa = K.Supabase(cfg)
    
    # Busca e deleta os leads por telefone (tentando variaes do 9 extra)
    phones_to_try = ["5562981429986", "556281429986"]
    
    deleted_count = 0
    for phone in phones_to_try:
        leads = K.fetch_all(supa, "leads", "id,telefone", extra=f"telefone=eq.{phone}")
        for lead in leads:
            print(f"Deletando lead: {lead['id']} | {lead['telefone']}")
            # Como a API Supabase (simulada ou real) pode no suportar DELETE diretamente via wrapper atual,
            # vamos usar a biblioteca httpx caso o supbase no tenha delete.
            # Olhando kelevra.py, no sabemos se tem supa.delete. Vamos checar.
            
    # Checando funo no kelevra
    import httpx
    for phone in phones_to_try:
        url = f"{supa.url}/rest/v1/leads?telefone=eq.{phone}"
        headers = {
            "apikey": supa.key,
            "Authorization": f"Bearer {supa.key}",
            "Prefer": "return=representation"
        }
        res = httpx.delete(url, headers=headers)
        if res.status_code in [200, 204]:
            print(f"Sucesso ao deletar {phone}: {res.status_code}")
            
if __name__ == "__main__":
    delete_lead()
