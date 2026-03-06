import { useEffect, useMemo, useRef, useState } from "react";
import { Chess } from "chess.js";
import { api } from "./api/client";
import AnalysisControls from "./components/AnalysisControls";
import BoardView from "./components/BoardView";
import EvalBar from "./components/EvalBar";
import ImportPanel from "./components/ImportPanel";
import MoveInsightsPanel from "./components/MoveInsightsPanel";
import MoveList from "./components/MoveList";
import CoachPanel from "./components/CoachPanel";

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

const ANALYSIS_MODE_KEY = "analysis.mode";
const VALID_ANALYSIS_MODES = new Set(["realtime", "deep"]);

function parsePositiveInt(value, fallback) {
  const parsed = Number.parseInt(value ?? "", 10);
  if (!Number.isFinite(parsed) || parsed <= 0) return fallback;
  return parsed;
}

const PREFETCH_BATCH_SIZE = parsePositiveInt(import.meta.env.VITE_PREFETCH_BATCH_SIZE, 4);
const PREFETCH_CONCURRENCY = parsePositiveInt(import.meta.env.VITE_PREFETCH_CONCURRENCY, 2);

function buildPrefetchOrder(total, centerPly) {
  const boundedCenter = Math.min(total, Math.max(1, centerPly || 1));
  const seen = new Set();
  const ordered = [];
  const push = (ply) => {
    if (ply < 1 || ply > total || seen.has(ply)) return;
    seen.add(ply);
    ordered.push(ply);
  };

  push(boundedCenter);
  for (let offset = 1; ordered.length < total; offset += 1) {
    push(boundedCenter + offset);
    push(boundedCenter - offset);
  }
  return ordered;
}

function getInitialAnalysisMode() {
  if (typeof window === "undefined") return "realtime";
  try {
    const stored = window.localStorage.getItem(ANALYSIS_MODE_KEY);
    return VALID_ANALYSIS_MODES.has(stored) ? stored : "realtime";
  } catch {
    return "realtime";
  }
}

function isAbortError(err) {
  if (!err) return false;
  return err.name === "AbortError" || err.code === 20 || (typeof err.message === "string" && err.message.includes("aborted"));
}

function buildHypotheticalFen(baseFen, moves, cursor) {
  const chess = new Chess(baseFen);
  for (let i = 0; i < cursor && i < moves.length; i += 1) {
    const move = moves[i];
    const result = chess.move(move.uci);
    if (!result) break;
  }
  return chess.fen();
}

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

function normalizeHeaderValue(value) {
  if (value == null) return "";
  const text = String(value).trim();
  if (!text || text === "?" || text === "*") return "";
  return text;
}

