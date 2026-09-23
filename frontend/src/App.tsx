import { useEffect, useState } from "react";
import { solveBatch, fetchHealth } from "./api";
import { SAMPLES, type Batch, type SolveResult } from "./types";
import { TreeTable } from "./components/TreeTable";
import { EdgeTable } from "./components/EdgeTable";
import { LeafTable } from "./components/LeafTable";
import { ConflictPanel } from "./components/ConflictPanel";

const STORAGE_KEY = "clocktree-audit-input-v1";

export default function App() {
  const [input, setInput] = useState<string>(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    return saved ?? JSON.stringify(SAMPLES.sharedUpstream, null, 2);
  });
  const [result, setResult] = useState<SolveResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [health, setHealth] = useState<"ok" | "down" | "checking">("checking");

  useEffect(() => {
    let alive = true;
    const ping = () =>
      fetchHealth()
        .then(() => alive && setHealth("ok"))
        .catch(() => alive && setHealth("down"));
    ping();
    const t = setInterval(ping, 10000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  // Persist the textarea content so failed submissions never lose input.
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, input);
  }, [input]);

  async function onSubmit() {
    setLoading(true);
    setError(null);
    let batch: Batch;
    try {
      batch = JSON.parse(input) as Batch;
    } catch (e) {
      // Input is deliberately kept verbatim in the textarea.
      setError(`JSON 解析失败, 输入已保留: ${(e as Error).message}`);
      setLoading(false);
      return;
    }
    try {
      const r = await solveBatch(batch);
      setResult(r);
      if (r.status === "infeasible") {
        setError(r.conflict?.message ?? "当前批次无解");
      }
    } catch (e) {
      // Validation/request failure: keep the textarea and prior result as-is.
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  function loadSample(name: keyof typeof SAMPLES) {
    setInput(JSON.stringify(SAMPLES[name], null, 2));
    setError(null);
  }

  return (
    <div className="page">
      <header>
        <h1>低温探测器时钟树补偿审计</h1>
        <span className={`health health-${health}`} data-testid="health">
          API {health === "ok" ? "● 在线" : health === "down" ? "● 离线" : "○ 检测中"}
        </span>
      </header>

      <section className="input-card">
        <div className="input-bar">
          <label>
            时钟树批次 (JSON：nodes / edges / windows)
          </label>
          <div className="sample-row">
            <span>样例：</span>
            <button type="button" onClick={() => loadSample("sharedUpstream")}>
              共享上游补偿
            </button>
            <button type="button" onClick={() => loadSample("tiedRanges")}>
              同优边范围
            </button>
            <button type="button" onClick={() => loadSample("windowConflict")}>
              叶端窗口冲突
            </button>
          </div>
        </div>
        <textarea
          data-testid="batch-input"
          spellCheck={false}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          rows={16}
        />
        <div className="submit-row">
          <button
            type="button"
            data-testid="submit"
            onClick={onSubmit}
            disabled={loading}
          >
            {loading ? "求解中…" : "提交时钟树"}
          </button>
          <button
            type="button"
            onClick={() => {
              try {
                setInput(JSON.stringify(JSON.parse(input), null, 2));
                setError(null);
              } catch (e) {
                setError(`JSON 解析失败, 无法格式化: ${(e as Error).message}`);
              }
            }}
          >
            格式化
          </button>
        </div>
        {error && (
          <div
            className={`banner ${result?.status === "infeasible" ? "banner-warn" : "banner-error"}`}
            data-testid="error-banner"
          >
            {error}
          </div>
        )}
      </section>

      {result?.status === "feasible" && result.objectives && (
        <section className="objectives" data-testid="objectives">
          <div>
            <span className="obj-label">加量为正的边数（第一级）</span>
            <strong>{result.objectives.positive_edges}</strong>
          </div>
          <div>
            <span className="obj-label">总加量（第二级）</span>
            <strong>{result.objectives.total_compensation}</strong>
          </div>
          <div className="vector-cell">
            <span className="obj-label">
              加量向量（第三级，按边标识排序，字典序最小）
            </span>
            <code data-testid="vector">
              ({result.objectives.vector_order.join(", ")}) = (
              {result.objectives.vector.join(", ")})
            </code>
          </div>
        </section>
      )}

      {result?.status === "feasible" && result.tree && (
        <section>
          <h2>树表 · 边补偿 / 叶端到达 / 剩余裕量</h2>
          <TreeTable rows={result.tree.rows} />
        </section>
      )}

      {result?.status === "feasible" && result.edges && (
        <section>
          <h2>可调边 · 采用值与全部前两级同优解范围</h2>
          <EdgeTable rows={result.edges} />
        </section>
      )}

      {result?.status === "feasible" && result.leaves && (
        <section>
          <h2>叶端到达值与剩余裕量</h2>
          <LeafTable rows={result.leaves} />
        </section>
      )}

      {result?.status === "infeasible" && result.conflict && (
        <ConflictPanel conflict={result.conflict} />
      )}
    </div>
  );
}
