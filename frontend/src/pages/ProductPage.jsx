import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { useToast } from "../components/Toast";
import { useTilt } from "../lib/motion";
import ProductCarousel from "../components/ProductCarousel";
import ConfirmModal from "../components/ConfirmModal";
import {
  ShieldCheck,
  Sparkles,
  Package,
  Activity,
  ShoppingCart,
  CheckCircle,
} from "../components/icons";

export default function ProductPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const { reload } = useAuth();
  const nav = useNavigate();
  const [p, setP] = useState(null);
  const [related, setRelated] = useState([]);
  // Return prevention: personalized size guidance + size selection.
  const [fitGuide, setFitGuide] = useState(null);
  const [selectedSize, setSelectedSize] = useState("");
  // Pending order awaiting "Buy anyway" confirmation (size/compatibility warning).
  const [pendingBuy, setPendingBuy] = useState(null);
  const { push } = useToast();
  const tilt = useTilt(5);

  const load = () => api.get(`/products/${id}`).then(setP);
  useEffect(() => {
    load();
    // load same-category products for the carousel
    api
      .get(`/products/${id}/related`)
      .then((res) => setRelated(res || []))
      .catch(() => setRelated([]));
  }, [id]);

  // Personalized size guide (apparel/footwear) — also warms the accessory
  // compatibility cache server-side. Requires auth, so only fetch when logged in.
  useEffect(() => {
    setFitGuide(null);
    setSelectedSize("");
    if (!user) return;
    api
      .get(`/products/${id}/fitguide`)
      .then((res) => {
        if (!res || !res.sized) return;
        setFitGuide(res);
        if (res.recommended_size) setSelectedSize(res.recommended_size);
      })
      .catch(() => {});
  }, [id, user]);

  // Core order placement; `ack` skips the warning gate on the second attempt.
  const placeOrder = async (listingId, ack) => {
    const prevBal = user?.green_credits?.balance || 0;
    await api.post("/orders/place", {
      listing_id: listingId,
      chosen_size: selectedSize,
      ack,
    });
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
  };

  const buy = async (listingId) => {
    if (!user) return nav("/login");
    if (fitGuide?.sized && !selectedSize) {
      push(`Please select a ${fitGuide.size_label || "size"} first`, "error");
      return;
    }
    try {
      await placeOrder(listingId, false);
    } catch (e) {
      // 409: backend flagged a wrong size or incompatible accessory.
      if (e.status === 409 && e.data?.warnings?.length) {
        setPendingBuy({
          listingId,
          warnings: e.data.warnings.map((w) => w.message),
          recommended: e.data.recommended_size || "",
        });
        return;
      }
      push(e.message || "Order failed", "error");
    }
  };

  const confirmBuy = async () => {
    if (!pendingBuy) return;
    const { listingId } = pendingBuy;
    setPendingBuy(null);
    try {
      await placeOrder(listingId, true);
    } catch (e) {
      push(e.message || "Order failed", "error");
    }
  };

  if (!p) return <div className="page muted">Loading…</div>;

  const newListings = p.listings.filter((l) => l.source === "NEW");
  const preLoved = p.listings.filter((l) => l.source !== "NEW");

  return (
    <div className="page">
      <div
        className="row enter"
        style={{ alignItems: "stretch", gap: 24, marginBottom: 8 }}
      >
        <div
          ref={tilt.ref}
          {...tilt.bind}
          className="media-card"
          style={{
            width: 320,
            maxWidth: "100%",
            aspectRatio: "1 / 1",
            flex: "0 0 auto",
          }}
        >
          {p.image_url ? (
            <img className="media-img" src={p.image_url} alt={p.title} />
          ) : (
            <div className="media-fallback">
              <Package size={56} />
            </div>
          )}
        </div>

        <div className="glass" style={{ flex: 1, minWidth: 260, padding: 20 }}>
          <span className="badge">{p.category}</span>
          <h2 style={{ marginTop: 8 }}>{p.title}</h2>
          <p className="muted">{p.description}</p>
          {p.attributes && Object.keys(p.attributes).length > 0 && (
            <div style={{ marginTop: 14 }}>
              <strong style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <Package size={15} /> Specifications
              </strong>
              <dl className="spec-list">
                {Object.entries(p.attributes).map(([k, v]) => (
                  <div className="spec-row" key={k}>
                    <dt>{k.replaceAll("_", " ")}</dt>
                    <dd>{String(v)}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}
          {fitGuide?.sized && (
            <div className="size-picker" style={{ marginTop: 14 }}>
              <strong
                style={{ display: "flex", alignItems: "center", gap: 6 }}
              >
                <Package size={15} /> Select {fitGuide.size_label || "size"}
              </strong>
              <div className="size-options">
                {fitGuide.size_options.map((s) => (
                  <button
                    key={s}
                    type="button"
                    className={
                      "size-pill" +
                      (selectedSize === s ? " selected" : "") +
                      (fitGuide.recommended_size === s ? " recommended" : "")
                    }
                    onClick={() => setSelectedSize(s)}
                    aria-pressed={selectedSize === s}
                  >
                    {s}
                  </button>
                ))}
              </div>
              {fitGuide.message && fitGuide.recommended_size && (
                <div
                  className="disposition"
                  style={{
                    marginTop: 12,
                    display: "flex",
                    alignItems: "flex-start",
                    gap: 8,
                  }}
                >
                  <Sparkles
                    size={16}
                    style={{
                      flexShrink: 0,
                      marginTop: 2,
                      color: "var(--brand-orange-deep)",
                    }}
                  />
                  <div>
                    <strong>{fitGuide.message}</strong>
                    <span className="muted"> — based on your size profile.</span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="product-lower">
        <div className="product-listings">
          <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <ShoppingCart size={18} /> Buy new
          </h3>
          {newListings.length === 0 && (
            <div className="muted">Out of stock.</div>
          )}
          {newListings.length > 0 && (
            <div className="grid preloved-grid stagger">
              {/* NEW units are fungible — show a single card and buy any one. */}
              <div className="card preloved-buy buynew">
                <div className="preloved-info">
                  <div className="price">₹{newListings[0].price}</div>
                  <div className="muted" style={{ marginTop: 4 }}>
                    {newListings.length} in stock
                  </div>
                </div>
                <div className="preloved-actions">
                  <button
                    className="buy"
                    onClick={() => buy(newListings[0].id)}
                    aria-label="Buy this item"
                  >
                    <ShoppingCart size={16} /> Buy
                  </button>
                </div>
              </div>
            </div>
          )}

          <h3
            style={{
              marginTop: 28,
              display: "flex",
              alignItems: "center",
              gap: 8,
            }}
          >
            <ShieldCheck size={18} style={{ color: "var(--success)" }} />{" "}
            Pre-loved
            <span
              className="muted"
              style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
            >
              (graded &amp; verified by
              <img
                src="/logo.png"
                alt="Orbit"
                style={{ height: 14, verticalAlign: "middle" }}
              />
              Orbit)
            </span>
          </h3>
          {preLoved.length === 0 && (
            <div className="muted">No pre-loved offers right now.</div>
          )}
          <div className="grid preloved-grid stagger">
            {preLoved.map((l) => (
              <div className="card no-hover preloved-buy" key={l.id}>
                <div className="preloved-info">
                  <div className="row" style={{ gap: 4 }}>
                    <span className={`badge grade-${l.grade}`}>
                      Grade {l.grade ?? "?"}
                    </span>
                    <span className="badge src">
                      {l.source.replaceAll("_", " ")}
                    </span>
                    {l.untouched && (
                      <span className="badge success">
                        <CheckCircle size={12} /> UNOPENED
                      </span>
                    )}
                  </div>
                  {l.photo_urls?.length > 0 && (
                    <div className="row" style={{ marginTop: 10, gap: 6 }}>
                      {l.photo_urls.slice(0, 3).map((ph) => (
                        <img
                          key={ph}
                          src={ph}
                          alt="condition"
                          className="photo-tile"
                        />
                      ))}
                    </div>
                  )}
                  <div style={{ marginTop: 10 }}>
                    <span className="price">₹{l.price}</span>
                    <span className="mrp">₹{p.mrp}</span>
                  </div>
                </div>
                <div className="preloved-actions">
                  <button
                    className="buy"
                    onClick={() => buy(l.id)}
                    aria-label="Buy this item"
                  >
                    <ShoppingCart size={16} /> Buy
                  </button>
                  <Link
                    to={`/unit/${l.unit_id}`}
                    className="button green"
                    aria-label="View Health Card"
                  >
                    <Activity size={16} /> View Health Card
                  </Link>
                </div>
              </div>
            ))}
          </div>
        </div>

        {related.length > 0 && (
          <aside className="product-aside">
            <ProductCarousel
              items={related}
              title={
                <span
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 8,
                  }}
                >
                  <Package size={16} /> More in {p.category}
                </span>
              }
            />
          </aside>
        )}
      </div>

      <ConfirmModal
        open={!!pendingBuy}
        warnings={pendingBuy?.warnings || []}
        recommended={pendingBuy?.recommended}
        onCancel={() => setPendingBuy(null)}
        onConfirm={confirmBuy}
      />
    </div>
  );
}
