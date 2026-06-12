import { useEffect, useRef, useState } from "react";
import { api } from "../api";

const EMPTY_PRODUCT = { title: "", category: "electronics", mrp: "", stock: 1, description: "" };

export default function SellerPortal() {
  const [inbox, setInbox] = useState([]);
  const [rules, setRules] = useState([]);
  const [myProducts, setMyProducts] = useState([]);
  const [form, setForm] = useState({ min_grade: "B", min_recovery_pct: 60, action: "AUTO_RELIST" });
  const [product, setProduct] = useState(EMPTY_PRODUCT);
  const [productImage, setProductImage] = useState(null);
  const [busy, setBusy] = useState(false);
  const imgInputRef = useRef(null);
  const [msg, setMsg] = useState("");

  const load = () => {
    api.get("/seller/returns").then(setInbox);
    api.get("/seller/rules").then(setRules);
    api.get("/seller/products").then(setMyProducts);
  };
  useEffect(() => { load(); }, []);

  const addProduct = async (e) => {
    e.preventDefault();
    setMsg("");
    setBusy(true);
    try {
      const fd = new FormData();
      Object.entries(product).forEach(([k, v]) => fd.append(k, v));
      if (productImage) fd.append("image", productImage);
      const created = await api.postForm("/seller/products", fd);
      setMsg(`"${created.title}" listed with ${created.stock_listed} unit(s).`);
      setProduct(EMPTY_PRODUCT);
      setProductImage(null);
      load();
    } catch (e2) { setMsg(e2.message); }
    finally { setBusy(false); }
  };

  const applyOne = async (unitId, action) => {
    setMsg("");
    try { await api.post("/seller/returns/apply", { unit_id: unitId, action }); load(); }
    catch (e) { setMsg(e.message); }
  };

  const bulk = async () => {
    setMsg("");
    try {
      const r = await api.post("/seller/returns/bulk");
      setMsg(`Rules handled ${r.handled} unit(s); ${r.remaining} left for review.`);
      load();
    } catch (e) { setMsg(e.message); }
  };

  const addRule = async (e) => {
    e.preventDefault();
    try { await api.post("/seller/rules", form); load(); }
    catch (e2) { setMsg(e2.message); }
  };

  const toggleRule = async (r) => {
    await api.patch(`/seller/rules/${r.id}`, { active: !r.active });
    load();
  };

  return (
    <div className="page">
      <h2>Sell a new product</h2>
      {msg && <div className="success">{msg}</div>}
      <form className="card" style={{ maxWidth: 720 }} onSubmit={addProduct}>
        <div className="row">
          <div style={{ flex: 2, minWidth: 220 }}>
            <label>Title</label>
            <input value={product.title} onChange={(e) => setProduct({ ...product, title: e.target.value })} />
          </div>
          <div>
            <label>Category</label>
            <select value={product.category} onChange={(e) => setProduct({ ...product, category: e.target.value })}>
              <option>electronics</option>
              <option>apparel</option>
              <option>footwear</option>
            </select>
          </div>
          <div style={{ maxWidth: 110 }}>
            <label>MRP ₹</label>
            <input type="number" min="1" value={product.mrp} onChange={(e) => setProduct({ ...product, mrp: e.target.value })} />
          </div>
          <div style={{ maxWidth: 90 }}>
            <label>Stock</label>
            <input type="number" min="1" max="50" value={product.stock} onChange={(e) => setProduct({ ...product, stock: e.target.value })} />
          </div>
        </div>
        <label>Description</label>
        <input value={product.description} onChange={(e) => setProduct({ ...product, description: e.target.value })} />
        <label>Product image</label>
        <div className="row">
          {productImage ? (
            <div style={{ position: "relative" }}>
              <img
                src={URL.createObjectURL(productImage)}
                alt="product"
                style={{ width: 80, height: 80, objectFit: "cover", borderRadius: 8 }}
              />
              <button
                type="button" className="danger"
                onClick={() => setProductImage(null)}
                style={{ position: "absolute", top: -6, right: -6, width: 20, height: 20, padding: 0, borderRadius: "50%", fontSize: 11, lineHeight: "20px" }}
              >×</button>
            </div>
          ) : (
            <button type="button" className="secondary" style={{ width: 80, height: 80, fontSize: 22 }}
              onClick={() => imgInputRef.current?.click()} title="Add image">🖼️</button>
          )}
          <input
            ref={imgInputRef} type="file" hidden
            accept="image/jpeg,image/png,image/webp"
            onChange={(e) => { setProductImage(e.target.files[0] || null); e.target.value = ""; }}
          />
          <span className="muted">jpg/png/webp, max 8 MB — shown on the shop page</span>
        </div>
        <button style={{ marginTop: 14 }} disabled={busy}>{busy ? "Publishing…" : "Publish product"}</button>
      </form>

      <h3 style={{ marginTop: 28 }}>My catalog</h3>
      <div className="grid">
        {myProducts.map((p) => (
          <div className="card" key={p.id}>
            {p.image_url && (
              <img src={p.image_url} alt={p.title}
                style={{ width: "100%", height: 110, objectFit: "cover", borderRadius: 8, marginBottom: 8 }} />
            )}
            <span className="badge">{p.category}</span>
            <h3>{p.title}</h3>
            <span className="price">₹{p.mrp}</span>
          </div>
        ))}
        {myProducts.length === 0 && <div className="muted">No products yet.</div>}
      </div>

      <div className="row" style={{ marginTop: 32 }}>
        <h2 style={{ margin: 0 }}>Returns inbox</h2>
        <button className="right" onClick={bulk}>Run rules on all</button>
      </div>
      <p className="muted">Units arrive pre-graded and pre-priced. Rules clear most of them without you.</p>

      <table>
        <thead>
          <tr><th>Item</th><th>Grade</th><th>Est. value</th><th>Recovery</th><th>Suggested</th><th>Actions</th></tr>
        </thead>
        <tbody>
          {inbox.map((u) => (
            <tr key={u.id}>
              <td>{u.product.title}{u.untouched && <span className="badge" style={{ marginLeft: 6 }}>UNOPENED</span>}</td>
              <td><span className={`badge grade-${u.grade}`}>{u.grade}</span></td>
              <td>₹{u.est_value}</td>
              <td className="muted">{u.est_value && u.product.mrp ? Math.round((u.est_value / u.product.mrp) * 100) : "?"}%</td>
              <td>{u.suggested_action ? <span className="badge src">{u.suggested_action}</span> : <span className="muted">—</span>}</td>
              <td className="row">
                <button className="secondary" onClick={() => applyOne(u.id, "AUTO_RELIST")}>Relist</button>
                <button className="secondary" onClick={() => applyOne(u.id, "DONATE")}>Donate</button>
                <button className="danger" onClick={() => applyOne(u.id, "LIQUIDATE")}>Liquidate</button>
              </td>
            </tr>
          ))}
          {inbox.length === 0 && (
            <tr><td colSpan={6} className="muted">Inbox zero — rules are doing their job.</td></tr>
          )}
        </tbody>
      </table>

      <h3 style={{ marginTop: 32 }}>Standing rules</h3>
      <table>
        <thead><tr><th>Rule</th><th>Action</th><th>Active</th></tr></thead>
        <tbody>
          {rules.map((r) => (
            <tr key={r.id}>
              <td>Grade ≥ {r.min_grade} AND recovery ≥ {r.min_recovery_pct}%</td>
              <td><span className="badge src">{r.action}</span></td>
              <td>
                <button className="secondary" onClick={() => toggleRule(r)}>
                  {r.active ? "Disable" : "Enable"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <form className="card" style={{ marginTop: 16, maxWidth: 560 }} onSubmit={addRule}>
        <div className="row">
          <div>
            <label>Min grade</label>
            <select value={form.min_grade} onChange={(e) => setForm({ ...form, min_grade: e.target.value })}>
              {["A", "B", "C", "D"].map((g) => <option key={g}>{g}</option>)}
            </select>
          </div>
          <div>
            <label>Min recovery %</label>
            <input
              type="number" min="0" max="100"
              value={form.min_recovery_pct}
              onChange={(e) => setForm({ ...form, min_recovery_pct: +e.target.value })}
            />
          </div>
          <div>
            <label>Action</label>
            <select value={form.action} onChange={(e) => setForm({ ...form, action: e.target.value })}>
              <option>AUTO_RELIST</option>
              <option>LIQUIDATE</option>
              <option>DONATE</option>
            </select>
          </div>
          <button style={{ alignSelf: "end" }}>Add rule</button>
        </div>
      </form>
    </div>
  );
}
