import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";
import {
  ShieldCheck,
  Sparkles,
  Activity,
  CheckCircle,
} from "../components/icons";

export default function HealthCard() {
  const { id } = useParams();
  const [unit, setUnit] = useState(null);

  useEffect(() => {
    api.get(`/units/${id}/healthcard`).then(setUnit);
  }, [id]);

  if (!unit) return <div className="page muted">Loading…</div>;

  const conf =
    unit.grade_confidence != null
      ? `${Math.round((unit.grade_confidence || 0) * 100)}%`
      : "—";

  return (
    <div className="page enter" style={{ maxWidth: 660 }}>
      <div className="glass" style={{ padding: 22 }}>
        <div className="row">
          <h2
            style={{
              margin: 0,
              display: "flex",
              alignItems: "center",
              gap: 10,
            }}
          >
            <span className="brand-hero" style={{ padding: 4 }}>
              <img src="/logo.png" alt="Orbit" style={{ height: 24 }} />
            </span>
            Product Health Card
          </h2>
          <span className="badge success right">
            <ShieldCheck size={13} /> Orbit-verified
          </span>
        </div>

        <h3 style={{ marginTop: 14 }}>{unit.product.title}</h3>
        <div className="row" style={{ gap: 4 }}>
          <span className={`badge grade-${unit.grade}`}>
            Grade {unit.grade ?? "?"}
          </span>
          {unit.untouched && (
            <span className="badge success">
              <CheckCircle size={12} /> UNOPENED RETURN
            </span>
          )}
          <span className="badge">{unit.state}</span>
        </div>

        {unit.current_price != null && (
          <div className="hc-price">
            <span className="hc-price-now">₹{unit.current_price}</span>
            {unit.product.mrp > unit.current_price && (
              <>
                <span className="hc-price-was">₹{unit.product.mrp}</span>
                <span className="hc-price-off">
                  {Math.round(
                    100 - (unit.current_price * 100) / unit.product.mrp,
                  )}
                  % off
                </span>
              </>
            )}
          </div>
        )}

        {unit.warranty_remaining && (
          <div className="hc-warranty">
            <ShieldCheck size={15} />
            <span>
              <strong>{unit.warranty_remaining}</strong> of warranty left
            </span>
          </div>
        )}

        <div className="stat-grid">
          <div className="stat-tile">
            <div className="v">{conf}</div>
            <div className="k">Grade confidence</div>
          </div>
          {unit.current_price == null && (
            <div className="stat-tile">
              <div className="v">₹{unit.est_value ?? "—"}</div>
              <div className="k">Estimated value</div>
            </div>
          )}
          <div className="stat-tile">
            <div className="v">₹{unit.storage_cost_accrued}</div>
            <div className="k">Storage cost so far</div>
          </div>
        </div>

        {unit.routing_recommendation && (
          <div className="disposition">
            <div className="row" style={{ alignItems: "center", gap: 8 }}>
              <h3
                style={{
                  margin: 0,
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                <Sparkles size={16} /> AI disposition:{" "}
                {unit.routing_recommendation.recommendation}
              </h3>
              {unit.routing_recommendation.decided_by && (
                <span className="badge src right">
                  {unit.routing_recommendation.decided_by === "llm"
                    ? "LLM"
                    : "Expected value"}
                </span>
              )}
            </div>
            {unit.routing_recommendation.confidence != null && (
              <div className="muted">
                Confidence:{" "}
                {Math.round(
                  (unit.routing_recommendation.confidence || 0) * 100,
                )}
                %
              </div>
            )}
            {unit.routing_recommendation.reasoning && (
              <p style={{ marginTop: 8, marginBottom: 8 }}>
                {unit.routing_recommendation.reasoning}
              </p>
            )}
            {unit.routing_recommendation.alternatives?.length > 0 && (
              <div className="muted">
                Alternatives:{" "}
                {unit.routing_recommendation.alternatives.map((alt) => (
                  <span key={alt} className="badge" style={{ marginLeft: 4 }}>
                    {alt}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        <h3
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginTop: 18,
          }}
        >
          <Activity size={18} /> History
        </h3>
        <ul className="timeline no-hover">
          {unit.events.map((e) => (
            <li key={e.id}>
              <strong>{e.type}</strong>
              {e.actor_name && <span className="muted"> · {e.actor_name}</span>}
              <span className="muted">
                {" "}
                · {new Date(e.created_at).toLocaleString()}
              </span>
            </li>
          ))}
          {unit.events.length === 0 && (
            <li className="muted">No events recorded yet.</li>
          )}
        </ul>
      </div>
    </div>
  );
}
