import { useState } from "react";

export default function CoachPanel({ onAnalyze, loading, report }) {
  const [pgn, setPgn] = useState("");
  const [username, setUsername] = useState("");
  const [selectedFileName, setSelectedFileName] = useState("");
  const [fileError, setFileError] = useState("");

  function readFileAsText(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(new Error("Failed to read PGN file"));
      reader.readAsText(file);
    });
  }

  async function handleFileChange(event) {
    const file = event.target.files?.[0];
    setFileError("");

    if (!file) {
      setPgn("");
      setSelectedFileName("");
      return;
    }

    const lowerName = file.name.toLowerCase();
    if (!lowerName.endsWith(".pgn")) {
      setPgn("");
      setSelectedFileName("");
      setFileError("Please upload a .pgn file.");
      return;
    }

    try {
      const fileText = await readFileAsText(file);
      setPgn(fileText);
      setSelectedFileName(file.name);
    } catch (err) {
      setPgn("");
      setSelectedFileName("");
      setFileError(err.message || "Failed to read PGN file.");
    }
  }

  async function submit(event) {
    event.preventDefault();
    await onAnalyze({ pgn, username: username || null });
  }

  const phaseRows = report
    ? [
        { key: "opening", label: "Opening", value: report.phase_breakdown.opening },
        { key: "middlegame", label: "Middlegame", value: report.phase_breakdown.middlegame },
        { key: "endgame", label: "Endgame", value: report.phase_breakdown.endgame },
      ]
    : [];
  const phaseTotal = phaseRows.reduce((sum, row) => sum + row.value, 0) || 1;

  return (
    <section className="panel coach-panel">
      <div className="coach-hero">
        <div className="coach-hero-copy">
          <h2>Coach Report</h2>
          <p>Upload multi-game PGN files to find recurring mistakes and a focused next-week plan.</p>
        </div>
        <form className="coach-upload-form" onSubmit={submit}>
          <label htmlFor="coach-username">Player username (optional)</label>
          <input
            id="coach-username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            placeholder="nikhil_kilari"
          />
          <label htmlFor="coach-pgn">Upload PGN file</label>
          <input
            id="coach-pgn"
            type="file"
            accept=".pgn"
            onChange={handleFileChange}
          />
          {selectedFileName && <p className="upload-meta">Selected: {selectedFileName}</p>}
          {fileError && <p className="warning">{fileError}</p>}
          <button type="submit" disabled={loading || !pgn.trim()}>
            {loading ? "Analyzing..." : "Analyze Trends"}
          </button>
        </form>
      </div>

      {report && (
        <div className="coach-results">
          <div className="coach-summary-band">
            <article className="coach-metric">
              <span>Player</span>
              <strong>{report.username || "Unknown"}</strong>
            </article>
            <article className="coach-metric">
              <span>Games analyzed</span>
              <strong>{report.games_analyzed}</strong>
            </article>
            <article className="coach-metric">
              <span>Recurring patterns</span>
              <strong>{report.top_mistakes.length}</strong>
            </article>
          </div>

          <section className="coach-block">
            <h3>Top recurring mistakes</h3>
            {report.top_mistakes.length === 0 ? (
              <p className="coach-empty">No repeated patterns detected from current data.</p>
            ) : (
              <div className="coach-card-grid">
                {report.top_mistakes.map((mistake) => (
                  <article key={mistake.key} className="coach-card">
                    <div className="coach-card-head">
                      <strong>{mistake.label}</strong>
                      <span>{mistake.count}x</span>
                    </div>
                    <p>{mistake.description}</p>
                    <ul>
                      {mistake.examples.map((example) => (
                        <li key={example}>{example}</li>
                      ))}
                    </ul>
                  </article>
                ))}
              </div>
            )}
          </section>

          <section className="coach-block">
            <h3>Phase breakdown</h3>
            <div className="phase-breakdown">
              {phaseRows.map((row) => (
                <div key={row.key} className="phase-row">
                  <span>{row.label}</span>
                  <div className="phase-track">
                    <span style={{ width: `${Math.round((row.value / phaseTotal) * 100)}%` }} />
                  </div>
                  <strong>{row.value}</strong>
                </div>
              ))}
            </div>
          </section>

          <section className="coach-block">
            <h3>White vs Black split</h3>
            <div className="coach-split-grid">
              {Object.entries(report.color_stats).map(([color, stats]) => (
                <article key={color} className="coach-card coach-color-card">
                  <div className="coach-card-head">
                    <strong>{color}</strong>
                    <span>{stats.games} games</span>
                  </div>
                  <p>W {stats.wins} · L {stats.losses} · D {stats.draws}</p>
                </article>
              ))}
            </div>
          </section>

          <section className="coach-block">
            <h3>Action plan (next 7 days)</h3>
            {report.action_plan.length === 0 ? (
              <p className="coach-empty">No action plan generated.</p>
            ) : (
              <div className="coach-card-grid">
                {report.action_plan.map((item) => (
                  <article key={item.focus} className="coach-card">
                    <strong>{item.focus}</strong>
                    <ul>
                      {item.drills.map((drill) => (
                        <li key={drill}>{drill}</li>
                      ))}
                    </ul>
                  </article>
                ))}
              </div>
            )}
          </section>

          <section className="coach-block checklist-block">
            <h3>Next-game focus checklist</h3>
            <ul className="coach-checklist">
              {report.next_game_focus.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </section>
  );
}
