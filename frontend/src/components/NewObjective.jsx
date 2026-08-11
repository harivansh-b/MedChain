import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Icon from "./Icon";
import { ApiError, apiJson } from "../lib/api";
import { useAuth } from "../lib/auth";

/* Admin-only panel: create a training objective by uploading a labeled validation CSV.
   The server derives the feature schema + scaler from it; nodes then train on their own
   CSVs with matching columns.

   Two-step flow:
     1. Upload CSV (+ optional target column) → server detects the two class labels and
        suggests which one means "positive".
     2. Coordinator reviews and picks the positive label → submit to create the objective. */
export default function NewObjective({ onCreated }) {
  const { token } = useAuth();
  const [name, setName] = useState("");
  const [specialty, setSpecialty] = useState("Radiology");
  const [minParticipants, setMinParticipants] = useState(2);
  const [csvText, setCsvText] = useState("");
  const [csvName, setCsvName] = useState("");
  const [targetColumn, setTargetColumn] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState(null);

  // Label detection state (step 2)
  const [detectedLabels, setDetectedLabels] = useState(null); // { labels, suggested_positive, target_column }
  const [positiveLabel, setPositiveLabel] = useState("");
  const [detecting, setDetecting] = useState(false);

  async function onFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setCsvName(file.name);
    setCsvText(await file.text());
    // Reset label detection when a new file is chosen.
    setDetectedLabels(null);
    setPositiveLabel("");
  }

  async function onDetectLabels() {
    if (!csvText) {
      setError("Upload a labeled validation CSV first.");
      return;
    }
    setError("");
    setDetecting(true);
    try {
      const result = await apiJson(
        "/training-objectives/detect-labels",
        {
          method: "POST",
          body: JSON.stringify({
            validation_csv: csvText,
            target_column: targetColumn || undefined,
          }),
        },
        token
      );
      setDetectedLabels(result);
      setPositiveLabel(result.suggested_positive);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not detect labels.");
    } finally {
      setDetecting(false);
    }
  }

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setCreated(null);
    if (!csvText) {
      setError("Upload a labeled validation CSV.");
      return;
    }
    if (!detectedLabels) {
      setError("Detect labels first so you can confirm which class is positive.");
      return;
    }
    setBusy(true);
    try {
      const objective = await apiJson(
        "/training-objectives",
        {
          method: "POST",
          body: JSON.stringify({
            name,
            disease_category: specialty.toLowerCase(),
            specialty,
            min_participants: Number(minParticipants),
            validation_csv: csvText,
            target_column: targetColumn || undefined,
            positive_label: positiveLabel || undefined,
          }),
        },
        token
      );
      setCreated(objective);
      setName("");
      setCsvText("");
      setCsvName("");
      setTargetColumn("");
      setDetectedLabels(null);
      setPositiveLabel("");
      onCreated?.(objective);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the objective.");
    } finally {
      setBusy(false);
    }
  }

  const field = { display: "flex", flexDirection: "column", gap: 6, flex: 1, minWidth: 150 };
  const label = { fontSize: "0.78rem", color: "var(--text-dim)" };
  const input = {
    padding: "9px 11px", borderRadius: 9, background: "rgba(255,255,255,0.04)",
    border: "1px solid var(--border-strong)", color: "#fff", fontSize: "0.9rem",
  };
  const radioRow = {
    display: "flex", alignItems: "center", gap: 8, cursor: "pointer",
    padding: "6px 10px", borderRadius: 8, background: "rgba(255,255,255,0.03)",
    border: "1px solid var(--border-strong)", transition: "border-color 0.2s",
  };
  const radioSelected = { ...radioRow, borderColor: "#7c6ef6", background: "rgba(124,110,246,0.08)" };

  return (
    <motion.section
      className="panel"
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
      style={{ padding: "20px 22px" }}
    >
      <div className="panel__head">
        <div>
          <h3>New training objective</h3>
          <span className="panel__caption">Upload a labeled validation CSV — the server derives the schema</span>
        </div>
      </div>

      <form onSubmit={onSubmit} style={{ display: "flex", flexDirection: "column", gap: 14, marginTop: 12 }}>
        <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
          <label style={field}>
            <span style={label}>Name</span>
            <input style={input} value={name} onChange={(e) => setName(e.target.value)} placeholder="Diabetes risk model" required />
          </label>
          <label style={field}>
            <span style={label}>Specialty</span>
            <input style={input} value={specialty} onChange={(e) => setSpecialty(e.target.value)} required />
          </label>
          <label style={{ ...field, maxWidth: 120 }}>
            <span style={label}>Min hospitals</span>
            <input style={input} type="number" min={1} value={minParticipants} onChange={(e) => setMinParticipants(e.target.value)} />
          </label>
        </div>

        <div style={{ display: "flex", gap: 14, flexWrap: "wrap", alignItems: "flex-end" }}>
          <label style={field}>
            <span style={label}>Validation CSV (labeled)</span>
            <input style={{ ...input, padding: "7px 9px" }} type="file" accept=".csv,text/csv" onChange={onFile} />
          </label>
          <label style={field}>
            <span style={label}>Target column (optional — defaults to last)</span>
            <input style={input} value={targetColumn} onChange={(e) => setTargetColumn(e.target.value)} placeholder="diagnosis" />
          </label>
        </div>

        {csvName && <span className="panel__caption">Selected: {csvName}</span>}

        {/* Step 1 → detect labels */}
        {csvText && !detectedLabels && (
          <button
            type="button"
            className="btn btn-secondary"
            disabled={detecting}
            onClick={onDetectLabels}
            style={{ alignSelf: "flex-start" }}
          >
            {detecting ? "Detecting…" : "Detect labels"}
          </button>
        )}

        {/* Step 2 → pick positive label */}
        <AnimatePresence>
          {detectedLabels && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              style={{ display: "flex", flexDirection: "column", gap: 10 }}
            >
              <span style={label}>
                Which class means <strong style={{ color: "#fff" }}>positive / disease</strong>?
              </span>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                {detectedLabels.labels.map((lbl) => (
                  <div
                    key={lbl}
                    style={positiveLabel === lbl ? radioSelected : radioRow}
                    onClick={() => setPositiveLabel(lbl)}
                  >
                    <input
                      type="radio"
                      name="positive_label"
                      value={lbl}
                      checked={positiveLabel === lbl}
                      onChange={() => setPositiveLabel(lbl)}
                      style={{ accentColor: "#7c6ef6" }}
                    />
                    <span style={{ color: "#fff", fontSize: "0.88rem" }}>{lbl}</span>
                    {lbl === detectedLabels.suggested_positive && (
                      <span style={{ fontSize: "0.7rem", color: "var(--text-dim)", marginLeft: 4 }}>(suggested)</span>
                    )}
                  </div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {error && <p className="diag__error">{error}</p>}
        {created && (
          <p className="panel__caption" style={{ color: "#9be3c1" }}>
            <Icon name="check" size={13} /> Created {created.name} — {created.n_features} features
            ({created.feature_columns?.join(", ")}); positive label: {created.positive_label}; objective id {created.id}
          </p>
        )}

        <button type="submit" className="btn btn-primary" disabled={busy || !detectedLabels} style={{ alignSelf: "flex-start" }}>
          {busy ? "Creating…" : "Create objective"}
        </button>
      </form>
    </motion.section>
  );
}
