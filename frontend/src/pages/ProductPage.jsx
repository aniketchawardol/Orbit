import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";

export default function ProductPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const nav = useNavigate();
  const [p, setP] = useState(null);
  const [msg, setMsg] = useState("");

  const load = () => api.get(`/products/${id}`).then(setP);
  useEffect(() => { load(); }, [id]);

  const buy = async (listingId) => {
    if (!user) return nav("/login");
    setMsg("");
    try {
      await api.post("/orders/place", { listing_id: listingId });
      setMsg("Order placed! Check Orders tab.");
      load();
    } catch (e) {
      setMsg(e.message);
    }
  };

  if (!p) return <div className="page muted">Loading…</div>;

  const newListings = p.listings.filter((l) => l.source === "NEW");
  const preLoved = p.listings.filter((l) => l.source !== "NEW");

  return (
    <div className="page">
      <div className="row" style={{ alignItems: "flex-start", gap: 20 }}>
        {p.image_url && (
          <img
            src={p.image_url}
            alt={p.title}
            style={{ width: 220, height: 220, objectFit: "cover", borderRadius: 12 }}
          />
        )}
        <div>
          <span className="badge">{p.category}</span>
          <h2>{p.title}</h2>
          <p className="muted">{p.description}</p>
        </div>
      </div>

      <h3>Buy new</h3>
      {newListings.length === 0 && <div className="muted">Out of stock.</div>}
      <div className="grid">
        {newListings.map((l) => (
          <div className="card" key={l.id}>
            <div className="price">₹{l.price}</div>
            <button onClick={() => buy(l.id)} style={{ marginTop: 8 }}>Buy</button>
          </div>
        ))}
      </div>

      <h3 style={{ marginTop: 28 }}>
        Pre-loved <span className="muted">(graded &amp; verified by Loop)</span>
      </h3>
      {preLoved.length === 0 && <div className="muted">No pre-loved offers right now.</div>}
      <div className="grid">
        {preLoved.map((l) => (
          <div className="card" key={l.id}>
            <div>
              <span className={`badge grade-${l.grade}`}>Grade {l.grade ?? "?"}</span>
              <span className="badge src">{l.source.replaceAll("_", " ")}</span>
              {l.untouched && <span className="badge">UNOPENED</span>}
            </div>
            {l.photo_urls?.length > 0 && (
              <div className="row" style={{ marginTop: 8, gap: 6 }}>
                {l.photo_urls.slice(0, 3).map((ph) => (
                  <img
                    key={ph}
                    src={ph}
                    alt="condition"
                    style={{ width: 56, height: 56, objectFit: "cover", borderRadius: 6 }}
                  />
                ))}
              </div>
            )}
            <div style={{ marginTop: 6 }}>
              <span className="price">₹{l.price}</span>
              <span className="mrp">₹{p.mrp}</span>
            </div>
            <div className="row" style={{ marginTop: 8 }}>
              <button onClick={() => buy(l.id)}>Buy</button>
              <Link to={`/unit/${l.unit_id}`} className="muted">Health Card →</Link>
            </div>
          </div>
        ))}
      </div>

      {msg && <div className="success">{msg}</div>}
    </div>
  );
}
