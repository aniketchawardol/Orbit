import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { useToast } from "../components/Toast";

export default function ProductPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const { reload } = useAuth();
  const nav = useNavigate();
  const [p, setP] = useState(null);
  const [fitHint, setFitHint] = useState("");
  const { push } = useToast();

  const load = () => api.get(`/products/${id}`).then(setP);
  useEffect(() => {
    load();
    // load fit-check hint
    api
      .get(`/products/${id}/fitcheck`)
      .then((res) => {
        if (res && res.hint) setFitHint(res.hint);
      })
      .catch(() => {});
  }, [id]);

  const buy = async (listingId) => {
    if (!user) return nav("/login");
    const prevBal = user?.green_credits?.balance || 0;
    try {
      await api.post("/orders/place", { listing_id: listingId });
      push("Order placed — check Orders tab", "success");
      load();
      // refresh auth payload to update green credits counter in header
      try {
        await reload();
      } catch (e) {
        /* ignore */
      }
      try {
        const me = await api.get("/auth/me");
        const newBal = me.user?.green_credits?.balance || 0;
        if (newBal > prevBal)
          push(`+${newBal - prevBal} green credits added`, "success");
      } catch (e) {}
    } catch (e) {
      push(e.message || "Order failed", "error");
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
            style={{
              width: 220,
              height: 220,
              objectFit: "cover",
              borderRadius: 12,
            }}
          />
        )}
        <div>
          <span className="badge">{p.category}</span>
          <h2>{p.title}</h2>
          <p className="muted">{p.description}</p>
          {fitHint && (
            <div
              style={{
                marginTop: 8,
                padding: 8,
                borderRadius: 6,
              }}
            >
              <strong>Fit hint:</strong> {fitHint}
            </div>
          )}
        </div>
      </div>

      <h3>Buy new</h3>
      {newListings.length === 0 && <div className="muted">Out of stock.</div>}
      <div className="grid">
        {newListings.map((l) => (
          <div className="card" key={l.id}>
            <div className="price">₹{l.price}</div>
            <button onClick={() => buy(l.id)} style={{ marginTop: 8 }}>
              Buy
            </button>
          </div>
        ))}
      </div>

      <h3 style={{ marginTop: 28 }}>
        Pre-loved{" "}
        <span className="muted">
          (graded &amp; verified by{" "}
          <img
            src="/logo.png"
            alt="Loop"
            style={{
              height: 14,
              verticalAlign: "middle",
              margin: "0 6px",
            }}
          />
          Loop)
        </span>
      </h3>
      {preLoved.length === 0 && (
        <div className="muted">No pre-loved offers right now.</div>
      )}
      <div className="grid">
        {preLoved.map((l) => (
          <div className="card no-hover" key={l.id}>
            <div>
              <span className={`badge grade-${l.grade}`}>
                Grade {l.grade ?? "?"}
              </span>
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
                    style={{
                      width: 56,
                      height: 56,
                      objectFit: "cover",
                      borderRadius: 6,
                    }}
                  />
                ))}
              </div>
            )}
            <div style={{ marginTop: 6 }}>
              <span className="price">₹{l.price}</span>
              <span className="mrp">₹{p.mrp}</span>
            </div>
            <div className="card-actions">
              <button onClick={() => buy(l.id)}>Buy</button>
              <Link to={`/unit/${l.unit_id}`} className="button green">
                Health Card
              </Link>
            </div>
          </div>
        ))}
      </div>

      {/* toasts handled globally */}
    </div>
  );
}
