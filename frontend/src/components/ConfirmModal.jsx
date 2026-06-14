import { AlertCircle, X } from "./icons";

/**
 * Pre-purchase confirmation popup. Shown when the backend flags a wrong apparel
 * size or an incompatible accessory (HTTP 409 with `warnings`). The buyer can
 * cancel or proceed with "Buy anyway" (which re-posts the order with ack=true).
 */
export default function ConfirmModal({
  open,
  title = "Before you buy",
  warnings = [],
  recommended,
  confirmLabel = "Buy anyway",
  cancelLabel = "Cancel",
  onConfirm,
  onCancel,
}) {
  if (!open) return null;
  return (
    <div className="modal-overlay" onClick={onCancel} role="presentation">
      <div
        className="modal-card glass"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <button className="modal-close" onClick={onCancel} aria-label="Close">
          <X size={18} />
        </button>
        <div className="modal-head">
          <span className="modal-icon">
            <AlertCircle size={22} />
          </span>
          <h3 style={{ margin: 0 }}>{title}</h3>
        </div>
        <div className="modal-body">
          {warnings.map((w, i) => (
            <p key={i} className="modal-warning">
              {w}
            </p>
          ))}
          {recommended && (
            <p className="muted" style={{ margin: "6px 0 0" }}>
              Recommended for you: <strong>{recommended}</strong>
            </p>
          )}
        </div>
        <div className="modal-actions">
          <button className="secondary" onClick={onCancel}>
            {cancelLabel}
          </button>
          <button className="buy" onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
