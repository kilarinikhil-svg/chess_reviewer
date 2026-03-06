export default function EvalBar({ score, markerLegend, classCounts, onClassCountClick, isFocusMode }) {
  const normalized = (() => {
    if (!score) return 50;
    if (score.type === "mate") return score.value > 0 ? 95 : 5;
    const cp = Math.max(-600, Math.min(600, score.value || 0));
    return 50 + cp / 12;
  })();
  const legendItems = Object.entries(markerLegend || {}).map(([key, meta]) => ({
    key,
    icon: meta.icon,
    label: meta.label,
    userCount: classCounts?.[key]?.user || 0,
    opponentCount: classCounts?.[key]?.opponent || 0,
  }));
  const scoreLabel = (() => {
    if (!score) return "No analysis yet";
    if (score.type === "mate") return `Mate ${score.value}`;
    const pawns = (score.value / 100).toFixed(2);
    return `${score.value > 0 ? "+" : ""}${pawns}`;
  })();
  const trendLabel = normalized >= 50 ? "White edge" : "Black edge";

  return (
    <section className={`panel eval-panel${isFocusMode ? " focus-eval-panel" : ""}`}>
      <div className="panel-head compact">
        <h2>Evaluation</h2>
        <p>{trendLabel}</p>
      </div>
      <div className="eval-panel-body">
        <div className="eval-bar-shell">
          <div className="eval-bar-fill" style={{ height: `${normalized}%` }} />
        </div>
        <div className="eval-class-vertical">
          {legendItems.map((item) => (
            <div key={item.key} className="eval-class-item" title={item.label}>
              <span className={`legend-class-icon marker-${item.key}`}>{item.icon}</span>
              <span className="class-count-label">{item.label}</span>
              <button
                className="class-count-pill user class-count-btn"
                title={`User ${item.label}`}
                disabled={item.userCount === 0}
                onClick={() => onClassCountClick?.(item.key, "user")}
              >
                U {item.userCount}
              </button>
              <button
                className="class-count-pill opponent class-count-btn"
                title={`Opponent ${item.label}`}
                disabled={item.opponentCount === 0}
                onClick={() => onClassCountClick?.(item.key, "opponent")}
              >
                O {item.opponentCount}
              </button>
            </div>
          ))}
        </div>
      </div>
      <div className="eval-text">{scoreLabel}</div>
    </section>
  );
}
