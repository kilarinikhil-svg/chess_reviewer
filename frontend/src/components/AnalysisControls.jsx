export default function AnalysisControls({
  mode,
  setMode,
  limits,
  setLimits,
  onAnalyzeMove,
  onAnalyzeFull,
  onJumpToMistake,
  isHypothetical,
  variationTrail,
  onAnalyzeHypothetical,
  onUndoHypo,
  onRedoHypo,
  onResetHypo,
  canUndoHypo,
  canRedoHypo,
  hypoAnalysisLoading,
  loading,
  fullStatus,
  prefetchStatus,
}) {
  const prefetchProgress = prefetchStatus?.total
    ? Math.round((prefetchStatus.done / prefetchStatus.total) * 100)
    : 0;
  const fullProgress = Math.round((fullStatus?.progress || 0) * 100);

  return (
    <section className="panel controls-panel">
      <div className="panel-head">
        <h2>Engine Controls</h2>
        <p>Tune speed vs depth and jump to critical moments.</p>
      </div>

      <div className="mode-toggle" role="tablist" aria-label="Analysis mode">
        <button
          type="button"
          className={`mode-btn${mode === "realtime" ? " active" : ""}`}
          onClick={() => setMode("realtime")}
        >
          Fast
        </button>
        <button
          type="button"
          className={`mode-btn${mode === "deep" ? " active" : ""}`}
          onClick={() => setMode("deep")}
        >
          Deep
        </button>
      </div>

      <div className="limits-grid">
        <label className="control-field">
          <span>Move time (ms)</span>
          <input
            type="number"
            min={100}
            value={limits.movetime_ms || ""}
            onChange={(event) => setLimits({ ...limits, movetime_ms: Number(event.target.value) || null })}
          />
        </label>
        <label className="control-field">
          <span>Depth</span>
          <input
            type="number"
            min={1}
            value={limits.depth || ""}
            onChange={(event) => setLimits({ ...limits, depth: Number(event.target.value) || null })}
          />
        </label>
      </div>

      <div className="control-note">
        Bottom side is treated as User. Flip board to switch perspective.
      </div>

      <div className="button-row two-col">
        <button disabled={loading || isHypothetical} onClick={onAnalyzeMove}>Analyze Move</button>
        <button disabled={loading || isHypothetical} onClick={onAnalyzeFull}>Deep Scan</button>
      </div>

      <div className="button-row">
        <button onClick={onJumpToMistake}>Jump to First Mistake</button>
      </div>

      {isHypothetical && (
        <div className="job-status hypothetical-status">
          <p><strong>Hypothetical Branch</strong></p>
          {variationTrail?.length ? (
            <div className="variation-trail">
              {variationTrail.map((move, idx) => (
                <span className="variation-chip" key={`${move.uci}-${idx}`}>
                  {idx + 1}. {move.san}
                </span>
              ))}
            </div>
          ) : (
            <p className="control-note">No hypothetical moves yet.</p>
          )}
          <div className="button-row two-col">
            <button disabled={!canUndoHypo} onClick={onUndoHypo}>Undo</button>
            <button disabled={!canRedoHypo} onClick={onRedoHypo}>Redo</button>
          </div>
          <div className="button-row two-col">
            <button disabled={loading || hypoAnalysisLoading} onClick={onAnalyzeHypothetical}>
              {hypoAnalysisLoading ? "Analyzing..." : "Analyze Hypothetical"}
            </button>
            <button disabled={loading} onClick={onResetHypo}>Reset Branch</button>
          </div>
        </div>
      )}

      {prefetchStatus?.total > 0 && (
        <div className="job-status status-card">
          <div className="status-row">
            <strong>Prefetch</strong>
            <span className="status-value">
              {prefetchStatus.done}/{prefetchStatus.total}
              {prefetchStatus.running ? " warming insights" : " ready"}
            </span>
          </div>
          <div className="status-meter">
            <span style={{ width: `${prefetchProgress}%` }} />
          </div>
        </div>
      )}

      {fullStatus && (
        <div className="job-status status-card">
          <div className="status-row">
            <strong>Deep Analysis</strong>
            <span className="status-value">{fullStatus.status}</span>
          </div>
          <div className="status-meter">
            <span style={{ width: `${fullProgress}%` }} />
          </div>
          <p className="status-percent">{fullProgress}%</p>
        </div>
      )}
    </section>
  );
}
