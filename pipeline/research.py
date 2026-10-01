import json
import os
import urllib.error
import urllib.parse
import urllib.request

SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "4b33e0de9ad758770dfc486ffffbefde087d123cc0500d14cf416c60969fe5ff") # TODO: remove hardcoded fallback

def search_business(lead):
    """
    Pesquisa a empresa no Google (SerpAPI) para extrair fatos reais e montar um dossiê.
    """
    nome = lead.get("nome", "")
    categoria = lead.get("category", "")
    cidade = lead.get("cidade", "")
    
    query = f"{nome} {categoria} {cidade}".strip()
    if not query:
        return None
        
    url = f"https://serpapi.com/search.json?q={urllib.parse.quote(query)}&engine=google&api_key={SERPAPI_KEY}&gl=br&hl=pt"
    
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            
        dossier = {}
        if "local_results" in data:
            results = data["local_results"]
            if isinstance(results, list) and len(results) > 0:
                top = results[0]
                dossier["nome_encontrado"] = top.get("title")
                if "rating" in top: dossier["rating"] = top.get("rating")
                if "reviews" in top: dossier["reviews"] = top.get("reviews")
                if "address" in top: dossier["endereco"] = top.get("address")
                if "links" in top and "website" in top["links"]:
                    dossier["website"] = top["links"]["website"]
                if "type" in top:
                    dossier["tipo"] = top["type"]
                    
        if "organic_results" in data:
            for result in data["organic_results"]:
                link = result.get("link", "")
                if "instagram.com" in link:
                    dossier["instagram"] = link
                    dossier["insta_snippet"] = result.get("snippet", "")
                elif "facebook.com" in link:
                    dossier["facebook"] = link
                elif "linkedin.com" in link:
                    dossier["linkedin"] = link
                
        return dossier
    except Exception as e:
        print(f"  [Research] Falha ao pesquisar {query}: {e}")
        return None
