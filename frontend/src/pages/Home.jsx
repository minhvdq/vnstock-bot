import { useState, useEffect } from 'react'
import { Input, Button, message, Tag, Spin } from 'antd'
import { useNavigate } from 'react-router-dom'
import { getMe, addStock, removeStock, getTelegramLink, getCompanies } from '../services/user'

export default function Home({ curUser }) {
  const navigate = useNavigate()
  const [user, setUser] = useState(null)
  const [watchlist, setWatchlist] = useState([])
  const [companies, setCompanies] = useState([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!curUser) {
      navigate('/authen')
      return
    }
    Promise.all([getMe(), getCompanies()])
      .then(([me, cps]) => {
        setUser(me)
        setWatchlist(me.stocks)
        setCompanies(cps)
      })
      .catch(() => message.error('Failed to load data'))
      .finally(() => setLoading(false))
  }, [curUser, navigate])

  const handleAdd = (symbol) => {
    const prev = [...watchlist]
    if (prev.includes(symbol)) return
    setWatchlist([...prev, symbol])
    addStock(user.id, symbol)
      .then(updated => setWatchlist(updated.stocks))
      .catch(() => {
        setWatchlist(prev)
        message.error(`Failed to add ${symbol}`)
      })
  }

  const handleRemove = (symbol) => {
    const prev = [...watchlist]
    setWatchlist(prev.filter(s => s !== symbol))
    removeStock(symbol)
      .then(updated => setWatchlist(updated.stocks))
      .catch(() => {
        setWatchlist(prev)
        message.error(`Failed to remove ${symbol}`)
      })
  }

  const handleConnectTelegram = () => {
    getTelegramLink()
      .then(({ link }) => window.open(link, '_blank'))
      .catch(() => message.error('Failed to get Telegram link'))
  }

  const filtered = search.trim()
    ? companies.filter(c =>
        `${c.symbol} ${c.organ_name}`.toLowerCase().includes(search.toLowerCase())
      ).slice(0, 10)
    : []

  if (loading) return <div className="text-center mt-5"><Spin size="large" /></div>

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center mb-4">
        <h4 className="mb-0">My Watchlist</h4>
        {user?.chat_id ? (
          <Tag color="green">Telegram Connected ✓</Tag>
        ) : (
          <Button onClick={handleConnectTelegram}>Connect Telegram</Button>
        )}
      </div>

      <div className="mb-4">
        {watchlist.length === 0 && (
          <p className="text-muted">No stocks yet. Search below to add some.</p>
        )}
        {watchlist.map(symbol => (
          <Tag
            key={symbol}
            closable
            onClose={() => handleRemove(symbol)}
            style={{ fontSize: '14px', padding: '4px 10px', marginBottom: '8px' }}
          >
            {symbol}
          </Tag>
        ))}
      </div>

      <div>
        <Input
          placeholder="Search by symbol or company name..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ maxWidth: 400 }}
        />
        {filtered.map(c => (
          <div
            key={c.symbol}
            className="d-flex justify-content-between align-items-center border-bottom py-2"
            style={{ maxWidth: 400 }}
          >
            <span><strong>{c.symbol}</strong> — {c.organ_name}</span>
            <Button
              size="small"
              type="primary"
              disabled={watchlist.includes(c.symbol)}
              onClick={() => handleAdd(c.symbol)}
            >
              {watchlist.includes(c.symbol) ? 'Added' : 'Add'}
            </Button>
          </div>
        ))}
      </div>
    </div>
  )
}
