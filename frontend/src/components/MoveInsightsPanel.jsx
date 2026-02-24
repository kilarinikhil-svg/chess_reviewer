export default function MoveInsightsPanel({ analysis }) {
  return (
    <section className="panel insights-panel">
      <h2>Move Insights</h2>
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
    </section>
  );
}