export default function App() {
  const [game, setGame] = useState(null);
  const [selectedPly, setSelectedPly] = useState(1);
  const [boardOrientation, setBoardOrientation] = useState("white");
  const [isFocusMode, setIsFocusMode] = useState(false);
  const playerColor = boardOrientation;
  const [mode, setMode] = useState(() => getInitialAnalysisMode());
  const [limits, setLimits] = useState({ movetime_ms: 2000, depth: 20, nodes: null, multipv: 1 });
  const [analysisByKey, setAnalysisByKey] = useState({});
  const [archives, setArchives] = useState([]);
  const [loading, setLoading] = useState(false);
  const [fullStatus, setFullStatus] = useState(null);
  const [prefetchStatus, setPrefetchStatus] = useState({ running: false, done: 0, total: 0 });
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState("analyzer");
  const [coachReport, setCoachReport] = useState(null);
  const [isHypothetical, setIsHypothetical] = useState(false);
  const [hypoBaseFen, setHypoBaseFen] = useState(null);
  const [hypoFen, setHypoFen] = useState(null);
  const [hypoMoves, setHypoMoves] = useState([]);
  const [hypoCursor, setHypoCursor] = useState(0);
  const [hypoAnalysis, setHypoAnalysis] = useState(null);
  const [hypoAnalysisLoading, setHypoAnalysisLoading] = useState(false);
  const [hypoAnalysisError, setHypoAnalysisError] = useState("");
  const analysisRef = useRef({});
  const pendingRequestsRef = useRef(new Map());
  const prefetchRunRef = useRef(0);
  const prefetchAbortControllerRef = useRef(null);
  const audioCtxRef = useRef(null);
  const lastMoveSoundPlyRef = useRef(null);

  const limitsKey = useMemo(
    () => buildLimitsKey(limits),
    [limits.movetime_ms, limits.depth, limits.nodes, limits.multipv]
  );

  useEffect(() => {
    if (!VALID_ANALYSIS_MODES.has(mode)) return;
    try {
      window.localStorage.setItem(ANALYSIS_MODE_KEY, mode);
    } catch {
      // Ignore storage failures and keep in-memory mode.
    }
  }, [mode]);

  const fenTimeline = useMemo(() => {
    if (!game) return [];
    return buildFenTimeline(game.initial_fen, game.moves);
  }, [game]);

  const getAnalysisKey = (ply, analysisMode = mode, currentLimitsKey = limitsKey) =>
    `${analysisMode}:${currentLimitsKey}:${ply}`;

  const currentFen = game ? fenTimeline[selectedPly] || game.initial_fen : "start";
  const displayFen = isHypothetical ? (hypoFen || currentFen) : currentFen;
  const currentAnalysis = analysisByKey[getAnalysisKey(selectedPly)] || null;
  const currentMove = game?.moves?.[selectedPly - 1] || null;
  const currentMoveTarget = parseUciSquares(currentMove?.uci)?.to;
  const variationTrail = hypoMoves.slice(0, hypoCursor);

  const boardMarkings = useMemo(() => {
    if (isHypothetical) {
      return { arrows: [], squareStyles: {} };
    }

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
  }, [isHypothetical, currentAnalysis?.pv, currentMove?.uci, currentMove?.color, playerColor]);

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

  const classificationByPly = useMemo(() => {
    const byPly = {};
    if (!game?.moves?.length) return byPly;

    for (let ply = 1; ply <= game.moves.length; ply += 1) {
      const cls = analysisByKey[`${mode}:${limitsKey}:${ply}`]?.classification;
      if (cls) byPly[ply] = cls;
    }
    return byPly;
  }, [game?.moves, analysisByKey, mode, limitsKey]);

  const gameSummary = useMemo(() => {
    if (!game) {
      return {
        title: "No game loaded",
        subtitle: "Import a PGN, FEN, or Chess.com game to begin analysis.",
        pills: [
          { label: "Mode", value: mode === "deep" ? "Deep" : "Fast" },
          { label: "Perspective", value: boardOrientation === "white" ? "White" : "Black" },
        ],
      };
    }

    const headers = game.headers || {};
    const white = normalizeHeaderValue(headers.White);
    const black = normalizeHeaderValue(headers.Black);
    const event = normalizeHeaderValue(headers.Event);
    const site = normalizeHeaderValue(headers.Site);
    const rawDate = normalizeHeaderValue(headers.Date);
    const result = normalizeHeaderValue(headers.Result);
    const date = rawDate ? rawDate.replace(/\./g, "-") : "";
    const totalPlies = game.moves?.length || 0;
    const clampedPly = totalPlies ? Math.min(Math.max(selectedPly, 1), totalPlies) : 0;

    const title =
      event ||
      ((white || black)
        ? `${white || "White"} vs ${black || "Black"}`
        : "Imported Game");

    const subtitleParts = [];
    if (white || black) subtitleParts.push(`${white || "White"} vs ${black || "Black"}`);
    if (site) subtitleParts.push(site);
    if (date) subtitleParts.push(date);

    const pills = [
      { label: "Ply", value: `${clampedPly}/${totalPlies || 0}` },
      { label: "Mode", value: mode === "deep" ? "Deep" : "Fast" },
      { label: "Perspective", value: boardOrientation === "white" ? "White" : "Black" },
    ];
    if (result) pills.unshift({ label: "Result", value: result });
    if (isHypothetical) pills.push({ label: "Branch", value: "Hypothetical" });

    return {
      title,
      subtitle: subtitleParts.join(" • ") || "Ready for move-by-move review",
      pills,
    };
  }, [game, selectedPly, mode, boardOrientation, isHypothetical]);

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

  function resetHypotheticalState() {
    setIsHypothetical(false);
    setHypoBaseFen(null);
    setHypoFen(null);
    setHypoMoves([]);
    setHypoCursor(0);
    setHypoAnalysis(null);
    setHypoAnalysisLoading(false);
    setHypoAnalysisError("");
  }

  function resetGameState(imported) {
    resetHypotheticalState();
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

  function enterHypotheticalMode() {
    if (!game) return;
    if (prefetchAbortControllerRef.current && !prefetchAbortControllerRef.current.signal.aborted) {
      prefetchAbortControllerRef.current.abort();
      prefetchAbortControllerRef.current = null;
      setPrefetchStatus((prev) => ({ ...prev, running: false }));
    }
    setIsHypothetical(true);
    setHypoBaseFen(currentFen);
    setHypoFen(currentFen);
    setHypoMoves([]);
    setHypoCursor(0);
    setHypoAnalysis(null);
    setHypoAnalysisError("");
  }

  function handleHypotheticalPieceDrop(sourceSquare, targetSquare) {
    if (!game || !sourceSquare || !targetSquare) return false;

    const wasHypothetical = isHypothetical;
    const baseFen = wasHypothetical ? (hypoBaseFen || currentFen) : currentFen;
    const currentHypoFen = wasHypothetical ? (hypoFen || currentFen) : currentFen;
    const currentCursor = wasHypothetical ? hypoCursor : 0;
    const currentMoves = wasHypothetical ? hypoMoves : [];

    const chess = new Chess(currentHypoFen);
    const move = chess.move({
      from: sourceSquare,
      to: targetSquare,
      promotion: "q",
    });
    if (!move) {
      return false;
    }

    const record = {
      san: move.san,
      uci: move.from + move.to + (move.promotion || ""),
      fenAfter: chess.fen(),
    };

    if (!wasHypothetical) {
      enterHypotheticalMode();
      setHypoBaseFen(baseFen);
    }
    const nextTrail = [...currentMoves.slice(0, currentCursor), record];
    const nextCursor = currentCursor + 1;

    setHypoMoves(nextTrail);
    setHypoCursor(nextCursor);
    setHypoFen(record.fenAfter);
    setHypoAnalysis(null);
    setHypoAnalysisError("");
    return true;
  }

  function handleUndoHypothetical() {
    if (!isHypothetical || !hypoBaseFen || hypoCursor <= 0) return;
    const nextCursor = hypoCursor - 1;
    setHypoCursor(nextCursor);
    setHypoFen(buildHypotheticalFen(hypoBaseFen, hypoMoves, nextCursor));
    setHypoAnalysis(null);
    setHypoAnalysisError("");
  }

  function handleRedoHypothetical() {
    if (!isHypothetical || !hypoBaseFen || hypoCursor >= hypoMoves.length) return;
    const nextCursor = hypoCursor + 1;
    setHypoCursor(nextCursor);
    setHypoFen(buildHypotheticalFen(hypoBaseFen, hypoMoves, nextCursor));
    setHypoAnalysis(null);
    setHypoAnalysisError("");
  }

  async function handleAnalyzeHypothetical() {
    if (!isHypothetical || !hypoFen) return;
    setHypoAnalysisLoading(true);
    setHypoAnalysisError("");
    try {
      const result = await api.analyzeFen({
        fen: hypoFen,
        limits,
      });
      setHypoAnalysis(result);
    } catch (err) {
      setHypoAnalysisError(err.message || "Failed to analyze hypothetical position");
      setHypoAnalysis(null);
    } finally {
      setHypoAnalysisLoading(false);
    }
  }

  function mergeMoveAnalysisResults(results, analysisMode, analysisLimits, { force = false } = {}) {
    if (!Array.isArray(results) || !results.length) return;
    const currentLimitsKey = buildLimitsKey(analysisLimits);
    setAnalysisByKey((prev) => {
      const next = { ...prev };
      let changed = false;
      for (const result of results) {
        if (!result || typeof result.ply !== "number") continue;
        const key = getAnalysisKey(result.ply, analysisMode, currentLimitsKey);
        if (!force && next[key]) continue;
        next[key] = result;
        changed = true;
      }
      if (!changed) return prev;
      analysisRef.current = next;
      return next;
    });
  }

  async function analyzeMoveForSession(
    session,
    ply,
    analysisMode,
    analysisLimits,
    { force = false, source = "user", signal = null } = {}
  ) {
    if (!session) return null;
    const key = getAnalysisKey(ply, analysisMode, buildLimitsKey(analysisLimits));

    if (!force && analysisRef.current[key]) {
      return analysisRef.current[key];
    }

    const pending = pendingRequestsRef.current.get(key);
    if (pending) {
      return pending.promise;
    }

    const promise = (async () => {
      try {
        const analysis = await api.analyzeMove(
          {
            game_id: session.game_id,
            ply,
            mode: analysisMode,
            limits: analysisLimits,
          },
          { signal }
        );
        mergeMoveAnalysisResults([analysis], analysisMode, analysisLimits, { force });
        return analysis;
      } catch (err) {
        if (isAbortError(err)) {
          return null;
        }
        throw err;
      } finally {
        const active = pendingRequestsRef.current.get(key);
        if (active?.promise === promise) {
          pendingRequestsRef.current.delete(key);
        }
      }
    })();

    pendingRequestsRef.current.set(key, { promise, source });
    return promise;
  }

  async function handleAnalyzeSelectedMove() {
    if (!game || selectedPly < 1 || selectedPly > game.moves.length) return;
    await withLoading(async () => {
      await analyzeMoveForSession(game, selectedPly, mode, limits, { force: true, source: "interactive" });
    });
  }


  async function handleAnalyzeCoach(payload) {
    await withLoading(async () => {
      const report = await api.analyzeCoach(payload);
      setCoachReport(report);
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
    if (isHypothetical) {
      resetHypotheticalState();
    }
    setSelectedPly((p) => Math.max(1, p - 1));
  }

  function goNext() {
    if (!game) return;
    if (isHypothetical) {
      resetHypotheticalState();
    }
    setSelectedPly((p) => Math.min(game.moves.length, p + 1));
  }

  function jumpToMistake() {
    if (!game) return;
    const move = game.moves.find((m) => {
      const cls = analysisByKey[getAnalysisKey(m.ply)]?.classification;
      return cls === "mistake" || cls === "blunder";
    });
    if (move) {
      if (isHypothetical) {
        resetHypotheticalState();
      }
      setSelectedPly(move.ply);
    }
  }

  function jumpToClassMove(classification, actor) {
    const plies = classMoveBuckets[`${actor}:${classification}`] || [];
    if (!plies.length) return;
    const nextPly = plies.find((ply) => ply > selectedPly) ?? plies[0];
    if (isHypothetical) {
      resetHypotheticalState();
    }
    setSelectedPly(nextPly);
  }

  function toggleFocusMode() {
    setIsFocusMode((v) => !v);
  }

  useEffect(() => {
    if (!isHypothetical) return;
    resetHypotheticalState();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [game?.game_id, selectedPly, mode, limitsKey]);

  useEffect(() => {
    if (!game || !game.moves?.length) {
      if (prefetchAbortControllerRef.current) {
        prefetchAbortControllerRef.current.abort();
        prefetchAbortControllerRef.current = null;
      }
      setPrefetchStatus({ running: false, done: 0, total: 0 });
      return;
    }

    const runId = ++prefetchRunRef.current;
    const total = game.moves.length;
    const abortController = new AbortController();
    prefetchAbortControllerRef.current = abortController;
    const uncachedPlies = buildPrefetchOrder(total, selectedPly).filter(
      (ply) => !analysisRef.current[getAnalysisKey(ply)]
    );

    let doneCount = total - uncachedPlies.length;
    setPrefetchStatus({ running: true, done: doneCount, total });

    const runPrefetch = async () => {
      if (!uncachedPlies.length) {
        setPrefetchStatus({ running: false, done: total, total });
        return;
      }

      const chunks = [];
      for (let i = 0; i < uncachedPlies.length; i += PREFETCH_BATCH_SIZE) {
        chunks.push(uncachedPlies.slice(i, i + PREFETCH_BATCH_SIZE));
      }
      const workerCount = Math.max(1, Math.min(PREFETCH_CONCURRENCY, chunks.length));
      let nextChunkIdx = 0;
      let failed = false;

      const runWorker = async () => {
        while (!failed) {
          if (runId !== prefetchRunRef.current || abortController.signal.aborted) {
            return;
          }
          const chunkIdx = nextChunkIdx;
          nextChunkIdx += 1;
          const chunk = chunks[chunkIdx];
          if (!chunk?.length) {
            return;
          }
          try {
            const data = await api.analyzeMovesBatch(
              {
                game_id: game.game_id,
                plies: chunk,
                mode,
                limits,
              },
              { signal: abortController.signal }
            );
            if (runId !== prefetchRunRef.current || abortController.signal.aborted) {
              return;
            }
            mergeMoveAnalysisResults(data?.results_by_ply || [], mode, limits);
            doneCount += chunk.length;
            setPrefetchStatus({ running: true, done: Math.min(doneCount, total), total });
          } catch (err) {
            if (isAbortError(err) || abortController.signal.aborted || runId !== prefetchRunRef.current) {
              return;
            }
            failed = true;
            setError(err.message || "Failed to pre-analyze moves");
            setPrefetchStatus((prev) => ({ ...prev, running: false }));
            return;
          }
        }
      };

      await Promise.all(Array.from({ length: workerCount }, () => runWorker()));
      if (failed) {
        return;
      }

      if (runId !== prefetchRunRef.current || abortController.signal.aborted) {
        return;
      }
      setPrefetchStatus({ running: false, done: total, total });
      if (prefetchAbortControllerRef.current === abortController) {
        prefetchAbortControllerRef.current = null;
      }
    };

    runPrefetch();

    return () => {
      abortController.abort();
      if (prefetchAbortControllerRef.current === abortController) {
        prefetchAbortControllerRef.current = null;
      }
      if (runId === prefetchRunRef.current) {
        setPrefetchStatus((prev) => ({ ...prev, running: false }));
      }
      prefetchRunRef.current += 1;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [game?.game_id, mode, limitsKey]);

  useEffect(() => {
    if (!game || selectedPly < 1 || selectedPly > game.moves.length) {
      return;
    }
    const key = getAnalysisKey(selectedPly);
    if (!analysisRef.current[key]) {
      analyzeMoveForSession(game, selectedPly, mode, limits).catch((err) => {
        if (!isAbortError(err)) {
          setError(err.message || "Failed to analyze move");
        }
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedPly, game?.game_id, mode, limitsKey]);

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
      if (prefetchAbortControllerRef.current) {
        prefetchAbortControllerRef.current.abort();
      }
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
          <p className="eyebrow">Chess Analyzer</p>
          <h1>Tournament Room</h1>
          <p>Stockfish-powered move review, deep scans, and coaching reports.</p>
        </header>
      )}

      {error && <div className="error-banner">{error}</div>}

      {!isFocusMode && (
        <div className="tab-row">
          <button
            className={`tab-btn${activeTab === "analyzer" ? " active" : ""}`}
            onClick={() => setActiveTab("analyzer")}
          >
            Analyzer
          </button>
          <button className={`tab-btn${activeTab === "coach" ? " active" : ""}`} onClick={() => setActiveTab("coach")}>
            Coach
          </button>
        </div>
      )}

      {activeTab === "coach" && !isFocusMode ? (
        <CoachPanel onAnalyze={handleAnalyzeCoach} loading={loading} report={coachReport} />
      ) : (
        <>
          {!isFocusMode && (
            <section className="game-summary-strip">
              <div className="summary-copy">
                <p className="summary-title">{gameSummary.title}</p>
                <p className="summary-subtitle">{gameSummary.subtitle}</p>
              </div>
              <div className="summary-pills">
                {gameSummary.pills.map((pill) => (
                  <span key={`${pill.label}-${pill.value}`} className="summary-pill">
                    <strong>{pill.label}</strong>
                    {pill.value}
                  </span>
                ))}
              </div>
            </section>
          )}

          <div className={isFocusMode ? "focus-stage" : "analyzer-shell"}>
            {!isFocusMode && (
              <aside className="analyzer-left-rail">
                <ImportPanel
                  onImportPgn={handleImportPgn}
                  onFetchArchives={handleFetchArchives}
                  onSelectArchiveGame={handleSelectArchiveGame}
                  archives={archives}
                  loading={loading}
                />
                <AnalysisControls
                  mode={mode}
                  setMode={setMode}
                  limits={limits}
                  setLimits={setLimits}
                  onAnalyzeMove={handleAnalyzeSelectedMove}
                  onAnalyzeFull={handleAnalyzeFull}
                  onJumpToMistake={jumpToMistake}
                  isHypothetical={isHypothetical}
                  variationTrail={variationTrail}
                  onAnalyzeHypothetical={handleAnalyzeHypothetical}
                  onUndoHypo={handleUndoHypothetical}
                  onRedoHypo={handleRedoHypothetical}
                  onResetHypo={resetHypotheticalState}
                  canUndoHypo={hypoCursor > 0}
                  canRedoHypo={hypoCursor < hypoMoves.length}
                  hypoAnalysisLoading={hypoAnalysisLoading}
                  loading={loading}
                  fullStatus={fullStatus}
                  prefetchStatus={prefetchStatus}
                />
              </aside>
            )}

            <div className="analyzer-board-stage">
              <BoardView
                fen={displayFen === "start" ? "start" : displayFen}
                boardOrientation={boardOrientation}
                isFocusMode={isFocusMode}
                arePiecesDraggable={Boolean(game)}
                onPieceDrop={handleHypotheticalPieceDrop}
                isHypothetical={isHypothetical}
                hypoControls={{
                  onUndo: handleUndoHypothetical,
                  onRedo: handleRedoHypothetical,
                  onReset: resetHypotheticalState,
                  canUndo: hypoCursor > 0,
                  canRedo: hypoCursor < hypoMoves.length,
                }}
                onToggleFocusMode={toggleFocusMode}
                onFlipBoard={() => setBoardOrientation((o) => (o === "white" ? "black" : "white"))}
                customArrows={boardMarkings.arrows}
                customSquareStyles={boardMarkings.squareStyles}
                classMarkers={isHypothetical ? [] : classMarkers}
                onPrev={goPrev}
                onNext={goNext}
                canPrev={Boolean(game?.moves?.length && selectedPly > 1)}
                canNext={Boolean(game?.moves?.length && selectedPly < game.moves.length)}
                gameSummary={gameSummary}
              />
            </div>

            <aside className={`analyzer-right-rail${isFocusMode ? " analyzer-right-rail-focus" : ""}`}>
              <EvalBar
                score={
                  isHypothetical
                    ? (hypoAnalysis?.score || null)
                    : (currentAnalysis?.score_after || currentAnalysis?.score_before || null)
                }
                markerLegend={CLASS_MARKER_META}
                classCounts={classCounts}
                onClassCountClick={jumpToClassMove}
                isFocusMode={isFocusMode}
              />

              {!isFocusMode && (
                <>
                  <MoveInsightsPanel
                    analysis={currentAnalysis}
                    isHypothetical={isHypothetical}
                    hypotheticalAnalysis={hypoAnalysis}
                    hypotheticalAnalysisLoading={hypoAnalysisLoading}
                    hypotheticalAnalysisError={hypoAnalysisError}
                  />
                  <MoveList
                    moves={game?.moves || []}
                    selectedPly={selectedPly}
                    playerColor={playerColor}
                    classificationByPly={classificationByPly}
                    markerLegend={CLASS_MARKER_META}
                    onSelectPly={(ply) => {
                      if (isHypothetical) {
                        resetHypotheticalState();
                      }
                      setSelectedPly(ply);
                    }}
                  />
                </>
              )}
            </aside>
          </div>
        </>
      )}
    </main>
  );
}
