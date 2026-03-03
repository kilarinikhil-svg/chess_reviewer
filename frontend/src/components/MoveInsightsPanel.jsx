function formatScore(score) {
  if (!score) return "-";
  if (score.type === "mate") {
    return `M${score.value}`;
  }
  return `${score.value} cp`;
}

export default function MoveInsightsPanel({
  analysis,
  isHypothetical = false,
  hypotheticalAnalysis = null,
  hypotheticalAnalysisLoading = false,
  hypotheticalAnalysisError = "",
}) {
  return (
    <section className="panel insights-panel">
      <h2>Move Insights</h2>
      {isHypothetical ? (
        <>
          {hypotheticalAnalysisLoading && <p>Analyzing hypothetical position...</p>}
          {!hypotheticalAnalysisLoading && hypotheticalAnalysisError && (
            <p className="warning">{hypotheticalAnalysisError}</p>
          )}
          {!hypotheticalAnalysisLoading && !hypotheticalAnalysis && !hypotheticalAnalysisError && (
            <p>Hypothetical position not analyzed yet.</p>
          )}
          {!hypotheticalAnalysisLoading && hypotheticalAnalysis && (
            <>
              <p><strong>Score:</strong> {formatScore(hypotheticalAnalysis.score)}</p>
              <p><strong>Best:</strong> {hypotheticalAnalysis.best || "-"}</p>
              <p><strong>PV:</strong> {hypotheticalAnalysis.pv?.join(" ") || "-"}</p>
              {hypotheticalAnalysis.analysis_incomplete && (
                <p className="warning">Engine timed out, partial result.</p>
              )}
            </>
          )}
        </>
      ) : (
        <>
          {!analysis && <p>Select a move and run analysis.</p>}
          {analysis && (
            <>
              <p><strong>Played:</strong> {analysis.played}</p>
              <p><strong>Best:</strong> {analysis.best}</p>
              <p><strong>Class:</strong> {analysis.classification}</p>
              <p><strong>Delta:</strong> {analysis.delta_cp} cp</p>
              <p><strong>Suggestion:</strong> {analysis.suggestion}</p>
              <p><strong>PV:</strong> {analysis.pv?.join(" ") || "-"}</p>
              {analysis.analysis_incomplete && <p className="warning">Engine timed out, partial result.</p>}
            </>
          )}
        </>
      )}
    </section>
  );
}
