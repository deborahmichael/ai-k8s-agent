import { useEffect, useMemo, useState } from 'react';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').trim();
const API_REQUEST_BASE = API_BASE_URL ? API_BASE_URL.replace(/\/$/, '') : '';
const API_BASE_LABEL = API_BASE_URL || 'Vite proxy /api -> FastAPI :8000';
const QUICK_DASHBOARD_ITEMS = ['broken-nginx', 'crashloop-app', 'pending-app'];

function buildApiUrl(path) {
  return API_REQUEST_BASE ? `${API_REQUEST_BASE}${path}` : path;
}

function formatValue(value) {
  if (value === null || value === undefined) {
    return '-';
  }

  if (typeof value === 'string') {
    return value;
  }

  return JSON.stringify(value, null, 2);
}

function Section({ title, children, open = false }) {
  return (
    <details className="details-card" open={open}>
      <summary>{title}</summary>
      <div className="details-body">{children}</div>
    </details>
  );
}

function JsonBlock({ value }) {
  return <pre className="code-block">{formatValue(value)}</pre>;
}

function KeyValueList({ items }) {
  return (
    <dl className="kv-list">
      {items.map(({ label, value }) => (
        <div key={label} className="kv-row">
          <dt>{label}</dt>
          <dd>{formatValue(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function SeverityBadge({ severity }) {
  const className = useMemo(() => {
    const base = 'severity-badge';
    const normalized = String(severity || '').toLowerCase();
    if (normalized.includes('high') || normalized.includes('critical')) {
      return `${base} severity-high`;
    }
    if (normalized.includes('medium')) {
      return `${base} severity-medium`;
    }
    return `${base} severity-low`;
  }, [severity]);

  return <span className={className}>{severity || 'Unknown'}</span>;
}

function getHistoryField(item, key, fallback = '') {
  if (!item) {
    return fallback;
  }

  if (item[key] !== undefined && item[key] !== null && item[key] !== '') {
    return item[key];
  }

  if (item.compact_result && item.compact_result[key] !== undefined) {
    return item.compact_result[key];
  }

  return fallback;
}

function DiagnosisCard({ title, diagnosis }) {
  if (!diagnosis) {
    return null;
  }

  return (
    <section className="card diagnosis-card">
      <div className="card-heading">
        <h2>{title}</h2>
        <SeverityBadge severity={diagnosis.severity} />
      </div>
      <KeyValueList
        items={[
          { label: 'Root cause', value: diagnosis.root_cause },
          { label: 'Severity', value: diagnosis.severity },
          { label: 'Confidence', value: diagnosis.confidence },
          { label: 'Suggested fix', value: diagnosis.suggested_fix },
        ]}
      />
    </section>
  );
}

export default function App() {
  const [namespace, setNamespace] = useState('demo-apps');
  const [resourceName, setResourceName] = useState('broken-nginx');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [historyState, setHistoryState] = useState({ enabled: null, items: [], error: '' });
  const [historyLoading, setHistoryLoading] = useState(false);
  const [selectedHistoryItem, setSelectedHistoryItem] = useState(null);
  const [selectedHistoryLoading, setSelectedHistoryLoading] = useState(false);
  const [selectedHistoryError, setSelectedHistoryError] = useState('');

  async function loadHistory() {
    setHistoryLoading(true);
    try {
      const response = await fetch(buildApiUrl('/api/history'));
      const payload = await response.json();
      setHistoryState({
        enabled: Boolean(payload.enabled),
        items: Array.isArray(payload.items) ? payload.items : [],
        error: payload.error || '',
      });
    } catch (err) {
      setHistoryState({
        enabled: null,
        items: [],
        error: err instanceof Error ? err.message : 'Unable to load history.',
      });
    } finally {
      setHistoryLoading(false);
    }
  }

  useEffect(() => {
    void loadHistory();
  }, []);

  async function investigate(nextNamespace = namespace, nextResourceName = resourceName) {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({
        namespace: nextNamespace,
        resource_name: nextResourceName,
      });
      const response = await fetch(buildApiUrl(`/api/investigate?${params.toString()}`));
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.detail || `Request failed with status ${response.status}`);
      }
      setResult(payload);
      void loadHistory();
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : 'Something went wrong.');
    } finally {
      setLoading(false);
    }
  }

  async function openHistoryItem(historyId) {
    setSelectedHistoryLoading(true);
    setSelectedHistoryError('');
    try {
      const response = await fetch(buildApiUrl(`/api/history/${encodeURIComponent(historyId)}`));
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.error || `Request failed with status ${response.status}`);
      }
      if (payload.enabled === false) {
        setSelectedHistoryItem(null);
        setSelectedHistoryError('History is disabled.');
        return;
      }
      if (!payload.item) {
        throw new Error(payload.error || 'History item not found.');
      }
      setSelectedHistoryItem(payload.item);
    } catch (err) {
      setSelectedHistoryItem(null);
      setSelectedHistoryError(err instanceof Error ? err.message : 'Unable to load history item.');
    } finally {
      setSelectedHistoryLoading(false);
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    investigate();
  }

  const selectedDiagnosis = selectedHistoryItem
    ? {
        root_cause: getHistoryField(selectedHistoryItem, 'root_cause', ''),
        severity: getHistoryField(selectedHistoryItem, 'severity', 'Unknown'),
        confidence: getHistoryField(selectedHistoryItem, 'confidence', 0),
        suggested_fix: getHistoryField(selectedHistoryItem, 'suggested_fix', ''),
      }
    : null;

  return (
    <div className="page-shell">
      <main className="app-shell">
        <header className="hero">
          <div className="eyebrow">Read-only Kubernetes troubleshooting</div>
          <h1>AI Kubernetes Troubleshooting Agent</h1>
          <p>
            Investigate a workload, review the evidence, and get a concise diagnosis without
            making any cluster changes.
          </p>
        </header>

        <section className="card controls-card">
          <form onSubmit={handleSubmit} className="controls-form">
            <label>
              Namespace
              <input
                value={namespace}
                onChange={(event) => setNamespace(event.target.value)}
                placeholder="demo-apps"
              />
            </label>
            <label>
              Resource name
              <input
                value={resourceName}
                onChange={(event) => setResourceName(event.target.value)}
                placeholder="broken-nginx"
              />
            </label>
            <div className="quick-buttons">
              {QUICK_DASHBOARD_ITEMS.map((name) => (
                <button
                  key={name}
                  type="button"
                  className="secondary-button"
                  onClick={() => {
                    setResourceName(name);
                    investigate(namespace, name);
                  }}
                >
                  {name}
                </button>
              ))}
            </div>
            <button type="submit" className="primary-button" disabled={loading}>
              {loading ? 'Investigating...' : 'Investigate'}
            </button>
          </form>
          <p className="api-note">API base URL: {API_BASE_LABEL}</p>
        </section>

        <section className="card history-card">
          <div className="card-heading">
            <h2>History</h2>
            {historyLoading ? <span className="history-status">Loading...</span> : null}
          </div>
          {historyState.enabled === false ? (
            <p className="history-empty">History disabled.</p>
          ) : historyState.error ? (
            <p className="history-error">{historyState.error}</p>
          ) : historyState.items.length === 0 ? (
            <p className="history-empty">No saved investigations yet.</p>
          ) : (
            <div className="history-list">
              {historyState.items.map((item) => (
                <button
                  key={item.history_id || `${item.namespace}-${item.resource_name}-${item.created_at}`}
                  type="button"
                  className="history-item"
                  onClick={() => openHistoryItem(item.history_id)}
                >
                  <strong>
                    {item.namespace} / {item.resource_name}
                  </strong>
                  <span>{item.root_cause}</span>
                  <span>
                    Severity: {item.severity} | Confidence: {item.confidence}
                  </span>
                  <span>{item.created_at}</span>
                </button>
              ))}
            </div>
          )}
        </section>

        {selectedHistoryItem ? (
          <section className="card">
            <div className="card-heading">
              <h2>Saved Investigation</h2>
              <button
                type="button"
                className="secondary-button"
                onClick={() => {
                  setSelectedHistoryItem(null);
                  setSelectedHistoryError('');
                }}
              >
                Close
              </button>
            </div>
            <KeyValueList
              items={[
                { label: 'Namespace', value: getHistoryField(selectedHistoryItem, 'namespace') },
                { label: 'Resource name', value: getHistoryField(selectedHistoryItem, 'resource_name') },
                { label: 'Root cause', value: getHistoryField(selectedHistoryItem, 'root_cause') },
                { label: 'Severity', value: getHistoryField(selectedHistoryItem, 'severity') },
                { label: 'Confidence', value: getHistoryField(selectedHistoryItem, 'confidence') },
                { label: 'Created at', value: getHistoryField(selectedHistoryItem, 'created_at') },
              ]}
            />
            <DiagnosisCard title="Saved Diagnosis" diagnosis={selectedDiagnosis} />
            <Section title="Saved compact JSON">
              <JsonBlock value={selectedHistoryItem.compact_result_json || selectedHistoryItem.compact_result} />
            </Section>
          </section>
        ) : null}

        {selectedHistoryLoading ? (
          <section className="card loading-card">
            <p>Loading saved investigation...</p>
          </section>
        ) : null}

        {selectedHistoryError ? (
          <section className="card error-card" role="alert">
            <h2>History Error</h2>
            <p>{selectedHistoryError}</p>
          </section>
        ) : null}

        {error ? (
          <section className="card error-card" role="alert">
            <h2>Error</h2>
            <p>{error}</p>
          </section>
        ) : null}

        {loading ? (
          <section className="card loading-card">
            <p>Gathering Kubernetes evidence...</p>
          </section>
        ) : null}

        {result ? (
          <div className="results-grid">
            <section className="card">
              <h2>Resource Summary</h2>
              <KeyValueList
                items={[
                  { label: 'Namespace', value: result.resource_summary?.namespace },
                  { label: 'Resource name', value: result.resource_summary?.resource_name },
                  { label: 'Detected pods', value: result.resource_summary?.detected_pod_names },
                  { label: 'Pod count', value: result.resource_summary?.pod_count },
                  { label: 'Has logs', value: result.resource_summary?.has_logs },
                  {
                    label: 'Investigation timestamp (UTC)',
                    value: result.resource_summary?.investigation_timestamp_utc,
                  },
                ]}
              />
            </section>

            <section className="card diagnosis-card">
              <div className="card-heading">
                <h2>Diagnosis</h2>
                <SeverityBadge severity={result.diagnosis?.severity} />
              </div>
              <KeyValueList
                items={[
                  { label: 'Root cause', value: result.diagnosis?.root_cause },
                  { label: 'Severity', value: result.diagnosis?.severity },
                  { label: 'Confidence', value: result.diagnosis?.confidence },
                  { label: 'Suggested fix', value: result.diagnosis?.suggested_fix },
                ]}
              />
            </section>

            <section className="card">
              <h2>Evidence</h2>
              <ul className="bullets">
                {(result.diagnosis?.evidence || []).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </section>

            <section className="card">
              <h2>Verification Commands</h2>
              <ul className="bullets">
                {(result.diagnosis?.verification_commands || []).map((item) => (
                  <li key={item}>
                    <code>{item}</code>
                  </li>
                ))}
              </ul>
            </section>

            {result.diagnosis?.llm ? (
              <section className="card">
                <h2>LLM Analysis</h2>
                <JsonBlock value={result.diagnosis.llm} />
              </section>
            ) : null}

            <section className="card">
              <h2>Raw Kubernetes Data</h2>
              <div className="details-stack">
                <Section title="Pods" open>
                  <JsonBlock value={result.pods} />
                </Section>
                <Section title="Events">
                  <JsonBlock value={result.events} />
                </Section>
                <Section title="Deployment">
                  <JsonBlock value={result.deployment} />
                </Section>
                <Section title="Services">
                  <JsonBlock value={result.services} />
                </Section>
                <Section title="Endpoints">
                  <JsonBlock value={result.endpoints} />
                </Section>
                <Section title="ReplicaSets">
                  <JsonBlock value={result.replicasets} />
                </Section>
                <Section title="Pod Describes">
                  <JsonBlock value={result.pod_describes} />
                </Section>
                <Section title="Pod Logs">
                  <JsonBlock value={result.pod_logs} />
                </Section>
              </div>
            </section>
          </div>
        ) : (
          <section className="card empty-state">
            <p>Run an investigation to see Kubernetes evidence and diagnosis results here.</p>
          </section>
        )}
      </main>
    </div>
  );
}