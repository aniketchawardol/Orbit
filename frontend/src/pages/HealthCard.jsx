import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";
import { FaCheck } from "react-icons/fa";

export default function HealthCard() {
  const { id } = useParams();
  const [unit, setUnit] = useState(null);

  useEffect(() => {
    api.get(`/units/${id}/healthcard`).then(setUnit);
  }, [id]);

  if (!unit) return <div className="page muted">Loading…</div>;

  return (
    <div className="page" style={{ maxWidth: 640 }}>
      <div className="card no-hover">
        <div className="row">
          <h2 style={{ margin: 0 }}>Product Health Card</h2>
          <span
            className="badge right"
            style={{ background: "#14532d", color: "#86efac" }}
          >
            <img
              src="/logo.png"
              alt="Loop"
              style={{
                height: 14,
                marginRight: 8,
                verticalAlign: "middle",
              }}
            />
            <FaCheck style={{ verticalAlign: "middle", marginRight: 8 }} />
            Loop-verified
          </span>
        </div>
        <h3>{unit.product.title}</h3>
        <div>
          <span className={`badge grade-${unit.grade}`}>
            Grade {unit.grade ?? "?"}
          </span>
          {unit.untouched && <span className="badge">UNOPENED RETURN</span>}
          <span className="badge">{unit.state}</span>
        </div>
        <p className="muted">
          Confidence: {unit.grade_confidence ?? "—"} · Est. value: ₹
          {unit.est_value ?? "—"} · Storage cost so far: ₹
          {unit.storage_cost_accrued}
        </p>

        {unit.routing_recommendation && (
          <div
            className="card no-hover"
            style={{ marginTop: 12, borderColor: "var(--accent2)" }}
          >
            <div className="row" style={{ alignItems: "center", gap: 8 }}>
              <h3 style={{ margin: 0 }}>
                AI disposition: {unit.routing_recommendation.recommendation}
              </h3>
              {unit.routing_recommendation.decided_by && (
                <span className="badge src">
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

        <h3>History</h3>
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
