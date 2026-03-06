function buildRows(moves) {
  const rows = [];
  for (let idx = 0; idx < moves.length; idx += 2) {
    rows.push({
      turn: Math.floor(idx / 2) + 1,
      white: moves[idx] || null,
      black: moves[idx + 1] || null,
    });
  }
  return rows;
}

function MoveCell({ move, selectedPly, playerColor, classificationByPly, markerLegend, onSelectPly }) {
  if (!move) return <div className="notation-empty">-</div>;

  const isSelected = move.ply === selectedPly;
  const actor = move.color === playerColor ? "user" : "opponent";
  const classification = classificationByPly?.[move.ply] || "";
  const marker = markerLegend?.[classification];

  return (
    <button
      className={`notation-move ${actor}${isSelected ? " active" : ""}`}
      onClick={() => onSelectPly(move.ply)}
      title={`${move.ply}. ${move.san}`}
    >
      <span className={`notation-dot${classification ? ` marker-${classification}` : ""}`}>
        {marker?.icon || "•"}
      </span>
      <span className="notation-san">{move.san}</span>
    </button>
  );
}

export default function MoveList({
  moves,
  selectedPly,
  playerColor,
  classificationByPly,
  markerLegend,
  onSelectPly,
}) {
  const rows = buildRows(moves);

  return (
    <section className="panel move-list-panel">
      <div className="panel-head compact">
        <h2>Notation</h2>
        <p>{moves.length ? `${moves.length} plies` : "No moves loaded"}</p>
      </div>
      <div className="notation-grid">
        <div className="notation-header">
          <span>#</span>
          <span>White</span>
          <span>Black</span>
        </div>
        {rows.map((row) => (
          <div className="notation-row" key={row.turn}>
            <span className="notation-turn">{row.turn}</span>
            <MoveCell
              move={row.white}
              selectedPly={selectedPly}
              playerColor={playerColor}
              classificationByPly={classificationByPly}
              markerLegend={markerLegend}
              onSelectPly={onSelectPly}
            />
            <MoveCell
              move={row.black}
              selectedPly={selectedPly}
              playerColor={playerColor}
              classificationByPly={classificationByPly}
              markerLegend={markerLegend}
              onSelectPly={onSelectPly}
            />
          </div>
        ))}
      </div>
    </section>
  );
}
