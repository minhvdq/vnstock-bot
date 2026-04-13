import { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import customStorage from './utils/customStorage'
import Authentication from './pages/Authentication'
import Home from './pages/Home'
import Backtest from './pages/Backtest'
import Layout from './components/Layout'

export default function App() {
  const [curUser, setCurUser] = useState(null)

  useEffect(() => {
    const loggedUser = customStorage.getItem('localUser')
    if (loggedUser) {
      setCurUser(JSON.parse(loggedUser))
    }
  }, [])

  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/authen"
          element={<Authentication curUser={curUser} setCurUser={setCurUser} />}
        />
        <Route element={<Layout curUser={curUser} setCurUser={setCurUser} />}>
          <Route path="/" element={<Home curUser={curUser} />} />
          <Route path="/backtest" element={<Backtest />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
