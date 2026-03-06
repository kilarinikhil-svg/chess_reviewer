function formatScore(score) {
  if (!score) return "-";
  if (score.type === "mate") {
    return `Mate ${score.value}`;
  }
  const pawns = (score.value / 100).toFixed(2);
  return `${score.value > 0 ? "+" : ""}${pawns}`;
}

function formatDelta(deltaCp) {
  if (deltaCp == null) return "-";
  return `${deltaCp > 0 ? "+" : ""}${deltaCp} cp`;
}

export default function MoveInsightsPanel({
  analysis,
  isHypothetical = false,
  hypotheticalAnalysis = null,
  hypotheticalAnalysisLoading = false,
  hypotheticalAnalysisError = "",
}) {
  const isLoading = isHypothetical ? hypotheticalAnalysisLoading : false;
  const error = isHypothetical ? hypotheticalAnalysisError : "";
  const active = isHypothetical ? hypotheticalAnalysis : analysis;
  const score = isHypothetical
    ? active?.score || null
    : active?.score_after || active?.score_before || null;

  const pvMoves = active?.pv || [];

  return (
    <section className={`panel insights-panel${isHypothetical ? " hypo" : ""}`}>
      <div className="panel-head compact">
        <h2>{isHypothetical ? "Variation Insights" : "Move Insights"}</h2>
        <p>{isHypothetical ? "Sandbox branch" : "Selected ply"}</p>
      </div>

      {isLoading && <p className="insight-empty">Analyzing hypothetical position...</p>}
      {!isLoading && error && <p className="warning">{error}</p>}
      {!isLoading && !active && !error && (
        <p className="insight-empty">
          {isHypothetical
            ? "Drag a piece and run Analyze Hypothetical."
            : "Select a move and run analysis."}
        </p>
      )}

      {!isLoading && active && (
        <>
          <div className="insights-grid">
            <article className="insight-card">
              <span className="insight-label">Score</span>
              <strong className="insight-value">{formatScore(score)}</strong>
            </article>
            <article className="insight-card">
              <span className="insight-label">Best</span>
              <strong className="insight-value">{active.best || "-"}</strong>
            </article>
            {!isHypothetical && (
              <article className="insight-card">
                <span className="insight-label">Played</span>
                <strong className="insight-value">{active.played || "-"}</strong>
              </article>
            )}
            {!isHypothetical && (
              <article className="insight-card">
                <span className="insight-label">Class</span>
                <strong className="insight-value insight-class">{active.classification || "-"}</strong>
              </article>
            )}
            {!isHypothetical && (
              <article className="insight-card">
                <span className="insight-label">Swing</span>
                <strong className="insight-value">{formatDelta(active.delta_cp)}</strong>
              </article>
            )}
            {isHypothetical && (
              <article className="insight-card">
                <span className="insight-label">Status</span>
                <strong className="insight-value">Hypothetical</strong>
              </article>
            )}
          </div>

          <div className="insight-suggestion">
            <span>Suggestion</span>
            <p>
              {isHypothetical
                ? "Use this branch to compare alternatives before committing to the main line."
                : (active.suggestion || "No suggestion provided.")}
            </p>
          </div>

          <div className="insight-pv-block">
            <span>PV</span>
            {pvMoves.length ? (
              <div className="pv-chip-row">
                {pvMoves.map((move, idx) => (
                  <span className="pv-chip" key={`${move}-${idx}`}>
                    {move}
                  </span>
                ))}
              </div>
            ) : (
              <p className="insight-empty">No principal variation available.</p>
            )}
          </div>

          {active.analysis_incomplete && (
            <p className="warning">Engine timed out and returned a partial result.</p>
          )}
        </>
      )}
    </section>
  );
}
