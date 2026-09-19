# Mapeamento do Ecossistema n8n - Agente SDR Kelevra

Este documento detalha a arquitetura atual do seu Agente de IA para captação e atendimento de leads, focado exclusivamente no **Inbound** (Receptivo), conforme alinhado.

---

## 🛑 1. O Problema do "Disparo Indesejado"
Você relatou que o Agente mandou mensagem para uma cliente que estava "quase fechando" (no estágio `acompanhar`).
**Por que isso aconteceu?**
Hoje mais cedo, nós construímos uma rotina proativa (Outbound) composta por um "Despertador" e ferramentas (Tools) para o Dify ler o seu banco de dados e mandar mensagens sozinho. Quando criei a query da ferramenta de leitura de leads, fixei para ele puxar os leads que estivessem exatamente no status `acompanhar` como teste, e o Agente acabou agindo em cima deles.

**A Solução Aplicada:**
Como decidimos que o Agente deve atuar de forma **100% RECEPTIVA** (você já tem seu próprio workflow de disparos), eu **deletei definitivamente** do seu n8n os seguintes fluxos criados hoje, purificando o ecossistema:
- *Despertador: Agente Outbound Kelevra*
- *Tool: get_pending_leads*
- *Tool: check_and_send_whatsapp*
- *Tool: update_lead_status*

A partir de agora, o Dify **jamais** irá agir sozinho ou incomodar clientes quentes do seu CRM. Ele só fala se falarem com ele.

---

## ⚙️ 2. Workflow Principal: "Kelevra: SDR Inbound (V4 - Estável)"
Este é o coração do seu sistema receptivo. Quando o lead responde um disparo seu ou te chama, esse fluxo toma o controle. Ele possui uma engenharia de ponta que prevê áudios e imagens. Abaixo está a lista detalhada de cada Nó e o que construímos nele:

### Captura e Preparação
- **Webhook (Evolution)**: Recebe o payload do WhatsApp em tempo real.
- **Normalizar (Code)**: Extrai o número do telefone, a instância e limpa o texto base.

### Roteamento Multimídia (O grande diferencial)
- **É Áudio? (If)**: Detecta se a mensagem é um áudio (`audioMessage`).
  - **Baixar Áudio**: Bate na Evolution e baixa o arquivo em `.ogg`.
  - **Transcrever (Whisper)**: Envia o áudio para a IA da OpenAI converter em texto.
  - **Formatar Áudio**: Devolve o texto transcrito para o fluxo principal.
- **É Imagem? (If)**: Detecta se o cliente mandou foto.
  - **Baixar Imagem**: Puxa o base64 da foto da Evolution.
  - **Visão GPT-4o**: Lê a imagem e traduz em texto para o Dify saber o que tem nela.
  - **Formatar Imagem**: Acopla a leitura da imagem no fluxo.
- **Texto OK (Code)**: Junta os três caminhos (Texto puro, Áudio transcrito ou Imagem lida) em uma única string unificada para o Agente entender.

### O Cérebro (Integração com Dify e Memória)
- **Buscar Memória (Supabase)**: O nó chave. Ele vai na sua tabela `cold_leads` no Supabase e puxa o `dify_conversation_id` do cliente. Isso garante que a inteligência artificial lembre do que falou ontem.
- **Montar Request Dify (Code)**: Prepara o JSON exato que o Agente novo do Dify exige, usando o formato de *streaming*.
- **Chat Dify (HttpRequest)**: Bate no Dify (usando a sua nova chave API do Agente) e recebe a resposta inteligente do LLM.
- **Parsear Resposta Dify (Code)**: **(Nossa obra-prima de hoje)**. Esse código decodifica o protocolo *Server-Sent Events* (SSE). Ele arranca fora o bloco `<think>` (raciocínio oculto da IA) e extrai apenas a fala final.
- **Salvar Memória (HttpRequest)**: Envia um PATCH de volta pro Supabase, atualizando ou salvando o `conversation_id` para que a conversa não se perca no futuro.

### Ação Final
- **Venda Pronta? (If)**: Avalia regras rígidas (por exemplo, se já está agendado) para decidir se manda para handoff.
- **Responder WhatsApp (HttpRequest)**: O braço executor. Ele injeta a fala do Solano-SDR e bate na Evolution (`/message/sendText`), devolvendo o texto no celular do cliente. Substitui tags, como colocar o link do seu Forms se o Agente mandou `[REUNIAO_MARCADA]`.
- **Handoff Chatwoot (Code)**: Em caso de falha ou transição, o fluxo se prepara para alertar o sistema humano.

---

## 🎯 3. Resumo da Estratégia Atual
Com essa limpeza e arquitetura, você atingiu o modelo perfeito de SDR:
1. **Atração/Prospecção Ativa:** Fica a cargo do seu workflow de disparo já existente ou Tráfego Pago.
2. **Recepção/Qualificação:** Fica a cargo do Agente Dify Inbound (conectado a este Workflow V4) usando o Prompt *BANT* agressivo que desenhamos.
3. **Fechamento:** Ocorre na call, após o lead preencher o `forms.kelevra.shop` que a própria IA entregou.

Seu ecossistema agora está totalmente focado na qualidade de recepção. Pode reativar o V4 Estável com segurança!
