import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import PhotoPicker from "../components/PhotoPicker";
import { useToast } from "../components/Toast";

const REASONS = [
  ["DIDNT_MATCH", "Didn't match description"],
  ["WRONG_SIZE", "Wrong size / fit"],
  ["CHANGED_MIND", "Changed my mind"],
  ["DEFECTIVE", "Damaged / defective"],
  ["OTHER", "Other"],
];

export default function Orders() {
  const [orders, setOrders] = useState([]);
  const [returning, setReturning] = useState(null); // order id
  const [reason, setReason] = useState("CHANGED_MIND");
  const [untouchedClaim, setUntouchedClaim] = useState(false);
  const [photos, setPhotos] = useState([]);
  const [photoMetas, setPhotoMetas] = useState([]);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const { push } = useToast();
  const navigate = useNavigate();

  const load = () => api.get("/orders").then(setOrders);
  useEffect(() => {
    load();
  }, []);

  const advance = async (id) => {
    try {
      await api.post(`/orders/${id}/advance`);
      load();
      push("Order advanced", "success");
    } catch (e) {
      push(e.message || "Action failed", "error");
    }
  };

  const startReturn = (id) => {
    setReturning(id);
    setPhotos([]);
    setPhotoMetas([]);
    setComment("");
    setUntouchedClaim(false);
    setReason("CHANGED_MIND");
  };

  const submitReturn = async (id) => {
    setMsg("");
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("reason", reason);
      fd.append("claimed_untouched", untouchedClaim ? "true" : "false");
      if (comment.trim()) fd.append("comment", comment.trim());
      photos.forEach((f) => fd.append("photos", f));
      fd.append("metadata", JSON.stringify(photoMetas));
      await api.postForm(`/orders/${id}/return`, fd);
      setReturning(null);
      setPhotos([]);
      setPhotoMetas([]);
      setComment("");
      load();
      push("Return scheduled", "success");
    } catch (e) {
      push(e.message || "Return failed", "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <h2>My orders</h2>
      {/* toasts handled globally */}
      <table>
        <thead>
          <tr>
            <th>Item</th>
            <th>Price</th>
            <th>State</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {orders.map((o) => (
            <tr key={o.id}>
              <td>{o.listing.product.title}</td>
              <td>₹{o.listing.price}</td>
              <td>
                <span className="badge">{o.state}</span>
              </td>
              <td>
                {o.state === "PLACED" && (
                  <button className="secondary" onClick={() => advance(o.id)}>
                    Mark delivered (demo)
                  </button>
                )}
                {o.state === "DELIVERED" &&
                  returning !== o.id &&
                  o.return_eligible && (
                    <button
                      className="secondary"
                      onClick={() => startReturn(o.id)}
                    >
                      Return
                    </button>
                  )}
                {o.state === "DELIVERED" &&
                  returning !== o.id &&
                  !o.return_eligible && (
                    <div
                      className="row"
                      style={{ gap: 8, alignItems: "center", margin: 0 }}
                    >
                      <span className="muted">Return window closed</span>
                      <button
                        className="secondary"
                        onClick={() => navigate("/resell")}
                      >
                        Resell instead
                      </button>
                    </div>
                  )}
                {returning === o.id && (
                  <div className="card" style={{ padding: 12 }}>
                    <div className="row">
                      <select
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                        style={{ maxWidth: 220 }}
                      >
                        {REASONS.map(([v, label]) => (
                          <option key={v} value={v}>
                            {label}
                          </option>
                        ))}
                      </select>
                      <label className="row" style={{ margin: 0 }}>
                        <input
                          type="checkbox"
                          style={{ width: "auto" }}
                          checked={untouchedClaim}
                          onChange={(e) => setUntouchedClaim(e.target.checked)}
                        />
                        unopened
                      </label>
                    </div>
                    <textarea
                      placeholder="Add a comment (optional) — describe the issue"
                      value={comment}
                      onChange={(e) => setComment(e.target.value)}
                      rows={2}
                      style={{ marginTop: 8, width: "100%" }}
                    />
                    <div style={{ marginTop: 10 }}>
                      <PhotoPicker
                        files={photos}
                        onChange={setPhotos}
                        onMetadata={setPhotoMetas}
                      />
                    </div>
                    <div className="row" style={{ marginTop: 10 }}>
                      <button
                        onClick={() => submitReturn(o.id)}
                        disabled={busy}
                      >
                        {busy ? "Uploading…" : "Confirm return"}
                      </button>
                      <button
                        className="secondary"
                        onClick={() => setReturning(null)}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </td>
            </tr>
          ))}
          {orders.length === 0 && (
            <tr>
              <td colSpan={4} className="muted">
                No orders yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
