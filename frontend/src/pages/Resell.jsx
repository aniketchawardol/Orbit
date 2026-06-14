import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import PhotoPicker from "../components/PhotoPicker";
import { useToast } from "../components/Toast";
import { Recycle, Sparkles, Tag } from "../components/icons";

// Next Best Owner resale — list an item for the P2P matching engine. Two modes:
//   linked   → resell a past platform order (has a reference image for grading)
//   external → a brand-new item brought from outside (graded in quality mode)
function NextOwnerResell({ orders, onListed }) {
  const { push } = useToast();
  const [mode, setMode] = useState("linked"); // "linked" | "external"
  const [orderId, setOrderId] = useState("");
  const [form, setForm] = useState({
    title: "",
    category: "electronics",
    mrp: "",
    original_price: "",
    brand: "",
    age_months: "",
  });
  const [photos, setPhotos] = useState([]);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  async function submit() {
    if (!photos.length) return push("Add at least one photo", "error");
    if (mode === "linked" && !orderId)
      return push("Pick an order to resell", "error");
    setBusy(true);
    try {
      const fd = new FormData();
      photos.forEach((f) => fd.append("photos", f));
      if (mode === "linked") fd.append("order_id", orderId);
      else Object.entries(form).forEach(([k, v]) => v && fd.append(k, v));
      const res = await api.postForm("/nextowner/resell", fd);
      // async (worker): status PENDING → poll demo/results for the auction.
      // eager (dev): res.auction is already present.
      push(
        res.auction
          ? "Listed — auction is live!"
          : "Grading… we'll match buyers shortly",
        "success",
      );
      setPhotos([]);
      setOrderId("");
      onListed?.(res);
    } catch (e) {
      push(e.message || "Resell failed", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card" style={{ padding: 16 }}>
      <div className="row" style={{ gap: 8, marginBottom: 12 }}>
        <button
          className={mode === "linked" ? "" : "secondary"}
          onClick={() => setMode("linked")}
        >
          <Tag size={15} /> From a past order
        </button>
        <button
          className={mode === "external" ? "" : "secondary"}
          onClick={() => setMode("external")}
        >
          <Recycle size={15} /> Brand-new item
        </button>
      </div>

      {mode === "linked" ? (
        <select value={orderId} onChange={(e) => setOrderId(e.target.value)}>
          <option value="">Pick a delivered order…</option>
          {orders.map((o) => (
            <option key={o.id} value={o.id}>
              {o.listing.product.title} — ₹{o.listing.price}
            </option>
          ))}
        </select>
      ) : (
        <div style={{ display: "grid", gap: 8 }}>
          <input
            placeholder="Title"
            value={form.title}
            onChange={set("title")}
          />
          <input
            placeholder="Category (electronics, apparel…)"
            value={form.category}
            onChange={set("category")}
          />
          <input
            placeholder="MRP ₹"
            type="number"
            value={form.mrp}
            onChange={set("mrp")}
          />
          <input
            placeholder="Paid ₹ (original price)"
            type="number"
            value={form.original_price}
            onChange={set("original_price")}
          />
          <input
            placeholder="Brand (optional)"
            value={form.brand}
            onChange={set("brand")}
          />
          <input
            placeholder="Age in months (optional)"
            type="number"
            value={form.age_months}
            onChange={set("age_months")}
          />
        </div>
      )}

      <div className="muted" style={{ margin: "12px 0 6px" }}>
        Photos — the grader scores from these.
      </div>
      <PhotoPicker files={photos} onChange={setPhotos} />

      <div className="row" style={{ marginTop: 12 }}>
        <button onClick={submit} disabled={busy}>
          <Sparkles size={15} /> {busy ? "Grading…" : "Grade & find next owner"}
        </button>
      </div>
    </div>
  );
}

export default function Resell() {
  const { reload } = useAuth();
  const [orders, setOrders] = useState([]);
  const [auctions, setAuctions] = useState([]);

  const load = () => {
    api
      .get("/orders")
      .then((all) => setOrders(all.filter((o) => o.state === "DELIVERED")))
      .catch(() => {});
    // My resale auctions (Next Best Owner). Replaces the old /resale listings.
    api
      .get("/nextowner/resell")
      .then(setAuctions)
      .catch(() => {});
  };
  useEffect(() => {
    load();
  }, []);

  return (
    <div className="page">
      <h2 style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <Recycle size={22} /> Resell
      </h2>
      <p className="muted">
        One tap: Orbit grades it, prices it inside a fair band, lists it to the
        shoppers who want it most, and a courier picks it up. No strangers, no
        haggling.
      </p>

      <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <Sparkles size={16} /> Grade &amp; find next owner
      </h3>
      <p className="muted" style={{ marginTop: 0 }}>
        Hand it to the P2P matching engine — we grade it, open a price, and
        alert the shoppers who want it most. List a past order or a brand-new
        item.
      </p>
      <NextOwnerResell
        orders={orders}
        onListed={() => {
          reload?.();
          load();
        }}
      />

      <h3
        style={{ marginTop: 28, display: "flex", alignItems: "center", gap: 8 }}
      >
        <Tag size={16} /> My resale auctions
      </h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Item</th>
              <th>Grade</th>
              <th>Price</th>
              <th>Status</th>
              <th>Matches</th>
            </tr>
          </thead>
          <tbody>
            {auctions.map((a) => (
              <tr key={a.id}>
                <td>{a.product.title}</td>
                <td>
                  {a.grade ? (
                    <span className={`badge grade-${a.grade}`}>{a.grade}</span>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                <td>₹{a.current_price}</td>
                <td>
                  <span className="badge">{a.status}</span>
                  {a.status === "SOLD" && a.buyer_name && (
                    <div
                      className="muted"
                      style={{ fontSize: 11, marginTop: 4 }}
                    >
                      Sold to {a.buyer_name}
                    </div>
                  )}
                </td>
                <td className="muted">{a.n_matches}</td>
              </tr>
            ))}
            {auctions.length === 0 && (
              <tr>
                <td colSpan={5} className="muted">
                  No resale auctions yet — list one above.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
