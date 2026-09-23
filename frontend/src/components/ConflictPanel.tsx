import type { ConflictLeaf } from "../types";

export function ConflictPanel({
  conflict,
}: {
  conflict: { leaves: ConflictLeaf[]; message: string };
}) {
  return (
    <section className="conflict" data-testid="conflict-panel">
      <h2>无解：叶端窗口冲突</h2>
      <p className="banner banner-warn">{conflict.message}</p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>不能同时满足的叶端</th>
              <th>要求闭区间</th>
              <th>各自可达区间</th>
            </tr>
          </thead>
          <tbody>
            {conflict.leaves.map((c) => (
              <tr key={c.node} data-conflict-leaf={c.node}>
                <td>
                  <code>{c.node}</code>
                </td>
                <td>[{c.lo}, {c.hi}]</td>
                <td>
                  [{c.reachable_low}, {c.reachable_high}]
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="hint">
        这些叶端的可达区间由其根路径上全部边的可加上限决定；冲突往往源于共享上游边
        只能整体移动子树。页面输入已保留，可直接修改后重新提交。
      </p>
    </section>
  );
}
