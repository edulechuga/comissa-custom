import pandas as pd
import logging
import os
from typing import Union, Dict, List, Any

# Configuração do Logger
LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.tmp', 'erros_impostos.log')
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def sanitizar_ncm(ncm_raw: Union[str, int, float]) -> str:
    if pd.isna(ncm_raw):
        return ""
    ncm_str = str(ncm_raw)
    if ncm_str.endswith('.0'): ncm_str = ncm_str[:-2]
    ncm_str = ncm_str.replace('.', '').replace(' ', '').strip()
    return ncm_str.zfill(8)

def sanitizar_string(valor: str) -> str:
    if pd.isna(valor) or not isinstance(valor, str):
        return str(valor).strip().upper() if not pd.isna(valor) else ""
    return valor.strip().upper()

def is_isento(ie_str: str) -> str:
    ie_san = sanitizar_string(ie_str)
    # Se está vazio, NaN ou explicitamente dito como isento, retorna "NÃO" (Não tem IE)
    if not ie_san or ie_san == "NAN" or "ISENT" in ie_san or ie_san == "NÃO":
        return "NÃO"
    return "SIM"

class CalculadoraImpostos:
    def __init__(self, db_path: str):
        # Em vez de carregar arquivos de 50mb pra memória RAM toda vez,
        # guardamos apenas a referência do banco de dados SQLite ultrarrápido
        self.db_path = db_path

    def calcular_aliquota_icms(self, origem_num: Union[int, float, str], uf_destino: str) -> float:
        """ Calcula a alíquota base de ICMS com Origem Faturamento = MG """
        try:
            origem = int(float(origem_num))
        except (ValueError, TypeError):
            origem = 0 # Default para Nacional
        
        uf_san = sanitizar_string(uf_destino)
        
        # 1. Se importado
        if origem in [1, 2, 3, 8]:
            return 0.04
        
        # 2. Se for Nacional
        if uf_san == 'MG':
            return 0.18  # Alíquota Interna
        elif uf_san in ['PR', 'SC', 'RS', 'SP', 'RJ']:
            return 0.12  # Sul/Sudeste Exceto ES (e MG)
        else:
            return 0.07  # Norte / Nordeste / C-O e ES
            
    def ler_pedido_venda(self, caminho_pedido: str) -> Dict[str, Any]:
        """ Lê os metadados (cabeçalho) de um arquivo de pedido RQCM. """
        df_pedido = pd.read_excel(caminho_pedido, nrows=40)
        
        metadados = {
            "NATUREZA_OPERACAO": "NÃO ENCONTRADA",
            "ESTADO_DESTINO": "NÃO ENCONTRADO",
            "TEM_IE": "NÃO",
            "RAZAO_SOCIAL": "Desconhecido"
        }
        
        # Explorar o excel buscando pelas Labels
        for i, row in df_pedido.iterrows():
            linha_valores = [str(x).upper().strip() for x in row.values if pd.notna(x)]
            
            # Buscar "Finalidade" ou "CONSUMO"/"REVENDA"
            if "REVENDA OR CONSUMO" in " ".join(linha_valores) or any(x in ["CONSUMO", "REVENDA"] for x in linha_valores):
                # Extrai do local conhecido nas primeiras 10 linhas
                if "CONSUMO" in row.values: metadados["NATUREZA_OPERACAO"] = "CONSUMO"
                elif "REVENDA" in row.values: metadados["NATUREZA_OPERACAO"] = "REVENDA"
                
            # Buscar Estado Destino do Cliente (faturamento) - Fica perto da Label "Estado" no bloco superior (antes de Revenda repassar)
            if "ESTADO" in linha_valores and i < 15:
                # Normalmente a coluna do lado
                for col_idx, val in enumerate(row.values):
                    if str(val).upper().strip() == "ESTADO" and col_idx + 1 < len(row.values):
                        metadados["ESTADO_DESTINO"] = sanitizar_string(row.values[col_idx + 1])
                        break
                        
            # Buscar Inscrição Estadual Cliente
            if "INSCRIÇÃO ESTADUAL" in linha_valores and i < 15:
                for col_idx, val in enumerate(row.values):
                    if str(val).upper().strip() == "INSCRIÇÃO ESTADUAL" and col_idx + 1 < len(row.values):
                        metadados["TEM_IE"] = is_isento(row.values[col_idx + 1])
                        break
                        
            # Buscar RAZAO SOCIAL ou NOME
            if ("NOME" in linha_valores or "RAZÃO SOCIAL" in [x.replace(" ", "") for x in linha_valores] or "RAZAOSOCIAL" in [x.replace(" ", "") for x in linha_valores]) and i < 20:
                for col_idx, val in enumerate(row.values):
                    v_str = str(val).upper().strip()
                    if (v_str == "NOME" or "RAZÃO SOCIAL" in v_str or "RAZAO SOCIAL" in v_str) and col_idx + 2 < len(row.values):
                        # Pega o primeiro valor real à direita
                        for nxt_val in row.values[col_idx+1:]:
                            if pd.notna(nxt_val) and str(nxt_val).strip() != "":
                                metadados["RAZAO_SOCIAL"] = str(nxt_val).strip()
                                break
                        break

        return metadados

    def extrair_linhas_pedido(self, caminho_pedido: str) -> pd.DataFrame:
        """ Extrai as linhas de produtos (PN) """
        df = pd.read_excel(caminho_pedido, nrows=100)
        start_row = -1
        # Procura a linha com as colunas de P/N ("Código do Produto") e "Preço Unitário"
        for i, row in df.iterrows():
            valores = [str(x).upper().strip() for x in row.values if pd.notna(x)]
            if "CÓDIGO DO PRODUTO" in valores and "PREÇO UNITÁRIO" in valores:
                start_row = i + 1
                break
                
        if start_row == -1:
            raise ValueError("Não foi possivel encontrar as colunas de produtos no Pedido.")
            
        dados_reais = df.iloc[start_row:].copy()
        cols = [str(x).strip() for x in df.iloc[start_row-1].values]
        unique_cols = []
        c_count = {}
        for c in cols:
            if c in c_count:
                c_count[c] += 1
                unique_cols.append(f"{c}_{c_count[c]}")
            else:
                c_count[c] = 0
                unique_cols.append(c)
        dados_reais.columns = unique_cols
        
        # Filtra apenas linhas que tenham o "Código do Produto" válido (Remove linhas de soma, totais, etc)
        produtos_df = dados_reais[dados_reais["Código do Produto"].notna()]
        produtos_df = produtos_df[produtos_df["Código do Produto"] != "nan"]
        
        # Filtra para não pegar os dados do "Custo de Revenda" (quando houver a segunda tabela lá embaixo)
        # Vamos parar quando encontrarmos NaN na Quantidade ou texto
        linhas_validas = []
        for _, row in produtos_df.iterrows():
            if pd.isna(row['Quantidade']) or str(row['Quantidade']).strip().upper() == 'NAN' or type(row['Quantidade']) not in [int, float]:
                if not isinstance(row['Quantidade'], int) and not str(row['Quantidade']).isdigit():
                    break
            linhas_validas.append(row)
            
        return pd.DataFrame(linhas_validas)

    def processar_pedido_completo(self, caminho_pedido: str) -> List[Dict[str, Any]]:
        """ Função principal que roda o pedido inteiro """
        import sqlite3
        
        metadados = self.ler_pedido_venda(caminho_pedido)
        linhas_prod = self.extrair_linhas_pedido(caminho_pedido)
        
        resultados = []
        
        # Abrir conexão rápida com SQLite
        try:
            conn = sqlite3.connect(self.db_path)
            # Acessar via nome das colunas
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
        except sqlite3.Error as e:
            logger.error(f"Erro ao conectar no banco SQLite: {e}")
            raise ValueError(f"Banco de dados indisponível. Detalhes: {e}")
        
        for _, row_prod in linhas_prod.iterrows():
            pn = sanitizar_string(str(row_prod.get('Código do Produto', '')))
            desc = row_prod.get('Descrição', '')
            qtd = row_prod.get('Quantidade', 1)
            preco_un = row_prod.get('Preço Unitário', 0)
            
            # Buscar na tabela de NCM via SQL (O(1))
            cursor.execute('SELECT "NCM", "Origem", "Aliq. IPI" FROM ncm WHERE "Codigo_SAN" = ? LIMIT 1', (pn,))
            ncm_info = cursor.fetchone()
            
            if not ncm_info:
                logger.warning(f"PN não encontrado no banco NCM: {pn}")
                resultados.append({
                    "PN": pn, "Descricao": desc, "NCM": "DESCONHECIDO", 
                    "Imposto_Calculado": "PN NÃO ENCONTRADO NA TABELA NCM"
                })
                continue
                
            ncm_produto = sanitizar_ncm(ncm_info['NCM'])
            origem_produto = ncm_info['Origem']
            aliq_ipi = ncm_info['Aliq. IPI']
                
            # Calcular ICMS
            uf = metadados["ESTADO_DESTINO"]
            aliq_calc = self.calcular_aliquota_icms(origem_produto, uf)
            nat_op = metadados["NATUREZA_OPERACAO"]
            tem_ie = metadados["TEM_IE"]
            
            imposto, tipo_imposto = self.buscar_taxa_exata(cursor, ncm_produto, uf, aliq_calc, nat_op, tem_ie)
            
            resultados.append({
                "PN": pn,
                "Descricao": desc,
                "Quantidade": qtd,
                "Preco_Unitario": preco_un,
                "NCM": ncm_produto,
                "Origem": origem_produto,
                "Aliq_Interestadual_Calculada": aliq_calc,
                "Aliq_IPI": aliq_ipi if (aliq_ipi is not None and not pd.isna(aliq_ipi)) else 0,
                "Metadados_Usados": f"{uf} | {nat_op} | IE:{tem_ie}",
                "Tipo_Imposto": tipo_imposto,
                "Imposto_Final": imposto
            })
            
        conn.close()
        return resultados

    def buscar_taxa_exata(self, cursor, ncm_san: str, uf_san: str, aliq_san: float, nat_san: str, ie_san: str) -> tuple[Union[float, str], str]:
        # Regra de Erro de Negócio bloqueante: Revenda sem Inscrição Estadual
        if nat_san == "REVENDA" and ie_san == "NÃO":
            msg_erro = f"ERRO - OPERAÇÃO NÃO PERMITIDA ({ncm_san}, {uf_san}, Nat: {nat_san}, IE: {ie_san})"
            logger.error(msg_erro)
            return ("ERRO - OPERAÇÃO NÃO PERMITIDA", "ERRO")
            
        aliq_arredondada = round(aliq_san, 4)
        
        cursor.execute(
            '''SELECT "ICMS ST ", "DIFAL CONTRIBUINTE", "DIFAL NÃO CONTRIBUINTE" 
               FROM impostos WHERE NCM_SAN = ? AND ESTADO_DESTINO_SAN = ? AND ABS(ALIQ_ICMS_SAN - ?) < 0.0001 LIMIT 1''',
            (ncm_san, uf_san, aliq_arredondada)
        )
        linha = cursor.fetchone()
        
        if not linha:
            msg_not_found = f"NÃO ENCONTRADO - NCM: {ncm_san} | ESTADO: {uf_san} | ALIQ: {aliq_arredondada}"
            logger.warning(msg_not_found)
            return ("NÃO ENCONTRADO", "ERRO")
            
        if nat_san == "REVENDA" and ie_san == "SIM":
            return (linha['ICMS ST '], "ICMS ST ")
        elif nat_san == "CONSUMO" and ie_san == "SIM":
            return (linha['DIFAL CONTRIBUINTE'], "DIFAL")
        elif nat_san == "CONSUMO" and ie_san == "NÃO":
            return (linha['DIFAL NÃO CONTRIBUINTE'], "DIFAL")
        else:
            return ("NÃO ENCONTRADO", "ERRO")

