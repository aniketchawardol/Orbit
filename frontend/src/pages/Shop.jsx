import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";

export default function Shop() {
  const [products, setProducts] = useState([]);
  const [q, setQ] = useState("");

  useEffect(() => {
    const t = setTimeout(() => {
      api.get(`/products${q ? `?q=${encodeURIComponent(q)}` : ""}`).then(setProducts);
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  return (
    <div className="page">
      <div className="row" style={{ marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>Shop</h2>
        <input
          style={{ maxWidth: 320 }}
          className="right"
          placeholder="Search products…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>
      <div className="grid">
        {products.map((p) => (
          <Link key={p.id} to={`/p/${p.id}`} className="card">
            {p.image_url && (
              <img
                src={p.image_url}
                alt={p.title}
                style={{ width: "100%", height: 130, objectFit: "cover", borderRadius: 8, marginBottom: 8 }}
              />
            )}
            <span className="badge">{p.category}</span>
            <h3>{p.title}</h3>
            <div>
              <span className="price">₹{p.mrp}</span>
            </div>
            <div className="muted">by {p.seller_name}</div>
          </Link>
        ))}
        {products.length === 0 && <div className="muted">No products found.</div>}
      </div>
    </div>
  );
}
