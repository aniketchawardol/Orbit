import { useState } from "react";
import {
  Navigate,
  Route,
  Routes,
  useNavigate,
  useLocation,
} from "react-router-dom";
import { useAuth } from "./auth";
import { useCountUp, useScrolled } from "./lib/motion";
import { Sprout, LogOut, Menu, X, User } from "./components/icons";
import Shop from "./pages/Shop";
import ProductPage from "./pages/ProductPage";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Orders from "./pages/Orders";
import Resell from "./pages/Resell";
import SellerPortal from "./pages/SellerPortal";
import FacilityPortal from "./pages/FacilityPortal";
import HealthCard from "./pages/HealthCard";
import PreLoved from "./pages/PreLoved";
import Rewards from "./pages/Rewards";
import Profile from "./pages/Profile";

function Guard({ need, children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="page muted">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (need && user.role !== need) return <Navigate to="/" replace />;
  return children;
}

function NavBar() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const scrolled = useScrolled(12);
  const [open, setOpen] = useState(false);

  const credits = useCountUp(user?.green_credits?.balance ?? 0);

  const go = (to) => {
    setOpen(false);
    nav(to);
  };

  const tabs = [
    { to: "/", label: "Shop", match: (p) => p === "/" },
    {
      to: "/preloved",
      label: "Pre-Loved",
      match: (p) => p.startsWith("/preloved"),
    },
  ];
  if (user) {
    tabs.splice(1, 0, {
      to: "/orders",
      label: "Orders",
      match: (p) => p.startsWith("/orders"),
    });
    tabs.splice(2, 0, {
      to: "/resell",
      label: "Resell",
      match: (p) => p.startsWith("/resell"),
    });
  }
  if (user?.role === "SELLER")
    tabs.push({
      to: "/seller",
      label: "Seller",
      match: (p) => p.startsWith("/seller"),
    });
  if (user?.role === "FACILITY")
    tabs.push({
      to: "/facility",
      label: "Facility",
      match: (p) => p.startsWith("/facility"),
    });

  return (
    <nav className={`nav${scrolled ? " scrolled" : ""}`}>
      <button
        className="brand"
        onClick={() => go("/")}
        style={{
          background: "transparent",
          border: "none",
          minHeight: 0,
          padding: 0,
        }}
      >
        <span className="logo-chip">
          <img src="/logo.png" alt="Orbit" />
        </span>
        <span className="wordmark">Orbit</span>
      </button>

      <button
        className="nav-toggle"
        aria-label={open ? "Close menu" : "Open menu"}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? <X size={20} /> : <Menu size={20} />}
      </button>

      <span className="spacer" />

      <div className={`tab-list${open ? " open" : ""}`}>
        {tabs.map((t) => (
          <button
            key={t.to}
            className={`tab${t.match(loc.pathname) ? " active" : ""}`}
            onClick={() => go(t.to)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <span className="spacer" />

      {user ? (
        <>
          <button
            className="credits"
            onClick={() => go("/rewards")}
            title="Green Credits"
          >
            <Sprout size={16} />
            {credits}
          </button>
          <button className="nav-user" onClick={() => go("/profile")}>
            <User size={15} />
            {user.username} · {user.role}
          </button>
          <button className="secondary" onClick={logout}>
            <LogOut size={15} /> Logout
          </button>
        </>
      ) : (
        <button onClick={() => go("/login")}>Login</button>
      )}
    </nav>
  );
}

export default function App() {
  return (
    <>
      <NavBar />
      <Routes>
        <Route path="/" element={<Shop />} />
        <Route path="/p/:id" element={<ProductPage />} />
        <Route path="/preloved" element={<PreLoved />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/unit/:id" element={<HealthCard />} />
        <Route
          path="/orders"
          element={
            <Guard>
              <Orders />
            </Guard>
          }
        />
        <Route
          path="/resell"
          element={
            <Guard>
              <Resell />
            </Guard>
          }
        />
        <Route
          path="/seller/*"
          element={
            <Guard need="SELLER">
              <SellerPortal />
            </Guard>
          }
        />
        <Route
          path="/facility/*"
          element={
            <Guard need="FACILITY">
              <FacilityPortal />
            </Guard>
          }
        />
        <Route
          path="/rewards"
          element={
            <Guard>
              <Rewards />
            </Guard>
          }
        />
        <Route
          path="/profile"
          element={
            <Guard>
              <Profile />
            </Guard>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}
