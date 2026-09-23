import type { TreeRow } from "../types";

export function TreeTable({ rows }: { rows: TreeRow[] }) {
  return (
    <div className="table-wrap" data-testid="tree-table">
      <table>
        <thead>
          <tr>
            <th>节点（树状）</th>
            <th>入边标识</th>
            <th>固有延迟</th>
            <th>可加上限</th>
            <th>采用加量</th>
            <th>到达值</th>
            <th>要求窗口</th>
            <th>剩余裕量</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.node}
              className={r.is_leaf ? "row-leaf" : "row-internal"}
              data-node={r.node}
              data-leaf={r.is_leaf}
            >
              <td>
                <span
                  className="indent"
                  style={{ paddingLeft: r.depth * 1.4 + "rem" }}
                >
                  {r.depth > 0 ? "└─ " : ""}
                </span>
                {r.node}
                {r.is_leaf && <em className="tag">叶</em>}
              </td>
              <td>{r.parent_edge ?? "—"}</td>
              <td>{r.edge_delay ?? "—"}</td>
              <td>{r.edge_cap ?? "—"}</td>
              <td className="num">
                {r.compensation === null ? "—" : r.compensation}
              </td>
              <td className="num strong" data-arrival={r.node}>
                {r.arrival}
              </td>
              <td>
                {r.window ? `[${r.window.lo}, ${r.window.hi}]` : "—"}
              </td>
              <td className="num">
                {r.margin === null ? (
                  "—"
                ) : (
                  <span className={r.margin === 0 ? "margin-zero" : "margin-ok"}>
                    {r.margin}
                    <small>
                      {" "}
                      (下界 +{r.margin_low}, 上界 −{r.margin_high})
                    </small>
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
