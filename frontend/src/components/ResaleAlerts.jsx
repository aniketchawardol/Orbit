import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { useToast } from "./Toast";
import { Sprout, ShoppingCart, Package } from "./icons";

/**
 * Buyer-facing resale alerts. Polls `GET /nextowner/alerts` every ~5s and lists
 * incoming resale offers (already sorted best-fit first by the backend). Renders
 * nothing when there are no alerts, so it's safe to drop anywhere — e.g. the Shop
 * home or near the nav credits chip.
 */
export default function ResaleAlerts() {
  const { reload } = useAuth();
  const { push } = useToast();
  const [alerts, setAlerts] = useState([]);

  const load = () =>
    api
      .get("/nextowner/alerts")
      .then(setAlerts)
      .catch(() => {});

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  const buy = async (auctionId) => {
    try {
      const r = await api.post(`/nextowner/auctions/${auctionId}/buy`);
      push(`Bought ₹${r.price} · +${r.green_credits} green credits`, "success");
      reload?.();
      load();
    } catch (e) {
      // 409 → already sold / you own it. Refetch so the list updates.
      push(e.message || "Already sold", "error");
      load();
    }
  };

  if (!alerts.length) return null;

  return (
    <div className="card" style={{ padding: 14, marginBottom: 18 }}>
      <h3
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginTop: 0,
        }}
      >
        <Sprout size={16} /> Resale matches for you
      </h3>
      {alerts.map(({ match, auction, current_price, green_credit_bonus }) => (
        <div
          key={match.id}
          className="row"
          style={{
            justifyContent: "space-between",
            alignItems: "center",
            padding: "8px 0",
            borderTop: "1px solid var(--glass-stroke)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            {auction.photo_urls?.[0] ? (
              <img
                src={auction.photo_urls[0]}
                alt=""
                style={{
                  width: 42,
                  height: 42,
                  borderRadius: 8,
                  objectFit: "cover",
                }}
              />
            ) : (
              <span
                style={{
                  width: 42,
                  height: 42,
                  borderRadius: 8,
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  background: "var(--surface-2)",
                  color: "var(--text-muted)",
                }}
              >
                <Package size={18} />
              </span>
            )}
            <div>
              <div style={{ fontWeight: 600 }}>{auction.product.title}</div>
              <div className="muted" style={{ fontSize: 12 }}>
                <span className="price" style={{ fontSize: 14 }}>
                  ₹{current_price}
                </span>
                {" · "}
                <span className="badge success" style={{ margin: 0 }}>
                  +{auction.green_credits ?? green_credit_bonus} green
                </span>
                {" · "}
                {Math.round(match.score * 100)}% match
              </div>
            </div>
          </div>
          <button className="buy" onClick={() => buy(auction.id)}>
            <ShoppingCart size={15} /> Buy
          </button>
        </div>
      ))}
    </div>
  );
}
