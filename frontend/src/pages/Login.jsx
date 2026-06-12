import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [username, setU] = useState("");
  const [password, setP] = useState("");
  const [err, setErr] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    try {
      const u = await login(username, password);
      nav(u.role === "SELLER" ? "/seller" : u.role === "FACILITY" ? "/facility" : "/");
    } catch (e2) {
      setErr(e2.message);
    }
  };

  return (
    <form className="form card" onSubmit={submit}>
      <h2>Login</h2>
      <label>Username</label>
      <input value={username} onChange={(e) => setU(e.target.value)} autoFocus />
      <label>Password</label>
      <input type="password" value={password} onChange={(e) => setP(e.target.value)} />
      {err && <div className="error">{err}</div>}
      <button style={{ marginTop: 14, width: "100%" }}>Login</button>
      <p className="muted" style={{ marginTop: 10 }}>
        No account? <Link to="/register">Register</Link>
        <br />
        Demo: buyer1 / rahul / seller1 / facility1 · password <code>demo1234</code>
      </p>
    </form>
  );
}
