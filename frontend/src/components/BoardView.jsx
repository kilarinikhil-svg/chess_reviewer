import { useEffect, useRef, useState } from "react";
import { Chessboard } from "react-chessboard";

function squareToGrid(square, orientation) {
  if (!square || square.length < 2) return null;
  const file = square.charCodeAt(0) - 96;
  const rank = Number(square[1]);
  if (Number.isNaN(file) || Number.isNaN(rank)) return null;
  if (orientation === "black") {
    return {
      gridColumn: 9 - file,
      gridRow: rank,
    };
  }
  return {
    gridColumn: file,
    gridRow: 9 - rank,
  };
}

export default function BoardView({
  fen,
  boardOrientation,
  isFocusMode,
  onToggleFocusMode,
  onFlipBoard,
  customArrows,
  customSquareStyles,
  classMarkers,
  onPrev,
  onNext,
  canPrev,
  canNext,
}) {
  const wrapRef = useRef(null);
  const [boardSize, setBoardSize] = useState(560);

  useEffect(() => {
    const element = wrapRef.current;
    if (!element) return;

    const recompute = () => {
      const width = element.clientWidth;
      const height = element.clientHeight;
      if (!width) return;

      const target = isFocusMode && height > 0 ? Math.min(width, height) : width;
      setBoardSize(Math.max(220, Math.floor(target)));
    };

    recompute();
    const observer = new ResizeObserver(recompute);
    observer.observe(element);
    window.addEventListener("resize", recompute);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", recompute);
    };
  }, [isFocusMode]);

  return (
    <section className={`panel board-panel${isFocusMode ? " focus-board-panel" : ""}`}>
      <h2>Board</h2>
      <button
        className="focus-toggle-btn"
        onClick={onToggleFocusMode}
        title={isFocusMode ? "Exit Full Screen Focus" : "Open Full Screen Focus"}
      >
        {isFocusMode ? "✕" : "⛶"}
      </button>
      <div className="board-wrap" ref={wrapRef}>
        <div className="board-canvas" style={{ width: `${boardSize}px`, height: `${boardSize}px` }}>
          <Chessboard
            id="analysis-board"
            position={fen}
            arePiecesDraggable={false}
            boardWidth={boardSize}
            boardOrientation={boardOrientation}
            customArrows={customArrows || []}
            customSquareStyles={customSquareStyles || {}}
          />
          <div className="marker-layer">
            {(classMarkers || []).map((marker) => {
              const grid = squareToGrid(marker.square, boardOrientation);
              if (!grid) return null;
              return (
                <div
                  key={`${marker.square}-${marker.ply}`}
                  className={`square-marker marker-${marker.classification} actor-${marker.actor}${marker.isCurrent ? " current" : ""}`}
                  style={grid}
                  title={`${marker.label} at ${marker.square}`}
                >
                  {marker.icon}
                </div>
              );
            })}
          </div>
        </div>
      </div>
      <div className="board-nav-row">
        <button
          className="board-nav-btn"
          onClick={onPrev}
          disabled={!canPrev}
          title="Previous Move (Left Arrow)"
        >
          ◀
        </button>
        <button
          className="board-nav-btn"
          onClick={onNext}
          disabled={!canNext}
          title="Next Move (Right Arrow)"
        >
          ▶
        </button>
        <button
          className="board-nav-btn board-flip-btn"
          onClick={onFlipBoard}
          title="Flip Board View"
        >
          Flip Board
        </button>
      </div>
    </section>
  );
}
