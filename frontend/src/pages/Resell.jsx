import { useEffect, useState } from "react";
import { api } from "../api";
import PhotoPicker from "../components/PhotoPicker";

export default function Resell() {
  const [orders, setOrders] = useState([]);
  const [listings, setListings] = useState([]);
  const [selling, setSelling] = useState(null); // order id being photographed
  const [photos, setPhotos] = useState([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const load = () => {
    api.get("/orders").then((all) =>
      setOrders(all.filter((o) => o.state === "DELIVERED"))
    );
    api.get("/resale").then(setListings);
  };
  useEffect(() => { load(); }, []);

  const startResell = (orderId) => {
    setSelling(orderId);
    setPhotos([]);
    setMsg("");
  };

  const confirmResell = async (orderId) => {
    setMsg("");
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("order_id", orderId);
      photos.forEach((f) => fd.append("photos", f));
      const l = await api.postForm("/resale", fd);
      setMsg(`Listed at ₹${l.price} (Grade ${l.grade}). Zero effort — Loop handles the rest.`);
      setSelling(null);
      setPhotos([]);
      load();
    } catch (e) { setMsg(e.message); }
    finally { setBusy(false); }
  };

  return (
    <div className="page">
      <h2>Resell</h2>
      <p className="muted">
        One tap: Loop grades it, prices it inside a fair band, lists it, and a
        courier picks it up. No strangers, no haggling.
      </p>
      {msg && <div className="success">{msg}</div>}

      <h3>Eligible (delivered) orders</h3>
      <table>
        <thead><tr><th>Item</th><th>Paid</th><th /></tr></thead>
        <tbody>
          {orders.map((o) => (
            <tr key={o.id}>
              <td>{o.listing.product.title}</td>
              <td>₹{o.listing.price}</td>
              <td>
                {selling !== o.id ? (
                  <button onClick={() => startResell(o.id)}>Resell this</button>
                ) : (
                  <div className="card" style={{ padding: 12 }}>
                    <div className="muted" style={{ marginBottom: 8 }}>
                      Add a few photos — AI grades from these.
                    </div>
                    <PhotoPicker files={photos} onChange={setPhotos} />
                    <div className="row" style={{ marginTop: 10 }}>
                      <button onClick={() => confirmResell(o.id)} disabled={busy}>
                        {busy ? "Grading…" : "Grade & list it"}
                      </button>
                      <button className="secondary" onClick={() => setSelling(null)}>Cancel</button>
                    </div>
                  </div>
                )}
              </td>
            </tr>
          ))}
          {orders.length === 0 && (
            <tr><td colSpan={3} className="muted">Nothing delivered yet.</td></tr>
          )}
        </tbody>
      </table>

      <h3 style={{ marginTop: 28 }}>My resale listings</h3>
      <table>
        <thead><tr><th>Item</th><th>Grade</th><th>Price</th><th>Band</th><th>State</th></tr></thead>
        <tbody>
          {listings.map((l) => (
            <tr key={l.id}>
              <td>{l.product.title}</td>
              <td><span className={`badge grade-${l.grade}`}>{l.grade}</span></td>
              <td>₹{l.price}</td>
              <td className="muted">₹{l.band_lo}–₹{l.band_hi}</td>
              <td><span className="badge">{l.state}</span></td>
            </tr>
          ))}
          {listings.length === 0 && (
            <tr><td colSpan={5} className="muted">No resale listings yet.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
