export default function MoveList({ moves, selectedPly, playerColor, onSelectPly }) {
  return (
    <section className="panel move-list-panel">
      <h2>Moves</h2>
      <div className="moves-grid">
        {moves.map((move) => (
          <button
            key={move.ply}
            className={
              move.ply === selectedPly
                ? move.color === playerColor
                  ? "move active-user"
                  : "move active-opponent"
                : "move"
            }
            onClick={() => onSelectPly(move.ply)}
          >
            {move.ply}. {move.san}
          </button>
        ))}
      </div>
    </section>
  );
}
