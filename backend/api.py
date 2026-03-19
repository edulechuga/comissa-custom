import os
import shutil
from fastapi import FastAPI, UploadFile, File, HTTPException, Request, BackgroundTasks
from fastapi.responses import FileResponse
import zipfile
from fastapi.middleware.cors import CORSMiddleware
import time
import asyncio

import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from execution.gerador_comissao import GeradorComissao
from execution.database_manager import initialize_database

app = FastAPI(title="Camada 2 - API Comissões")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
TMP_DIR = os.path.join(BASE_DIR, '.tmp')
IMPOSTOS_PATH = os.path.join(BASE_DIR, 'IMPOSTOS.xlsx')
NCM_PATH = os.path.join(BASE_DIR, 'NCM.xlsx')
DB_PATH = os.path.join(TMP_DIR, 'banco_impostos.db')

os.makedirs(TMP_DIR, exist_ok=True)

def cleanup_old_files():
    """Remove arquivos e diretórios na pasta .tmp mais velhos que 7 dias (604800 segundos)"""
    now = time.time()
    seven_days = 7 * 24 * 60 * 60
    
    # Não deletar o banco de dados
    safe_files = ['banco_impostos.db']
    
    for root, dirs, files in os.walk(TMP_DIR, topdown=False):
        for name in files:
            if name in safe_files:
                continue
            file_path = os.path.join(root, name)
            if now - os.path.getmtime(file_path) > seven_days:
                try:
                    os.remove(file_path)
                except Exception:
                    pass
        for name in dirs:
            dir_path = os.path.join(root, name)
            try:
                # Tenta remover apenas se estiver vazio
                os.rmdir(dir_path)
            except Exception:
                pass

@app.on_event("startup")
async def startup_event():
    # Inicializa o banco de dados se não existir
    if not os.path.exists(DB_PATH):
        await asyncio.to_thread(initialize_database, IMPOSTOS_PATH, NCM_PATH, DB_PATH)

@app.post("/api/gerar-comissao")
async def gerar_comissao(request: Request, background_tasks: BackgroundTasks):
    background_tasks.add_task(cleanup_old_files)
    
    form = await request.form()
    ts = int(time.time())
    
    pares = []
    i = 0
    while True:
        pedido = form.get(f"pedido_{i}")
        if not pedido: 
            break
        nf = form.get(f"nf_{i}")
        # se nf existe mas não é arquivo com nome pdf
        if nf and getattr(nf, 'filename', '') == '':
            nf = None
            
        pares.append((pedido, nf))
        i += 1
        
    if not pares:
        raise HTTPException(status_code=400, detail="Nenhum pedido enviado.")
        
    # Salvar temporários e mapear as tarefas
    tasks = []
    gerador = GeradorComissao(DB_PATH)
    
    for idx, (pedido, nf) in enumerate(pares):
        if not getattr(pedido, 'filename', '').endswith('.xlsx'):
            raise HTTPException(status_code=400, detail=f"O pedido no bloco {idx+1} não é um .xlsx")
            
        pedido_path = os.path.join(TMP_DIR, f"pedido_{ts}_{idx}.xlsx")
        with open(pedido_path, "wb") as buffer:
            shutil.copyfileobj(pedido.file, buffer)
            
        nf_path = None
        if nf and getattr(nf, 'filename', '').endswith('.pdf'):
            nf_path = os.path.join(TMP_DIR, f"nf_{ts}_{idx}.pdf")
            with open(nf_path, "wb") as buffer:
                shutil.copyfileobj(nf.file, buffer)
                
        import uuid
        task_dir = os.path.join(TMP_DIR, str(uuid.uuid4()))
        os.makedirs(task_dir, exist_ok=True)
        
        # Empilhar a tarefa asssíncrona
        tasks.append(
            asyncio.to_thread(gerador.gerar_planilha_blocos, pedido_path, nf_path, task_dir)
        )
        
    try:
        # Paraleliza a execução de todos os pedidos ao mesmo tempo
        caminhos_gerados = await asyncio.gather(*tasks)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro no cômputo: {str(e)}")
        
    # Se existe apenas 1 arquivo devolve normal
    if len(caminhos_gerados) == 1:
        caminho_final = caminhos_gerados[0]
        nome_arquivo = os.path.basename(caminho_final)
        return FileResponse(
            path=caminho_final,
            filename=nome_arquivo,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Access-Control-Expose-Headers": "Content-Disposition"}
        )
    else:
        # Cria um arquivo ZIP contendo todas
        zip_filename = f"Lote_Comissoes_{ts}.zip"
        zip_path = os.path.join(TMP_DIR, zip_filename)
        
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            seen_names = {}
            for index, xl_path in enumerate(caminhos_gerados):
                # Caso a geração não tenha gerado um arquivo, ignore
                if not xl_path or not os.path.exists(xl_path):
                    continue
                    
                base_name = os.path.basename(xl_path)
                # Para diferenciar com absoluta certeza
                if base_name in seen_names:
                    seen_names[base_name] += 1
                    name, ext = os.path.splitext(base_name)
                    arc_name = f"{name} ({seen_names[base_name]}){ext}"
                else:
                    seen_names[base_name] = 0
                    arc_name = base_name
                    
                # Garante que se duas threads nomearam a MESMA RAZAO, forçamos index fallback pra não pular arquivo
                if arc_name in zipf.namelist():
                    name, ext = os.path.splitext(base_name)
                    arc_name = f"{name} ({index}){ext}"
                    
                zipf.write(xl_path, arcname=arc_name)
                
        return FileResponse(
            path=zip_path,
            filename=zip_filename,
            media_type="application/zip",
            headers={"Access-Control-Expose-Headers": "Content-Disposition"}
        )

@app.post("/api/atualizar-banco")
async def atualizar_banco(
    impostos_file: UploadFile = File(None),
    ncm_file: UploadFile = File(None)
):
    try:
        # Se mandou de Impostos, atualiza o arquivo físico root e processa
        if impostos_file and impostos_file.filename.endswith('.xlsx'):
            with open(IMPOSTOS_PATH, "wb") as buffer:
                shutil.copyfileobj(impostos_file.file, buffer)
                
        # Se mandou de NCM
        if ncm_file and ncm_file.filename.endswith('.xlsx'):
            with open(NCM_PATH, "wb") as buffer:
                shutil.copyfileobj(ncm_file.file, buffer)
                
        # Rebuid full banco
        from execution.database_manager import initialize_database
        await asyncio.to_thread(initialize_database, IMPOSTOS_PATH, NCM_PATH, DB_PATH)
        
        return {"detail": "Banco de dados sincronizado e acelerado com sucesso!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao reconstruir o banco: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
