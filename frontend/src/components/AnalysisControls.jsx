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
  return (
    <section className="panel controls-panel">
      <h2>Analysis Controls</h2>
      <div className="control-row">
        <label>Mode</label>
        <select value={mode} onChange={(e) => setMode(e.target.value)}>
          <option value="realtime">Fast</option>
          <option value="deep">Deep</option>
        </select>
      </div>
      <div className="control-row">
        <label>User Side</label>
        <div className="control-note">Bottom side of the board is always treated as User. Use Flip Board to switch.</div>
      </div>
      <div className="control-row">
        <label>Move time (ms)</label>
        <input
          type="number"
          min={100}
          value={limits.movetime_ms || ""}
          onChange={(e) => setLimits({ ...limits, movetime_ms: Number(e.target.value) || null })}
        />
      </div>
      <div className="control-row">
        <label>Depth</label>
        <input
          type="number"
          min={1}
          value={limits.depth || ""}
          onChange={(e) => setLimits({ ...limits, depth: Number(e.target.value) || null })}
        />
      </div>

      <div className="button-row">
        <button disabled={loading || isHypothetical} onClick={onAnalyzeMove}>Analyze Selected Move</button>
        <button disabled={loading || isHypothetical} onClick={onAnalyzeFull}>Run Deep Full Analysis</button>
      </div>

      <div className="button-row">
        <button onClick={onJumpToMistake}>Jump to Mistake</button>
      </div>

      {isHypothetical && (
        <div className="job-status hypothetical-status">
          <p><strong>Hypothetical Position</strong></p>
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
        <div className="job-status">
          <p>
            <strong>Insights Ready:</strong> {prefetchStatus.done}/{prefetchStatus.total}
            {prefetchStatus.running ? " (analyzing...)" : " (ready)"}
          </p>
        </div>
      )}

      {fullStatus && (
        <div className="job-status">
          <p><strong>Status:</strong> {fullStatus.status}</p>
          <p><strong>Progress:</strong> {Math.round((fullStatus.progress || 0) * 100)}%</p>
        </div>
      )}
    </section>
  );
}
