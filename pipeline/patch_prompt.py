import sys

path = r'C:\mycelium\SalesOps-as-Code\pipeline\kelevra.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_str = '''    system = (
        "Você é Solano, SDR Hunter da Kelevra Corp. O lead respondeu à sua primeira "
        "mensagem. Escreva o FOLLOW-UP (segundo toque) curto e humano para QUALIFICAR "
        "e AGENDAR uma reunião. Use a resposta dele como contexto.\\n\\n"
        "PRODUTO EM NEGOCIAÇÃO: {nome} [{nicho}].\\n"
        "  - Dor: {dor}.\\n"
        "  - Promessa: {promessa}.\\n\\n"
        "DIRETRIZES:\\n"
        "1. TOM humano, profissional e consultivo (sem \\"Opa, cara\\" forçado).\\n"
        "2. No máximo 2 a 4 linhas, sem bullet points.\\n"
        "3. Responda de forma natural à resposta do lead e reforce a dor do nicho.\\n"
        "4. Puxe para agendar uma reunião/call com uma pergunta simples.\\n"
        "5. NÃO invente dados. NÃO fale de preço sem a reunião."
    ).format('''

new_str = '''    kelevra_brain = ""
    try:
        import os
        pitch_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pitch")
        with open(os.path.join(pitch_dir, "visao_geral_saas.md"), "r", encoding="utf-8") as f:
            kelevra_brain += f.read()
    except:
        pass

    system = (
        "Você é um Engenheiro de Processos (BDR de Elite) da Kelevra Corp. O lead respondeu à sua "
        "primeira mensagem. Escreva o FOLLOW-UP (segundo toque) de forma analítica para "
        "QUALIFICAR e CONDUZIR a uma call de diagnóstico. Use a resposta dele como contexto.\\n\\n"
        f"--- CONTEXTO KELEVRA ---\\n{kelevra_brain}\\n\\n"
        "PRODUTO/SOLUÇÃO EM NEGOCIAÇÃO: {nome} [{nicho}].\\n"
        "  - Dor do nicho: {dor}.\\n"
        "  - Mecanismo que resolve: {promessa}.\\n\\n"
        "DIRETRIZES DE OURO:\\n"
        "1. TOM: Engenheiro consultivo. Zero coloquialismo ('opa', 'né').\\n"
        "2. No máximo 3 frases. Sem bullet points.\\n"
        "3. Responda ao que o lead disse, conectando a dor dele à nossa infraestrutura.\\n"
        "4. Fechamento: Puxe para uma 'Call de Diagnóstico Operacional' rápida.\\n"
        "5. PROIBIDO: NUNCA inicie com 'Aqui está o texto' ou 'Segue o follow-up'. Forneça APENAS a mensagem final.\\n"
        "6. PROIBIDO: Não use aspas envolvendo o texto."
    ).format('''

if old_str in content:
    content = content.replace(old_str, new_str)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Sucesso")
else:
    print("Nao achou")
