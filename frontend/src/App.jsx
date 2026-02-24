import { useEffect, useMemo, useRef, useState } from "react";
import { Chess } from "chess.js";
import { api } from "./api/client";
import AnalysisControls from "./components/AnalysisControls";
import BoardView from "./components/BoardView";
import EvalBar from "./components/EvalBar";
import ImportPanel from "./components/ImportPanel";
import MoveInsightsPanel from "./components/MoveInsightsPanel";
import MoveList from "./components/MoveList";

function buildFenTimeline(initialFen, moves) {
  const chess = new Chess(initialFen);
  const fens = [initialFen];
  for (const move of moves) {
    chess.move(move.uci);
    fens.push(chess.fen());
  }
  return fens;
}

function buildLimitsKey(limits) {
  return `${limits.movetime_ms ?? "n"}-${limits.depth ?? "n"}-${limits.nodes ?? "n"}-${limits.multipv ?? 1}`;
}

const CLASS_MARKER_META = {
  best: { icon: "★", label: "Best" },
  good: { icon: "✓", label: "Good" },
  inaccuracy: { icon: "?!", label: "Inaccuracy" },
  mistake: { icon: "?", label: "Mistake" },
  blunder: { icon: "??", label: "Blunder" },
};

function parseUciSquares(uci) {
  if (!uci || uci.length < 4) return null;
  return { from: uci.slice(0, 2), to: uci.slice(2, 4) };
}

function getMovePalette(moveColor, playerColor) {
  const isUserMove = moveColor === playerColor;
  if (isUserMove) {
    return {
      actor: "user",
      arrow: "rgba(20, 90, 50, 0.9)",
      currentFrom: "rgba(20, 90, 50, 0.35)",
      currentTo: "rgba(20, 90, 50, 0.58)",
      suggestedBorder: "2px solid rgba(20, 90, 50, 0.9)",
    };
  }
  return {
    actor: "opponent",
    arrow: "rgba(143, 29, 33, 0.9)",
    currentFrom: "rgba(143, 29, 33, 0.35)",
    currentTo: "rgba(143, 29, 33, 0.58)",
    suggestedBorder: "2px solid rgba(143, 29, 33, 0.9)",
  };
}

