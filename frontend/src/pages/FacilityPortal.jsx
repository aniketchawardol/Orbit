import { useEffect, useState } from "react";
import { api } from "../api";
import { useToast } from "../components/Toast";

export default function FacilityPortal() {
  const [incoming, setIncoming] = useState([]);
  const [watchlist, setWatchlist] = useState([]);
  const [receivedRecommendation, setReceivedRecommendation] = useState(null);
  const [msg, setMsg] = useState("");
  const { push } = useToast();

  const load = () => {
    api.get("/facility/incoming").then(setIncoming);
    api.get("/facility/watchlist").then(setWatchlist);
  };
  useEffect(() => {
    load();
  }, []);

  const receive = async (unitId, untouched) => {
    setMsg("");
    try {
      const res = await api.post("/facility/receive", {
        unit_id: unitId,
        untouched,
      });
      // API returns the unit payload and routing_recommendation; show UI for confirmation
      if (res && res.routing_recommendation) {
        setReceivedRecommendation({
          unit: res,
          routing: res.routing_recommendation,
        });
      } else {
        load();
      }
    } catch (e) {
      push(e.message || "Receive failed", "error");
    }
  };

  const confirmRecommendation = async (unitId, rec) => {
    setMsg("");
    try {
      if (!rec) return;
      const action = rec.recommendation;
      if (action === "RESELL" || action === "REFURBISH" || action === "P2P") {
        await api.post(`/facility/units/${unitId}/relist`);
      } else if (action === "DONATE") {
        await api.post(`/facility/units/${unitId}/dispose`, {
          target: "DONATED",
        });
      } else if (action === "LIQUIDATE") {
        await api.post(`/facility/units/${unitId}/dispose`, {
          target: "LIQUIDATE",
        });
      }
      setReceivedRecommendation(null);
      load();
    } catch (e) {
      push(e.message || "Action failed", "error");
    }
  };

  const overrideRecommendation = async (unitId, choice) => {
    // choice: RESELL, REFURBISH, P2P, DONATE, LIQUIDATE
    setMsg("");
    try {
      if (choice === "RESELL" || choice === "REFURBISH" || choice === "P2P") {
        await api.post(`/facility/units/${unitId}/relist`);
      } else if (choice === "DONATE") {
        await api.post(`/facility/units/${unitId}/dispose`, {
          target: "DONATED",
        });
      } else if (choice === "LIQUIDATE") {
        await api.post(`/facility/units/${unitId}/dispose`, {
          target: "LIQUIDATE",
        });
      }
      setReceivedRecommendation(null);
      load();
    } catch (e) {
      push(e.message || "Action failed", "error");
    }
  };

  // New: relist / dispose handlers used by the watchlist actions
  const relist = async (unitId) => {
    setMsg("");
    try {
      await api.post(`/facility/units/${unitId}/relist`);
      load();
      push("Relisted", "success");
    } catch (e) {
      push(e.message || "Relist failed", "error");
    }
  };

  const dispose = async (unitId, target) => {
    setMsg("");
    try {
      await api.post(`/facility/units/${unitId}/dispose`, { target });
      load();
      push(target === "DONATED" ? "Donated" : "Liquidated", "success");
    } catch (e) {
      push(e.message || "Dispose failed", "error");
    }
  };

  const simulateDay = async () => {
    setMsg("");
    const s = await api.post("/facility/simulate-day");
    push(
      `+1 day: ${s.units_accrued} units accrued · ${s.price_stepdowns} price step-downs · ${s.liquidated} liquidated.`,
      "info",
    );
    load();
  };

  return (
    <div className="page">
      <div className="row">
        <h2 style={{ margin: 0 }}>Facility</h2>
        <button className="right" onClick={simulateDay}>
          Simulate one day
        </button>
      </div>
      {/* toasts handled globally */}

      <h3>Incoming returns</h3>
      {receivedRecommendation && (
        <div className="card" style={{ marginBottom: 12 }}>
          <div className="row" style={{ alignItems: "center", gap: 8 }}>
            <h4 style={{ margin: 0 }}>
              AI Recommendation: {receivedRecommendation.routing.recommendation}
            </h4>
            {receivedRecommendation.routing.decided_by && (
              <span className="badge src">
                {receivedRecommendation.routing.decided_by === "llm"
                  ? "LLM"
                  : "Expected value"}
              </span>
            )}
          </div>
          {receivedRecommendation.routing.confidence != null && (
            <div className="muted">
              Confidence:{" "}
              {Math.round(
                (receivedRecommendation.routing.confidence || 0) * 100,
              )}
              %
            </div>
          )}
          <p style={{ marginTop: 8 }}>
            {receivedRecommendation.routing.reasoning}
          </p>
          {receivedRecommendation.routing.alternatives?.length > 0 && (
            <div className="muted" style={{ marginBottom: 8 }}>
              Alternatives:{" "}
              {receivedRecommendation.routing.alternatives.map((alt) => (
                <span key={alt} className="badge" style={{ marginLeft: 4 }}>
                  {alt}
                </span>
              ))}
            </div>
          )}
          <div className="row" style={{ gap: 8 }}>
            <button
              onClick={() =>
                confirmRecommendation(
                  receivedRecommendation.unit.id,
                  receivedRecommendation.routing,
                )
              }
            >
              Confirm
            </button>
            <div>
              <select
                onChange={(e) =>
                  overrideRecommendation(
                    receivedRecommendation.unit.id,
                    e.target.value,
                  )
                }
                defaultValue=""
              >
                <option value="" disabled>
                  Override…
                </option>
                <option value="RESELL">Resell (relist)</option>
                <option value="REFURBISH">Refurbish</option>
                <option value="P2P">Peer-to-peer</option>
                <option value="DONATE">Donate</option>
                <option value="LIQUIDATE">Liquidate</option>
              </select>
            </div>
            <button
              className="secondary"
              onClick={() => {
                setReceivedRecommendation(null);
                load();
              }}
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      <table>
        <thead>
          <tr>
            <th>Item</th>
            <th>Claimed</th>
            <th>Receive as…</th>
          </tr>
        </thead>
        <tbody>
          {incoming.map((u) => (
            <tr key={u.id}>
              <td>{u.product.title}</td>
              <td className="muted">{u.untouched ? "unopened" : "—"}</td>
              <td className="row">
                <button onClick={() => receive(u.id, true)}>Unopened</button>
                <button
                  className="secondary"
                  onClick={() => receive(u.id, false)}
                >
                  Opened
                </button>
              </td>
            </tr>
          ))}
          {incoming.length === 0 && (
            <tr>
              <td colSpan={3} className="muted">
                No incoming returns.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <h3 style={{ marginTop: 32 }}>
        Storage watchlist{" "}
        <span className="muted">(closest to liquidation first)</span>
      </h3>
      <table>
        <thead>
          <tr>
            <th>Item</th>
            <th>State</th>
            <th>Grade</th>
            <th>Storage / value</th>
            <th>Ratio</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {watchlist.map((u) => (
            <tr key={u.id}>
              <td>{u.product.title}</td>
              <td>
                <span className="badge">{u.state}</span>
              </td>
              <td>
                <span className={`badge grade-${u.grade}`}>{u.grade}</span>
              </td>
              <td className="muted">
                ₹{u.storage_cost_accrued} / ₹{u.est_value}
              </td>
              <td>
                <div className="ratio-bar">
                  <div
                    className="ratio-fill"
                    style={{
                      width: `${Math.min(100, u.storage_ratio * 100)}%`,
                    }}
                  />
                </div>
              </td>
              <td className="row">
                {u.state === "AT_FACILITY" && (
                  <button onClick={() => relist(u.id)}>Relist</button>
                )}
                <button
                  className="secondary"
                  onClick={() => dispose(u.id, "DONATED")}
                >
                  Donate
                </button>
                <button
                  className="danger"
                  onClick={() => dispose(u.id, "LIQUIDATE")}
                >
                  Liquidate
                </button>
              </td>
            </tr>
          ))}
          {watchlist.length === 0 && (
            <tr>
              <td colSpan={6} className="muted">
                Floor is clear.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
