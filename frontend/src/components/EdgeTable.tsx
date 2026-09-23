import type { EdgeRow } from "../types";

export function EdgeTable({ rows }: { rows: EdgeRow[] }) {
  return (
    <div className="table-wrap" data-testid="edge-table">
      <table>
        <thead>
          <tr>
            <th>边标识</th>
            <th>源 → 目标</th>
            <th>固有延迟</th>
            <th>可加上限</th>
            <th>采用加量</th>
            <th>同优最小</th>
            <th>同优最大</th>
            <th>可调</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} data-edge={r.id}>
              <td>
                <code>{r.id}</code>
              </td>
              <td>
                {r.source} → {r.target}
              </td>
              <td className="num">{r.delay}</td>
              <td className="num">{r.cap}</td>
              <td className="num strong" data-chosen={r.id}>
                {r.chosen}
              </td>
              <td className="num" data-min={r.id}>
                {r.min}
              </td>
              <td className="num" data-max={r.id}>
                {r.max}
              </td>
              <td>{r.adjustable ? "是" : "否（固定 0）"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="hint">
        同优最小/最大：在「正向边数最少」且「总加量最小」的全部解中，该边可取的范围；
        移动共享边会整体平移子树，逐叶校准可能使他叶越出窗口。
      </p>
    </div>
  );
}
