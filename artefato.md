# Guia: Atualizar Serviço da API (LXC Proxmox) para Novo Diretório

Este guia explica como redirecionar o serviço `systemd` que roda no seu container LXC Proxmox para uma nova pasta clonada do GitHub (`comissa-custom`), recriando também o ambiente virtual (`venv`) que não pode ser copiado de outro sistema.

## 0. Como Identificar o Nome do Serviço
Caso você não saiba qual o nome exato do seu serviço, você pode listar todos os serviços que estão rodando no seu servidor e procurar por um nome que pareça com a sua aplicação (ex: `app.service`, `comissao.service`):

```bash
systemctl list-units --type=service --state=running
```
*(No nosso caso acima, o serviço foi identificado como **`comissao-api.service`**).*

Para checar os detalhes e a pasta de um serviço e confirmar se achou o certo:
```bash
systemctl status <nome-do-servico>
```

## 1. Recriar o Ambiente Virtual (venv) Limpo
Quando o projeto é clonado do GitHub, a pasta `venv` baixada vêm com caminhos absolutos e atalhos quebrados, próprios do computador anterior. Você deve recriá-la:

Acesse sua pasta nova:
```bash
cd /opt/comissoes/comissoes/comissa-custom
```

Desative qualquer ambiente ativo (caso exista), apague a pasta quebrada e crie do zero:
```bash
deactivate          # Se falhar porque não estava em um, tudo bem
rm -rf venv         # Apaga a pasta com atalhos corrompidos
python3 -m venv venv # Cria um venv novo limpo
```

Ative e instale as dependências:
```bash
source venv/bin/activate
pip install -r requirements.txt
deactivate          # (Opcional) desativa ao terminar
```

## 2. Atualizar o Serviço no Systemd
Pare o serviço da sua API que está rodando apontando para a pasta antiga:
```bash
systemctl stop comissao-api.service
```

Abra o arquivo de configuração de serviço no Nano:
```bash
nano /etc/systemd/system/comissao-api.service
```

Substitua todo o conteúdo pelo bloco abaixo (verifique se os caminhos batem em `WorkingDirectory`, `Environment` duplo e `ExecStart`):

```ini
[Unit]
Description=Comissao API Backend
After=network.target

[Service]
User=root
WorkingDirectory=/opt/comissoes/comissoes/comissa-custom
Environment="PATH=/opt/comissoes/comissoes/comissa-custom/venv/bin"
Environment="PYTHONUNBUFFERED=1"
ExecStart=/opt/comissoes/comissoes/comissa-custom/venv/bin/uvicorn backend.api:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

**(Para salvar no Nano: aperte `CTRL+O`, depois `ENTER`, e por último `CTRL+X`)*.*

## 3. Reload e Teste (Comandos Finais)
Recarregue as configurações do sistema para aplicar a mudança:
```bash
systemctl daemon-reload
```

Inicie o serviço usando os arquivos do repositório novo:
```bash
systemctl start comissao-api.service
```

Por fim, avalie se subiu sem erros observando se ele está `active (running)`:
```bash
systemctl status comissao-api.service
```
