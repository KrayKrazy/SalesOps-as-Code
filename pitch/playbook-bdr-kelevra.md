# Kelevra BDR Playbook: O Agente SDR de Elite

**Data:** 01 de Outubro de 2026
**Objetivo:** Elevar o nível do agente de Inteligência Artificial para operar como um *Business Development Representative* (BDR) Enterprise, alinhado ao posicionamento "Dark/Elite" da Kelevra Corp.

---

## 1. O que um BDR Moderno de Alta Performance faz?
Após uma pesquisa profunda sobre as melhores práticas de prospecção B2B (SaaS/Enterprise) em 2026, ficou claro que a era do "Volume cego" acabou. O BDR moderno não é um panfleteiro digital; ele atua como um engenheiro de diagnóstico.

**As 3 Regras de Ouro do BDR B2B:**
1. **Sinais e Diagnóstico, não Apresentação:** O BDR não empurra um produto. Ele aponta uma ineficiência sistêmica. Ele usa dados (Technographics e SEO) para mostrar que estudou a operação do cliente.
2. **Problemas > Soluções:** Ninguém quer comprar "Tráfego" ou "Site". Eles querem resolver "Perda de lucro por No-Show" ou "Caos operacional no WhatsApp". O BDR toca na dor mecânica.
3. **Fricção Zero na Chamada (Call to Action Leve):** Um BDR de elite não pede "30 minutos do seu tempo para uma call". Ele levanta uma hipótese e pede permissão para enviar uma prova conceitual (ex: "Posso te mandar um diagnóstico rápido de como resolver isso?").

## 2. A Inadequação do Agente Antigo (O Problema do "Opa")
O agente atual estava operando como um "SDR de Agência Genérica".
*A abordagem gerada hoje:* `"Opa, tudo bem? Vi que vocês estão em Goiânia - mercado forte pra negócios locais, né? Por onde vocês tão puxando mais clientes ultimamente?"`

**Por que isso falha para a Kelevra?**
A Kelevra se vende como: *"A infraestrutura autônoma para escalar negócios locais. Substituímos o caos operacional por sistemas inteligentes e engenharia de processos."*
Alguém que vende "Engenharia e Sistemas de Elite" não aborda um CEO dizendo "Opa, tudo bem? Mercado forte, né?". Essa quebra de expectativa destrói o valor da marca no primeiro segundo.

## 3. Adaptação ao Contexto Kelevra Corp (O Novo Prompt)
Para adaptar o agente de IA ao seu ecossistema, o Prompt do DeepSeek será reescrito. O Agente BDR da Kelevra será treinado com os seguintes traços de personalidade:
- **Arquétipo:** Consultor Técnico / Engenheiro de Processos (Estilo Palantir/McKinsey, mas para negócios locais).
- **Tom de Voz:** Direto, polido, analítico, sem emojis extravagantes, sem gírias ("opa", "beleza", "né").
- **Gatilho de Autoridade:** Uso do Dossiê do Google Maps (SEO) para apontar uma ineficiência cirúrgica.
- **O Pitch Invisível:** Ele não vende tráfego. Ele pergunta se a empresa tem capacidade de absorver automação, infraestrutura e escala.

### Matriz de Abordagens (O que a IA vai gerar)
Em vez de perguntar "por onde capta clientes", a IA perguntará sobre infraestrutura:
* *Exemplo de Saída 1 (Clínica com poucas reviews):* "Olá. Aqui é da Kelevra Corp. Nossa inteligência mapeou a operação da [Nome da Clínica] no Google e notamos um gargalo na captura autônoma de avaliações, o que está drenando seu ranqueamento orgânico em Goiânia. Vocês já utilizam alguma infraestrutura de IA para blindar a presença local e reter leads, ou a operação ainda depende de esforço manual?"
* *Exemplo de Saída 2 (Restaurante):* "Boa tarde. Analisamos a infraestrutura da [Nome do Restaurante]. O fluxo de caixa na região do Entorno é alto, mas operações que não possuem travas anti no-show e qualificação autônoma no WhatsApp sofrem com caos operacional. Como está o nível de automação comercial de vocês hoje? Posso enviar um mapa de como resolver isso?"

---

## 4. Plano de Execução Técnica
1. **Reescrever o System Prompt em `kelevra.py`:** Trocar o `ROLE` do Agente na função `generate_opening`. Remover a permissão para uso de linguagem coloquial e injetar o contexto da "Operação de Elite" e "Engenharia de Vendas".
2. **Atualizar o Prompt no LangGraph (V4.0):** Garantir que o novo nó `node_generate_pitch` no `sdr_v4_fastapi.py` já herde esse *System Prompt* robusto e enterprise.
3. **Teste de Calibragem:** Rodar o pipeline em DRY-RUN focando exclusivamente em ler o texto gerado para garantir que a agressividade cirúrgica foi atingida sem soar robótico.
