# Arquitetura Global Kelevra Corp (Ecosystem Overview)
**Classificação:** Visão Executiva e Topológica
**Foco:** Interconexão dos Sistemas, CRM, E-commerce e Gestão de Conhecimento (SalesOps-as-Code).

Para entender a totalidade do seu poder de fogo, não podemos olhar apenas para o "bot do WhatsApp". O Agente SDR é apenas o "front-end" inteligente de um ecossistema gigantesco que roda em background nas suas VPS. Abaixo está o mapeamento global da sua infraestrutura e como o repositório **SalesOps-as-Code** se torna a "Bíblia" de todo o sistema.

---

## 🏛️ A CAMADA DE FONTE DA VERDADE (SOURCE OF TRUTH)
O cérebro de uma operação não pode ficar espalhado em dezenas de blocos de notas. A inteligência deve ser versionada.

**Repositório: [SalesOps-as-Code](https://github.com/KrayKrazy/SalesOps-as-Code)**
- **O que é:** O repositório central no GitHub onde armazenamos matrizes BANT, roteiros de objeção (como o `faq_kelevra.md` e `produtos_e_servicos_kelevra.md`), scripts de automação e schemas de banco de dados.
- **O Papel na Arquitetura:**
  - **Dify Knowledge Base Sync:** O Dify está conectado nativamente a este repositório. Toda vez que você (ou um dev) fizer um `git push` atualizando o preço de um produto ou uma objeção nova, o Dify re-vetoriza os arquivos automaticamente. O Agente SDR nunca fica desatualizado.
  - **Pipeline As Code:** Automações do n8n podem puxar JSONs de configuração desse repositório, garantindo que fluxos em produção estejam sempre alinhados com o repositório Master.

---

## 🧠 A CAMADA DE ORQUESTRAÇÃO E IA (NERVOUS SYSTEM)
Onde as decisões são tomadas e o fluxo de dados é roteado.

**1. Dify (Orquestrador Neural)**
- **Função:** Gerencia os Chatflows, roteamento de intenção e recuperação de contexto (RAG) direto do *SalesOps-as-Code*.
- **Modelos:** OpenAI (GPT-4o / GPT-4o-mini).

**2. n8n (Middleware de Integração)**
- **Função:** O "encanamento" da internet. Recebe webhooks, gerencia filas (Debounce), processa áudios (Whisper via APIs de terceiros) e imagens (Visão).
- **Ativos Críticos:** Microsserviços Inbound, Webhooks do Chatwoot e Disparos Ativos (Despertador Outbound - atualmente isolado).

**3. Apify & Scrapers (Inteligência Competitiva)**
- **Função:** Robôs como o `gmb-claw` e `insta-audit` (vistos na sua máquina) que raspam dados do Google Maps e Instagram para alimentar o n8n e o Dify com informações quentes sobre os concorrentes do Lead.

---

## 🏬 A CAMADA DE COMÉRCIO E FRONTEND (STOREFRONTS)
Onde as transações financeiras acontecem e onde o tráfego aterrissa.

**1. Lojas e Páginas (Next.js / React)**
- **Ativos:** `clouthes_shop`, `vitalebrasil_shop`, `repairon`, `cardapio-que-vende`, `landing_page_diagnostico`.
- **Função:** Interfaces de alta performance focadas em UX e velocidade de carregamento para conversão de e-commerce e captação de leads.

**2. MedusaJS (Backend Headless de E-commerce)**
- **Ativos:** `medusa_ecommerce`.
- **Função:** Motor parrudo de e-commerce que gerencia produtos, carrinhos e integrações complexas (muito superior ao Shopify em escalabilidade de código).

**3. Cakto (Checkout e Pagamentos)**
- **Função:** Processador de pagamento / Gateway integrado para finalizar a compra do cliente sem fricção.

---

## 📡 A CAMADA DE ATENDIMENTO E CRM (THE COCKPIT)
Onde a equipe humana (Gabriela, Solano) atua.

**1. Evolution API (Gateway WhatsApp)**
- **Função:** Mantém as instâncias do WhatsApp aquecidas, disparando e recebendo mensagens massivas sem bloqueios, interligando o WhatsApp físico ao n8n.

**2. Chatwoot (Omnichannel Inbox)**
- **Função:** O painel de atendimento humano. É aqui que o "Kill Switch" funciona. Quando a Gabriela assume o ticket, o Chatwoot manda um webhook pro n8n avisando o Supabase para calar a IA.

**3. CRM (Twenty / Kommo CRM)**
- **Função:** Rastreabilidade do funil de vendas. Todo lead que interage com o Dify (ou cai pelo tráfego pago) é espelhado no CRM com status BANT visível.

**4. Cal.com / Kelevra Agenda**
- **Função:** Sistema de agendamento que o Dify envia (`forms.kelevra.shop`). Quando o lead agenda, um webhook entra no n8n movendo o card no CRM para "Agendado".

---

## 🗄️ A CAMADA DE INFRAESTRUTURA E DADOS (THE BACKBONE)
Onde os dados descansam e o sistema é hospedado.

**1. Supabase (BaaS / PostgreSQL)**
- **Função:** O coração dos dados em tempo real. Guarda o histórico de conversas (`dify_conversation_id`), a máquina de estados (`is_bot_active`), e as tabelas de `cold_leads`.

**2. OpenResty / Nginx & Docker**
- **Função:** Proxy reverso que roteia os domínios (`dify.kelevra.shop`, `n8n...`, `agenda...`) para os containers Docker corretos, lidando com SSL, balanceamento de carga e mitigação de ataques básicos.

---

## 🔄 COMO TUDO SE CONECTA NO FLUXO DA VENDA:
1. Um SCRAPER (`Apify`) coleta dados de uma clínica no Google Maps.
2. O n8n formata e injeta a lista de leads no **Supabase** e no **Twenty CRM**.
3. (Em um fluxo Ativo futuro) O n8n usa a **Evolution API** para prospectar.
4. O Lead responde "Quero saber mais". O n8n roteia para o **Dify**.
5. O Dify consulta o **SalesOps-as-Code (GitHub)**, entende que é uma clínica e aplica o "Pitch Anti No-Show".
6. O Lead agenda no **Cal.com** (`forms.kelevra.shop`).
7. O n8n lê a marcação e muda o CRM para "Agendado".
8. A venda acontece e o **Cakto** aprova o Pix.
9. Se for e-commerce, o pedido cai no **MedusaJS** e reflete no **Next.js**.
