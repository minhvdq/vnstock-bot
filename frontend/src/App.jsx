import { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { frontendBase } from './utils/homeUrl'
import customStorage from './utils/customStorage';

import Authentication from './pages/Authentication';

export default function App() {
  const [curUser, setCurUser] = useState(null)


  useEffect(() => {
    const loggedUser = customStorage.getItem('localUser')
    if(loggedUser){
      const lUser = JSON.parse(loggedUser)

      // console.log('cur user is ' + lUser)
      setCurUser(lUser)
    } 
  }, [])
  
  return (
    <BrowserRouter>
      <Route path='/authen' element={<Authentication curUser={curUser} setCurUser={setCurUser} />} />
    </BrowserRouter>
  )
}