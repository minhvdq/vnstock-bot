import { useState, useEffect } from 'react';
import { message } from 'antd';
import { useNavigate } from 'react-router-dom';
import customStorage from '../utils/customStorage';
import loginService from '../services/login';
import { backendBase, frontendBase } from '../utils/homeUrl';

export default function Authentication({ curUser, setCurUser }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const navigate = useNavigate();

  useEffect(() => {
    if (curUser) {
      window.location.href = `${frontendBase}`;
    }
  }, [curUser]);

  const handleEmail = (event) => {  
    setEmail(event.target.value);
  };

  const handlePassword = (event) => {
    setPassword(event.target.value);
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      const logUser = await loginService.login({ email, password });

      setCurUser(logUser);
      customStorage.setItem('localUser', JSON.stringify(logUser));

      setEmail('');
      setPassword('');

      const loginDirect = window.localStorage.getItem("loginDirect");

      if (loginDirect) {
        window.localStorage.removeItem("loginDirect");
        window.location.href = loginDirect;
      } else {
        window.location.href = frontendBase;
      }
    } catch (e) {
      console.error("Login error:", e);
      message.error("Wrong username or password");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className='container d-flex justify-content-center align-items-center min-vh-100 min-vw-100 position-relative'>
      
      {/* Top-left Back to Home Button */}
      <button
        onClick={() => navigate('/')}
        className="btn btn-link position-absolute"
        style={{ top: "20px", left: "20px", fontSize: "0.9rem", color: "#6c63ff", textDecoration: "none" }}
      >
        ← Back to Home
      </button>

      <div className='row border rounded-5 p-3 bg-white shadow box-area'>
        {/* Left Panel */}
        <div className='col-md-6 rounded-4 d-flex justify-content-center align-items-center flex-column left-box'>
          <div className='featured-image mb-3'>
            <img src={`${frontendBase}/gb-logo.png`} className='img-fluid' style={{ width: "85%" }} alt="logo"/>
          </div>
        </div>

        {/* Right Panel */}
        <div className='col-md-6 right-box shadow'>
          <div className='row align-items-center px-4 py-5'>
            <div className='header-text mb-4'>
              <h2 className='text-center mb-1' style={{ fontFamily: "Poppins, sans-serif", fontWeight: "700", color: "#333" }}>
                Welcome Back
              </h2>
              <p className='text-center text-muted'>Sign in to continue your journey</p>
            </div>

            <form onSubmit={handleLogin} className="login-form">
              {/* Email */}
              <div className="form-group mb-4">
                <label htmlFor="emailInput" className="form-label fw-bold">Email Address</label>
                <div className='input-group'>
                  <span className="input-group-text bg-light">
                    <i className="bi bi-envelope"></i>
                  </span>
                  <input
                    type="email"
                    className="form-control form-control-lg bg-light border-start-0"
                    id="emailInput"
                    placeholder="name@example.com"
                    value={email}
                    onChange={handleEmail}
                    required
                  />
                </div>
              </div>

              {/* Password */}
              <div className="form-group mb-4">
                <div className="d-flex justify-content-between align-items-center">
                  <label htmlFor="passwordInput" className="form-label fw-bold">Password</label>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      window.location.href = `${backendBase}/PasswordResetRequest/ui_assets/request.html`;
                    }}
                    className="btn btn-link p-0 text-decoration-none"
                    style={{ fontSize: "0.9rem", color: "#6c63ff" }}
                  >
                    Forgot password?
                  </button>
                </div>
                <div className='input-group'>
                  <span className="input-group-text bg-light">
                    <i className="bi bi-lock"></i>
                  </span>
                  <input
                    type="password"
                    id="passwordInput"
                    className="form-control form-control-lg bg-light border-start-0"
                    placeholder="Enter your password"
                    value={password}
                    onChange={handlePassword}
                    required
                  />
                </div>
              </div>

              {/* Submit */}
              <div className="form-group mt-5">
                <button
                  type='submit'
                  className="btn btn-primary w-100 py-3 fw-bold"
                  style={{ backgroundColor: "#6c63ff", borderColor: "#6c63ff", borderRadius: "8px" }}
                  disabled={loading}
                >
                  {loading ? (
                    <span>
                      <span className="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                      Signing In...
                    </span>
                  ) : "Sign In"}
                </button>
              </div>
            </form>

            <div className="text-center mt-4">
              <p className="text-muted small">
                By signing in, you agree to our <a href="#" className="text-decoration-none">Terms of Service</a> and <a href="#" className="text-decoration-none">Privacy Policy</a>
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}