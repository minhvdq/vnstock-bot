import { Outlet, Link, useNavigate } from 'react-router-dom'
import customStorage from '../utils/customStorage'

export default function Layout({ setCurUser }) {
  const navigate = useNavigate()

  const handleLogout = () => {
    customStorage.removeItem('localUser')
    setCurUser(null)
    navigate('/authen')
  }

  return (
    <div>
      <nav className="navbar navbar-expand-lg navbar-dark bg-dark px-4">
        <Link className="navbar-brand fw-bold" to="/">VN Stock Bot</Link>
        <div className="d-flex gap-3 mx-auto">
          <Link className="nav-link text-white" to="/">Watchlist</Link>
          <Link className="nav-link text-white" to="/backtest">Backtest</Link>
          <Link className="nav-link text-white" to="/batch-backtest">Batch Backtest</Link>
          <Link className="nav-link text-white" to="/paper-trading">Paper Trading</Link>
        </div>
        <button
          className="btn btn-outline-light btn-sm"
          onClick={handleLogout}
        >
          Logout
        </button>
      </nav>
      <div className="container py-4">
        <Outlet />
      </div>
    </div>
  )
}
