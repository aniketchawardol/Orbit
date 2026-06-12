import { useEffect, useState } from "react";
import { api } from "../api";
import PhotoPicker from "../components/PhotoPicker";

const REASONS = [
  ["DIDNT_MATCH", "Didn't match description"],
  ["WRONG_SIZE", "Wrong size / fit"],
  ["CHANGED_MIND", "Changed my mind"],
  ["DEFECTIVE", "Damaged / defective"],
  ["OTHER", "Other"],
];

export default function Orders() {
  const [orders, setOrders] = useState([]);
  const [returning, setReturning] = useState(null); // order id
  const [reason, setReason] = useState("CHANGED_MIND");
  const [untouchedClaim, setUntouchedClaim] = useState(false);
  const [photos, setPhotos] = useState([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const load = () => api.get("/orders").then(setOrders);
  useEffect(() => { load(); }, []);

  const advance = async (id) => {
    setMsg("");
    try { await api.post(`/orders/${id}/advance`); load(); }
    catch (e) { setMsg(e.message); }
  };

  const startReturn = (id) => {
    setReturning(id);
    setPhotos([]);
    setUntouchedClaim(false);
    setReason("CHANGED_MIND");
  };

  const submitReturn = async (id) => {
    setMsg("");
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("reason", reason);
      fd.append("claimed_untouched", untouchedClaim ? "true" : "false");
      photos.forEach((f) => fd.append("photos", f));
      await api.postForm(`/orders/${id}/return`, fd);
      setReturning(null);
      setPhotos([]);
      load();
    } catch (e) { setMsg(e.message); }
    finally { setBusy(false); }
  };

  return (
    <div className="page">
      <h2>My orders</h2>
      {msg && <div className="error">{msg}</div>}
      <table>
        <thead>
          <tr><th>Item</th><th>Price</th><th>State</th><th /></tr>
        </thead>
        <tbody>
          {orders.map((o) => (
            <tr key={o.id}>
              <td>{o.listing.product.title}</td>
              <td>₹{o.listing.price}</td>
              <td><span className="badge">{o.state}</span></td>
              <td>
                {o.state === "PLACED" && (
                  <button className="secondary" onClick={() => advance(o.id)}>
                    Mark delivered (demo)
                  </button>
                )}
                {o.state === "DELIVERED" && returning !== o.id && (
                  <button className="secondary" onClick={() => startReturn(o.id)}>
                    Return
                  </button>
                )}
                {returning === o.id && (
                  <div className="card" style={{ padding: 12 }}>
                    <div className="row">
                      <select value={reason} onChange={(e) => setReason(e.target.value)} style={{ maxWidth: 220 }}>
                        {REASONS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
                      </select>
                      <label className="row" style={{ margin: 0 }}>
                        <input
                          type="checkbox"
                          style={{ width: "auto" }}
                          checked={untouchedClaim}
                          onChange={(e) => setUntouchedClaim(e.target.checked)}
                        />
                        unopened
                      </label>
                    </div>
                    <div style={{ marginTop: 10 }}>
                      <PhotoPicker files={photos} onChange={setPhotos} />
                    </div>
                    <div className="row" style={{ marginTop: 10 }}>
                      <button onClick={() => submitReturn(o.id)} disabled={busy}>
                        {busy ? "Uploading…" : "Confirm return"}
                      </button>
                      <button className="secondary" onClick={() => setReturning(null)}>Cancel</button>
                    </div>
                  </div>
                )}
              </td>
            </tr>
          ))}
          {orders.length === 0 && (
            <tr><td colSpan={4} className="muted">No orders yet.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
