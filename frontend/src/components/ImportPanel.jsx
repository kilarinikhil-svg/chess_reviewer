import { useEffect, useMemo, useState } from "react";

const SOURCES = [
  { key: "pgn", label: "PGN" },
  { key: "fen", label: "FEN" },
  { key: "chesscom", label: "Chess.com" },
];

function archiveLabel(archive) {
  return `${archive.year}-${String(archive.month).padStart(2, "0")}`;
}

export default function ImportPanel({ onImportPgn, onFetchArchives, onSelectArchiveGame, archives, loading }) {
  const [activeSource, setActiveSource] = useState("pgn");
  const [pgn, setPgn] = useState("");
  const [fen, setFen] = useState("");
  const [username, setUsername] = useState("");
  const [archiveUrl, setArchiveUrl] = useState("");
  const [gameIndex, setGameIndex] = useState(0);

  useEffect(() => {
    if (!archives?.length) {
      setArchiveUrl("");
      return;
    }
    if (!archiveUrl || !archives.some((archive) => archive.url === archiveUrl)) {
      setArchiveUrl(archives[0].url);
    }
  }, [archives, archiveUrl]);

  const selectedArchive = useMemo(
    () => archives.find((archive) => archive.url === archiveUrl) || null,
    [archives, archiveUrl]
  );

  return (
    <section className="panel import-panel">
      <div className="panel-head">
        <h2>Game Sources</h2>
        <p>Load from notation or pick an archived game.</p>
      </div>

      <div className="import-source-tabs" role="tablist" aria-label="Import source">
        {SOURCES.map((source) => (
          <button
            key={source.key}
            type="button"
            className={`import-source-tab${activeSource === source.key ? " active" : ""}`}
            onClick={() => setActiveSource(source.key)}
          >
            {source.label}
          </button>
        ))}
      </div>

      {activeSource === "pgn" && (
        <div className="import-section">
          <p className="import-helper">Paste a full PGN to recover headers and moves.</p>
          <textarea
            value={pgn}
            onChange={(event) => setPgn(event.target.value)}
            placeholder="Paste PGN"
            rows={7}
          />
          <button
            disabled={loading || !pgn.trim()}
            onClick={() => onImportPgn({ pgn: pgn.trim(), fen: null, moves: [] })}
          >
            Import PGN
          </button>
        </div>
      )}

      {activeSource === "fen" && (
        <div className="import-section">
          <p className="import-helper">Start from a position using FEN.</p>
          <textarea
            value={fen}
            onChange={(event) => setFen(event.target.value)}
            placeholder="Paste FEN"
            rows={4}
          />
          <button
            disabled={loading || !fen.trim()}
            onClick={() => onImportPgn({ pgn: null, fen: fen.trim(), moves: [] })}
          >
            Import FEN
          </button>
        </div>
      )}

      {activeSource === "chesscom" && (
        <div className="import-section">
          <p className="import-helper">Fetch monthly archives, then choose a game index.</p>
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            placeholder="Chess.com username"
          />
          <button
            disabled={loading || !username.trim()}
            onClick={() => onFetchArchives(username.trim())}
          >
            Fetch Archives
          </button>

          {archives.length > 0 ? (
            <>
              <select value={archiveUrl} onChange={(event) => setArchiveUrl(event.target.value)}>
                <option value="">Select archive month</option>
                {archives.map((archive) => (
                  <option key={archive.url} value={archive.url}>
                    {archiveLabel(archive)}
                  </option>
                ))}
              </select>
              <div className="import-inline">
                <input
                  type="number"
                  min={0}
                  value={gameIndex}
                  onChange={(event) => setGameIndex(Number(event.target.value))}
                  placeholder="Game index"
                />
                <button
                  disabled={loading || !archiveUrl}
                  onClick={() => onSelectArchiveGame(archiveUrl, gameIndex)}
                >
                  Import Game
                </button>
              </div>
              {selectedArchive && (
                <p className="archive-note">Selected month: {archiveLabel(selectedArchive)}</p>
              )}
            </>
          ) : (
            <p className="archive-note">No archives loaded yet.</p>
          )}
        </div>
      )}
    </section>
  );
}
