import { useState } from 'react'
import { Toaster, toast } from 'react-hot-toast'
import './App.css'

function App() {
  const [activeTab, setActiveTab] = useState('gerador') // 'gerador' ou 'config'
  const [blocks, setBlocks] = useState([{ id: Date.now(), pedido: null, nf: null }])
  const [loading, setLoading] = useState(false)
  const [uploadingDb, setUploadingDb] = useState(false)
  const [impostoDb, setImpostoDb] = useState(null)
  const [ncmDb, setNcmDb] = useState(null)

  const addBlock = () => {
    setBlocks([...blocks, { id: Date.now(), pedido: null, nf: null }])
  }

  const removeBlock = (idToRemove) => {
    if (blocks.length > 1) {
      setBlocks(blocks.filter(b => b.id !== idToRemove))
    }
  }

  const updateBlock = (id, field, file) => {
    setBlocks(blocks.map(b => b.id === id ? { ...b, [field]: file } : b))
  }

  const handleGenerate = async () => {
    // Validar se todos os blocos têm pelo menos o pedido de venda
    for (let i = 0; i < blocks.length; i++) {
      if (!blocks[i].pedido) {
        toast.error(`O Pedido de Venda no bloco ${i + 1} é obrigatório.`)
        return
      }
    }

    setLoading(true)
    const toastId = toast.loading('Processando lote assíncrono e cruzando impostos...')

    try {
      const formData = new FormData()
      blocks.forEach((block, index) => {
        formData.append(`pedido_${index}`, block.pedido)
        if (block.nf) {
          formData.append(`nf_${index}`, block.nf)
        }
      })

      const response = await fetch('/api/gerar-comissao', {
        method: 'POST',
        body: formData,
      })

      // Evita crashar se backend devolver JSON em erro HTTP
      if (!response.ok) {
        const isJson = response.headers.get('content-type')?.includes('application/json');
        const erroMensagem = isJson ? (await response.json()).detail : `Erro Crítico: ${response.status} ${response.statusText}`;
        throw new Error(erroMensagem);
      }

      // Baixar o arquivo .xlsx com nome dinâmico
      const blob = await response.blob()

      let filename = 'Comissao_Gerada.xlsx';
      const disposition = response.headers.get('Content-Disposition');
      if (disposition) {
        const filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/;
        const matches = filenameRegex.exec(disposition);
        if (matches != null && matches[1]) {
          filename = matches[1].replace(/['"]/g, '');
        }

        const filenameStarRegex = /filename\*=utf-8''([^;\n]*)/i;
        const matchesStar = filenameStarRegex.exec(disposition);
        if (matchesStar != null && matchesStar[1]) {
          filename = decodeURIComponent(matchesStar[1]);
        }
      }

      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)

      // Notificação de sucesso (ZIP ou XLSX)
      toast.success(blocks.length > 1 ? `Lote gerado com sucesso! Baixando arquivo ZIP...` : `Planilha gerada com sucesso!`, { id: toastId })

    } catch (err) {
      toast.error(err.message, { id: toastId })
    } finally {
      setLoading(false)
    }
  }

  const handleUpdateDatabase = async () => {
    if (!impostoDb && !ncmDb) {
      toast.error("Selecione pelo menos um arquivo de banco para atualizar (Impostos ou NCM).")
      return
    }

    setUploadingDb(true)
    const toastId = toast.loading('Alimentando SQLite interno...')

    try {
      const formData = new FormData()
      if (impostoDb) formData.append('impostos_file', impostoDb)
      if (ncmDb) formData.append('ncm_file', ncmDb)

      const response = await fetch('/api/atualizar-banco', {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const errData = await response.json()
        throw new Error(errData.detail || 'Erro ao atualizar banco de dados.')
      }

      toast.success('Bancos de dados atualizados com sucesso!', { id: toastId })
      setImpostoDb(null)
      setNcmDb(null)
      // Resetar os inputs de DOM
      document.getElementById('input-imposto').value = ''
      document.getElementById('input-ncm').value = ''
    } catch (err) {
      toast.error(err.message, { id: toastId })
    } finally {
      setUploadingDb(false)
    }
  }

  return (
    <div className="container">
      <Toaster position="top-right" duration={4000} />
      <header className="header">
        <h1>Gerador de Comissões <span>v2.0</span></h1>
        <p>Gere suas planilhas estéticas de comissionamento via motor Python, diretamente pelo navegador.</p>

        <div style={{ marginTop: '20px', display: 'flex', gap: '10px', justifyContent: 'center' }}>
          <button
            style={{ padding: '8px 16px', background: activeTab === 'gerador' ? '#1677ff' : '#f0f0f0', color: activeTab === 'gerador' ? '#fff' : '#333', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}
            onClick={() => setActiveTab('gerador')}
          >
            Gerador em Lote
          </button>
          <button
            style={{ padding: '8px 16px', background: activeTab === 'config' ? '#1677ff' : '#f0f0f0', color: activeTab === 'config' ? '#fff' : '#333', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}
            onClick={() => setActiveTab('config')}
          >
            Atualizar Banco (NCM/Impostos)
          </button>
        </div>
      </header>

      {activeTab === 'gerador' ? (
        <main className="main-card">
          {blocks.map((block, index) => (
            <div key={block.id} className="block-container" style={{ border: '1px solid #eee', padding: '15px', borderRadius: '8px', marginBottom: '15px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                <h3 style={{ margin: 0, fontSize: '1rem', color: '#555' }}>Venda {index + 1}</h3>
                {blocks.length > 1 && (
                  <button onClick={() => removeBlock(block.id)} style={{ background: '#ff4d4f', color: '#fff', border: 'none', borderRadius: '4px', padding: '4px 8px', cursor: 'pointer', fontSize: '0.8rem' }}>Remover</button>
                )}
              </div>

              <div className="upload-group" style={{ marginBottom: '10px' }}>
                <label>1. Pedido de Venda (Obrigatório - .xlsx)</label>
                <div className="file-input-wrapper">
                  <input
                    type="file"
                    accept=".xlsx"
                    onChange={e => updateBlock(block.id, 'pedido', e.target.files[0])}
                  />
                </div>
              </div>

              <div className="upload-group">
                <label>2. Nota Fiscal (Opcional - .pdf)</label>
                <div className="file-input-wrapper">
                  <input
                    type="file"
                    accept=".pdf"
                    onChange={e => updateBlock(block.id, 'nf', e.target.files[0])}
                  />
                </div>
              </div>
            </div>
          ))}

          <div style={{ display: 'flex', gap: '10px', marginTop: '20px' }}>
            <button
              className="add-block-btn"
              onClick={addBlock}
              disabled={loading}
              style={{ flex: 1, padding: '12px', background: '#e0e0e0', color: '#333', border: 'none', borderRadius: '8px', fontSize: '1rem', fontWeight: '600', cursor: 'pointer', transition: 'background 0.3s' }}
            >
              + Adicionar mais vendas
            </button>
          </div>

          <button
            className="generate-btn"
            onClick={handleGenerate}
            disabled={loading}
            style={{ width: '100%', marginTop: '15px' }}
          >
            {loading ? 'Processando Lote...' : blocks.length > 1 ? `Gerar Lote de Comissões ZIP (${blocks.length} arquivos)` : 'Gerar Comissão em Excel'}
          </button>
        </main>
      ) : (
        <main className="main-card" style={{ maxWidth: '600px', margin: '0 auto' }}>
          <h3>Alimentar Banco SQLite</h3>
          <p style={{ fontSize: '0.9rem', color: '#666', marginBottom: '20px' }}>
            Nesta área você sobe os super-excels da contabilidade. O servidor processa uma única vez e gera um banco de relâmpago. Use sempre que o Governo mudar aliquotas ou novos NCMs.
            Você pode atualizar um só ou ambos ao mesmo tempo.
          </p>

          <div className="upload-group" style={{ marginBottom: '15px' }}>
            <label>Substituir Matriz de IMPOSTOS (.xlsx)</label>
            <div className="file-input-wrapper">
              <input
                id="input-imposto"
                type="file"
                accept=".xlsx"
                onChange={e => setImpostoDb(e.target.files[0])}
              />
            </div>
          </div>

          <div className="upload-group" style={{ marginBottom: '20px' }}>
            <label>Substituir Matriz de NCM (.xlsx)</label>
            <div className="file-input-wrapper">
              <input
                id="input-ncm"
                type="file"
                accept=".xlsx"
                onChange={e => setNcmDb(e.target.files[0])}
              />
            </div>
          </div>

          <button
            className="generate-btn"
            onClick={handleUpdateDatabase}
            disabled={uploadingDb}
            style={{ width: '100%', background: '#52c41a' }}
          >
            {uploadingDb ? 'Atualizando Banco de Dados...' : 'Gravar Alterações no Sistema'}
          </button>
        </main>
      )}

      <footer className="footer" style={{ marginTop: '20px', textAlign: 'center', fontSize: '0.85rem' }}>
        Configurações internas: Tabelas `IMPOSTOS.xlsx` e `NCM.xlsx` locais acopladas automaticamente.
      </footer>
    </div>
  )
}

export default App
