import axios from 'axios'
import {backendBase} from '../utils/homeUrl'

const loginUrl = `${backendBase}/auth/login`
const login = async (logInfo) => {
    const response = await axios.post(loginUrl, logInfo)
    // console.log(response.data)
    return response.data
}

export default {login}