export default function App() {
  const [game, setGame] = useState(null);
  const [selectedPly, setSelectedPly] = useState(1);
  const [boardOrientation, setBoardOrientation] = useState("white");
  const [isFocusMode, setIsFocusMode] = useState(false);
  const playerColor = boardOrientation;
  const [mode, setMode] = useState("deep");
  const [limits, setLimits] = useState({ movetime_ms: 5000, depth: 24, nodes: null, multipv: 1 });
  const [analysisByKey, setAnalysisByKey] = useState({});
  const [archives, setArchives] = useState([]);
  const [loading, setLoading] = useState(false);
  const [fullStatus, setFullStatus] = useState(null);
  const [prefetchStatus, setPrefetchStatus] = useState({ running: false, done: 0, total: 0 });
  const [error, setError] = useState("");
  const analysisRef = useRef({});
  const pendingRequestKeysRef = useRef(new Set());
  const prefetchRunRef = useRef(0);
  const audioCtxRef = useRef(null);
  const lastMoveSoundPlyRef = useRef(null);

  const limitsKey = useMemo(
    () => buildLimitsKey(limits),
    [limits.movetime_ms, limits.depth, limits.nodes, limits.multipv]
  );

  const fenTimeline = useMemo(() => {
    if (!game) return [];
    return buildFenTimeline(game.initial_fen, game.moves);
  }, [game]);

  const getAnalysisKey = (ply, analysisMode = mode, currentLimitsKey = limitsKey) =>
    `${analysisMode}:${currentLimitsKey}:${ply}`;

  const currentFen = game ? fenTimeline[selectedPly] || game.initial_fen : "start";
  const currentAnalysis = analysisByKey[getAnalysisKey(selectedPly)] || null;
  const currentMove = game?.moves?.[selectedPly - 1] || null;
  const currentMoveTarget = parseUciSquares(currentMove?.uci)?.to;

  const boardMarkings = useMemo(() => {
    const suggestedSquares = parseUciSquares(currentAnalysis?.pv?.[0]);
    const currentSquares = parseUciSquares(currentMove?.uci);
    const palette = getMovePalette(currentMove?.color || "white", playerColor);
    const arrows = [];
    const squareStyles = {};

    if (suggestedSquares) {
      arrows.push([suggestedSquares.from, suggestedSquares.to, palette.arrow]);
      squareStyles[suggestedSquares.from] = {
        ...(squareStyles[suggestedSquares.from] || {}),
        boxShadow: `inset 0 0 0 9999px rgba(0,0,0,0.08)`,
        border: palette.suggestedBorder,
      };
      squareStyles[suggestedSquares.to] = {
        ...(squareStyles[suggestedSquares.to] || {}),
        boxShadow: `inset 0 0 0 9999px rgba(0,0,0,0.08)`,
        border: palette.suggestedBorder,
      };
    }

    if (currentSquares) {
      squareStyles[currentSquares.from] = {
        ...(squareStyles[currentSquares.from] || {}),
        boxShadow: `inset 0 0 0 9999px ${palette.currentFrom}`,
      };
      squareStyles[currentSquares.to] = {
        ...(squareStyles[currentSquares.to] || {}),
        boxShadow: `inset 0 0 0 9999px ${palette.currentTo}`,
      };
    }

    return { arrows, squareStyles };
  }, [currentAnalysis?.pv, currentMove?.uci, currentMove?.color, playerColor]);

  const classMarkers = useMemo(() => {
    if (!game?.moves?.length || selectedPly < 1 || selectedPly > game.moves.length) return [];

    const move = game.moves[selectedPly - 1];
    const analysis = analysisByKey[getAnalysisKey(selectedPly)];
    if (!analysis?.classification) return [];

    const squares = parseUciSquares(move.uci);
    if (!squares?.to) return [];

    const markerMeta = CLASS_MARKER_META[analysis.classification];
    if (!markerMeta) return [];

    return [{
      square: squares.to,
      classification: analysis.classification,
      icon: markerMeta.icon,
      label: markerMeta.label,
      actor: move.color === playerColor ? "user" : "opponent",
      ply: selectedPly,
      isCurrent: true,
    }];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [game?.game_id, selectedPly, playerColor, analysisByKey, mode, limitsKey, currentMoveTarget]);

  const classMoveBuckets = useMemo(() => {
    const buckets = {};
    for (const cls of Object.keys(CLASS_MARKER_META)) {
      buckets[`user:${cls}`] = [];
      buckets[`opponent:${cls}`] = [];
    }

    if (!game?.moves?.length) {
      return buckets;
    }

    for (let ply = 1; ply <= game.moves.length; ply += 1) {
      const move = game.moves[ply - 1];
      const analysis = analysisByKey[getAnalysisKey(ply)];
      const cls = analysis?.classification;
      if (!cls || !CLASS_MARKER_META[cls]) continue;
      const actor = move.color === playerColor ? "user" : "opponent";
      buckets[`${actor}:${cls}`].push(ply);
    }
    return buckets;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [game?.game_id, game?.moves, analysisByKey, playerColor, mode, limitsKey]);

  const classCounts = useMemo(() => {
    const counts = {};
    for (const cls of Object.keys(CLASS_MARKER_META)) {
      counts[cls] = {
        user: classMoveBuckets[`user:${cls}`]?.length || 0,
        opponent: classMoveBuckets[`opponent:${cls}`]?.length || 0,
      };
    }
    return counts;
  }, [classMoveBuckets]);

  async function withLoading(fn) {
    setError("");
    setLoading(true);
    try {
      await fn();
    } catch (err) {
      setError(err.message || "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  function resetGameState(imported) {
    setGame(imported);
    setSelectedPly(1);
    setAnalysisByKey({});
    analysisRef.current = {};
    lastMoveSoundPlyRef.current = null;
    setFullStatus(null);
    setPrefetchStatus({ running: false, done: 0, total: imported.moves?.length || 0 });
  }

  function playMoveTick() {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;

    if (!audioCtxRef.current) {
      audioCtxRef.current = new AudioCtx();
    }
    const ctx = audioCtxRef.current;
    if (ctx.state === "suspended") {
      ctx.resume().catch(() => {});
    }

    const now = ctx.currentTime;
    const oscillator = ctx.createOscillator();
    const gain = ctx.createGain();
    oscillator.type = "square";
    oscillator.frequency.setValueAtTime(1100, now);
    oscillator.frequency.exponentialRampToValueAtTime(850, now + 0.03);
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.06, now + 0.005);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.045);
    oscillator.connect(gain);
    gain.connect(ctx.destination);
    oscillator.start(now);
    oscillator.stop(now + 0.05);
  }

  async function handleImportPgn(payload) {
    await withLoading(async () => {
      const data = await api.importPgn(payload);
      resetGameState(data);
    });
  }

  async function handleFetchArchives(username) {
    await withLoading(async () => {
      const data = await api.fetchArchives(username);
      setArchives(data.archives || []);
    });
  }

  async function handleSelectArchiveGame(archiveUrl, gameIndex) {
    await withLoading(async () => {
      const data = await api.selectChessComGame(archiveUrl, gameIndex);
      resetGameState(data);
    });
  }

  async function analyzeMoveForSession(session, ply, analysisMode, analysisLimits, force = false) {
    if (!session) return null;
    const key = getAnalysisKey(ply, analysisMode, buildLimitsKey(analysisLimits));

    if (!force && analysisRef.current[key]) {
      return analysisRef.current[key];
    }
    if (pendingRequestKeysRef.current.has(key)) {
      return null;
    }

    pendingRequestKeysRef.current.add(key);
    try {
      const analysis = await api.analyzeMove({
        game_id: session.game_id,
        ply,
        mode: analysisMode,
        limits: analysisLimits,
      });
      setAnalysisByKey((prev) => {
        const next = force || !prev[key] ? { ...prev, [key]: analysis } : prev;
        analysisRef.current = next;
        return next;
      });
      return analysis;
    } finally {
      pendingRequestKeysRef.current.delete(key);
    }
  }

  async function handleAnalyzeSelectedMove() {
    if (!game || selectedPly < 1 || selectedPly > game.moves.length) return;
    await withLoading(async () => {
      await analyzeMoveForSession(game, selectedPly, mode, limits, true);
    });
  }

  async function handleAnalyzeFull() {
    if (!game) return;
    await withLoading(async () => {
      const deepLimits = {
        ...limits,
        movetime_ms: Math.max(limits.movetime_ms || 0, 5000),
        depth: Math.max(limits.depth || 0, 24),
      };
      const start = await api.startFullAnalysis({ game_id: game.game_id, mode: "deep", limits: deepLimits });

      let done = false;
      while (!done) {
        const status = await api.getFullStatus(start.job_id);
        setFullStatus(status);

        if (status.results_by_ply?.length) {
          const deepLimitsKey = buildLimitsKey(limits);
          setAnalysisByKey((prev) => {
            const next = { ...prev };
            for (const result of status.results_by_ply) {
              next[getAnalysisKey(result.ply, "deep", deepLimitsKey)] = result;
            }
            analysisRef.current = next;
            return next;
          });
        }

        done = status.status === "completed" || status.status === "failed";
        if (!done) {
          await new Promise((r) => setTimeout(r, 1000));
        }
      }
    });
  }

  function goPrev() {
    setSelectedPly((p) => Math.max(1, p - 1));
  }

  function goNext() {
    if (!game) return;
    setSelectedPly((p) => Math.min(game.moves.length, p + 1));
  }

  function jumpToMistake() {
    if (!game) return;
    const move = game.moves.find((m) => {
      const cls = analysisByKey[getAnalysisKey(m.ply)]?.classification;
      return cls === "mistake" || cls === "blunder";
    });
    if (move) {
      setSelectedPly(move.ply);
    }
  }

  function jumpToClassMove(classification, actor) {
    const plies = classMoveBuckets[`${actor}:${classification}`] || [];
    if (!plies.length) return;
    const nextPly = plies.find((ply) => ply > selectedPly) ?? plies[0];
    setSelectedPly(nextPly);
  }

  function toggleFocusMode() {
    setIsFocusMode((v) => !v);
  }

  useEffect(() => {
    if (!game || selectedPly < 1 || selectedPly > game.moves.length) {
      return;
    }
    const key = getAnalysisKey(selectedPly);
    if (!analysisRef.current[key]) {
      analyzeMoveForSession(game, selectedPly, mode, limits).catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedPly, game?.game_id, mode, limitsKey]);

  useEffect(() => {
    if (!game || !game.moves?.length) {
      setPrefetchStatus({ running: false, done: 0, total: 0 });
      return;
    }

    const runId = ++prefetchRunRef.current;
    const total = game.moves.length;
    setPrefetchStatus({ running: true, done: 0, total });

    (async () => {
      for (let ply = 1; ply <= total; ply += 1) {
        if (runId !== prefetchRunRef.current) {
          return;
        }
        try {
          await analyzeMoveForSession(game, ply, mode, limits);
        } catch (err) {
          if (runId === prefetchRunRef.current) {
            setError(err.message || "Failed to pre-analyze moves");
            setPrefetchStatus((prev) => ({ ...prev, running: false }));
          }
          return;
        }
        if (runId !== prefetchRunRef.current) {
          return;
        }
        setPrefetchStatus({ running: true, done: ply, total });
        await new Promise((resolve) => setTimeout(resolve, 0));
      }
      if (runId === prefetchRunRef.current) {
        setPrefetchStatus({ running: false, done: total, total });
      }
    })();

    return () => {
      prefetchRunRef.current += 1;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [game?.game_id, mode, limitsKey]);

  useEffect(() => {
    const onKeyDown = (event) => {
      if (!game || !game.moves?.length) return;
      const active = document.activeElement;
      const tagName = active?.tagName;
      const isTypingContext =
        active?.isContentEditable || tagName === "INPUT" || tagName === "TEXTAREA" || tagName === "SELECT";
      if (isTypingContext) return;

      if (event.key === "ArrowLeft") {
        event.preventDefault();
        setSelectedPly((p) => Math.max(1, p - 1));
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        setSelectedPly((p) => Math.min(game.moves.length, p + 1));
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [game?.game_id, game?.moves?.length]);

  useEffect(() => {
    if (!game?.moves?.length || selectedPly < 1 || selectedPly > game.moves.length) {
      return;
    }
    const previous = lastMoveSoundPlyRef.current;
    if (previous !== null && previous !== selectedPly) {
      playMoveTick();
    }
    lastMoveSoundPlyRef.current = selectedPly;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedPly, game?.game_id, game?.moves?.length]);

  useEffect(
    () => () => {
      if (audioCtxRef.current) {
        audioCtxRef.current.close().catch(() => {});
      }
    },
    []
  );

  useEffect(() => {
    const previous = document.body.style.overflow;
    if (isFocusMode) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = previous || "";
    }
    return () => {
      document.body.style.overflow = previous || "";
    };
  }, [isFocusMode]);

  return (
    <main className={`layout${isFocusMode ? " focus-layout" : ""}`}>
      {!isFocusMode && (
        <header className="app-header">
          <h1>Chess Analyzer</h1>
          <p>Stockfish-powered move-by-move insights with fast and deep modes.</p>
        </header>
      )}

      {error && <div className="error-banner">{error}</div>}

      <div className={isFocusMode ? "focus-stage" : "grid"}>
        {!isFocusMode && (
          <ImportPanel
            onImportPgn={handleImportPgn}
            onFetchArchives={handleFetchArchives}
            onSelectArchiveGame={handleSelectArchiveGame}
            archives={archives}
            loading={loading}
          />
        )}

        <BoardView
          fen={currentFen === "start" ? "start" : currentFen}
          boardOrientation={boardOrientation}
          isFocusMode={isFocusMode}
          onToggleFocusMode={toggleFocusMode}
          onFlipBoard={() => setBoardOrientation((o) => (o === "white" ? "black" : "white"))}
          customArrows={boardMarkings.arrows}
          customSquareStyles={boardMarkings.squareStyles}
          classMarkers={classMarkers}
          onPrev={goPrev}
          onNext={goNext}
          canPrev={Boolean(game?.moves?.length && selectedPly > 1)}
          canNext={Boolean(game?.moves?.length && selectedPly < game.moves.length)}
        />

        <EvalBar
          score={currentAnalysis?.score_after || currentAnalysis?.score_before || null}
          markerLegend={CLASS_MARKER_META}
          classCounts={classCounts}
          onClassCountClick={jumpToClassMove}
          isFocusMode={isFocusMode}
        />

        {!isFocusMode && (
          <AnalysisControls
            mode={mode}
            setMode={setMode}
            limits={limits}
            setLimits={setLimits}
            onAnalyzeMove={handleAnalyzeSelectedMove}
            onAnalyzeFull={handleAnalyzeFull}
            onJumpToMistake={jumpToMistake}
            loading={loading}
            fullStatus={fullStatus}
            prefetchStatus={prefetchStatus}
          />
        )}

        {!isFocusMode && (
          <MoveList
            moves={game?.moves || []}
            selectedPly={selectedPly}
            playerColor={playerColor}
            onSelectPly={(ply) => setSelectedPly(ply)}
          />
        )}

        {!isFocusMode && <MoveInsightsPanel analysis={currentAnalysis} />}
      </div>
    </main>
  );
}
