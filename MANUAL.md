# Manual de Arquitetura e Implantação - Gerador de Comissões v2.0

Este documento descreve a arquitetura, o fluxo de implantação no Proxmox (LXC) e os procedimentos de manutenção do sistema de Geração de Comissões.

---

## 1. Arquitetura do Sistema

O sistema foi refatorado para uma arquitetura moderna de microsserviços ("Enterprise-grade") focando em extrema performance e experiência do usuário.

### Tecnologias (Stack)
- **Frontend (UI Web):** Construído em **React.js + Vite**. Permite envios dinâmicos form-data (lotes com infinitos arquivos), feedbacks visuais modernos via `react-hot-toast`, rodando 100% estático compilado via HTML/JS para não pesar no servidor.
- **Servidor Web e Proxy:** **Nginx**. Atua servindo a interface estática na porta `80` e despachando as conexões originadas de `/api/*` diretamente para o backend.
- **Backend (API):** **Python 3 / FastAPI**. O motor lida com I/O nativo, rotas de geração, extração de texto (via `PyMuPDF`) e requisições HTTP seguras.
- **Coração (Data Engine):** O processamento de planilhas pesadas do arquivo original via Pandas foi trocado por um **Banco de Dados SQLite3**. A API mapeia o "IMPOSTOS.xlsx" e "NCM.xlsx" dinamicamente uma única vez e gera um arquivo `.db` local de alta velocidade com queries milissegundos.
- **Job Asynchronous:** Módulo multithread assíncrono nativo (`asyncio.gather`), que extrai N faturas/pedidos simultaneamente. E um Garbage Collector que roda em Background rodando `cleanup_old_files` para manter o HD do container sempre vazio.

---

## 2. Passo a Passo de Implantação (Deploy no Proxmox LXC)

Como Containers LXC limpos no Proxmox possuem bloqueios nativos de kernel para as pontes de rede do Docker (erro nativo do `ip_unprivileged_port_start`), a aplicação é instalada organicamente de maneira "Bare-Metal" no Debian/Ubuntu.

Assumindo que o código em `.zip` foi extraído para a pasta `/opt/comissoes/comissoes`:

### Passo 2.1: Instalação das Dependências Base
```bash
apt update
apt install -y python3 python3-venv python3-pip nginx wget gcc git
```

### Passo 2.2: Configuração do Backend Python
```bash
cd /opt/comissoes/comissoes
python3 -m venv venv
source venv/bin/activate
# Instalar bibliotecas primárias como fastapi, pandas, openpyxl, fitz
pip install -r requirements.txt
deactivate
```

### Passo 2.3: Compilando e Servindo o Frontend
A build do React foi injetada diretamente na pasta raiz do servidor Web do Linux (`/var/www/html/`).
```bash
cd /opt/comissoes/comissoes
rm -rf /var/www/html/*
cp -r frontend/dist/* /var/www/html/

# Vinculando a regra nginx (Proxy /api -> Porta 8000)
cp deployment/nginx.conf /etc/nginx/sites-available/default
systemctl restart nginx
```

### Passo 2.4: Daemon (Serviço) do Backend
Com o SystemD, o servidor Python nunca desliga. Se o Proxmox reiniciar ou a aplicação falhar, ela ressuscita no segundo seguinte.

```bash
cat << 'EOF' > /etc/systemd/system/comissao-api.service
[Unit]
Description=Comissao API Backend
After=network.target

[Service]
User=root
WorkingDirectory=/opt/comissoes/comissoes
Environment="PATH=/opt/comissoes/comissoes/venv/bin"
Environment="PYTHONUNBUFFERED=1"
ExecStart=/opt/comissoes/comissoes/venv/bin/uvicorn backend.api:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF
```

### Passo 2.5: Ligando os motores
```bash
systemctl daemon-reload
systemctl enable comissao-api
systemctl start comissao-api
```

A aplicação está online através do IP atribuído e roteado do LXC pela porta 80.

---

## 3. Manutenção e Operações (Cheatsheet)

### A. Atualização da Lógica Python (Backend)
Se você modificar arquivos como `gerador_comissao.py` na sua máquina local e enviá-los para o servidor (`/opt/comissoes/comissoes`), **SEMPRE reinicie o serviço Python** para aplicar as mudanças:
```bash
systemctl restart comissao-api
```

### B. Onde ficam os arquivos temporários?
Tudo que o cliente envia, PDFs processados ou lotes `.zip` ficam blindados geograficamente na pasta oculta `.tmp` do repositório:
```bash
cd /opt/comissoes/comissoes/.tmp
```
> **Nota:** Não existe preocupação de superlotação do disco. O Backend possui um script `cleanup_old_files` atrelado a toda a requisição que deleta automaticamente arquivos velhos há mais de *7 dias* presentes ali.

### C. Analisar Logs de Erro 
Se a interface relatar quevação forte (Erro HTTP 500), acompanhe em tempo real do que a inteligência Python está reclamando abrindo os logs nativos do sistema operacional:
```bash
journalctl -u comissao-api -f -n 100
```
> *(Aperte `Ctrl + C` para sair da leitura ao vivo)*

### D. Atualização do Banco de Dados Fiscal (Impostos/NCM)
Não é necessário acesso ao bash do terminal Linux para atualizar alíquotas. 
Basta abrir a Interface Gráfica da Web (navegador), acessar a aba **"Atualizar Banco (NCM/Impostos)"** e inserir os novos Excels oficiais da contabilidade. O FastAPI cuidará sozinho de sobrepor as raízes xlsx, apagar o `banco_impostos.db` velho e recompilar um super sqlite O(1) com a nova regra de negócio de forma relâmpago.
