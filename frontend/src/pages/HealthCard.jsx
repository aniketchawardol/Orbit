import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";

export default function HealthCard() {
  const { id } = useParams();
  const [unit, setUnit] = useState(null);

  useEffect(() => {
    api.get(`/units/${id}/healthcard`).then(setUnit);
  }, [id]);

  if (!unit) return <div className="page muted">Loading…</div>;

  return (
    <div className="page" style={{ maxWidth: 640 }}>
      <div className="card">
        <div className="row">
          <h2 style={{ margin: 0 }}>Product Health Card</h2>
          <span className="badge right" style={{ background: "#14532d", color: "#86efac" }}>
            ✓ Loop-verified
          </span>
        </div>
        <h3>{unit.product.title}</h3>
        <div>
          <span className={`badge grade-${unit.grade}`}>Grade {unit.grade ?? "?"}</span>
          {unit.untouched && <span className="badge">UNOPENED RETURN</span>}
          <span className="badge">{unit.state}</span>
        </div>
        <p className="muted">
          Confidence: {unit.grade_confidence ?? "—"} · Est. value: ₹{unit.est_value ?? "—"} ·
          Storage cost so far: ₹{unit.storage_cost_accrued}
        </p>

        <h3>History</h3>
        <ul className="timeline">
          {unit.events.map((e) => (
            <li key={e.id}>
              <strong>{e.type}</strong>
              {e.actor_name && <span className="muted"> · {e.actor_name}</span>}
              <span className="muted"> · {new Date(e.created_at).toLocaleString()}</span>
            </li>
          ))}
          {unit.events.length === 0 && <li className="muted">No events recorded yet.</li>}
        </ul>
      </div>
    </div>
  );
}
