import type { LeafRow } from "../types";

export function LeafTable({ rows }: { rows: LeafRow[] }) {
  return (
    <div className="table-wrap" data-testid="leaf-table">
      <table>
        <thead>
          <tr>
            <th>叶端</th>
            <th>到达值</th>
            <th>要求闭区间</th>
            <th>剩余裕量</th>
            <th>可达区间（零加量…满加量）</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.node} data-leaf-row={r.node}>
              <td>
                <code>{r.node}</code>
              </td>
              <td className="num strong" data-leaf-arrival={r.node}>
                {r.arrival}
              </td>
              <td>[{r.lo}, {r.hi}]</td>
              <td className="num">
                <span
                  className={r.margin === 0 ? "margin-zero" : "margin-ok"}
                  data-leaf-margin={r.node}
                >
                  {r.margin}
                  <small>
                    {" "}
                    (下界 +{r.margin_low} / 上界 −{r.margin_high})
                  </small>
                </span>
              </td>
              <td>
                [{r.reachable_low}, {r.reachable_high}]
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