if __name__ == "__main__":
    caminho_base = os.path.dirname(os.path.dirname(__file__))
    impostos_file = os.path.join(caminho_base, "IMPOSTOS.xlsx")
    ncm_file = os.path.join(caminho_base, "NCM.xlsx")
    pedido_file = os.path.join(caminho_base, "RQCM-001 - Pedido de venda - O.LIVE - 02022026.xlsx")
    
    if os.path.exists(pedido_file):
        # Passaremos direto pro SQLite simulado 
        db_path = os.path.join(caminho_base, ".tmp", "impostos.db")
        from execution.database_manager import initialize_database
        initialize_database(impostos_file, ncm_file, db_path)
        
        calc = CalculadoraImpostos(db_path)
        resultados = calc.processar_pedido_completo(pedido_file)
        print("\\n==================================")
        print("RESULTADO DO PROCESSAMENTO DO PEDIDO")
        print("==================================\\n")
        for res in resultados:
            print(f"Produto: {res['PN']} ({res['Descricao']})")
            print(f"Info Extraida: NCM {res['NCM']} | Origem {res['Origem']} | ICMS Interestadual {res['Aliq_Interestadual_Calculada']*100}%")
            print(f"Mapeamento Cliente: {res['Metadados_Usados']}")
            print(f"*** IMPOSTO RETORNADO: {res['Imposto_Final']} ***\\n")
    else:
        print("Arquivos locais incompletos para teste.")
