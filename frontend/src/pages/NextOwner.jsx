import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { useToast } from "../components/Toast";
import { useCountUp } from "../lib/motion";
import {
  Sparkles,
  Package,
  ShoppingCart,
  Sprout,
  Star,
} from "../components/icons";

// Green-credit bonus derived from the live price. The API already includes the
// authoritative value on each alert/edge — this is only for optimistic UI on the
// demo grid between polls. MAX_BONUS = 40 on the backend.
const MAX_BONUS = 40;
const bonusAt = (a) =>
  a.ceiling > a.floor
    ? Math.round(
        ((a.ceiling - a.current_price) / (a.ceiling - a.floor)) * MAX_BONUS,
      )
    : 0;

const isLive = (a) => a.status === "ACTIVE";

export default function NextOwner() {
  const { user, reload } = useAuth();
  const { push } = useToast();
  const [cards, setCards] = useState([]);
  const [matching, setMatching] = useState(false);
  const [loading, setLoading] = useState(true);
  const timer = useRef(null);

  // Pull the freshest results (cards + top buyers + live price). Used after a
  // buy / advance and as the polling tick once matching has started.
  const refresh = () =>
    api
      .get("/nextowner/demo/results")
      .then(setCards)
      .catch(() => {});

  useEffect(() => {
    api
      .get("/nextowner/demo/products")
      .then(setCards)
      .catch(() => {})
      .finally(() => setLoading(false));
    return () => clearInterval(timer.current);
  }, []);

  async function startMatching() {
    setMatching(true);
    try {
      // Kick off the parallel embed + bipartite match on the backend.
      await api.post("/nextowner/demo/match", {});
      clearInterval(timer.current);
      // Poll the results grid; stop once nothing is ACTIVE anymore.
      timer.current = setInterval(async () => {
        try {
          const res = await api.get("/nextowner/demo/results");
          setCards(res);
          if (!res.some(isLive)) {
            clearInterval(timer.current);
            setMatching(false);
          }
        } catch {
          /* keep polling on transient errors */
        }
      }, 3000);
    } catch (e) {
      push(e.message || "Matching failed", "error");
      setMatching(false);
    }
  }

  async function buy(a) {
    try {
      const r = await api.post(`/nextowner/auctions/${a.id}/buy`);
      push(`Bought ₹${r.price} · +${r.green_credits} green credits`, "success");
      reload?.();
      refresh();
    } catch (e) {
      // 409 → already sold / you own it. Refetch so the card updates.
      push(e.message || "Already sold", "error");
      refresh();
    }
  }

  // Demo-only manual price step. In production the Celery worker advances the
  // Dutch auction on its own timer — this just lets you watch a drop live.
  async function advance(a) {
    try {
      await api.post(`/nextowner/auctions/${a.id}/step`);
      refresh();
    } catch {
      /* ignore — auction may have just sold/expired */
    }
  }

  const liveCount = cards.filter(isLive).length;

  return (
    <div className="page">
      <div
        className="row"
        style={{ justifyContent: "space-between", alignItems: "center" }}
      >
        <h2
          style={{ display: "flex", alignItems: "center", gap: 8, margin: 0 }}
        >
          <Sparkles size={22} /> Find the Next Owner
        </h2>
        <button onClick={startMatching} disabled={matching || liveCount === 0}>
          <Sparkles size={16} /> {matching ? "Matching…" : "Start matching"}
        </button>
      </div>

      <p className="muted" style={{ maxWidth: 720 }}>
        We match every resale item to the shoppers who want it most and alert
        them first — and the green-credit reward keeps growing the longer an
        item waits for its next owner.
      </p>

      {loading ? (
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
      ) : cards.length === 0 ? (
        <div className="empty">
          <span className="medallion">
            <Package size={28} />
          </span>
          <div>No resale items yet — list one from the Resell page.</div>
        </div>
      ) : (
        <div className="grid stagger">
          {cards.map((a) => (
            <AuctionCard
              key={a.id}
              a={a}
              you={user?.username}
              onBuy={buy}
              onAdvance={advance}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function AuctionCard({ a, you, onBuy, onAdvance }) {
  const done = a.status === "SOLD" || a.status === "EXPIRED";
  const src = a.photo_urls?.[0];
  const bonus = bonusAt(a);
  const price = useCountUp(a.current_price);
  const mineToSell = a.seller_name && a.seller_name === you;

  return (
    <div className="media-card sheen" style={{ opacity: done ? 0.65 : 1 }}>
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
        <span className="badge src float">{a.product.origin}</span>
        {a.status === "SOLD" && (
          <span className="badge success float">Sold</span>
        )}
        {a.status === "EXPIRED" && <span className="badge float">Expired</span>}
      </div>

      <div className="panel">
        <h3>{a.product.title}</h3>

        {/* current_price is the price. The descending Dutch auction that produced
            it is a backend detail — we don't surface ceiling/floor/tier here. The
            growing green badge is the gamified hook. */}
        <div
          className="row"
          style={{ justifyContent: "space-between", alignItems: "baseline" }}
        >
          <span>
            <span className="price">₹{price}</span>
            {a.product.mrp > a.current_price && (
              <span className="mrp">₹{a.product.mrp}</span>
            )}
          </span>
          {!done && bonus > 0 && (
            <span className="badge success" style={{ margin: 0 }}>
              <Sprout size={13} /> +{bonus} green
            </span>
          )}
        </div>

        <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
          {a.n_matches} {a.n_matches === 1 ? "match" : "matches"}
          {a.status === "SOLD" && a.buyer_name
            ? ` · sold to ${a.buyer_name}`
            : ""}
        </div>

        {/* Top ranked buyers — alerted ones get a star. */}
        {a.edges?.length > 0 && (
          <div style={{ marginTop: 10 }}>
            <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>
              Top buyers
            </div>
            {a.edges.slice(0, 4).map((e) => (
              <div
                key={e.id}
                className="row"
                style={{
                  justifyContent: "space-between",
                  fontSize: 13,
                  padding: "2px 0",
                }}
              >
                <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  {e.alerted && (
                    <Star size={12} style={{ color: "var(--brand-orange)" }} />
                  )}
                  {e.username}
                </span>
                <span className="muted">
                  {Math.round(e.score * 100)}% · T{e.tier}
                </span>
              </div>
            ))}
          </div>
        )}

        {!done && (
          <div className="card-actions" style={{ marginTop: 12 }}>
            <button
              className="buy"
              onClick={() => onBuy(a)}
              disabled={mineToSell}
              title={mineToSell ? "You're selling this item" : undefined}
            >
              <ShoppingCart size={15} /> Buy ₹{a.current_price}
            </button>
            <button className="button green" onClick={() => onAdvance(a)}>
              Advance
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
