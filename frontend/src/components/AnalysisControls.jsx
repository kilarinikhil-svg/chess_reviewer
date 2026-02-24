export default function AnalysisControls({
  mode,
  setMode,
  limits,
  setLimits,
  onAnalyzeMove,
  onAnalyzeFull,
  onJumpToMistake,
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
        <button disabled={loading} onClick={onAnalyzeMove}>Analyze Selected Move</button>
        <button disabled={loading} onClick={onAnalyzeFull}>Run Deep Full Analysis</button>
      </div>

      <div className="button-row">
        <button onClick={onJumpToMistake}>Jump to Mistake</button>
      </div>

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
