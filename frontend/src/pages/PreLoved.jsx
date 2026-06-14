import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { useToast } from "../components/Toast";
import { Link } from "react-router-dom";
import { useCountUp } from "../lib/motion";
import {
  Activity,
  ShoppingCart,
  Package,
  Recycle,
  Sprout,
  Sparkles,
} from "../components/icons";

export default function PreLoved() {
  const [items, setItems] = useState([]);
  const { user, reload } = useAuth();
  const { push } = useToast();
  const [loading, setLoading] = useState(true);
  const timer = useRef(null);

  const load = (showSpinner = false) => {
    if (showSpinner) setLoading(true);
    return api
      .get("/listings/preloved")
      .then((res) => setItems(res))
      .catch(() => {})
      .finally(() => showSpinner && setLoading(false));
  };

  useEffect(() => {
    load(true);
    // Poll so the descending price + growing green reward stay live while the
    // page is open (the worker advances each auction on its own timer).
    timer.current = setInterval(() => load(false), 3000);
    return () => clearInterval(timer.current);
  }, []);

  const buy = async (auctionId) => {
    if (!user) return window.location.assign("/login");
    try {
      const r = await api.post(`/nextowner/auctions/${auctionId}/buy`);
      push(`Bought ₹${r.price} · +${r.green_credits} green credits`, "success");
      reload?.();
      load(false);
    } catch (e) {
      // 409 → already sold / you own it. Refetch so the card updates.
      push(e.message || "Already sold", "error");
      load(false);
    }
  };

  // Recommended items get their own rail; exclude them from the "all items"
  // grid below so the same auction never shows up twice.
  const recommended = items.filter((a) => a.recommended);
  const others = items.filter((a) => !a.recommended);

  return (
    <div className="page">
      <h2 style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span className="brand-hero" style={{ padding: 4 }}>
          <img src="/logo.png" alt="Orbit" style={{ height: 22 }} />
        </span>
        Pre-Loved Shop
      </h2>

      {/* Recommended-for-you rail: auctions where the matching engine has alerted
          the current buyer. Hidden when logged out or nothing matches. */}
      {!loading && recommended.length > 0 && (
        <section style={{ marginBottom: 28 }}>
          <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Sparkles size={18} /> Recommended for you
          </h3>
          <p className="muted" style={{ marginTop: 0 }}>
            Matched to your taste and budget
          </p>
          <div className="grid stagger">
            {recommended.map((a) => (
              <AuctionCard
                key={a.id}
                a={a}
                you={user?.username}
                recommended
                onBuy={buy}
              />
            ))}
          </div>
        </section>
      )}

      {!loading && items.length === 0 ? (
        <div className="empty">
          <span className="medallion">
            <Recycle size={28} />
          </span>
          <div>No pre-loved listings yet — check back soon.</div>
        </div>
      ) : loading ? (
        <div className="grid stagger">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="media-card skel">
              <div className="media-img skeleton" />
              <div className="panel">
                <div className="line skeleton" />
                <div className="line short skeleton" />
              </div>
            </div>
          ))}
        </div>
      ) : (
        others.length > 0 && (
          <>
            {recommended.length > 0 && (
              <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Recycle size={18} /> All pre-loved items
              </h3>
            )}
            <div className="grid stagger">
              {others.map((a) => (
                <AuctionCard
                  key={a.id}
                  a={a}
                  you={user?.username}
                  onBuy={buy}
                />
              ))}
            </div>
          </>
        )
      )}
    </div>
  );
}

function AuctionCard({ a, you, recommended = false, onBuy }) {
  const done = a.status === "SOLD" || a.status === "EXPIRED";
  const src =
    a.photo_urls?.[0] || a.product.image_url || a.product.thumbnail_url;
  const price = useCountUp(a.current_price);
  const green = a.green_credits ?? 0;
  const save = a.product.mrp
    ? Math.round(100 - (a.current_price * 100) / a.product.mrp)
    : 0;
  const mineToSell = a.seller_name && a.seller_name === you;

  return (
    <div className="media-card sheen" style={{ opacity: done ? 0.65 : 1 }}>
      <Link
        to={`/p/${a.product.id}`}
        style={{ position: "absolute", inset: 0, zIndex: 1 }}
        aria-label={a.product.title}
      />
      {src ? (
        <img
          className="media-img"
          src={src}
          alt={a.product.title}
          loading="lazy"
        />
      ) : (
        <div className="media-fallback">
          <Package size={48} />
        </div>
      )}

      <div className="corner left">
        {a.grade && (
          <span className={`badge grade-${a.grade} float`}>
            Grade {a.grade}
          </span>
        )}
        {recommended && (
          <span className="badge success float">
            <Sparkles size={12} /> For you
          </span>
        )}
        {!done && save > 0 && (
          <span className="badge success float">Save {save}%</span>
        )}
        {a.status === "SOLD" && (
          <span className="badge success float">Sold</span>
        )}
        {a.status === "EXPIRED" && <span className="badge float">Expired</span>}
      </div>

      <div className="panel" style={{ zIndex: 2 }}>
        <h3>{a.product.title}</h3>
        <div
          className="row"
          style={{
            gap: 8,
            justifyContent: "space-between",
            alignItems: "baseline",
          }}
        >
          <span>
            <span className="price">₹{price}</span>
            {a.product.mrp > a.current_price && (
              <span className="mrp">₹{a.product.mrp}</span>
            )}
          </span>
          {!done && green > 0 && (
            <span className="badge success" style={{ margin: 0 }}>
              <Sprout size={13} /> +{green} green
            </span>
          )}
        </div>

        {!done && (
          <div className="card-actions" style={{ marginTop: 10 }}>
            <button
              className="buy"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onBuy(a.id);
              }}
              disabled={mineToSell}
              title={mineToSell ? "You're selling this item" : undefined}
            >
              <ShoppingCart size={15} /> Buy ₹{a.current_price}
            </button>
            <a
              className="button green"
              href={`/unit/${a.unit_id}`}
              onClick={(e) => e.stopPropagation()}
            >
              <Activity size={15} /> Health
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
