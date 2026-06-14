import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { Package, Search } from "../components/icons";
import ResaleAlerts from "../components/ResaleAlerts";

function MediaCard({ p }) {
  const src =
    p.thumbnail_url ||
    (p.listings &&
      p.listings[0] &&
      p.listings[0].photo_urls &&
      p.listings[0].photo_urls[0]) ||
    p.image_url;
  return (
    <Link className="media-card sheen" to={`/p/${p.id}`}>
      {src ? (
        <img
          className="media-img"
          src={src}
          alt={p.title}
          loading="lazy"
          onError={(e) => {
            e.currentTarget.style.display = "none";
          }}
        />
      ) : (
        <div className="media-fallback">
          <Package size={48} />
        </div>
      )}
      {p.category && (
        <div className="corner left">
          <span className="badge float">{p.category}</span>
        </div>
      )}
      <div className="panel">
        <h3>{p.title}</h3>
        <div
          className="row"
          style={{ gap: 8, justifyContent: "space-between" }}
        >
          <span className="price">₹{p.mrp}</span>
          <span className="muted">by {p.seller_name}</span>
        </div>
      </div>
    </Link>
  );
}

export default function Shop() {
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") || "");

  useEffect(() => {
    setLoading(true);
    const t = setTimeout(() => {
      api
        .get(`/products${q ? `?q=${encodeURIComponent(q)}` : ""}`)
        .then((res) => setProducts(res.data || res))
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  const onSearch = (val) => {
    setQ(val);
    setParams(val ? { q: val } : {}, { replace: true });
  };

  return (
    <div className="page">
      <ResaleAlerts />
      <div className="row" style={{ marginBottom: 18 }}>
        <h2 style={{ margin: 0 }}>Shop</h2>
        <div className="nav-search right" style={{ maxWidth: 320 }}>
          <Search size={18} style={{ color: "var(--text-muted)" }} />
          <input
            placeholder="Search products…"
            value={q}
            onChange={(e) => onSearch(e.target.value)}
            style={{
              background: "transparent",
              border: "none",
              boxShadow: "none",
            }}
          />
        </div>
      </div>

      {!loading && products.length === 0 ? (
        <div className="empty">
          <span className="medallion">
            <Package size={28} />
          </span>
          <div>No products found{q ? ` for “${q}”` : ""}.</div>
        </div>
      ) : (
        <div className="grid stagger">
          {loading
            ? Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="media-card skel">
                  <div className="media-img skeleton" />
                  <div className="panel">
                    <div className="line skeleton" />
                    <div className="line short skeleton" />
                  </div>
                </div>
              ))
            : products.map((p) => <MediaCard key={p.id} p={p} />)}
        </div>
      )}
    </div>
  );
}
