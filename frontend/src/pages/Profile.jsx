import { useAuth } from "../auth";
import { useCountUp } from "../lib/motion";
import {
  User,
  Mail,
  MapPin,
  Calendar,
  Sprout,
  Package,
} from "../components/icons";

const ROLE_LABELS = {
  BUYER: "Buyer",
  SELLER: "Seller",
  FACILITY: "Facility",
};

const ROLE_BLURB = {
  BUYER: "Shops new arrivals and gives pre-loved finds a second life.",
  SELLER: "Lists products and tunes resale rules on the marketplace.",
  FACILITY: "Inspects, grades and routes returned items.",
};

const SIZE_LABELS = {
  waist: "Waist",
  top: "Top",
  shirt: "Shirt",
  shoe_uk: "Shoe (UK)",
};

function InfoCard({ icon, title, children }) {
  return (
    <div className="glass profile-card">
      <h3 className="profile-card-title">
        {icon}
        {title}
      </h3>
      <dl className="spec-list">{children}</dl>
    </div>
  );
}

function Field({ label, value }) {
  return (
    <div className="spec-row">
      <dt>{label}</dt>
      <dd>{value || <span className="muted">Not provided</span>}</dd>
    </div>
  );
}

export default function Profile() {
  const { user } = useAuth();
  const credits = useCountUp(user?.green_credits?.balance ?? 0);

  if (!user) return <div className="page muted">Loading…</div>;

  const fullName = [user.first_name, user.last_name].filter(Boolean).join(" ");
  const joined = user.date_joined
    ? new Date(user.date_joined).toLocaleDateString(undefined, {
        year: "numeric",
        month: "long",
        day: "numeric",
      })
    : "";
  const coords =
    user.lat != null && user.lng != null
      ? `${user.lat.toFixed(2)}, ${user.lng.toFixed(2)}`
      : "";
  const sizeEntries = Object.entries(user.profile?.sizes || {});

  return (
    <div className="page">
      <div className="glass profile-header enter">
        <span className="profile-avatar">
          <User size={36} />
        </span>
        <div className="profile-id">
          <h2>{fullName || user.username}</h2>
          <div
            className="row"
            style={{ gap: 8, alignItems: "center", flexWrap: "wrap" }}
          >
            <span className="badge">{ROLE_LABELS[user.role] || user.role}</span>
            {fullName && <span className="muted">@{user.username}</span>}
            {user.city && (
              <span
                className="muted"
                style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
              >
                <MapPin size={13} /> {user.city}
              </span>
            )}
          </div>
          {ROLE_BLURB[user.role] && (
            <p className="muted profile-blurb">{ROLE_BLURB[user.role]}</p>
          )}
        </div>
        <div className="profile-credits">
          <span className="profile-credits-figure">{credits}</span>
          <span className="profile-credits-label">
            <Sprout size={14} style={{ color: "var(--success)" }} /> green
            credits
          </span>
        </div>
      </div>

      <div className="profile-grid">
        <InfoCard icon={<Mail size={16} />} title="Contact">
          <Field label="Email" value={user.email} />
          <Field label="Username" value={user.username} />
        </InfoCard>

        <InfoCard icon={<MapPin size={16} />} title="Location">
          <Field label="City" value={user.city} />
          <Field label="Coordinates" value={coords} />
        </InfoCard>

        <InfoCard icon={<Calendar size={16} />} title="Account">
          <Field label="Role" value={ROLE_LABELS[user.role] || user.role} />
          <Field label="Member since" value={joined} />
          <Field label="Account ID" value={`#${user.id}`} />
        </InfoCard>

        {sizeEntries.length > 0 && (
          <InfoCard icon={<Package size={16} />} title="Size profile">
            {sizeEntries.map(([k, v]) => (
              <Field key={k} label={SIZE_LABELS[k] || k} value={v} />
            ))}
          </InfoCard>
        )}
      </div>
    </div>
  );
}
