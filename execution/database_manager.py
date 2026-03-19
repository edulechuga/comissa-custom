import sqlite3
import pandas as pd
import os
import math
from .calculo_impostos import sanitizar_ncm, sanitizar_string

def initialize_database(caminho_impostos_xlsx: str, caminho_ncm_xlsx: str, db_path: str):
    print(f"[{__name__}] Inicializando banco de dados SQLite em {db_path}...")
    conn = sqlite3.connect(db_path)
    
    # Processar IMPOSTOS
    if os.path.exists(caminho_impostos_xlsx):
        print("Lendo IMPOSTOS.xlsx para o SQLite...")
        df_impostos = pd.read_excel(caminho_impostos_xlsx)
        df_impostos['NCM_SAN'] = df_impostos['NCM'].apply(sanitizar_ncm)
        df_impostos['ESTADO_DESTINO_SAN'] = df_impostos['ESTADO DESTINO'].apply(sanitizar_string)
        df_impostos['ALIQ_ICMS_SAN'] = df_impostos['ALIQ. ICMS'].round(4)
        df_impostos.to_sql('impostos', conn, if_exists='replace', index=False)
        
        # Otimizar consultas para o banco de dados
        conn.execute("CREATE INDEX IF NOT EXISTS idx_impostos_lookup ON impostos (NCM_SAN, ESTADO_DESTINO_SAN, ALIQ_ICMS_SAN);")
    else:
        print(f"AVISO: Arquivo {caminho_impostos_xlsx} não encontrado.")

    # Processar NCM
    if os.path.exists(caminho_ncm_xlsx):
        print("Lendo NCM.xlsx para o SQLite...")
        df_ncm = pd.read_excel(caminho_ncm_xlsx)
        df_ncm['Codigo_SAN'] = df_ncm['Codigo'].apply(sanitizar_string)
        df_ncm.to_sql('ncm', conn, if_exists='replace', index=False)
        
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ncm_lookup ON ncm (Codigo_SAN);")
    else:
        print(f"AVISO: Arquivo {caminho_ncm_xlsx} não encontrado.")

    conn.commit()
    conn.close()
    print("Banco de dados SQLite gerado com sucesso!")
