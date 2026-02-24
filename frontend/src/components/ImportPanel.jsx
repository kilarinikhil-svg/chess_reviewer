import { useState } from "react";

export default function ImportPanel({ onImportPgn, onFetchArchives, onSelectArchiveGame, archives, loading }) {
  const [pgn, setPgn] = useState("");
  const [fen, setFen] = useState("");
  const [username, setUsername] = useState("");
  const [archiveUrl, setArchiveUrl] = useState("");
  const [gameIndex, setGameIndex] = useState(0);

  return (
    <section className="panel import-panel">
      <h2>Import Game</h2>
      <textarea
        value={pgn}
        onChange={(e) => setPgn(e.target.value)}
        placeholder="Paste PGN"
        rows={6}
      />
      <input value={fen} onChange={(e) => setFen(e.target.value)} placeholder="Or paste FEN" />
      <button disabled={loading} onClick={() => onImportPgn({ pgn: pgn || null, fen: fen || null, moves: [] })}>
        Import PGN/FEN
      </button>

      <div className="divider" />

      <input
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        placeholder="Chess.com username"
      />
      <button disabled={loading || !username.trim()} onClick={() => onFetchArchives(username.trim())}>
        Fetch Archives
      </button>

      {archives.length > 0 && (
        <>
          <select value={archiveUrl} onChange={(e) => setArchiveUrl(e.target.value)}>
            <option value="">Select archive month</option>
            {archives.map((archive) => (
              <option key={archive.url} value={archive.url}>
                {archive.year}-{String(archive.month).padStart(2, "0")}
              </option>
            ))}
          </select>
          <input
            type="number"
            min={0}
            value={gameIndex}
            onChange={(e) => setGameIndex(Number(e.target.value))}
            placeholder="Game index"
          />
          <button
            disabled={loading || !archiveUrl}
            onClick={() => onSelectArchiveGame(archiveUrl, gameIndex)}
          >
            Import Selected Game
          </button>
        </>
      )}
    </section>
  );
}
