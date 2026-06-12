import { useEffect, useState } from "react";
import { api } from "../api";

export default function FacilityPortal() {
  const [incoming, setIncoming] = useState([]);
  const [watchlist, setWatchlist] = useState([]);
  const [msg, setMsg] = useState("");

  const load = () => {
    api.get("/facility/incoming").then(setIncoming);
    api.get("/facility/watchlist").then(setWatchlist);
  };
  useEffect(() => { load(); }, []);

  const receive = async (unitId, untouched) => {
    setMsg("");
    try {
      await api.post("/facility/receive", { unit_id: unitId, untouched });
      load();
    } catch (e) { setMsg(e.message); }
  };

  const relist = async (unitId) => {
    setMsg("");
    try { await api.post(`/facility/units/${unitId}/relist`); load(); }
    catch (e) { setMsg(e.message); }
  };

  const dispose = async (unitId, target) => {
    setMsg("");
    try { await api.post(`/facility/units/${unitId}/dispose`, { target }); load(); }
    catch (e) { setMsg(e.message); }
  };

  const simulateDay = async () => {
    setMsg("");
    const s = await api.post("/facility/simulate-day");
    setMsg(`+1 day: ${s.units_accrued} units accrued · ${s.price_stepdowns} price step-downs · ${s.liquidated} liquidated.`);
    load();
  };

  return (
    <div className="page">
      <div className="row">
        <h2 style={{ margin: 0 }}>Facility</h2>
        <button className="right" onClick={simulateDay}>⏩ Simulate one day</button>
      </div>
      {msg && <div className="success">{msg}</div>}

      <h3>Incoming returns</h3>
      <table>
        <thead><tr><th>Item</th><th>Claimed</th><th>Receive as…</th></tr></thead>
        <tbody>
          {incoming.map((u) => (
            <tr key={u.id}>
              <td>{u.product.title}</td>
              <td className="muted">{u.untouched ? "unopened" : "—"}</td>
              <td className="row">
                <button onClick={() => receive(u.id, true)}>Unopened ✓</button>
                <button className="secondary" onClick={() => receive(u.id, false)}>Opened</button>
              </td>
            </tr>
          ))}
          {incoming.length === 0 && (
            <tr><td colSpan={3} className="muted">No incoming returns.</td></tr>
          )}
        </tbody>
      </table>

      <h3 style={{ marginTop: 32 }}>Storage watchlist <span className="muted">(closest to liquidation first)</span></h3>
      <table>
        <thead>
          <tr><th>Item</th><th>State</th><th>Grade</th><th>Storage / value</th><th>Ratio</th><th>Actions</th></tr>
        </thead>
        <tbody>
          {watchlist.map((u) => (
            <tr key={u.id}>
              <td>{u.product.title}</td>
              <td><span className="badge">{u.state}</span></td>
              <td><span className={`badge grade-${u.grade}`}>{u.grade}</span></td>
              <td className="muted">₹{u.storage_cost_accrued} / ₹{u.est_value}</td>
              <td>
                <div className="ratio-bar">
                  <div className="ratio-fill" style={{ width: `${Math.min(100, u.storage_ratio * 100)}%` }} />
                </div>
              </td>
              <td className="row">
                {u.state === "AT_FACILITY" && (
                  <button onClick={() => relist(u.id)}>Relist</button>
                )}
                <button className="secondary" onClick={() => dispose(u.id, "DONATED")}>Donate</button>
                <button className="danger" onClick={() => dispose(u.id, "LIQUIDATE")}>Liquidate</button>
              </td>
            </tr>
          ))}
          {watchlist.length === 0 && (
            <tr><td colSpan={6} className="muted">Floor is clear.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
