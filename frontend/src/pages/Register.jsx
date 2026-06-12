import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export default function Register() {
  const { register } = useAuth();
  const nav = useNavigate();
  const [username, setU] = useState("");
  const [password, setP] = useState("");
  const [role, setRole] = useState("BUYER");
  const [err, setErr] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    try {
      const u = await register(username, password, role);
      nav(u.role === "SELLER" ? "/seller" : "/");
    } catch (e2) {
      setErr(e2.message);
    }
  };

  return (
    <form className="form card" onSubmit={submit}>
      <h2>Register</h2>
      <label>Username</label>
      <input value={username} onChange={(e) => setU(e.target.value)} autoFocus />
      <label>Password</label>
      <input type="password" value={password} onChange={(e) => setP(e.target.value)} />
      <label>I am a…</label>
      <select value={role} onChange={(e) => setRole(e.target.value)}>
        <option value="BUYER">Buyer (can also resell)</option>
        <option value="SELLER">Seller</option>
      </select>
      {err && <div className="error">{err}</div>}
      <button style={{ marginTop: 14, width: "100%" }}>Create account</button>
      <p className="muted" style={{ marginTop: 10 }}>
        Have an account? <Link to="/login">Login</Link>
      </p>
    </form>
  );
}
